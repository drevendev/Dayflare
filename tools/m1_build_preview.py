"""Build a synthetic-only M1 browser evidence preview; NOT a public release.

Only local, validated synthetic fixture data may be rendered. This tool never
fetches network data, publishes Pages, or upgrades reported receipts to evidence.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from tools.m1_identity_panel import canonical_bytes, load_panel

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / 'examples/synthetic_viewer_panel.json'
SITE = ROOT / 'site/m1-preview'
SCHEMA = 'dayflare.identity-panel.v1'


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def expected_outputs(fixture: Path = DEFAULT_FIXTURE, site: Path = SITE) -> dict[str, bytes]:
    panel = load_panel(fixture)
    if (panel['schema_version'] != SCHEMA or panel['selection']['evidence_kind'] != 'synthetic'
            or panel['coverage']['provenance_verification'] != 'synthetic_only'):
        raise ValueError('M1 preview requires validated synthetic-only inputs')
    if not re.fullmatch(r'[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*', panel['panel_id']):
        raise ValueError('unsafe panel ID')
    dataset = canonical_bytes(panel)
    template = (site / 'index.template.html').read_text(encoding='utf-8')
    if template.count('__EXPECTED_HASH__') != 1 or template.count('__PANEL_ID__') != 1:
        raise ValueError('broken preview template')
    html = template.replace('__EXPECTED_HASH__', digest(dataset)).replace('__PANEL_ID__', panel['panel_id']).encode('utf-8')
    outputs = {'index.html': html, 'panel.json': dataset}
    asset_hashes = {name: digest(data) for name, data in outputs.items()}
    for name in ('styles.css', 'app.js'):
        asset_hashes[name] = digest((site / name).read_bytes())
    manifest = {
        'kind': 'synthetic-only-identity-preview',
        'schema_version': SCHEMA,
        'panel_id': panel['panel_id'],
        'observation_kind': 'fictional-engineering-fixture',
        'content_sha256': dict(sorted(asset_hashes.items())),
        'observed_panel_identities': panel['coverage']['obtained_count'],
        'intended_panel_identities': panel['coverage']['intended_count'],
        'not_a_public_attention_atlas': True,
    }
    outputs['manifest.json'] = canonical_bytes(manifest)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='verify byte-identical built outputs without writing')
    parser.add_argument('--fixture', type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args()
    try:
        outputs = expected_outputs(args.fixture)
        for name, content in outputs.items():
            target = SITE / name
            if args.check:
                if not target.is_file() or target.read_bytes() != content:
                    raise ValueError(f'preview out of date: {name}')
            else:
                target.write_bytes(content)
    except (OSError, ValueError) as exc:
        parser.exit(2, f'INVALID PREVIEW: {exc}\n')
    print(('VERIFIED' if args.check else 'BUILT') + ' synthetic M1 identity preview: ' +
          ', '.join(sorted(outputs)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
