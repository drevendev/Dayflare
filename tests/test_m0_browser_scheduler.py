"""Offline runner must never quietly drop failing or timed-out browser suites."""
import contextlib
import io
import os
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from tools import run_m0_ci


class BrowserSchedulerTests(unittest.TestCase):
    def test_shards_cover_every_suite_once_without_overlap(self):
        partitions = [run_m0_ci.browser_shard(i)
                      for i in range(1, run_m0_ci.BROWSER_SHARDS + 1)]
        self.assertEqual(sum(map(len, partitions)), len(run_m0_ci.BROWSERS))
        self.assertEqual(set().union(*(set(part) for part in partitions)),
                         set(run_m0_ci.BROWSERS))
        self.assertTrue(all(part for part in partitions))
        self.assertTrue(all(len(part) <= 4 for part in partitions))
        for index in (0, -1, 5):
            with self.assertRaises(ValueError):
                run_m0_ci.browser_shard(index)

    def test_shard_runs_only_its_assigned_suites(self):
        calls = []
        def record(name):
            calls.append(name)
            return name, 0, '', '', 0.01
        with patch.object(run_m0_ci, 'run_browser_suite', side_effect=record):
            with contextlib.redirect_stdout(io.StringIO()):
                run_m0_ci.run_browser_suites(run_m0_ci.browser_shard(2))
        self.assertEqual(calls, list(run_m0_ci.browser_shard(2)))

    def test_failed_suite_fails_acceptance(self):
        def one_suite(name):
            return name, (1 if name == 'fails.py' else 0), 'test output\n', '', 0.01

        with patch.object(run_m0_ci, 'BROWSERS', ('good.py', 'fails.py')):
            with patch.object(run_m0_ci, 'run_browser_suite', side_effect=one_suite):
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(SystemExit, 'fails.py: exit=1'):
                        run_m0_ci.run_browser_suites()

    def test_timeout_is_error_not_pass(self):
        with patch.object(run_m0_ci, 'bounded_browser_command', return_value=(124, '', '', True)):
            name, code, stdout, stderr, elapsed = run_m0_ci.run_browser_suite('browser_smoke.py')
        self.assertEqual(name, 'browser_smoke.py')
        self.assertEqual(code, 124)
        self.assertIn('TIMEOUT after 45s', stderr)
        self.assertIn('process group terminated', stderr)
        self.assertGreaterEqual(elapsed, 0)

    @unittest.skipUnless(os.name == 'posix', 'requires POSIX process groups')
    def test_descendant_with_open_pipe_cannot_hang_acceptance(self):
        # Child inherits stdout/stderr. Previously, killing only the parent
        # could leave communicate() waiting for those handles indefinitely.
        script = (
            'import subprocess,sys,time; '
            'subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]); '
            'print("started",flush=True);time.sleep(30)'
        )
        before = time.monotonic()
        code, out, err, timed_out = run_m0_ci.bounded_browser_command(
            [sys.executable, '-c', script], timeout=1.5
        )
        self.assertLess(time.monotonic()-before, 6.0)
        self.assertEqual(code, 124)
        self.assertTrue(timed_out)
        self.assertIsInstance(out, str)

    def test_successful_suite_prints_pass(self):
        with patch.object(run_m0_ci, 'BROWSERS', ('good.py',)):
            with patch.object(run_m0_ci, 'run_browser_suite', return_value=('good.py', 0, 'checked\n', '', 0.01)):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    run_m0_ci.run_browser_suites()
        self.assertIn('BROWSER good.py: PASS', out.getvalue())
        self.assertIn('checked', out.getvalue())


if __name__ == '__main__':
    unittest.main()
