"""Regression against accidentally removing an M0 acceptance gate."""
from pathlib import Path
import unittest

from tools.run_m0_ci import BROWSERS, ROOT


class M0CIContractTests(unittest.TestCase):
    def test_browser_inventory_is_complete(self):
        expected = {p.name for p in (ROOT/'tests').glob('browser_*.py')} - {'browser_runner.py'}
        self.assertEqual(set(BROWSERS), expected)
        for name in BROWSERS:
            text = (ROOT/'tests'/name).read_text()
            self.assertIn('launch_chromium(', text)
            self.assertNotIn("executable_path='/usr/bin/chromium'", text)

    def test_unprivileged_ci_runs_offline_python_and_browser(self):
        workflow=(ROOT/'.github/workflows/m0-preview-validation.yml').read_text()
        self.assertIn('contents: read', workflow)
        self.assertIn('pull_request:', workflow)
        self.assertIn('branches: [master]', workflow)
        self.assertIn('python -m tools.run_m0_ci --python-only',workflow)
        self.assertIn('shard: [1, 2, 3, 4]',workflow)
        self.assertIn('fail-fast: false', workflow)
        self.assertIn('python -m tools.run_m0_ci --browser-shard ${{ matrix.shard }}', workflow)
        self.assertNotIn('run: python -m tools.run_m0_ci\n', workflow)
        self.assertIn('playwright==1.55.0',workflow)
        self.assertNotIn('deploy-pages',workflow)
        self.assertNotIn('write-all',workflow)
        self.assertNotIn('secrets.',workflow)


if __name__=='__main__':
    unittest.main()
