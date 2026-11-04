# Retained real identity explorer

## User outcome

Inspect 20 actual dated EN/RU page identities, their observed Wikidata IDs and
locally retained source responses without an expiring CI download. This is a
single metadata snapshot, **not popularity or a claim of change**. It advances
#19 and preserves the first raw baseline for #145. Public deployment remains #12.

## Local entry point

Python 3.12+ and the standard library are sufficient:

```sh
python -m tools.m1_retained_identity
python -m tools.m1_retained_identity /tmp/dayflare-real-baseline
python -m tools.m1_retained_identity --check /tmp/dayflare-real-baseline
python -m http.server 8000 --directory /tmp/dayflare-real-baseline
```

Open `http://localhost:8000/`. Choose a subject, open a record's source disclosure,
inspect the exact timestamp/ID/QID/hash and follow **Retained raw JSON response**.
A current Wikipedia/API link is explicitly distinct from the preserved response.
All content, coverage tables, source links and dated record anchors work without
JavaScript. The same path can be served beneath `/Dayflare/`.

The first screen discloses the actual observation date **4 November 2026**, request
interval and selected coverage. The source's older selection date is never used
as an observation date. Cards keep local IDs and observed/resolved mappings
separate; no EN/RU pair is silently declared equivalent.

## Reproducibility and source ownership

[evidence/m1-identity-20261104](../evidence/m1-identity-20261104/README.md) owns the
pinned original source-member bytes and retention provenance. The builder is a
small archive adapter/presentation layer over the existing `m1_identity_panel`,
`m1_source_verify` and `m1_bundle_verify` contracts; it does not replace them.
The downloadable panel is the original input schema, not a normalized output
with extra fields silently passed back to an input validator.

The generated directory contains 28 files: 24 original source files under
`source/`, `index.html`, retention provenance, recomputed verification and a build
manifest. The manifest hashes every other file and is written **last**. No build
timestamp or environment path enters the rendered bytes. Two builds from the
same reviewed source are byte-identical. `--check` validates inventory and bytes
without repair or writes. A missing, malformed, tampered or linked input fails
closed before touching the destination. New builds require a new destination;
concurrent writers cannot overwrite the winner. A partial I/O failure cannot
leave a complete manifest and is not a publishable result.

Archive limits: 256 KiB compressed, at most 104 members, 256 KiB per member and
1 MiB total decoded. This accepted capsule is only 15,547 bytes / 24 members /
45,118 decoded bytes. Paths are allowlisted before writing into a private
verification scratch directory; traversal, duplicate names, symlinks, encryption,
unsupported compression and oversized content are rejected. Frozen source and
provenance hashes are independent code pins, not approval inferred from an
archive's own assertions. They do not authenticate upstream origin.

## Acceptance commands

```sh
python -m unittest discover -s tests -p 'test_m1_retained_identity.py' -v
python -m compileall -q tools tests
# With compatible Playwright/Chromium installed:
python tests/m1/browser_retained_identity.py
```

The existing read-only M1 workflow runs these checks without new source requests.
Real-data artifacts and screenshots have separate `m1-real-baseline-*` names,
not synthetic labels. Chromium uses normal local HTTP at a project subpath,
320/390/1280 widths, JS/no-JS, reduced motion, keyboard navigation, exact source
link bytes, 404 negative control and horizontal overflow assertions. Inspect the
actual screenshots before visual acceptance. Missing Chromium is NOT_RUN, and
local HTTP is never evidence of a publicly served GitHub Pages revision.

## Later comparison

Once a separately dated raw panel has been collected and accepted, the existing
[identity-history CLI](M1_IDENTITY_HISTORY.md) can consume this preview's
`source/panel.json` as the earlier input. Preserve independent raw-source evidence
for both dates. A second run on the **same** UTC date is not the requested second
date. Never backdate, stitch by title/QID, reconstruct unavailable responses, infer
a deletion from absence or claim that two observations prove continuity between
them. #145 remains open until its complete pair and browser acceptance is met.

No new scheduler, provider, inference service, external asset, article-content
collection, repository setting or deployment is part of this feature.
