# Dayflare

**See measurable change in English and Russian Wikipedia.** Explore a bounded, dated atlas of 20 selected titles across books, culture, games, science and sport. Compare complete weeks, inspect all 700 exact daily request counts and follow source evidence. This is **not** a live feed, a representative popularity ranking or a measure of people, importance or causes.

## Explore the newest retained observations (18 Nov 2026; local only)

**Newer real-source data, not a newly accepted public release:** The separately
retained [21 November source capsule](evidence/m1-20-20261121/README.md)
contains 20 editorially selected EN/RU Wikipedia title histories across five
subjects, **700 measured UTC daily request counts for 15 October–18 November
2026**, retrieved 21 November. Their original decoded JSON responses and receipts
are SHA-256 checked and replayed *before* the page is built. One command now
produces a standalone, accessible HTML atlas with a first-screen discovery
action, five-week graphs, per-title exact 35-day tables and evidence, and
dataset-bound comparison/share (the exact history still works without JavaScript):

```sh
mkdir -p artifacts
python -m tools.m1_20_local_atlas artifacts/dayflare-20-20261118
# Open artifacts/dayflare-20-20261118/index.html in your browser.
# Or serve locally: python -m http.server 8000 --directory artifacts
# Then browse http://localhost:8000/dayflare-20-20261118/
python -m unittest discover -s tests -p 'test_m1_20_local_atlas.py' -v
```

**Print / Save as PDF:** In modern browsers, the print-only layout expands
collapsed detail/evidence content *for printing* without opening it on screen,
including exact historical tables and source endpoints. Browser print includes
**all 20 selected titles and exact weekly rows even if on-screen filters have
hidden some results**; a print-only note identifies this full selected cohort.
After printing, on-screen discovery filters remain unchanged. The print layout
keeps observation/retrieval dates, links and exact values in a light, high-contrast
view. Older browsers without `::details-content` support should manually expand
the desired disclosures before printing. This is an offline evidence copy,
**not a live site or an independently accepted new release.**

A separate, **reviewable release-format candidate** can now be built from the
same pinned original responses. It is not a deployment and cannot overwrite the
accepted 11 November archive or any existing directory:

```sh
python -m tools.m1_20_release_candidate artifacts/dayflare-20-20261118-release
python -m unittest discover -s tests -p 'test_m1_20_release_candidate.py' -v
# Inspect artifacts/dayflare-20-20261118-release/index.html and release-manifest.json
# The manifest SHA-256 printed by this command is a local consistency receipt,
# NOT independent approval or proof that any public URL serves these bytes.
```

**Two different signed comparisons in each measured discovery card:** the
existing last full week minus the **median of the prior four complete weeks**
(baseline delta), and the new **latest vs immediately preceding full UTC week**
(short-term step). Both are exact request-count differences derived from the same
five dated weeks, not percentages, inferred causes, or validated rising/fading
classifications. Open the history for the five exact weekly totals and all 35
daily observations; the cards work without JavaScript.

**See short-term direction by subject (works without JavaScript):** The
selected-subject overview now displays a second, explicitly labeled count for
**Gain / Drop / No change** between the final two complete UTC weeks alongside
the existing four-week-median direction mix. Both rows count the same selected
titles, but their signs can disagree: a title may fall since last week while
remaining above its longer baseline. The colored bars still describe only the four-week-median comparison,
while the static, horizontally scrollable **exact subject table now has two
separately labelled groups of counts**: Median increase/decrease/no change and
Week gain/drop/no change. Without JavaScript, both remain available and preserve
the same selected-cohort counts. With JavaScript, `Download selected-subject
coverage CSV` now exports both distinct directions alongside the selected,
EN and RU counts and dataset/method/observation provenance. This is an additive
change to **that CSV's columns only** (three new `week_*` columns), not to the
measurement method or other exports. Before download the code rechecks all 35
daily values, the five exact UTC week totals, both signed counts and each
displayed week-step; altered source, card or table values fail closed. This is
bounded selected-title coverage, not a Wikipedia-wide subject ranking or a
validated trend classification.

