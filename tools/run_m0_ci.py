"""Run the publishable M0 static candidate and all offline/browser regressions.

No network retrieval, GitHub writes, branch updates or Pages deployment. The
browser tests use real Chromium in controlled DOM and *do not* certify public HTTP.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import signal
from pathlib import Path
import subprocess
import sys
import time

from tools.build_static_release import build_zip, bundle_files
from tools.build_portable import DESTINATION, build_html

ROOT = Path(__file__).resolve().parents[1]
# Four bounded, independently reported Chromium shards in read-only CI.
# The no-argument local command still runs the complete suite.
BROWSER_SHARDS = 4
BROWSERS = (
    'browser_clipboard_race.py',
    'browser_compare_daily.py',
    'browser_control_guard.py',
    'browser_discovery_order.py',
    'browser_filter_links.py',
    'browser_history_disclosure.py',
    'browser_incompatible_links.py',
    'browser_nojs.py',
    'browser_portable.py',
    'browser_release_evidence.py',
    'browser_share_destination.py',
    'browser_smoke.py',
    'browser_stream_budget.py',
    'browser_zip_inflate_limit.py',
    'browser_version_required.py',
)


def command(*argv):
    print('RUN', ' '.join(argv), flush=True)
    subprocess.run(argv, check=True, cwd=ROOT, timeout=180)


def bounded_browser_command(argv, timeout=45):
    """Kill the *whole* local Chromium/Playwright process group on timeout.

    A test launcher can leave browser subprocesses holding captured stdout and
    stderr open. Killing only its Python parent does not reliably unblock
    subprocess.run().communicate(), so acceptance must bound descendants too.
    Hosted CI runs on Linux, where an isolated POSIX process group is available.
    """
    proc = subprocess.Popen(
        argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=(os.name == 'posix'),
    )
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out, err, False
    except subprocess.TimeoutExpired:
        if os.name == 'posix':
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            proc.kill()
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            # Fail closed even when descendants have inherited pipe handles.
            # Closing here prevents a second, unbounded read of their output.
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
            out, err = '', 'Cannot drain terminated browser process pipes.'
        return 124, out, err, True


def run_browser_suite(name):
    """Execute one controlled-DOM Chromium test with bounded descendants."""
    argv = [sys.executable, str(ROOT / 'tests' / name)]
    started = time.monotonic()
    try:
        code, stdout, stderr, timed_out = bounded_browser_command(argv, timeout=45)
        if timed_out:
            stderr = (stderr or '') + '\nTIMEOUT after 45s; browser process group terminated'
        return name, code, stdout, stderr, time.monotonic() - started
    except OSError as error:
        return name, 125, '', str(error), time.monotonic() - started


def browser_shard(index):
    """Deterministically partition every browser suite exactly once."""
    if not 1 <= index <= BROWSER_SHARDS:
        raise ValueError(f'Browser shard must be in 1..{BROWSER_SHARDS}')
    return BROWSERS[index - 1::BROWSER_SHARDS]


def run_browser_suites(names=None):
    """Run each Chromium process from the main thread, serially and bounded.

    This avoids process-spawn contention with Playwright subprocesses and makes
    a failing/expired suite an explicit failure rather than a silent omission.
    """
    failures = []
    if names is None:
        names = BROWSERS
    for name in names:
        name, code, stdout, stderr, elapsed = run_browser_suite(name)
        print(f'BROWSER {name}: {"PASS" if code == 0 else "FAIL"} ({elapsed:.1f}s)', flush=True)
        if stdout:
            print(stdout, end='' if stdout.endswith('\n') else '\n', flush=True)
        if stderr:
            print(stderr, end='' if stderr.endswith('\n') else '\n', file=sys.stderr, flush=True)
        if code:
            failures.append(f'{name}: exit={code}')
    if failures:
        raise SystemExit('Browser acceptance failed: ' + ', '.join(sorted(failures)))


def ensure_portable_preview():
    """Build a missing generated file in a cold checkout; reject stale output.

    The portable HTML is a deterministic projection, not committed source.
    Evidence validation occurs before any candidate write.
    """
    expected = build_html()
    if DESTINATION.exists():
        if DESTINATION.read_bytes() != expected:
            raise SystemExit('Stale generated portable preview; refusing to overwrite it')
        print('PASS existing generated portable preview is current', flush=True)
        return
    try:
        with DESTINATION.open('xb') as output:
            output.write(expected)
    except FileExistsError:
        if DESTINATION.read_bytes() != expected:
            raise SystemExit('Concurrent portable preview differs; refusing acceptance')
    print('PASS generated portable preview for clean checkout', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python-only', action='store_true', help='Do not run Chromium (for the Python matrix)')
    parser.add_argument('--browser-shard', type=int, choices=range(1, BROWSER_SHARDS + 1),
                        help='Run one of four deterministic browser partitions (hosted CI)')
    args = parser.parse_args()
    if args.python_only and args.browser_shard is not None:
        parser.error('--python-only and --browser-shard cannot be combined')

    # Fail if a new browser suite was added but silently left out of CI.
    known = {p.name for p in (ROOT/'tests').glob('browser_*.py')} - {'browser_runner.py', 'browser_m0_http.py'}
    if set(BROWSERS) != known:
        raise SystemExit(f'Browser test inventory differs: expected={sorted(BROWSERS)} actual={sorted(known)}')
    ensure_portable_preview()
    if args.browser_shard is None:
        command(sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-q')
        command(sys.executable, '-m', 'compileall', '-q', 'tools', 'tests')

    # Verify source-bound historical evidence and deterministic release bytes.
    verified = bundle_files(ROOT)
    first = build_zip(verified)
    if first != build_zip(bundle_files(ROOT)):
        raise SystemExit('Release build is not deterministic')
    print('PASS local static Pages candidate sha256=' + hashlib.sha256(first).hexdigest(),flush=True)
    if not args.python_only:
        if args.browser_shard is not None:
            names = browser_shard(args.browser_shard)
            print(f'RUN browser shard {args.browser_shard}/{BROWSER_SHARDS}: {names!r}', flush=True)
            run_browser_suites(names)
            print(f'PASS shard {args.browser_shard}/{BROWSER_SHARDS} ({len(names)} suites); '
                  'full acceptance requires every shard and the separate Python matrix', flush=True)
        else:
            run_browser_suites()
            print(f'PASS all {len(BROWSERS)} browser suites; hosted CI and public HTTP NOT_VERIFIED',flush=True)
    else:
        print('PASS offline Python acceptance; browser, hosted CI and public HTTP NOT_VERIFIED',flush=True)


if __name__ == '__main__':
    main()
