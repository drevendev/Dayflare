# Dayflare

Explore how attention changes in English and Russian Wikipedia — with inspectable
counts, dated comparisons and explicit limits, not an opaque popularity score.

## What works today

The repository contains a standard-library Python collector and measurement tests.
The merged [D02 implementation](https://github.com/drevendev/Dayflare/pull/6) retrieves
six preselected EN/RU series across science/technology, books and chess for the fixed
historical window **11 August–14 September 2026**: 35 UTC days and 210 requested daily
observations. Source receipts record filters, request status, coverage and checksums.

The interactive atlas is **not yet merged into this repository**. There is no verified
public website. Its evidence pipeline, visitor interface and release presentation are
tracked in [#7](https://github.com/drevendev/Dayflare/issues/7),
[#8](https://github.com/drevendev/Dayflare/issues/8) and
[#9](https://github.com/drevendev/Dayflare/issues/9). Local preview archives are not a
substitute for reviewed source delivery or a public release.

## Run the available software

Use Python 3.12 or newer, from the repository root. No third-party Python dependency
is needed. Tests use controlled fixtures and require no Wikimedia access:

```sh
python -m unittest discover -s tests -p 'test_d0*.py' -v
python -m compileall -q tools tests
```

Collect the fixed historical sample on a runtime with network access to Wikimedia:

```sh
python -m tools.d02_probe
```

Read `artifacts/d02/receipt.json` for success/failure and coverage, and
`artifacts/d02/sample.json` for validated values. An unavailable request is not an
empty successful dataset. Rerunning the collector updates retrieval time, **not** the
observation window. Do not invoke the file directly as `python tools/d02_probe.py`.

The [D02 workflow](.github/workflows/d02-runtime-probe.yml) runs tests before the
bounded collector and retains evidence artifacts for seven days. It does not deploy
a site. Full commands, validation rules and runtime limits are in the
[D02 probe documentation](research/D02_RUNTIME_PROBE.md).

## How to read a measured change

The last observed seven-day total is compared with the median of four preceding
complete seven-day totals. Volume, absolute change and baseline-relative change are
separate values; relative change is unavailable when the baseline is zero. Missing
windows must not silently become zero. These descriptive values do not establish
that a topic is rising, returning or fading under a validated lifecycle model.

The six series are a small, selected experiment — not representative Wikipedia
coverage, the whole internet, countries or unique readers. `agent=user` does not prove
that requests came from humans. Attention is not importance, approval or causation.
The accepted [identity model](research/D03_IDENTITY_MODEL.md) forbids title-only
stitching and preserves uncertain mappings and deletion/restore boundaries.

## Next public milestone

Deliver a validated, versioned snapshot with accessible discovery, topic history,
comparison and share restoration; then perform separate acceptance, merge, authorized
publication and served-revision checks. The intended delivery path is:

```text
scheduled CI -> collect -> validate -> calculate -> versioned artifacts -> GitHub Pages
```

The [compact roadmap](control/STATE_AND_QUEUE.md) prioritizes finishing #7–#9 rather
than repeating the already-merged 35-day probe. Wider topic coverage and validated
lifecycle signals follow the first usable public release.

[Product anchor](https://github.com/drevendev/Dayflare/issues/1) ·
[Research registry](research/REGISTRY.md) · [Source register](research/SOURCES.md) ·
[Project manifest](control/PROJECT_MANIFEST.md)
