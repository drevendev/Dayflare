"""Collect a *later UTC day* for the pinned 4-Nov EN/RU stable page IDs.

A single manual, bounded, no-retry run. All data stays UNPUBLISHED and a failed
attempt never replaces an earlier accepted source/report. Does not resolve moves,
pageview continuity, or upstream authenticity. No scheduler/Pages mutations.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile

from .m1_collect import (
    CollectionFailure, MAX_IDENTITY_CALLS, SLOW_ACTION_API_PAUSE_SECONDS,
    TIMEOUT_SECONDS, _fetch_once, _rename_directory_no_replace,
    collect_to_new_directory, validate_seed,
)
from .m1_bundle_verify import verify_bundle
from .m1_identity_history import compare_bytes, write_bundle
from .m1_identity_panel import PanelError, canonical_bytes
from .m1_retained_identity import DEFAULT, load_retained

SCHEMA = 'dayflare.identity-followup.v1'
# Preflight pessimistically: per-request network timeout plus conservative pause,
# workflow overhead and verification before UTC midnight. No retries.
SAFETY_SECONDS = MAX_IDENTITY_CALLS * (TIMEOUT_SECONDS + SLOW_ACTION_API_PAUSE_SECONDS) + 90


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def eligible_snapshot(panel: dict, provenance: dict, *, clock: datetime) -> str:
    if not isinstance(clock, datetime) or clock.tzinfo is None or clock.utcoffset() != timedelta(0):
        raise PanelError('UTC-aware clock required')
    baseline_day = provenance['observation_date_utc']
    days = {row['titles'][-1]['date'] for row in panel['pages']}
    if days != {baseline_day} or not panel['pages'] or panel['selection']['evidence_kind'] != 'reported_retrieval':
        raise PanelError('pinned baseline observation/coverage does not agree')
    today = clock.date().isoformat()
    if today <= baseline_day:
        raise CollectionFailure(f'later UTC date required; baseline={baseline_day}, today={today}; no requests made')
    if (datetime.combine(clock.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc) - clock).total_seconds() < SAFETY_SECONDS:
        raise CollectionFailure('too close to UTC midnight for bounded later-day collection; no requests made')
    if len(panel['pages']) > 20:
        raise CollectionFailure('follow-up limited to 20 retained local identities')
    return today


def seed_for_same_ids(panel: dict, day: str) -> dict:
    """Pin stable IDs and explicit editorial scope, never rediscover by title."""
    entries = [{field: row[field] for field in ('page_ref', 'topic_id', 'subject', 'relation')}
               for row in panel['pages']]
    entries.sort(key=lambda x: (x['page_ref']['project'], x['page_ref']['page_id']))
    seed = {'schema_version': 'dayflare.identity-seeds.v1',
            'panel_id': f'm1-followup-{day.replace("-", "")}',
            'selected_at': day, 'pages': entries}
    if len(entries) != 20 or len({(x['page_ref']['project'], x['page_ref']['page_id']) for x in entries}) != 20:
        raise CollectionFailure('baseline stable-ID coverage changed; expected exactly 20 distinct identities')
    validate_seed(seed)
    return seed


def _manifest(root: Path) -> dict:
    """All files in the candidate, exact relative paths, sizes and hashes."""
    files = {}
    for file in sorted(root.rglob('*')):
        if file.is_symlink():
            raise CollectionFailure('symlink in output')
        if file.is_file():
            name = file.relative_to(root).as_posix()
            if name == 'manifest.json':
                continue
            if file.stat().st_size > 1024 * 1024:
                raise CollectionFailure('oversized output member')
            data = file.read_bytes()
            files[name] = {'sha256': sha256(data).hexdigest(), 'bytes': len(data)}
    return {'schema_version': SCHEMA, 'files': files}


def collect_followup(destination: Path, *, source: Path = DEFAULT,
                     now=utc_now, fetch=_fetch_once, sleep=None,
                     source_revision: str | None = None) -> dict:
    """Validate first, collect exactly once, compare, then atomically expose a new bundle.

    `fetch`/`now`/`sleep` are injected only in offline tests. Production uses
    the existing identified, paced and bounded Wikimedia collector unchanged.
    """
    from time import sleep as real_sleep
    if sleep is None:
        sleep = real_sleep
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise CollectionFailure('destination exists; never overwrite accepted evidence')
    panel, _, provenance, members = load_retained(source)
    clock = now()
    day = eligible_snapshot(panel, provenance, clock=clock)
    if source_revision is not None and (len(source_revision) != 40 or any(c not in '0123456789abcdef' for c in source_revision)):
        raise CollectionFailure('source revision must be a full lowercase commit SHA')
    seed = seed_for_same_ids(panel, day)
    original = members['panel.json']
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.dayflare-followup-', dir=destination.parent) as scratch:
        root = Path(scratch)
        (root / 'baseline-panel.json').write_bytes(original)
        (root / 'identity-seeds.json').write_bytes(canonical_bytes(seed))
        followup = root / 'followup-source'
        receipt = collect_to_new_directory(root / 'identity-seeds.json', followup,
                                           fetch=fetch, now=now, sleep=sleep)
        verification = verify_bundle(followup)
        if receipt['intended_count'] != 20 or receipt['requests_attempted'] != 20:
            raise CollectionFailure('incomplete requested identity set')
        new_panel_bytes = (followup / 'panel.json').read_bytes()
        new_panel = json.loads(new_panel_bytes)
        if not new_panel['pages'] or {x['titles'][-1]['date'] for x in new_panel['pages']} != {day}:
            raise CollectionFailure('mixed-date or empty later observation; do not publish')
        for page in new_panel['pages']:
            if page['source']['requested_at'][:10] != day:
                raise CollectionFailure('retrieval crossed a UTC day boundary')
        report = compare_bytes(original, new_panel_bytes)
        if report['inputs'][0]['observation_date_utc'] != provenance['observation_date_utc'] or report['inputs'][1]['observation_date_utc'] != day:
            raise CollectionFailure('invalid before/after chronology')
        # The report contains only observations; no inferred pageview joining.
        if any(row['pageview_join_allowed'] for row in report['pages']):
            raise CollectionFailure('identity comparison requested unsafe pageview join')
        write_bundle(root / 'baseline-panel.json', followup / 'panel.json', root / 'history')
        meta = {'schema_version': SCHEMA, 'status': 'UNPUBLISHED_SOURCE_REVIEW_REQUIRED',
                'baseline_observed_utc': provenance['observation_date_utc'],
                'followup_observed_utc': day,
                'baseline_capsule_sha256': provenance['capsule']['sha256'],
                'baseline_panel_sha256': sha256(original).hexdigest(),
                'followup_panel_sha256': sha256(new_panel_bytes).hexdigest(),
                'followup_source_manifest_sha256': verification['manifest_sha256'],
                'followup_retained_count': receipt['retained_count'],
                'followup_unavailable_count': receipt['unavailable_count'],
                'source_revision': source_revision,
                'scope': '20 selected stable EN/RU local page IDs; factual Action API metadata only',
                'limitations': [
                    'No historical pageviews or independently authenticated upstream transport.',
                    'No inferred page creation/deletion, move history or uninterrupted identity continuity.',
                    'Unknown/missing Wikidata mappings and unavailable IDs are not zero interest.',
                    'Source responses are decoded JSON, not original compressed wire bodies.',
                    'No Pages deployment or scheduled refresh has occurred.',
                ]}
        (root / 'receipt.json').write_bytes(canonical_bytes(meta))
        manifest = _manifest(root)
        (root / 'manifest.json').write_bytes(canonical_bytes(manifest))
        # Re-read candidate bytes and file membership before atomic promotion.
        if _manifest(root) != manifest:
            raise CollectionFailure('candidate files changed during packaging')
        _rename_directory_no_replace(root, destination)
    return meta


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path, help='new unique evidence and HTML directory')
    parser.add_argument('--source', type=Path, default=DEFAULT,
                        help='pinned reviewed baseline directory; cannot substitute unreviewed bytes')
    parser.add_argument('--source-revision', help='optional actual source commit SHA, not guessed')
    args = parser.parse_args(argv)
    try:
        result = collect_followup(args.destination, source=args.source,
                                  source_revision=args.source_revision)
    except (ValueError, OSError, PanelError, CollectionFailure, KeyError, TypeError) as error:
        print('UNPUBLISHED: ' + str(error), file=sys.stderr)
        return 2
    print(f"COLLECTED {result['followup_retained_count']} / 20 stable IDs for {result['followup_observed_utc']}; source review required; not deployed")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
