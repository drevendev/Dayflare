"""All MediaWiki bodies here are fictional test fixtures, NOT Wikimedia receipts."""
import hashlib
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from urllib.parse import urlencode

from tools.m1_identity_panel import PanelError, canonical_bytes
from tools.m1_source_verify import verify_sources

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/synthetic_panel.json"


class M1UpstreamBodyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root / "raw"
        self.raw.mkdir()
        self.panel = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.panel["selection"]["evidence_kind"] = "reported_retrieval"
        self.panel["selection"]["selected_at"] = "2026-10-20"
        self.panel_path = self.root / "panel.json"
        self.bodies = {}
        self.refresh()

    def endpoint(self, project, pid):
        return f"https://{project}.org/w/api.php?" + urlencode({
            "action":"query", "format":"json", "formatversion": "2",
            "prop":"info|pageprops", "ppprop":"wikibase_item", "pageids":str(pid),
        })

    def refresh(self):
        for page in self.panel["pages"]:
            ref = page["page_ref"]
            project, pid = ref["project"], ref["page_id"]
            page["titles"][-1]["date"] = "2026-10-20"
            last_title = page["titles"][-1]["title"]
            entry = {"pageid":pid, "ns":0, "title":last_title}
            observed_qid = page["wikidata"]["observed_qid"]
            if observed_qid is not None:
                entry["pageprops"] = {"wikibase_item":observed_qid}
                page["wikidata"]["evidence_url"] = f"https://www.wikidata.org/wiki/{observed_qid}"
            body = canonical_bytes({"batchcomplete":True,"query":{"pages":[entry]}})
            self.bodies[(project,pid)] = body
            (self.raw / f"{project}.{pid}.json").write_bytes(body)
            page["source"] = {
                "endpoint":self.endpoint(project,pid),
                "requested_at":"2026-10-20T10:00:00Z", "http_status":200,
                "body_sha256": hashlib.sha256(body).hexdigest(), "response_bytes":len(body),
            }
        self.panel_path.write_bytes(canonical_bytes(self.panel))

    def check(self):
        self.panel_path.write_bytes(canonical_bytes(self.panel))
        return verify_sources(self.panel_path, self.raw)

    def reject(self, snippet):
        with self.assertRaises(PanelError) as ctx:
            self.check()
        self.assertIn(snippet, str(ctx.exception))

    def test_two_valid_bodies_deterministic_without_network(self):
        r = self.check()
        self.assertEqual(r["verified_page_count"], 2)
        self.assertEqual(r["result"], "all_retained_bodies_internally_consistent")
        self.panel["pages"].reverse()
        self.assertEqual(canonical_bytes(r), canonical_bytes(self.check()))
        self.assertTrue(any("NOT authenticated" in value for value in r["limitations"]))
        self.assertTrue(any("decoded JSON entities" in value for value in r["limitations"]))

    def test_no_synthetic_upgrade(self):
        self.panel["selection"]["evidence_kind"] = "synthetic"
        self.reject("synthetic fixture may not claim retrieval")

    def test_sha_mismatch(self):
        self.raw.joinpath("en.wikipedia.17.json").write_bytes(b'{}')
        self.reject("byte size mismatch")

    def test_same_length_corruption_detected(self):
        b = bytearray(self.bodies[("en.wikipedia",17)])
        b[b.index(b"Example-new")] = ord("X")
        self.raw.joinpath("en.wikipedia.17.json").write_bytes(b)
        self.reject("SHA-256 mismatch")

    def test_extra_or_substituted_page_denied(self):
        b = self.bodies[("en.wikipedia",17)].replace(b'"pageid":17',b'"pageid":19')
        self.panel["pages"][0]["source"]["body_sha256"] = hashlib.sha256(b).hexdigest()
        self.panel["pages"][0]["source"]["response_bytes"] = len(b)
        self.raw.joinpath("en.wikipedia.17.json").write_bytes(b)
        self.reject("page id")

    def test_current_title_mismatch(self):
        b = self.bodies[("en.wikipedia",17)].replace(b"Example-new", b"Unknown-new")
        self.panel["pages"][0]["source"]["body_sha256"] = hashlib.sha256(b).hexdigest()
        self.panel["pages"][0]["source"]["response_bytes"] = len(b)
        self.raw.joinpath("en.wikipedia.17.json").write_bytes(b)
        self.reject("current title")

    def test_observed_qid_mismatch(self):
        b = self.bodies[("en.wikipedia",17)].replace(b'"Q10"',b'"Q11"')
        self.panel["pages"][0]["source"]["body_sha256"] = hashlib.sha256(b).hexdigest()
        self.panel["pages"][0]["source"]["response_bytes"] = len(b)
        self.raw.joinpath("en.wikipedia.17.json").write_bytes(b)
        self.reject("QID disagrees")

    def test_redirects_query_forbidden(self):
        self.panel["pages"][0]["source"]["endpoint"] += "&redirects=1"
        self.reject("unexpected/missing query")

    def test_different_project_endpoint_forbidden(self):
        self.panel["pages"][0]["source"]["endpoint"] = self.endpoint("ru.wikipedia",17)
        self.reject("origin")

    def test_multiple_query_ids_forbidden(self):
        self.panel["pages"][0]["source"]["endpoint"] += "&pageids=18"
        self.reject("unexpected pageids")

    def test_stale_title_date_denied(self):
        self.panel["pages"][0]["titles"][-1]["date"] = "2026-10-19"
        self.reject("UTC retrieval date")

    def test_bad_or_missing_raw_body(self):
        self.raw.joinpath("en.wikipedia.17.json").unlink()
        self.reject("missing/linked raw body")

    def test_unlisted_retained_raw_file_rejected(self):
        (self.raw / "en.wikipedia.123456.json").write_bytes(b"EXTRA UNSOURCED BODY")
        self.reject("unexpected/missing raw members")

    def test_symlink_raw_body_rejected(self):
        original = self.raw.joinpath("en.wikipedia.17.json")
        external = self.root / "external.json"
        external.write_bytes(original.read_bytes())
        original.unlink()
        original.symlink_to(external)
        self.reject("missing/linked raw body")

    def test_invalid_json_duplicate_keys_forbidden(self):
        b = b'{"query":{"pages":[{"pageid":17,"pageid":17}]}}'
        p = self.panel["pages"][0]["source"]
        p["response_bytes"] = len(b)
        p["body_sha256"] = hashlib.sha256(b).hexdigest()
        self.raw.joinpath("en.wikipedia.17.json").write_bytes(b)
        self.reject("duplicate JSON key")

    def test_missing_page_not_valid(self):
        b = canonical_bytes({"query":{"pages":[{"pageid":17,"ns":0,"title":"Example-new","missing":True}]}})
        p = self.panel["pages"][0]["source"]
        p["response_bytes"] = len(b)
        p["body_sha256"] = hashlib.sha256(b).hexdigest()
        self.raw.joinpath("en.wikipedia.17.json").write_bytes(b)
        self.reject("missing/redirected")

    def test_unexpected_redirect_mapping_fails(self):
        b = canonical_bytes({"query":{"redirects":[{}],"pages":[{"pageid":17,"ns":0,"title":"Example-new"}]}})
        p = self.panel["pages"][0]["source"]
        p["response_bytes"] = len(b)
        p["body_sha256"] = hashlib.sha256(b).hexdigest()
        self.raw.joinpath("en.wikipedia.17.json").write_bytes(b)
        self.reject("unexpected title redirect")


    def test_oversized_retained_body_denied_before_json(self):
        self.raw.joinpath("en.wikipedia.17.json").write_bytes(b"x" * (1024 * 1024 + 1))
        self.reject("oversized raw response")

    def test_cli_replay_succeeds_and_corrupted_body_fails(self):
        self.panel_path.write_bytes(canonical_bytes(self.panel))
        args = [sys.executable, "-m", "tools.m1_source_verify", str(self.panel_path), str(self.raw)]
        first = subprocess.run(args, capture_output=True, cwd=EXAMPLE.parent.parent, check=False)
        self.assertEqual(first.returncode, 0, first.stderr.decode())
        self.assertEqual(json.loads(first.stdout)["verified_page_count"], 2)
        again = subprocess.run(args, capture_output=True, cwd=EXAMPLE.parent.parent, check=False)
        self.assertEqual(first.stdout, again.stdout)
        self.raw.joinpath("en.wikipedia.17.json").write_bytes(b"bad")
        failure = subprocess.run(args, capture_output=True, cwd=EXAMPLE.parent.parent, check=False)
        self.assertEqual(failure.returncode, 2)
        self.assertIn(b"INVALID", failure.stderr)
        self.assertEqual(failure.stdout, b"")


if __name__ == "__main__":
    unittest.main()
