"""Negative controls for native, independently pinned release acceptance."""
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.m1_native_review_pin import NativeReviewError, approved_manifest_pin, check_release, api_json

PR = 205
HEAD = "a" * 40
BASE = "b" * 40
PIN = "c" * 64
REPO = "drevendev/Dayflare"


def native_pr():
    return {"number": PR, "state": "open", "merged": False,
            "head": {"sha": HEAD, "repo": {"full_name": REPO}},
            "base": {"sha": BASE, "ref": "gh-pages", "repo": {"full_name": REPO}}}


def review(state="APPROVED", commit=HEAD, pin=PIN, reviewer="drevendev", number=7):
    return {"id": number, "submitted_at": f"2026-11-10T13:00:{number:02d}Z",
            "state": state, "commit_id": commit,
            "body": f"Exact-head, independent native review.\nDayflare-M1-Manifest-SHA256: {pin}\n",
            "user": {"login": reviewer, "id": 19223266 if reviewer == "drevendev" else 3}}


def fetcher(pr=None, reviews=None):
    pr = native_pr() if pr is None else pr
    reviews = [review()] if reviews is None else reviews

    def fetch(path):
        if path.endswith("/reviews?per_page=100"):
            return reviews
        if path.endswith(f"/pulls/{PR}"):
            return pr
        raise AssertionError("unexpected endpoint: " + path)
    return fetch


class NativeReviewPinTests(unittest.TestCase):
    def test_three_distinct_refreshes_with_unchanged_verifier(self):
        for index in range(3):
            head = format(index + 1, "040x")
            pin = format(index + 100, "064x")
            pr = native_pr()
            pr["head"]["sha"] = head
            self.assertEqual(approved_manifest_pin(PR, head,
                fetch=fetcher(pr, [review(commit=head, pin=pin)])), pin)

    def test_exact_head_base_and_review_are_required(self):
        pr = native_pr()
        for change in (
            lambda p: p["head"].update(sha="f" * 40),
            lambda p: p["head"]["repo"].update(full_name="attacker/fork"),
            lambda p: p["base"].update(ref="master"),
            lambda p: p["base"]["repo"].update(full_name="attacker/fork"),
            lambda p: p.update(state="closed", merged=False),
        ):
            candidate = native_pr()
            change(candidate)
            with self.assertRaises(NativeReviewError):
                approved_manifest_pin(PR, HEAD, fetch=fetcher(candidate))
        for reviews in ([], [review("CHANGES_REQUESTED")],
                        [review(commit="f" * 40)], [review(reviewer="other")],
                        [review("DISMISSED")], [review(), review("CHANGES_REQUESTED", number=9)]):
            with self.assertRaises(NativeReviewError):
                approved_manifest_pin(PR, HEAD, fetch=fetcher(reviews=reviews))

    def test_broken_review_markers_identity_ordering_and_pagination_fail(self):
        bad_cases = [
            [review(pin="not-a-sha")],
            [dict(review(), body=f"Dayflare-M1-Manifest-SHA256: {PIN}\nDayflare-M1-Manifest-SHA256: {PIN}\n")],
            [dict(review(), user={"login":"drevendev", "id":123})],
            [dict(review(), submitted_at=None)],
            [review()] * 100,
        ]
        for value in bad_cases:
            with self.assertRaises(NativeReviewError):
                approved_manifest_pin(PR, HEAD, fetch=fetcher(reviews=value))

    def test_invalid_inputs_and_transport_failure_fail_closed(self):
        for num, head in ((0, HEAD), (PR, "short"), (True, HEAD)):
            with self.assertRaises(NativeReviewError):
                approved_manifest_pin(num, head, fetch=fetcher())
        def offline(_):
            raise NativeReviewError("GitHub native review evidence unavailable")
        with self.assertRaisesRegex(NativeReviewError, "unavailable"):
            approved_manifest_pin(PR, HEAD, fetch=offline)

    def test_rest_transport_rejects_redirects_bad_json_and_oversized_input(self):
        class FakeReply:
            status = 200
            def __init__(self, url, content):
                self.url, self.content = url, content
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def geturl(self): return self.url
            def read(self, _cap): return self.content
        endpoint = "/repos/drevendev/Dayflare/pulls/205"
        target = "https://api.github.com" + endpoint
        with patch("tools.m1_native_review_pin.urlopen", return_value=FakeReply(target, b'{"number":205}')):
            self.assertEqual(api_json(endpoint), {"number":205})
        for url, body in (("https://malicious.invalid/", b'{}'), (target, b'{'),
                          (target, b'x' * (1024 * 1024 + 1))):
            with patch("tools.m1_native_review_pin.urlopen", return_value=FakeReply(url, body)):
                with self.assertRaises(NativeReviewError):
                    api_json(endpoint)
        with self.assertRaises(NativeReviewError):
            api_json("/repos/attacker/fork/pulls/1")

    def test_native_pin_is_forwarded_to_strict_existing_release_verifier(self):
        with patch("tools.m1_native_review_pin.verify_release", return_value={
                "status": "BRANCH_BYTES_VERIFIED_NOT_DEPLOYED"}) as validator:
            receipt = check_release(Path("unused"), PR, HEAD, fetch=fetcher())
        validator.assert_called_once_with(Path("unused"), PIN)
        self.assertEqual(receipt["native_review_pin"], PIN)
        self.assertEqual(receipt["publication_status"], "NOT_DEPLOYED_NOT_LIVE_VERIFIED")
        with patch("tools.m1_native_review_pin.verify_release", side_effect=ValueError("bad HTML")):
            with self.assertRaisesRegex(ValueError, "bad HTML"):
                check_release(Path("unused"), PR, HEAD, fetch=fetcher())


if __name__ == "__main__":
    unittest.main()
