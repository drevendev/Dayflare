"""Export distinct weekly signals from a verified 30-title source capsule, offline."""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory


def signals(weekly):
    if len(weekly) != 5 or any(type(v) is not int or v < 0 for v in weekly):
        raise ValueError('five nonnegative integer weekly totals required')
    ordered = sorted(weekly[:4])
    baseline = Fraction(ordered[1] + ordered[2], 2)
    delta = weekly[-1] - baseline
    step = weekly[-1] - weekly[-2]
    relative = None if baseline == 0 else delta / baseline
    sign = lambda x: (x > 0) - (x < 0)
    return baseline, delta, relative, step, sign(delta) * sign(step) == -1


def half(value):
    return str(value.numerator) if value.denominator == 1 else (
        ('-' if value < 0 else '') + str(abs(value.numerator) // 2) + '.5')


def render_csv(candidate, receipt):
    """Only call with a source-verified candidate and receipt."""
    if receipt['provenance_status'] != 'runtime_reported_transport_not_independently_authenticated':
        raise ValueError('real-source receipt required; synthetic input rejected')
    out = StringIO(newline='')
    writer = csv.writer(out, lineterminator='\r\n')
    writer.writerow(('project_page_id', 'title', 'subject', 'week1', 'week2', 'week3', 'week4', 'week5',
                     'prior4_median', 'median_delta', 'relative_lift_numerator', 'relative_lift_denominator',
                     'adjacent_week_step', 'opposite_nonzero_signs', 'dataset_id', 'method_version',
                     'observation_start', 'observation_end', 'retrieved_at', 'access', 'agent',
                     'candidate_sha256', 'source_endpoint', 'body_sha256', 'provenance_status'))
    for row, source in zip(candidate['series'], receipt['sources'], strict=True):
        counts = [d['views'] for d in row['daily']]
        weekly = [sum(counts[i:i+7]) for i in range(0, 35, 7)]
        baseline, delta, rel, step, opposite = signals(weekly)
        title = row['title']
        if title.lstrip().startswith(('=', '+', '-', '@')) or title.startswith(('\t', '\r', '\n')):
            title = "'" + title
        writer.writerow((f"{row['project']}:{row['page_id']}", title, source['subject'], *weekly,
                         half(baseline), half(delta), '' if rel is None else rel.numerator,
                         '' if rel is None else rel.denominator, step, int(opposite), candidate['dataset_id'],
                         candidate['method_version'], receipt['observation_start'], receipt['observation_end'],
                         receipt['retrieved_at'], row['access'], row['agent'], receipt['candidate_sha256'],
                         source['endpoint'], source['body_sha256'], receipt['provenance_status']))
    return out.getvalue().encode('utf-8')


def export(capsule, destination, capsule_pin, original_pin):
    from .m1_30_source_capsule import unpack
    from .rolling_pageview_source import verify_bundle
    from .rolling_window_gate import stamp

    members = unpack(capsule, capsule_pin, original_pin)
    candidate = json.loads(members['candidate.json'])
    receipt = json.loads(members['source-receipt.json'])
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'raw').mkdir()
        for name, raw in members.items():
            (root / name).write_bytes(raw)
        proof = verify_bundle(root, now=stamp(receipt['retrieved_at']))
        if proof['series'] != 30 or proof['observations'] != 1050:
            raise ValueError('expected 30 complete histories')
        result = render_csv(candidate, receipt)
    with destination.open('xb') as stream:
        stream.write(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capsule', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--capsule-sha256', required=True)
    parser.add_argument('--original-sha256', required=True)
    args = parser.parse_args()
    export(args.capsule, args.destination, args.capsule_sha256, args.original_sha256)


if __name__ == '__main__':
    main()