**Sort by latest weekly movement (optional JavaScript):** The discovery filter
now offers `Week-to-week gain` and `Week-to-week drop`. These order the
editor-selected titles by the signed, **last complete UTC week minus immediately
preceding complete UTC week** request count, independently of the four-week
median-based `Increase`/`Decrease` and `Relative rise/fall` modes. Both
the source-derived exact weekly table and downloadable visible weekly CSV follow
the same stable order; links restore the sort only for the matching dataset.
Tied changes retain editorial selection order. No-JavaScript reading retains the
original order and all exact observations. Sorting is **not** a Wikipedia-wide
ranking, a trend classification, a percentage or evidence of a cause.

**Filter by recent week-to-week direction (JavaScript only):** Use the new
`Latest vs prior UTC week` selector for **Gain / Drop / No change** measured
between the final two complete UTC weeks. It is separate from the existing
`Exact weekly change (vs four-week median)` direction selector. Combining
them shows only titles meeting **both** exact signed conditions; a title can
gain week-on-week while remaining below its four-week median. Visible cards,
exact weekly comparison and CSV remain aligned; the dataset-specific
`af_step` share parameter restores the selection and fails closed on
unknown/duplicate values. Older dataset-bound links default to all steps.
Without JavaScript all selected histories, tables and evidence remain readable.
Printing still includes the full selected cohort regardless of filters.
Neither direction is a validated trend classification or evidence of a cause.

**Export exact recent movement for any filtered selection (JavaScript only):**
Use `Download visible weekly changes CSV` alongside the unchanged weekly and
daily exports. Each visible, sorted title contributes five dated UTC-week rows
with its exact weekly request total and its own signed difference from the
preceding week; the oldest week has a **blank unavailable change**, not zero.
The export uses the same source-reconciled 35-day evidence as the cards, is
bound to the dataset/method/window and refuses incomplete, altered, duplicate
or mismatched histories rather than silently exporting wrong comparisons.
All four weekly CSV paths (visible totals, selected-pair totals, visible weekly
changes, selected-pair weekly changes) also verify that every dated column
covers the expected **seven consecutive UTC days**, ending on the recorded
observation date; shifted, repeated or reordered week dates fail closed
rather than generating misleading CSV headings. This does not refresh data.
Filtering to zero results disables the button. Titles are observations, **not**
automatically matched cross-edition topics; the values are requests rather than
people or causal trend labels. With JavaScript disabled the original exact
tables remain readable, but CSV buttons are unavailable.

The new directory contains exactly `index.html`, `.nojekyll` and an immutable
`release-manifest.json`, with the precise original observation/retrieval
dates, 20/700 coverage, method version and source/HTML SHA-256 values.
It replays and checks the source and only replaces the three reviewed
local-only presentation labels; numeric evidence and uncertainty disclosures
remain unchanged. To check a **later** candidate against an independently
accepted prior M1 release, pass `--previous-manifest /path/to/accepted/release-manifest.json`.
Rollback, method/cohort changes and same-revision collisions fail closed.
A later separate exact-head review, authorized Pages deployment and served-byte
browser verification remain required before calling this URL live.

