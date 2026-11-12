"""Regenerate the homepage's two accepted M1 examples from a pinned release.

This intentionally reads an independently accepted offline release directory, not
Wikipedia, the default branch or an unreviewed future candidate. The immutable
commit URL remains useful without a Pages deployment or JavaScript.
"""
from __future__ import annotations

import argparse
from html import escape, unescape
import os
from pathlib import Path
import re
import stat
import tempfile

from tools.m1_readme_sync import (
    SyncError, _read_regular, accepted_manifest, render as render_readme,
)
from tools.m1_home_window_sync import _reject_linked_output_path, _revisions

START = "<!-- dayflare:m1-home:start -->"
END = "<!-- dayflare:m1-home:end -->"
RAW = "https://raw.githubusercontent.com/drevendev/Dayflare/{revision}/m1/index.html"
REVISION = re.compile(r"[0-9a-f]{40}\Z")
SPOTLIGHT = re.compile(
    r'<a class="spotlight" href="#(?P<id>detail-(?:en|ru)-wikipedia-[0-9]+)">'
    r'<span class="badge">(?P<badge>[^<]+)</span>'
    r'<strong>(?P<title>[^<]+)</strong>'
    r'<span class="spotlight-number">(?P<change>[^<]+)</span>'
    r'<span class="spotlight-context">(?P<context>[^<]+)</span>'
    r'<span>Inspect 35 exact UTC days ↗</span></a>'
)


def source_examples(accepted_html: str, end: str) -> list[dict[str, str]]:
    """Only the generator's source-bound spotlight pairs, not arbitrary HTML."""
    start = accepted_html.find('<section class="spotlights"')
    stop = accepted_html.find("</section>", start)
    if start < 0 or stop < start or accepted_html.count('<section class="spotlights"') != 1:
        raise SyncError("accepted atlas has no unique spotlight section")
    section = accepted_html[start:stop + len("</section>")]
    found = [m.groupdict() for m in SPOTLIGHT.finditer(section)]
    if len(found) != 2 or len({m["id"] for m in found}) != 2:
        raise SyncError("accepted atlas does not have exactly two unique evidence examples")
    if not ("Largest increase" in found[0]["badge"] and
            "Largest decrease" in found[1]["badge"]):
        raise SyncError("accepted spotlight roles changed")
    for item in found:
        if section.count('href="#' + item["id"] + '"') != 1:
            raise SyncError("ambiguous accepted spotlight link")
        if accepted_html.count('id="' + item["id"] + '"') != 1:
            raise SyncError("accepted spotlight detail target is missing or ambiguous")
        if end not in item["context"] or "preceding four-week median" not in item["context"]:
            raise SyncError("accepted spotlight does not describe the complete source window")
    return found


def render_feature(source: str, manifest: dict, pages_revision: str) -> str:
    if not REVISION.fullmatch(pages_revision):
        raise SyncError("accepted Pages revision must be an exact 40-char commit SHA")
    values = source_examples(source, manifest["observation_end"])
    url = escape(RAW.format(revision=pages_revision), quote=True)
    result = (
        '<div id="m1-home-evidence" class="m1-home-evidence" '
        'data-dataset-id="' + escape(manifest["dataset_id"], quote=True) + '" '
        'data-html-sha256="' + escape(manifest["html_sha256"], quote=True) + '" '
        'data-observation-end="' + escape(manifest["observation_end"], quote=True) + '">\n'
    )
    for i, item in enumerate(values):
        title = unescape(item["title"])
        language = ' lang="ru"' if item["id"].startswith("detail-ru-") else ""
        result += (
            '  <article class="m1-home-example" data-topic="' +
            escape(item["id"], quote=True) + '">\n'
            '    <span class="m1-home-kind">' + escape(unescape(item["badge"])) + '</span>\n'
            '    <h3' + language + '>' + escape(title) + '</h3>\n'
            '    <strong class="m1-home-change">' + escape(unescape(item["change"])) + '</strong>\n'
            '    <p>' + escape(unescape(item["context"])) + '</p>\n'
            '    <a class="m1-home-link" href="' + url + '" data-m1-detail="' +
            escape(item["id"], quote=True) +
            '">Download pinned M1 HTML to inspect this title ↗</a>\n'
            '  </article>\n'
        )
    return result + '</div>'


def synchronize(html: str, generated: str) -> str:
    if html.count(START) != 1 or html.count(END) != 1:
        raise SyncError("missing or duplicate homepage example markers")
    left = html.index(START) + len(START)
    right = html.index(END)
    if right <= left:
        raise SyncError("invalid homepage example marker order")
    return html[:left] + "\n" + generated + "\n" + html[right:]


def run(site: Path, readme: Path, release: Path, pin: str, revision: str, *,
        write: bool = False) -> bool:
    _reject_linked_output_path(site)
    if site.resolve() == readme.resolve() or site.resolve().is_relative_to(release.resolve()):
        raise SyncError("homepage output overlaps accepted release or README")
    manifest = accepted_manifest(release, pin)
    site_bytes = _read_regular(site, 1024 * 1024)
    readme_bytes = _read_regular(readme, 512 * 1024)
    html = site_bytes.decode("utf-8")
    readme_text = readme_bytes.decode("utf-8")
    if render_readme(manifest) not in readme_text:
        raise SyncError("README does not document this independently accepted release")
    _, end, retrieved = _revisions(html)
    if end.isoformat() != manifest["observation_end"] or (
        retrieved.strftime("%Y-%m-%dT%H:%M:%SZ") != manifest["retrieved_at"]
    ):
        raise SyncError("homepage dates must first match the accepted M1 release")
    source_bytes = _read_regular(release / "index.html", 4 * 1024 * 1024)
    rendered = render_feature(source_bytes.decode("utf-8"), manifest, revision)
    updated = synchronize(html, rendered)
    if updated == html:
        return False
    if not write:
        raise SyncError("homepage examples differ from pinned accepted release; use --write")
    if (_read_regular(site, 1024 * 1024) != site_bytes or
            _read_regular(readme, 512 * 1024) != readme_bytes or
            accepted_manifest(release, pin) != manifest):
        raise SyncError("inputs changed during homepage synchronization")
    _reject_linked_output_path(site)
    fd, tmp = tempfile.mkstemp(prefix=".dayflare-spotlight-", dir=site.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(updated.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, stat.S_IMODE(site.stat().st_mode))
        if _read_regular(site, 1024 * 1024) != site_bytes:
            raise SyncError("homepage changed before replacement")
        _reject_linked_output_path(site)
        os.replace(tmp, site)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-m1", required=True, type=Path)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--accepted-pages-revision", required=True)
    parser.add_argument("--site-index", type=Path, default=Path("site/index.html"))
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        changed = run(args.site_index, args.readme, args.accepted_m1,
                      args.expected_manifest_sha256, args.accepted_pages_revision,
                      write=args.write)
    except (OSError, ValueError, UnicodeError, SyncError) as exc:
        parser.exit(1, f"M1 homepage examples rejected: {exc}\n")
    print("M1_HOME_EXAMPLES_UPDATED" if changed else "M1_HOME_EXAMPLES_MATCH")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
