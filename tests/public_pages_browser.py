"""Anonymous public Pages acceptance; separate from staged HTTP and deployment."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path

import browser_dated_niche_pages as dated
from browser_runner import launch_chromium
from playwright.sync_api import sync_playwright
from tools.verify_public_release import verify, V2_MANIFEST_SHA256, V2_ROUTE, V2_SHA256

BASE = "https://drevendev.github.io/Dayflare/"
OUT = Path(__file__).resolve().parents[1] / "artifacts/public-pages"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-manifest-sha256", required=True)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=False)
    dated.OUT = OUT
    receipt = {
        "status": "INCOMPLETE",
        "transport": "ANONYMOUS_PUBLIC_HTTPS",
        "url": BASE,
        "expected_manifest_sha256": args.expected_manifest_sha256,
        "started_utc": utc_now(),
        "journeys": [],
        "versioned_journeys": [],
    }
    try:
        receipt["http_before"] = asdict(verify(BASE, args.expected_manifest_sha256))
        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            try:
                for width in (320, 390, 1280):
                    receipt["journeys"].append(dated.journey(browser, BASE, width))
                    if args.expected_manifest_sha256 == V2_MANIFEST_SHA256:
                        receipt["versioned_journeys"].append(dated.candidate_journey(
                            browser, BASE, width, V2_SHA256, route=V2_ROUTE,
                            entry_selector="#open-niche-edition"))
            finally:
                browser.close()
        receipt["http_after"] = asdict(verify(BASE, args.expected_manifest_sha256))
        assert receipt["http_before"] == receipt["http_after"]
        receipt["status"] = "HTTP_AND_BROWSER_PASS_REVIEW_PENDING"
    except Exception as exc:
        receipt["status"] = "FAIL"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        receipt["finished_utc"] = utc_now()
        (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n",
                                          encoding="utf-8")
    print("PASS public HTTPS pinned bytes and Chromium visitor journeys; screenshot review pending")


if __name__ == "__main__":
    main()
