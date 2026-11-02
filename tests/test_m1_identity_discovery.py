"""Version-bound observed-identity discovery must not conceal no-JS evidence."""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

from tools.m1_observed_panel import load
from tools.build_static_release import bundle_files

ROOT = Path(__file__).resolve().parents[1]


class IdentityDiscoveryTests(unittest.TestCase):
    def test_readable_nojs_fallback_and_live_control_contract(self):
        doc = (ROOT / "site/identities-m1-20261024.html").read_text(encoding="utf-8")
        panel = load(ROOT / "site/identities-m1-20261024.json")
        self.assertEqual(doc.count('data-identity-explorer hidden'), 1)
        self.assertEqual(doc.count('src="identity-explorer.js" defer'), 1)
        self.assertIn('id="identity-query"', doc)
        self.assertIn('id="identity-result-count" role="status" aria-live="polite"', doc)
        self.assertIn('id="identity-no-results" hidden', doc)
        self.assertIn('id="identity-reset"', doc)
        self.assertIn('[hidden]{display:none!important}', doc)
        self.assertEqual(set(re.findall(r'name="identity-edition" value="(\w+)"', doc)),
                         {"all", "en", "ru"})
        self.assertEqual(len(re.findall(r'<article class="card" id=', doc)), 20)
        for row in panel["pages"]:
            self.assertIn('data-page-ref="%s:%s"' % (row["project"], row["page_id"]), doc)
        self.assertIn("Identity metadata, not attention trends.", doc)

    def test_discovery_precedes_long_historical_companion_stories(self):
        """The first visitor path is the real 20-ID search, not a long preamble."""
        doc = (ROOT / "site/identities-m1-20261024.html").read_text(encoding="utf-8")
        landmarks = (
            '<section class="hero"',
            '<section class="explore-controls"',
            '<nav id="subjects"',
            '<section class="category" id="culture"',
            '<section class="category" id="sport"',
            '<section class="method" id="measured-chess"',
            '<section class="method" id="measured-more"',
            '<section class="method" id="method"',
        )
        locations = [doc.index(mark) for mark in landmarks]
        self.assertEqual(locations, sorted(locations))
        self.assertEqual(doc.count('<section class="explore-controls"'), 1)
        self.assertEqual(doc.count('data-page-ref="'), 20)
        # Jump links remain valid for both keyboard and JavaScript-disabled visitors.
        self.assertIn('href="#subjects"', doc[:locations[1]])
        self.assertIn('href="#measured-more"', doc[:locations[1]])
        self.assertIn('href="#culture"', doc[locations[2]:locations[3]])
        self.assertIn('id="measured-chess-title"', doc)
        self.assertIn('id="measured-more-title"', doc)

    def test_versioned_static_build_contains_search_script(self):
        files = bundle_files()
        script = (ROOT / "site/identity-explorer.js").read_bytes()
        self.assertEqual(files["identity-explorer.js"], script)
        self.assertIn(b"History API must not break", script)
        self.assertIn(b"if (typeof document === 'undefined') return;", script)

    @unittest.skipUnless(shutil.which("node"), "Node.js not available")
    def test_filter_match_and_url_restoration(self):
        result = subprocess.run(["node", "tests/js_identity_explorer.cjs"],
                                cwd=ROOT, timeout=20, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS identity explorer", result.stdout)


if __name__ == "__main__":
    unittest.main()
