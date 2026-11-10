"""Read-only M1 acceptance from native GitHub PR review evidence.

This is a candidate checker, NOT a merge/publisher. An explicit digest in the
repository owner's GitHub APPROVED review (at the *current exact PR head*) is
independent of the candidate tree's self-declared checksums. GitHub TLS/API
availability is a prerequisite; a transport failure is never acceptance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tools.m1_branch_acceptance import verify as verify_release

REPO = "drevendev/Dayflare"
OWNER = "drevendev"
OWNER_ID = 19223266
HOST = "https://api.github.com"
SHA1 = re.compile(r"[a-f0-9]{40}\Z")
PIN_LINE = re.compile(r"(?m)^Dayflare-M1-Manifest-SHA256: ([a-f0-9]{64})$")
MAX_BYTES = 1024 * 1024


class NativeReviewError(ValueError):
    """The exact release has no independently verified native review pin."""


def api_json(path: str):
    """Fetch only a hard-coded Dayflare GitHub REST path, never arbitrary URLs."""
    if not path.startswith("/repos/drevendev/Dayflare/pulls/"):
        raise NativeReviewError("unexpected GitHub API path")
    url = HOST + path
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "Dayflare-M1-Native-Review-Pin/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urlopen(request, timeout=12) as reply:
            if reply.geturl() != url or reply.status != 200:
                raise NativeReviewError("GitHub API redirect or non-200 response")
            raw = reply.read(MAX_BYTES + 1)
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        raise NativeReviewError("GitHub native review evidence unavailable") from exc
    if len(raw) > MAX_BYTES:
        raise NativeReviewError("oversized GitHub native review response")
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise NativeReviewError("invalid GitHub native review JSON") from exc


def approved_manifest_pin(pr_number: int, expected_head: str, *, fetch=api_json) -> str:
    """Require repository-owner exact-head approval with an explicit digest.

    The PR metadata, head and review come from GitHub's native API; neither a
    PR's body nor release manifest, HTML or workflow can grant their own trust.
    Fail closed on review pagination instead of omitting a later revocation.
    """
    if (type(pr_number) is not int or not 1 <= pr_number <= 2**31-1 or
            type(expected_head) is not str or not SHA1.fullmatch(expected_head)):
        raise NativeReviewError("exact PR number and full expected head required")
    prefix = f"/repos/{REPO}/pulls/{pr_number}"
    pr = fetch(prefix)
    if type(pr) is not dict:
        raise NativeReviewError("invalid native pull request")
    try:
        head = pr["head"]
        base = pr["base"]
        if (head["sha"] != expected_head or head["repo"]["full_name"] != REPO or
                base["ref"] != "gh-pages" or base["repo"]["full_name"] != REPO or
                pr["number"] != pr_number or pr["state"] not in ("open", "closed") or
                (pr["state"] == "closed" and not pr["merged"])):
            raise NativeReviewError("PR head/base/state differs from native acceptance target")
    except (KeyError, TypeError) as exc:
        raise NativeReviewError("incomplete native PR metadata") from exc
    reviews = fetch(prefix + "/reviews?per_page=100")
    if type(reviews) is not list or len(reviews) >= 100:
        raise NativeReviewError("review evidence incomplete or paginated")
    latest = None
    for entry in reviews:
        if type(entry) is not dict:
            raise NativeReviewError("malformed native review")
        user = entry.get("user")
        if not isinstance(user, dict):
            raise NativeReviewError("native review missing author")
        if user.get("login") != OWNER:
            continue
        if user.get("id") != OWNER_ID:
            raise NativeReviewError("owner reviewer identity mismatch")
        if entry.get("submitted_at") is None or type(entry.get("id")) is not int:
            raise NativeReviewError("owner review missing native ordering evidence")
        if latest is None or (entry["submitted_at"], entry["id"]) > (
                latest["submitted_at"], latest["id"]):
            latest = entry
    if (latest is None or latest.get("state") != "APPROVED" or
            latest.get("commit_id") != expected_head or
            type(latest.get("body")) is not str):
        raise NativeReviewError("no current exact-head owner approval")
    markers = PIN_LINE.findall(latest["body"])
    if len(markers) != 1:
        raise NativeReviewError("exactly one explicit owner-reviewed M1 digest required")
    return markers[0]


def check_release(site_root: Path, pr_number: int, expected_head: str,
                  *, fetch=api_json) -> dict:
    """Bind native approval to strict candidate HTML/manifest byte checks."""
    pin = approved_manifest_pin(pr_number, expected_head, fetch=fetch)
    verified = verify_release(site_root, pin)
    return {**verified, "native_review_pin": pin, "reviewed_pr": pr_number,
            "reviewed_head": expected_head, "publication_status": "NOT_DEPLOYED_NOT_LIVE_VERIFIED"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--site-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = check_release(args.site_root, args.pr, args.expected_head)
    except (NativeReviewError, ValueError, OSError) as exc:
        parser.exit(2, f"NOT_ACCEPTED_NOT_DEPLOYED: {exc}\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