A **read-only integrity check of an already extracted 18 November candidate**
is also available. Supply the manifest SHA-256 recorded *outside* the candidate
directory: the pin below belongs specifically to the
[earlier CI artifact #14720999879](https://github.com/drevendev/Dayflare/actions/runs/44941514028/artifacts/14720999879),
not to a freshly rebuilt candidate (whose HTML may legitimately differ).
Extract that known artifact into a separate, initially empty folder using a
safe ZIP extractor, then from the repository root run:

```sh
python -m tools.m1_20_release_candidate artifacts/m1-20261118-from-ci \
  --verify-manifest-sha256 a81fa95095a6c4de29eda2f0666ee50ecde9eb0b7e88bd9093380a4111bdb6fc
```

Verification never contacts Wikimedia, rebuilds, overwrites or publishes. It
requires POSIX file-descriptor/no-follow support and fails closed on unsupported
platforms; concurrent member/ancestor substitutions cannot redirect its reads.
It refuses missing/extra/linked/oversized files and incorrect source, manifest or
HTML hashes. A self-derived hash is **not independent approval**: this receipt
checks an existing archive against an externally supplied pin, but does **not**
grant a release decision, Pages deployment or LIVE_VERIFIED status.


Exact-head **Offline PR validation** retains a short-lived downloadable
`m1-20-20261118-local-*` artifact (HTML plus SHA-256 manifest),
separate from the original source capsule. This is **NOT PUBLISHED / NOT LIVE**,
not the independently accepted 11 November archive below, not a representative
Wikipedia-wide ranking and not proof of uninterrupted historical page-ID
continuity. Reported `agent=user` traffic is not verified unique people;
hashes do not independently authenticate provider origin. Earlier accepted
archives remain unchanged; public/browser acceptance is separately gated.

## Try the measured atlas — no Pages account required

The `site/index.html` first screen also offers five **Books / Culture / Games /
Science / Sport** shortcuts into the accepted 11 November EN/RU subject
examples. Each opens the existing dated evidence disclosure and works with
keyboard navigation or without JavaScript; no new topics, measurements or
identity equivalences are inferred. This local site is still **not a verified
public Pages deployment**.

**[Download the accepted M1 atlas (11 Nov 2026; pinned HTML)](https://raw.githubusercontent.com/drevendev/Dayflare/4851d6a7e106f02261b6e7a58226295ac94a664d/m1/index.html)** · [Browse its exact release files](https://github.com/drevendev/Dayflare/tree/4851d6a7e106f02261b6e7a58226295ac94a664d/m1) · [View dataset/method manifest](https://github.com/drevendev/Dayflare/blob/4851d6a7e106f02261b6e7a58226295ac94a664d/m1/release-manifest.json)

Save the downloadable file as `dayflare-m1.html` and open it locally. The archive contains its own CSS, 35-day zero-origin SVG timelines with independent per-title scales, 20 EN/RU selected title histories, 700 daily request counts, filters, exact tables, comparisons, five exact CSV routes (single-title daily; paired daily, weekly and week-over-week changes; filtered visible-title daily), and sharing controls. The SVG timelines and exact historical tables remain readable with JavaScript disabled. Chart heights between different titles are not directly comparable. The current accepted archive puts **Explore 20 measured histories ↓** on the first screen; its link opens the actual `#overview` data cards (also with JavaScript disabled). Mobile-first discovery, **Relative rise (%)** / **Relative fall (%)** ordering and the keyboard-accessible methodology disclosure remain available. **This is a working offline archive, not a hosted live website.** For reproducible local URLs and link restoration:

```sh
curl -fL https://raw.githubusercontent.com/drevendev/Dayflare/4851d6a7e106f02261b6e7a58226295ac94a664d/m1/index.html -o dayflare-m1.html &&
printf '%s  %s\n' 4553257f5b16dd3a94d18fd19bea9b3289a670c85055ee231f6a2289f2a7d85f dayflare-m1.html | sha256sum --check &&
python -m http.server 8000
# Open http://localhost:8000/dayflare-m1.html
```

**One-command verified offline download (fixed accepted release):** Instead of trusting a mutable branch download, use the independently owner-reviewed manifest SHA-256 from [release PR #249](https://github.com/drevendev/Dayflare/pull/249) and the exact merged release commit. This checks the release manifest, dataset, complete UTC window and HTML bytes *before* writing a new file:


```sh
python -m tools.m1_pinned_offline_download \
  --commit 4851d6a7e106f02261b6e7a58226295ac94a664d \
  --expected-manifest-sha256 ec762b408be5bb35266b73421fbeed8104380a48cb938e01449de91b83e49198 \
  --expected-dataset-id run-20261114-163048-a32c03ef7daa \
  --expected-observation-end 2026-11-11 \
  --destination dayflare-m1-2026-11-11.html
```

Open the resulting HTML offline, or serve its directory locally with `python -m http.server 8000` for reproducible share URLs. Choose a new output file under an existing real directory. On POSIX systems with `dir_fd` and `O_NOFOLLOW`, each output-directory component is opened without following symlinks and the final file is created relative to the held directory descriptor, including if a pathname changes during download. Other platforms (including Windows) currently fail closed rather than silently falling back to an unsafe path-based create. If a directory is moved concurrently, the file is bound to the original directory identity, not a replacement path. Existing files are never overwritten; network failures or mismatches leave them untouched. Use a **new independently accepted pin and commit** for later releases. This verifies the downloaded bytes, **not** Pages deployment, original provider authentication, or browser acceptance.

<!-- dayflare:m1-release:start -->
**Latest accepted archive (observed 2026-10-08–2026-11-11 UTC; retrieved 2026-11-14 16:30:48 UTC):** 20 editor-selected title-scoped EN/RU histories across books, culture, games, science and sport; five complete UTC weeks / 700 daily request observations. Dataset `run-20261114-163048-a32c03ef7daa`, method `v0-empirical-35d`, schema `dayflare.m1.static-snapshot.v1`. [Accepted release manifest](https://github.com/drevendev/Dayflare/blob/gh-pages/m1/release-manifest.json) pins the downloadable HTML SHA-256 `4553257f5b16dd3a94d18fd19bea9b3289a670c85055ee231f6a2289f2a7d85f`; verify with `sha256sum dayflare-m1.html`. The manifest pin must be independently established by native release review; this generated summary alone does not authenticate Wikimedia, approve a release or prove Pages is live. Counts are requests, **not** people, causes, verified page-ID histories or cross-edition equivalences. This selected, dated sample is **not** a representative ranking, live refresh or verified deployed website.
<!-- dayflare:m1-release:end -->

**Release-facts synchronization (offline, after independent release acceptance):** Export the exact accepted `gh-pages` tree into a clean directory (not a mutable checkout); take the **manifest SHA-256 from the approved native release PR/checks**, not from that directory. **Current accepted example (observed 2026-11-11 UTC):** [PR #249](https://github.com/drevendev/Dayflare/pull/249) independently approved manifest SHA-256 `ec762b408be5bb35266b73421fbeed8104380a48cb938e01449de91b83e49198`. These example commands apply to this exact accepted archive; use the corresponding native-review pin for any later release. Then, from the repository root:

```sh
mkdir -p /tmp/dayflare-reviewed-pages
git archive gh-pages | tar -xf - -C /tmp/dayflare-reviewed-pages
python -m tools.m1_readme_sync --accepted-m1 /tmp/dayflare-reviewed-pages/m1 --expected-manifest-sha256 ec762b408be5bb35266b73421fbeed8104380a48cb938e01449de91b83e49198
# The default command is a read-only check. After separately reviewing the accepted release:
python -m tools.m1_readme_sync --accepted-m1 /tmp/dayflare-reviewed-pages/m1 --expected-manifest-sha256 ec762b408be5bb35266b73421fbeed8104380a48cb938e01449de91b83e49198 --write
```

**Historical acceptance evidence for the 6 November 2026 archive only:** [PR #195](https://github.com/drevendev/Dayflare/pull/195) passed [exact-source and local-HTTP Chromium acceptance](https://github.com/drevendev/Dayflare/actions/runs/42568487642), including mobile, keyboard, sharing, CSV and error states. Its accepted publication-branch merge commit is [b03f7f5e](https://github.com/drevendev/Dayflare/commit/b03f7f5e7639452df97bb840764a54301b766713). This receipt is **not** approval of any later release and does **not** establish that the public Pages URL is serving it.

For any later accepted release use its **own** independently reviewed manifest pin; the 11 November digest in the commands above is a dated example, not a perpetual allowlist. The historical 6 November evidence above remains valid only for that earlier archive. The synchronizer verifies the canonical release manifest, complete-window chronology and exact HTML SHA, then changes only the marker-bound README facts. Wrong pins, incompatible metrics, changed HTML, ambiguous markers, and attempts to roll back an already documented observation/retrieval revision leave the README untouched. This is documentation synchronization, **not** source acquisition, release approval or deployment.


### Earlier accepted release example (1 November snapshot; not current)

During **23–29 October 2026 UTC**, the selected English Wikipedia *Basketball* title received **45,166 requests**. The four preceding complete weeks recorded **14,884**, **14,899**, **14,068** and **14,955** requests; their median was **14,891.5**. The measured change is **+30,274.5 requests (≈+203.3%)**. In the [older 1 November release](https://github.com/drevendev/Dayflare/blob/4bbc895b647e9c17a0fae00863c1692979a1a214/m1/index.html), open the Basketball card to inspect all 35 exact daily values, weekly chart, source endpoint and version-bound detail (download the HTML first as described above). This example is from a **different, earlier dataset** than the current download. It is an editor-selected, title-scoped observation, **not** evidence of why attention changed, uniquely counted readers or a validated lifecycle classification.


## Inspect the expanded 30-title atlas (unpublished, offline)

The separately preserved **30 EN/RU title histories / 1,050 exact daily counts**
cover 2026-10-11–2026-11-14 UTC. This is an editorially selected historical
candidate, **not** the independently accepted 20-title release above, not a
ranking of Wikipedia as a whole, and not a hosted site. The original
[successful source and Chromium run](https://github.com/drevendev/Dayflare/actions/runs/44046865069)
retains its [Actions artifact](https://github.com/drevendev/Dayflare/actions/runs/44046865069/artifacts/14312401439)
only until **2026-12-17**; preserve it before expiry. An offline reader can be
reproduced without publishing or contacting Wikimedia:

```sh
# First download the original Actions ZIP as original.zip.
printf '%s  %s\n' \
  86133de1ed074266b172c1aa682a4cdbbaa01b3799061e78d9f9acb37d00032d original.zip | sha256sum --check
python -m tools.m1_30_archive original.zip preserved.zip
python -m tools.m1_30_consume preserved.zip \
  --expected-sha256 0473e8b52f90df70c227e648a06bbae1e833740844dff77f8c28ef1e32e2b0c4 \
  --html-out dayflare-30-verified.html
# Open dayflare-30-verified.html; exact values/tables work without JavaScript.
```

**Git-retained raw Pageviews bodies (30-title snapshot, still unpublished):**
The original 30 decoded Wikimedia API response bodies **and exact original source receipt**
are now included as [checksum-verified offline archives](docs/M1_30_PRESERVATION.md#git-retained-original-decoded-pageviews-bodies).
Run `python -m tools.m1_30_raw_archive --output /tmp/dayflare-new-raw-30 --include-receipt`
to restore the 30 exact original JSON bodies **and byte-identical original source receipt** into a new directory. Omit `--include-receipt` for the previous 30-body behavior. The larger original
148-file Actions source/browser bundle is **not** yet durably retained and still
expires 2026-12-17; this source-only backup is not a Pages deployment.

**Independent normalized-data route (does not need the expiring Actions ZIP):**
The repository also retains the exact 30-title candidate JSON. Build a smaller
self-contained, searchable EN/RU offline atlas with 35-day evidence tables,
measured weekly changes, two-title comparison/share restoration, and two native no-JavaScript cohort downloads: the 30-title exact five-week comparison CSV and the full 1,050-observation daily CSV (with dataset/method keys; per-article source receipts remain in the companion weekly CSV and evidence cards):

```sh
python -m unittest tests.test_m1_30_retained_candidate tests.test_m1_30_reader -v
python -m tools.m1_30_reader --output dayflare-30-retained.html
# Open the new HTML locally. Existing destinations are not overwritten.
```

This [retained-candidate reader](docs/M1_30_OFFLINE_READER.md) is **UNPUBLISHED**;
it cannot replace the original raw HTTP/browser archive or establish a live site.
It preserves request counts and cited source hashes, not independent origin proof.

The SHA-256 pin applies only to this exact archived run, as documented in
[30-title preservation instructions](docs/M1_30_PRESERVATION.md).
A successful local verification is **not** an external Wikimedia-origin audit,
an approved 30-title public release or proof of GitHub Pages deployment.

## Explore the real 4–5 November identity comparison (accepted, offline)

**Twenty selected EN/RU Wikipedia numeric page IDs were independently observed on 4 and 5 November 2026 UTC.** The [retained real-source comparison](evidence/m1-identity-20261105/README.md) reconstructs the actual responses, verifies 24 source members and produces a keyboard-accessible, no-JavaScript before/after report. **All 20 had unchanged observed titles, QIDs and redirects**; no uninterrupted identity, new pageview measurements or causes are inferred. [PR #151](https://github.com/drevendev/Dayflare/pull/151) merged the evidence and browser checks; [#145](https://github.com/drevendev/Dayflare/issues/145) is closed.

From a checkout with Python 3.12+, build the real report into a fresh directory, then open its `index.html` locally. The HTML links to the accompanying exact `history.json`, so keep the files together:

```sh
python -m tools.m1_real_pair /tmp/dayflare-real-identity-history
# Open /tmp/dayflare-real-identity-history/index.html in a browser.
```

For a single downloadable offline package, the existing read-only M1 acceptance workflow additionally retains a deterministic ZIP of the same three report files for seven days. Reproduce it from the retained sources without fetching Wikipedia:

```sh
python -m tools.m1_real_pair --zip /tmp/dayflare-identity-20261104-20261105.zip
# Extract the ZIP and open index.html beside history.json and manifest.json.
```

The ZIP is **BUILT, not DEPLOYED or LIVE_VERIFIED**. The measured M1 atlas above contains historical *title-scoped page requests*, not joined stable-ID histories.

## Inspect the retained 4 November identity baseline

The [real identity explorer](docs/M1_RETAINED_IDENTITY.md) presents **20 selected
EN/RU page IDs across five subjects**, with exact request times, observed QIDs,
coverage and locally preserved raw JSON evidence. Unlike the older October
projection, this [baseline source capsule](evidence/m1-identity-20261104/README.md)
is committed and can be replayed after the original CI artifact expires.
It is **one historical metadata snapshot**, not pageviews. Its accepted 5 November follow-up and two-date comparison are linked above.

```sh
python -m tools.m1_retained_identity /tmp/dayflare-real-baseline
python -m tools.m1_retained_identity --check /tmp/dayflare-real-baseline
python -m http.server 8000 --directory /tmp/dayflare-real-baseline
# Open http://localhost:8000/ and inspect a record's retained source evidence.
```

The subject index, exact coverage table, dated record links and source disclosures
work without JavaScript. Observed QIDs are not resolved equivalences. The
[accepted 5 November source capsule](evidence/m1-identity-20261105/README.md)
now powers the two-date report above. No public Pages URL, continuous identity
or new attention measurements are implied.

## Public hosting — not yet enabled or live-verified

**Not live-verified (15 November 2026):** The accepted static files are committed to `gh-pages`, including root `index.html` and `m1/index.html`, but a branch commit and successful browser CI do not prove that GitHub Pages is serving them. Public HTTP access could not be confirmed from the available reader on 15 November 2026; this is **not evidence of an HTTP response status**. A historical repository API read on 9 November reported `has_pages=false`; no current Pages provisioning state or HTTP response is inferred from that older receipt. The **expected** address is `https://drevendev.github.io/Dayflare/` (not a working link until verified).

**Public atlas URL (activation pending):** repository [Pages settings](https://github.com/drevendev/Dayflare/settings/pages) require an authorized administrator to select **Deploy from a branch → `gh-pages` → `/(root)`** and Save. The connected delivery account has repository write access but no admin permission. After activation, verify public HTTP bytes, release/dataset/method versions and actual desktop/mobile/keyboard behavior before labeling the URL live. The current available route is the downloadable HTML above.

## Try the guided current-stage demo

The [repository's historical landing page](site/index.html) shows real, dated Basketball (EN) and Шахматы (RU) examples with five exact weekly totals. To explore the older preview and its deep links, run `python -m http.server 8000` from the repository root, then visit `http://localhost:8000/site/#prototype`. That guided prototype uses a **different, older** 19 September–23 October dataset (retrieved 26 October), not a live feed. Compare the full histories and share only version-bound links; separate historical title scopes do not prove the same cross-language entity or stable page IDs.

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
navigation and retains separately labelled synthetic and real-baseline screenshots
for later inspection. All are read-only,
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
The bounded publication-safety pipeline [#7](https://github.com/drevendev/Dayflare/issues/7)
is delivered. Next: verified Pages publication [#12](https://github.com/drevendev/Dayflare/issues/12)
and the real second-date comparison [#145](https://github.com/drevendev/Dayflare/issues/145),
with exact HTTP/mobile/visual acceptance rather than a deployment inferred from CI.
[Rolling refresh #13](https://github.com/drevendev/Dayflare/issues/13) must preserve
shared versions and the last valid publication. [Real identity #19](https://github.com/drevendev/Dayflare/issues/19)
and [broader coverage #14](https://github.com/drevendev/Dayflare/issues/14) require
actual cross-subject evidence, not synthetic fixtures. The expected Pages URL
above is linked for discoverability but explicitly remains unverified.

[Product anchor](https://github.com/drevendev/Dayflare/issues/1) ·
[Research registry](research/REGISTRY.md) · [Source register](research/SOURCES.md) ·
[Project manifest](control/PROJECT_MANIFEST.md)

### Revisit the **same page IDs** on a later UTC date

The reviewed 4 November 2026 baseline can be safely followed up without
rediscovering titles: `python -m tools.m1_identity_followup /tmp/dayflare-next-identity`
(after 4 November **UTC**). It preserves each original numeric ID, gathers a
separate bounded source bundle, and generates a local no-JavaScript before/after
report under `history/`. See the [exact follow-up workflow](docs/M1_IDENTITY_FOLLOWUP.md).
This does **not** run automatically, constitute a second observation until a real
later-day collection succeeds, or publish a Pages site.
