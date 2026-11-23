"""Download an independently pinned M1 HTML archive without GitHub Pages.

Fetch *one fixed Git commit*, never mutable gh-pages/HEAD, and verify the exact
manifest and HTML before writing. This does not publish, authenticate the
original Wikimedia transport, or prove browser acceptance.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from tools.verify_m1_public_release import check_manifest
from tools.verify_public_release import NoRedirect, VerificationError, hexdigest, origin

HEX = re.compile(r'[0-9a-f]{64}\Z')
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
MAX_HTML = 1024 * 1024
MAX_MANIFEST = 128 * 1024


def release_root(commit_sha: str) -> str:
    if type(commit_sha) is not str or not COMMIT.fullmatch(commit_sha):
        raise VerificationError('A full lowercase 40-character accepted commit SHA is required')
    return f'https://raw.githubusercontent.com/drevendev/Dayflare/{commit_sha}/m1/'


def _get(opener, url: str, name: str, limit: int) -> bytes:
    request = Request(url, headers={
        'Accept-Encoding': 'identity', 'Cache-Control': 'no-cache',
        'User-Agent': 'Dayflare-pinned-offline-download/1.0',
    })
    try:
        with opener.open(request, timeout=12) as response:
            if response.status != 200 or response.geturl() != url:
                raise VerificationError(f'{name}: unexpected HTTP response or URL')
            if response.headers.get('Content-Encoding', 'identity').strip().lower() not in ('', 'identity'):
                raise VerificationError(f'{name}: encoded bytes rejected')
            mime = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            accepted = {'text/plain', 'application/json'} if name.endswith('.json') else {'text/plain', 'text/html'}
            if mime not in accepted:
                raise VerificationError(f'{name}: incorrect MIME {mime!r}')
            lengths = response.headers.get_all('Content-Length', [])
            if len(lengths) > 1:
                raise VerificationError(f'{name}: duplicate Content-Length')
            if lengths:
                if not re.fullmatch(r'(0|[1-9][0-9]*)', lengths[0]) or int(lengths[0]) > limit:
                    raise VerificationError(f'{name}: unsafe Content-Length')
            body = response.read(limit + 1)
            if len(body) == 0 or len(body) > limit:
                raise VerificationError(f'{name}: empty or oversized body')
            if lengths and len(body) != int(lengths[0]):
                raise VerificationError(f'{name}: incomplete HTTP body')
            return body
    except VerificationError:
        raise
    except Exception as exc:
        raise VerificationError(f'{name}: HTTP request failed: {type(exc).__name__}: {exc}') from exc


def _root_for_test(commit_sha: str, base_url: str | None, allow_loopback_http: bool) -> str:
    official = release_root(commit_sha)
    if base_url is None:
        return official
    if not allow_loopback_http:
        raise VerificationError('Custom origins are allowed only in explicit loopback tests')
    if origin(base_url, allow_loopback_http=True):
        raise VerificationError('Test override must use numeric loopback HTTP')
    parsed = urlsplit(base_url)
    expected_path = f'/drevendev/Dayflare/{commit_sha}/m1/'
    if parsed.path != expected_path:
        raise VerificationError('Loopback test path must match the exact pinned commit')
    return base_url


def _open_nofollow_parent(parent: Path) -> int:
    """Hold a validated directory identity across fetch and the final create.

    Open every ancestor relative to its validated parent fd; a path-only
    symlink preflight cannot defend against directory replacement during I/O.
    Unsupported platforms fail closed rather than reverting to path-based open.
    """
    if (not hasattr(os, 'O_DIRECTORY') or not hasattr(os, 'O_NOFOLLOW')
            or any(fn not in os.supports_dir_fd for fn in (os.open, os.stat, os.unlink))
            or os.stat not in os.supports_follow_symlinks):
        raise VerificationError('Race-safe output creation requires POSIX dir_fd/O_NOFOLLOW; unsupported platform')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
    held = None
    try:
        held = os.open('/' if parent.is_absolute() else '.', flags)
        for component in parent.parts:
            if component in ('/', '.'):
                continue
            child = os.open(component, flags, dir_fd=held)
            os.close(held)
            held = child
        return held
    except OSError as exc:
        if held is not None:
            os.close(held)
        raise VerificationError('Destination has a linked directory ancestor or inaccessible parent') from exc


def download(commit_sha: str, expected_manifest_sha256: str,
             expected_dataset_id: str, expected_observation_end: str,
             destination: Path | str, *, base_url: str | None = None,
             allow_loopback_http: bool = False) -> dict:
    """Verify independently pinned immutable bytes; never overwrite a file."""
    root = _root_for_test(commit_sha, base_url, allow_loopback_http)
    if type(expected_manifest_sha256) is not str or not HEX.fullmatch(expected_manifest_sha256):
        raise VerificationError('Independent lowercase manifest SHA-256 is required')
    dest = Path(destination)
    if not dest.name:
        raise VerificationError('Destination must name a new file')

    # A directory fd pins the original output-directory identity even if a
    # different process swaps a pathname for a symlink during network reads.
    parent_fd = _open_nofollow_parent(dest.parent)
    try:
        try:
            os.stat(dest.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise VerificationError('Cannot inspect output file safely') from exc
        else:
            raise VerificationError('Destination exists; refusing to replace an accepted archive')

        opener = build_opener(NoRedirect())
        raw = _get(opener, root + 'release-manifest.json', 'release-manifest.json', MAX_MANIFEST)
        if hexdigest(raw) != expected_manifest_sha256:
            raise VerificationError('Manifest differs from independently accepted SHA-256')
        manifest = check_manifest(raw, expected_dataset_id=expected_dataset_id,
                                  expected_observation_end=expected_observation_end)
        html = _get(opener, root + 'index.html', 'index.html', MAX_HTML)
        if hexdigest(html) != manifest['html_sha256']:
            raise VerificationError('HTML differs from pinned manifest')

        # Both directory and file identity are anchored to no-follow handles.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        try:
            output_fd = os.open(dest.name, flags, 0o644, dir_fd=parent_fd)
        except FileExistsError as exc:
            raise VerificationError('Destination exists; refusing to overwrite') from exc
        except OSError as exc:
            raise VerificationError('Cannot create output safely') from exc
        created = os.fstat(output_fd)
        try:
            with os.fdopen(output_fd, 'wb') as stream:
                stream.write(html)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            # Never unlink through the untrusted original pathname. If the
            # leaf was replaced, do not delete somebody else's file.
            try:
                current = os.stat(dest.name, dir_fd=parent_fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                    os.unlink(dest.name, dir_fd=parent_fd)
            except OSError:
                pass
            raise
        return {
            'path': str(dest), 'html_bytes': len(html),
            'html_sha256': hexdigest(html), 'manifest_sha256': hexdigest(raw),
            'dataset_id': manifest['dataset_id'],
            'method_version': manifest['method_version'],
            'observation_end': manifest['observation_end'],
            'retrieved_at': manifest['retrieved_at'],
            'source_commit': commit_sha,
            'status': 'OFFLINE_BYTES_VERIFIED_NOT_DEPLOYED',
        }
    finally:
        os.close(parent_fd)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True, help='Full approved gh-pages commit SHA')
    parser.add_argument('--expected-manifest-sha256', required=True,
                        help='Independent native release-review SHA-256, not fetched manifest value')
    parser.add_argument('--expected-dataset-id', required=True)
    parser.add_argument('--expected-observation-end', required=True)
    parser.add_argument('--destination', type=Path, required=True,
                        help='New .html path; never overwrites an existing file')
    args = parser.parse_args()
    try:
        result = download(args.commit, args.expected_manifest_sha256,
                          args.expected_dataset_id, args.expected_observation_end,
                          args.destination)
    except VerificationError as exc:
        parser.exit(1, f'FAIL: {exc}\n')
    print(json.dumps(result, sort_keys=True))
    print('NOTE: Verified pinned downloadable HTML, not a published Pages site or browser acceptance.')


if __name__ == '__main__':
    main()
