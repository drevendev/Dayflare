"""Complete-cohort guard for the separate ten-title acquisition.

Only call after the canonical discovery/bundle/source verifiers. These checks
bind the independently observed IDs and exact titles to this editorial cohort;
they do not authenticate provider origin or establish historical identity.
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'examples/m1_curated_additional_10_enru.json'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_bytes())


def gate(curated, report, selected, handoff):
    expected_titles = {(r['project'], r['title'].replace(' ', '_')): r['subject']
                       for r in curated['pages']}
    require(len(expected_titles) == 10 and report['requested_count'] == 10
            and report['candidate_count'] == 10 and report['excluded_count'] == 0
            and len(report['attempts']) == 10, 'Incomplete title discovery')
    require(all(r['status'] == 'candidate' for r in report['attempts']),
            'Excluded title must remain excluded')
    discovered = {(r['project'], r['requested_title'].replace(' ', '_'), r['page_id'])
                  for r in report['attempts']}
    actual = {(r['project'], r['title'].replace(' ', '_'), r['page_id']) for r in selected}
    require(len(discovered) == 10 and len(actual) == len(selected) == 10
            and len({(p, i) for p, _, i in discovered}) == 10
            and actual == discovered
            and {(p, t) for p, t, _ in actual} == set(expected_titles),
            'Exact independently re-queried identity/title mismatch')
    require(all(r['subject'] == expected_titles[(r['project'], r['title'].replace(' ', '_'))]
                for r in selected), 'Subject mismatch')
    require(Counter((r['project'], r['subject']) for r in selected) ==
            Counter({(p, s): 1 for p in ('en.wikipedia', 'ru.wikipedia')
                     for s in ('culture', 'books', 'games', 'science', 'sport')}),
            'Incomplete subject/edition coverage')
    require(handoff['candidate_count'] == 10 and handoff['excluded_count'] == 0
            and handoff['metric_scope'] == 'title_scoped_views_not_stable_page_id_history',
            'Invalid handoff scope')


def source(root):
    handoff = root / 'additional-handoff/seeds.json'
    bundle = root / 'additional-source'
    require(handoff.read_bytes() == (bundle / 'seeds.json').read_bytes(), 'Source seed mismatch')
    rows = load(bundle / 'candidate.json')['series']
    receipt = load(bundle / 'source-receipt.json')
    require(len(rows) == 10 and all(len(r['daily']) == 35 for r in rows)
            and receipt['requests_attempted'] == 10
            and receipt['provenance_status'] == 'runtime_reported_transport_not_independently_authenticated'
            and receipt['publication_status'] == 'LOCAL_EVIDENCE_ONLY_NOT_PUBLISHED',
            'Incomplete or mislabelled source')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('gate', 'source', 'failure'))
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    root = args.root
    if args.mode == 'gate':
        gate(load(SEED), load(root / 'additional-title/discovery-report.json'),
             load(root / 'additional-handoff/seeds.json')['pages'],
             load(root / 'additional-handoff/handoff.json'))
    elif args.mode == 'source':
        source(root)
    else:
        from tools.rolling_pageview_source import verify_failure_receipt
        proof = verify_failure_receipt(root / 'additional-source.failure.json')
        require(not (root / 'additional-source').exists()
                and proof['seed_sha256'] == sha256(
                    (root / 'additional-handoff/seeds.json').read_bytes()).hexdigest(),
                'Failure receipt/source seed mismatch')


if __name__ == '__main__':
    main()
