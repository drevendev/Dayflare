# Dayflare

Explore how attention changes in English and Russian Wikipedia, with inspectable
counts, dated comparisons and explicit limits rather than an opaque popularity score.

**Public atlas URL (activation pending):** [Open Dayflare](https://drevendev.github.io/Dayflare/) · [inspect the ready `gh-pages` release](https://github.com/drevendev/Dayflare/tree/gh-pages) · [Pages settings](https://github.com/drevendev/Dayflare/settings/pages).

**Not yet live-verified (27 October 2026):** GitHub reports `has_pages=false`.
The ready static release is committed to `gh-pages` with root `index.html`,
`.nojekyll` and a versioned manifest. A repository admin/maintainer must select
**Settings → Pages → Build and deployment → Deploy from a branch → `gh-pages` → `/(root)` → Save**.
The URL above is the expected address, **not a claim that the website currently serves**.
After activation, verify the public HTTP response, release manifest and actual desktop/mobile journey before marking it live.

## Try the guided current-stage demo

The [working prototype story in the site's first screen](site/index.html) uses two
**real archived** examples from the 20-title EN/RU dataset to demonstrate the
whole visitor journey. Serve the repository (not `file://`) with
`python -m http.server 8000`, then visit
`http://localhost:8000/site/#prototype`. The October Basketball (EN) and
Шахматы (RU) cards show five exact, dated weekly totals and baseline changes,
with working links into the 35-day tables, the subject explorer, comparison
controls and dataset-bound sharing. Both are selected examples, **not** a
popularity ranking or a claim about what caused their changes.

The corresponding versioned 20-title dataset was observed **19 September–23
October 2026 UTC**, retrieved **26 October 2026**. Current numeric page IDs do
not prove historic ID continuity. The static release is already prepared in
[`gh-pages/(root)`](https://github.com/drevendev/Dayflare/tree/gh-pages), but
its **public hosting is not yet enabled or verified**. Follow the branch-source
Pages activation instructions above; the historical data is not a live feed.

## Website: historical atlas

[Open expected public Pages URL](https://drevendev.github.io/Dayflare/) · [Inspect the release branch](https://github.com/drevendev/Dayflare/tree/gh-pages) · [Inspect the visitor interface source](site/index.html) · [Reproduce and check the release](site/README.md).

**Publication is pending configuration**, not a missing HTML build. At the
27 October 2026 readback the GitHub repository still reports `has_pages=false`,
while `gh-pages` contains the complete prebuilt static atlas. The selected
publication mode is **Deploy from a branch → `gh-pages` → `/(root)`**. A push
permission cannot change this administrator-controlled setting. Until GitHub
serves the expected URL and its manifest/assets pass independent HTTP/browser
checks, the link is a **target address only**, not a verified live deployment.

On the landing screen, **20 measured EN/RU title histories** across five subject
areas (19 September–23 October 2026) are the primary discovery path, with **700 exact
daily counts** and source evidence. The **earlier Chess (EN)** spotlight demonstrates
the original six-series method: 19,804 requests in its final September week versus
a four-week median of 18,369.5 (+7.8%). Both are archived editorial selections,
**not** a live popularity feed or verified historical page-ID continuity.

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

## Run the historical atlas locally

The M0 interface supports discovery, exact daily history, dated comparison,
version-bound sharing, source evidence and explicit stale/error/incompatible states.
It includes exact-value tables without JavaScript. **There is no verified public
site, live refresh or validated lifecycle classification.**

From the repository root with Python 3.12 or newer:

```sh
python -m tools.verify_d02_artifacts --retained evidence/d02-20261018
python -m http.server 8000
# Visit http://localhost:8000/site/ in a browser.
```

The verifier is standard-library only: it checks the two retained JSON members and
recomputes all six comparisons without network access, extraction or input changes.
The [source record](evidence/d02-20261018/provenance.json) distinguishes the original
Actions artifact from the deterministic data-only repack. See [site/README.md](site/README.md)
for the visitor journey and exact method limits.

## Observed 20-ID EN/RU identity atlas (not pageviews)

The [24 October 2026 observed identity atlas](site/identities-m1-20261024.html)
provides five subject areas, 20 real current-page numeric IDs in English and Russian
Wikipedia, observed QIDs, exact request times and retained response hashes, along
with original article links and accessible expandable source evidence. Editorial
cross-edition pairs are **not verified equivalent**; Cinema and Football pairs
have different observed QIDs. This is separate from the six-series historical
pageviews and the fictional M1 lab. The source is a [versioned JSON
projection](site/identities-m1-20261024.json) of the
[read-only Wikimedia Actions acquisition](https://github.com/drevendev/Dayflare/actions/runs/40129874259).
The original raw response ZIP is **not** committed or included in Pages assets.
Retained hashes demonstrate internal agreement, not independent source origin.
The observed dataset is archived, editorially selected and not live,
representative, or a measured attention trend.

Search the archived 20-ID page interactively by observed title, numeric ID or QID; optional JavaScript adds EN/RU filters, exact result counts, empty/reset states and restorable `?q=...&edition=ru` links. The visitor-triggered **Copy filtered link** action preserves the dated page and active search/edition filters while discarding unrelated query parameters; when clipboard access is unavailable it displays a keyboard-selectable URL. Local HTTP/file previews explicitly do **not** claim a publicly shareable address. With JavaScript off all 20 evidence cards remain visible. Filters do **not** turn identity metadata into historical attention measurements.

Use the same local HTTP server and visit
`http://localhost:8000/site/identities-m1-20261024.html`.

The observed Chess IDs (`en.wikipedia:5134` and `ru.wikipedia:10646`) now link to
**separate**, version-bound historical **title-scoped** Chess/Шахматы data and an
exact EN/RU comparison. Those 35-day requests cover 11 August–14 September 2026
(retrieved 18 October); the numeric IDs were observed 24 October. These are
**not** histories verified for those stable IDs, and no move/redirect continuity
is inferred. Links are visible without JavaScript; the historical page offers
no-JS exact tables. This is not a population comparison or a new live fetch.
Run `python -m unittest tests.test_m1_observed_panel -v` to test the
bounded source contract and static release inventory. Pages remains
**not live-verified**; no public deployment is claimed.

## More measured culture and game histories (archived, separate dataset)

[Culture and games — 140 exact daily counts](site/m1-cross-subject-20261025.html) adds four editor-selected EN/RU title-scoped series (Cinema/Кинематограф and Video game/Компьютерная игра) for the **same 11 Aug–14 Sep 2026 observation window**, retrieved **25 Oct 2026**. It is a separate versioned JSON/static-HTML projection of verified [PR #43 acquisition](https://github.com/drevendev/Dayflare/pull/43), **not** a rewrite of the six-series D02 capsule, live refresh or historical proof for October page IDs. Each series has exact 35-day tables, five weekly totals, computed median/delta, source endpoint and raw-body SHA-256. The two dated subject sections also have no-JavaScript, keyboard-accessible EN/RU comparison tables with exact request counts, independent baseline changes and stable same-snapshot permalinks; they do not assert entity equivalence. Original raw HTTP bodies were retained by the time-limited Actions artifact, **not committed** with this projection. EN/RU editorial comparisons are not verified same-entity mappings or national populations.

From the same local server visit `http://localhost:8000/site/m1-cross-subject-20261025.html` and run `python -m unittest tests.test_m1_cross_subject_static -v`. Published Pages/served revision remain unverified.

## 20 measured title histories across five subject areas (archived)

The [measured 20-title atlas](site/m1-curated-20261023.html) includes **700 exact
daily Wikimedia pageview counts** (20 × 35 UTC days, **19 September–23 October
2026**) across culture, books, games, science and sport in EN/RU. It gives
subject discovery, five weekly values and baseline-relative changes, 35-day
source tables, and stable dated-topic links. The [versioned, source-bound JSON](site/m1-curated-20261023.json)
contains the per-response hashes and source endpoint for each title. Retrieved
**26 October 2026**; this snapshot is archived, **not a live refresh**.
The [Actions source acquisition](https://github.com/drevendev/Dayflare/actions/runs/40254961414)
retained the 20 original HTTP responses in a temporary artifact (scheduled
expiry 2 November 2026), independently replayed against all 700 values. The
canonical projection pins the collected candidate SHA-256
`d96477427ece441302b11485f56a79703f77615b4a2b8cc98b4afaec078fc091`
and independently checked response/body receipts. The original raw HTTP
bodies are **not** in the repository; an internal checksum does not prove
provider authenticity.

Historical requests are **title-scoped**, not proven histories of the numeric
page IDs separately observed on 24 October. Editorial EN/RU pairs may not be
the same entity; neither edition measures a country's population. These selected
titles are not representative, and the counts are requests, not unique people.
No lifecycle classification or causation is inferred.

Serve the repo as above and visit
`http://localhost:8000/site/m1-curated-20261023.html`.
Re-check with `python -m unittest tests.test_m1_curated_static -v`.
On the measured 20-title page, optional JavaScript provides real title/observed-ID search,
subject and EN/RU filters, exact visible result counts, empty/reset feedback and a
**version-bound Copy filtered link** with a keyboard-selectable fallback on local
or clipboard-restricted previews. The URL pins dataset `m1-curated-20261023-d96477427ece`;
incompatible dataset/filter links show an explicit recovery path rather than
silently substituting newer data. All 700 exact daily values remain available
without JavaScript. Test state logic with `node tests/js_curated_explorer.cjs`.
The same page now provides an optional pairwise comparison of any two of those 20
archived title histories: exactly equivalent 35 UTC days, five weekly totals and
35 exact paired daily counts. Dataset-bound copied links preserve comparison IDs and
filters, while unknown IDs or incompatible windows fail closed; no-JS cards still
show the full original evidence. This does not establish Wikidata equivalence,
identity continuity, national interest or a live refresh.
The published Pages site remains unverified and must not be called live.

## Optional identity laboratory — synthetic, not popularity

The separate [M1 preview](docs/M1_PREVIEW.md) explores stable page IDs, dated titles,
redirect edges and uncertain Wikidata mapping. Filter EN/RU and subjects, inspect
identity traces and restore a version-bound link. Missing coverage says **Not included**,
not zero interest. The examples are prominently fictional; they add no real coverage.

```sh
python -m tools.m1_build_preview --check
# With the same local server, visit http://localhost:8000/site/m1-preview/
```

The [M1 evidence tools](docs/M1_IDENTITY_PANEL.md) validate identity panels, perform
bounded one-shot metadata collection from vetted IDs, and independently check
retained decoded JSON, manifests, chronology and coverage. Collection reports
separate wire, decoded and retained bytes. Checksums prove internal agreement,
not authentic provider origin. Never use the fictional example seeds for live calls.
The M1 preview is excluded from the main real-data M0 release candidate.

## Test and build

The complete offline suite uses pinned **test-only** HTML/CSS parsers; product
runtime and evidence tooling remain standard-library Python and static assets.
Node.js runs the separate no-network JavaScript interaction contracts.

```sh
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q tools tests
node tests/js_m1_share.cjs
python -m tools.m1_build_preview --check
python -m tools.run_m0_ci --python-only
python -m tools.build_static_release
```

The last command creates a self-contained Pages **candidate**, not a deployment.
The [offline workflow](.github/workflows/pr-validation.yml) checks exact proposed
heads on Python 3.12/3.13. The [M0 workflow](.github/workflows/m0-preview-validation.yml)
retains the four controlled-DOM Chromium shards and adds separate native localhost HTTP browser acceptance of the release under `/Dayflare/`, with exact-source desktop/mobile screenshot artifacts awaiting visual inspection. This does not verify public Pages. The separate
[M1 workflow](.github/workflows/m1-validation.yml) performs ordinary local HTTP
navigation and retains synthetic screenshots for later inspection. All are read-only,
without live collection or publishing. A test definition is not a passing run;
controlled DOM, actual HTTP, inspected screenshots and a live site are distinct.

## Existing collection and measurement limits

The [D02 collector](https://github.com/drevendev/Dayflare/pull/6) uses the fixed
historical window on a runtime with Wikimedia access:

```sh
python -m tools.d02_probe
python -m tools.verify_d02_artifacts
```

Read `artifacts/d02/receipt.json` and `artifacts/d02/sample.json`. Run the collector
as a module, not `python tools/d02_probe.py`; failed commands are not valid datasets.
[Execution details](research/D02_RUNTIME_PROBE.md) cover six sequential requests,
30-second request timeouts, a five-minute job budget and seven-day Actions retention.
The checked-in capsule does not expire with that artifact. D02 rejects over-budget
or incomplete responses and inexact/nonfinite calculations rather than publishing
false complete hashes or metrics. Its [runtime workflow](.github/workflows/d02-runtime-probe.yml)
is separate and does not deploy a website.

Volume, absolute change and baseline-relative change are distinct. Relative change
is unavailable for a zero baseline; incomplete windows are not comparable. No
validated rising/returning/fading classifications are published. `agent=user` is
not verified human traffic; attention is not importance, approval, truth or causation.
Compare Wikipedia editions, not countries or populations. Top-N absence is not zero.

The historical capsule has no stable page-ID observations and retains reported raw
HTTP hashes, not raw response bodies. It cannot prove cross-snapshot identity continuity
or independently rehash upstream bodies. The [D03 contract](research/D03_IDENTITY_MODEL.md)
remains binding: no title-only stitching, silent redirect aggregation or invented mapping.
Wikimedia Analytics API data is CC0; article text and images are not included or relicensed.

## Next public milestone

The [single roadmap](control/STATE_AND_QUEUE.md) and
[bounded D08 decision](research/D08_DESCRIPTIVE_DELIVERY.md) separate engineering
readiness from release acceptance. Source delivery is not completion of all research.
Next: publication safety [#7](https://github.com/drevendev/Dayflare/issues/7),
actual HTTP/mobile/visual acceptance [#21](https://github.com/drevendev/Dayflare/issues/21)
and verified Pages publication [#12](https://github.com/drevendev/Dayflare/issues/12).
[Rolling refresh #13](https://github.com/drevendev/Dayflare/issues/13) must preserve
shared versions and the last valid publication. [Real identity #19](https://github.com/drevendev/Dayflare/issues/19)
and [broader coverage #14](https://github.com/drevendev/Dayflare/issues/14) require
actual cross-subject evidence, not synthetic fixtures. The expected Pages URL
above is linked for discoverability but explicitly remains unverified.

[Product anchor](https://github.com/drevendev/Dayflare/issues/1) ·
[Research registry](research/REGISTRY.md) · [Source register](research/SOURCES.md) ·
[Project manifest](control/PROJECT_MANIFEST.md)
