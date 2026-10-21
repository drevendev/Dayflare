# Dayflare

Explore how attention changes in English and Russian Wikipedia, with inspectable
counts, dated comparisons and explicit limits rather than an opaque popularity score.

## Try a real historical example

For **Chess** in English Wikipedia, the week **8–14 September 2026** recorded
**19,804 pageviews**, compared with a baseline of **18,369.5**: **+1,434.5 views
(+7.81%)**. The baseline is the median of the four preceding complete weekly totals,
not simply the previous week. These are request counts, not unique readers or causes.

The [retained evidence](evidence/d02-20261018/README.md) contains all **210 daily
observations** for six preselected EN/RU series across science, books and chess,
covering **11 August–14 September 2026**. Retrieved **18 October 2026**; the later
retrieval does **not** make those observation dates current. The sample is selected,
historical and not representative Wikipedia coverage.

## Verify without network access

From the repository root with Python 3.12 or newer; no third-party package required:

```sh
python -m tools.verify_d02_artifacts --retained evidence/d02-20261018
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q tools tests
```

The first command reads the two checked-in JSON members in memory, verifies their
hashes and recomputes all six comparisons. It does not extract files, contact Wikimedia,
publish a site or modify inputs. The tests distinguish the actual historical fixture
from deliberately synthetic/mutated failure controls. The [source record](evidence/d02-20261018/provenance.json)
distinguishes the original Actions artifact from the deterministic data-only repack.

## Available software and limits

The [merged D02 collector](https://github.com/drevendev/Dayflare/pull/6) collects the
same fixed historical window on a runtime with Wikimedia access:

```sh
python -m tools.d02_probe
python -m tools.verify_d02_artifacts
```

Read `artifacts/d02/receipt.json` and `artifacts/d02/sample.json`. A failed command is
not a valid dataset. Run the collector as a module, not `python tools/d02_probe.py`.
[Execution details](research/D02_RUNTIME_PROBE.md) explain the six sequential requests,
30-second request timeout, five-minute job budget and seven-day Actions retention.
The checked-in capsule does not expire with that Actions artifact.

D02 bounds successful/error bodies to 1 MiB plus a detection byte; oversized,
interrupted or inconsistent Content-Length responses do not receive a false complete
response hash. Inexact daily/weekly/median/delta values and non-finite results fail
explicitly. Source observations can survive a calculation error for investigation,
but metrics remain unavailable and the run unsuccessful.

The [all-PR offline workflow](.github/workflows/pr-validation.yml) checks exact heads
on Python 3.12/3.13, without live collection, retained credentials or write permissions.
Only actual checks establish hosted success. The [D02 runtime workflow](.github/workflows/d02-runtime-probe.yml)
is separate and does not deploy a website.

**The interactive atlas is not yet integrated and there is no verified public site.**
The remaining pipeline, visitor interface and scoped readiness are tracked in
[#7](https://github.com/drevendev/Dayflare/issues/7),
[#8](https://github.com/drevendev/Dayflare/issues/8) and
[#9](https://github.com/drevendev/Dayflare/issues/9). Local previews are not releases.

## Read the measurements responsibly

Volume, absolute change and baseline-relative change are distinct. Relative change
is unavailable for a zero baseline; incomplete windows are not comparable. No validated
rising/returning/fading classifications are published. `agent=user` is not verified
human traffic; attention is not importance, approval, truth or causation. Compare
Wikipedia editions, not countries or populations. Top-N absence is not zero.

The historical evidence has no stable page-ID observations and retains reported raw
HTTP hashes, not raw response bodies. It cannot prove cross-snapshot identity continuity
or independently rehash the upstream bodies. The [D03 identity contract](research/D03_IDENTITY_MODEL.md)
remains binding: no title-only stitching, silent redirect aggregation or invented mapping.
Wikimedia Analytics API data is CC0; article text and images are not included or relicensed.

## Next public milestone

The [single roadmap](control/STATE_AND_QUEUE.md) orders collector acceptance, retained
source adoption, the accessible M0 journey with browser CI, then
[verified publication #12](https://github.com/drevendev/Dayflare/issues/12).
[Rolling refresh #13](https://github.com/drevendev/Dayflare/issues/13) must preserve
version-bound shared views and the last valid publication;
[broader coverage #14](https://github.com/drevendev/Dayflare/issues/14) follows with
explicit identities and measured actual coverage. No live URL is advertised before verification.

[Product anchor](https://github.com/drevendev/Dayflare/issues/1) ·
[Research registry](research/REGISTRY.md) · [Source register](research/SOURCES.md) ·
[Project manifest](control/PROJECT_MANIFEST.md)
