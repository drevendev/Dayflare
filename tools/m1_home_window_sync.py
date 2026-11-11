"""Fail-closed synchronization of the archived M1 window on the visitor homepage.

This is offline release documentation, never source acquisition, native review,
deployment or proof that GitHub Pages is serving the accepted release.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import os
from pathlib import Path
import re
import stat
import tempfile

from tools.m1_readme_sync import (
    END, START, SyncError, _read_regular, accepted_manifest, render,
)

MONTH = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
         "Oct", "Nov", "Dec")
SITE_WINDOW = re.compile(
    r'<p id="accepted-window" class="intro" '
    r'data-observed-start="(?P<start>\d{4}-\d{2}-\d{2})" '
    r'data-observed-end="(?P<end>\d{4}-\d{2}-\d{2})" '
    r'data-retrieved-at="(?P<retrieved>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)">'
    r'.*?</p>', re.DOTALL,
)


def _day_label(day: date, *, with_year: bool = True) -> str:
    return f"{day.day} {MONTH[day.month - 1]}" + (f" {day.year}" if with_year else "")


def render_window(end: date, retrieved: datetime) -> str:
    """One original semantic UTC date block; no variable user-supplied HTML."""
    start = end - timedelta(days=34)
    retrieved_iso = retrieved.strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f'<p id="accepted-window" class="intro" data-observed-start="{start.isoformat()}" '
        f'data-observed-end="{end.isoformat()}" data-retrieved-at="{retrieved_iso}">'
        '<strong>Latest accepted window:</strong> '
        f'<time datetime="{start.isoformat()}">{_day_label(start, with_year=start.year != end.year)}</time>'
        f'–<time datetime="{end.isoformat()}">{_day_label(end)}</time> UTC · retrieved '
        f'<time datetime="{retrieved_iso}">{_day_label(retrieved.date())}, '
        f'{retrieved:%H:%M:%S} UTC</time>. '
        'Historical title requests, not live attention or unique people.</p>'
    )


def _revisions(html: str) -> tuple[re.Match[str], date, datetime]:
    if html.count('id="accepted-window"') != 1:
        raise SyncError("missing or duplicate homepage accepted-window ID")
    matches = list(SITE_WINDOW.finditer(html))
    if len(matches) != 1:
        raise SyncError("homepage accepted-window DOM is not canonical")
    match = matches[0]
    try:
        end = date.fromisoformat(match["end"])
        retrieved = datetime.strptime(match["retrieved"], "%Y-%m-%dT%H:%M:%SZ")
        if (match["start"] != (end - timedelta(days=34)).isoformat() or
                retrieved.date() <= end or
                match.group(0) != render_window(end, retrieved)):
            raise ValueError("noncanonical or modified first-screen dates")
    except (ValueError, OverflowError) as exc:
        raise SyncError("homepage accepted-window chronology or markup changed") from exc
    return match, end, retrieved


def synchronize(site_html: str, manifest: dict) -> str:
    match, old_end, old_retrieved = _revisions(site_html)
    new_end = date.fromisoformat(manifest["observation_end"])
    new_retrieved = datetime.strptime(manifest["retrieved_at"], "%Y-%m-%dT%H:%M:%SZ")
    if (new_end, new_retrieved) < (old_end, old_retrieved):
        raise SyncError("stale accepted release cannot roll back homepage dates")
    replacement = render_window(new_end, new_retrieved)
    return site_html[:match.start()] + replacement + site_html[match.end():]


def _reject_linked_output_path(path: Path) -> None:
    """Reject symlink/reparse-point components of the homepage output path.

    Resolve neither a symlinked parent nor the leaf: we must inspect the
    caller-supplied filesystem path, not only the directory it points to.
    """
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        info = component.lstat()
        if (stat.S_ISLNK(info.st_mode) or
                getattr(info, "st_file_attributes", 0) &
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
            raise SyncError(f"linked/reparse homepage output path component: {component}")


def run(site_index: Path, readme: Path, release_dir: Path, pin: str,
        *, write: bool = False) -> bool:
    """Require separately accepted manifest and already-synchronized README."""
    # Never follow linked output directories (including Windows reparse points).
    _reject_linked_output_path(site_index)
    # Never rewrite the accepted archive or README through a homepage operation.
    if (site_index.resolve() == readme.resolve() or
            site_index.resolve().is_relative_to(release_dir.resolve())):
        raise SyncError("homepage target overlaps the trusted release or README")
    manifest = accepted_manifest(release_dir, pin)
    readme_raw = _read_regular(readme, 512 * 1024)
    site_raw = _read_regular(site_index, 1024 * 1024)
    try:
        readme_text = readme_raw.decode("utf-8")
        html = site_raw.decode("utf-8")
    except UnicodeError as exc:
        raise SyncError("homepage/README is not UTF-8") from exc
    # This tool is intentionally the second local documentation step after the
    # existing README synchronizer. A candidate archive cannot approve itself.
    if (readme_text.count(START) != 1 or readme_text.count(END) != 1 or
            render(manifest) not in readme_text):
        raise SyncError("README does not document this independently pinned accepted release")
    new_html = synchronize(html, manifest)
    if new_html == html:
        return False
    if not write:
        raise SyncError("homepage release window differs from accepted README; use --write")
    # Recheck both local inputs, including independent manifest and HTML pin,
    # immediately before the single-file atomic replacement.
    if (readme.read_bytes() != readme_raw or site_index.read_bytes() != site_raw or
            accepted_manifest(release_dir, pin) != manifest):
        raise SyncError("input changed during homepage synchronization")
    _reject_linked_output_path(site_index)
    fd, temp_name = tempfile.mkstemp(prefix=".dayflare-window-", dir=site_index.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(new_html.encode("utf-8"))
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temp_name, stat.S_IMODE(site_index.stat().st_mode))
        if readme.read_bytes() != readme_raw or site_index.read_bytes() != site_raw:
            raise SyncError("input changed before homepage replacement")
        _reject_linked_output_path(site_index)
        os.replace(temp_name, site_index)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-m1", required=True, type=Path,
                        help="Exact independently accepted gh-pages/m1 export")
    parser.add_argument("--expected-manifest-sha256", required=True,
                        help="SHA-256 obtained from native review, not this archive")
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--site-index", type=Path, default=Path("site/index.html"))
    parser.add_argument("--write", action="store_true",
                        help="Atomically update only the homepage first-screen date block")
    args = parser.parse_args()
    try:
        changed = run(args.site_index, args.readme, args.accepted_m1,
                      args.expected_manifest_sha256, write=args.write)
    except (OSError, SyncError) as exc:
        parser.exit(1, f"M1 homepage sync rejected: {exc}\n")
    print("HOMEPAGE_WINDOW_UPDATED" if changed else "HOMEPAGE_WINDOW_MATCHES_ACCEPTED_RELEASE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
