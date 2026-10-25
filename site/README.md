# Dayflare M0: historical visitor interface

This is a static read-only visitor view of the **selected** six-series D02 sample.
`site/index.html` is source HTML, `site/styles.css` and `site/app.js` are the UI,
and `../evidence/d02-20261018/source.zip` is the single versioned measurement input.
Run an HTTP server from the repository root and open `/site/` to inspect it. The
site fetches only the retained local archive, not live Wikipedia or third-party assets.

The snapshot covers 11 August–14 September 2026 (35 UTC days, 210 observations),
retrieved 18 October 2026. It is historical, selected, and not representative.
The `agent=user` filter does not prove requests were made by people. Counts do not
measure truth, approval, causation or unique readers. Missing page IDs and raw HTTP
bodies preclude cross-snapshot identity continuity and independent upstream-body
verification. No rising/returning/fading label is validated; the visible comparison
uses the last seven-day total and median of four preceding complete weeks.

The separate dated 20-ID identity atlas (`identities-m1-20261024.html`)
includes version-bound deep links to all six selected historical title series:
Artificial intelligence / Искусственный интеллект (science), The Master and Margarita /
Мастер и Маргарита (books), and Chess / Шахматы (games). Only the Chess
titles also appear in the selected current-ID panel; no historic source proves
that the October-observed numeric IDs owned the August–September histories.
The other four measured titles have **no corresponding ID observation in that
20-ID panel**. Edition comparisons are of page requests, not populations.
These links work without JavaScript and do not imply new source acquisition,
expanded current-ID coverage, a rolling refresh or a deployed site.

The dated [culture/games companion](m1-cross-subject-20261025.html) adopts four additional, independently retrieved *title-scoped* histories (140 exact observations) into a versioned, JavaScript-free page and [machine-readable observations](m1-cross-subject-20261025.json). Its raw-source hashes and all daily values are checked before they enter the deterministic Pages bundle. This is separate from the historical M0 six-series sample and the observed 20-ID panel; no stable ID history, equivalent cross-edition Wikidata identity, live refresh or verified public Pages URL is asserted. Source raw HTTP bodies were retained only in the time-limited 25 Oct Actions artifact.

Before reviewing a changed preview:

```sh
python -m tools.build_nojs --check
python -m tools.build_portable  # generate the untracked portable HTML on a fresh checkout
python -m tools.build_portable --check
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q tools tests
node --check site/app.js
python tests/browser_portable.py
python tests/browser_nojs.py
python tests/browser_incompatible_links.py
python tests/browser_smoke.py
python tests/browser_version_required.py
python tests/browser_filter_links.py
python tests/browser_control_guard.py
```

The read-only M0 Actions workflow runs Python 3.12/3.13 separately and divides all
15 controlled-DOM Chromium scripts into four deterministic, independently reported shards; a separate native HTTP Chromium job exercises the real local release under `/Dayflare/`. You
can reproduce one shard locally with `python -m tools.run_m0_ci --browser-shard 1`
(repeat for 2, 3 and 4), or run the unsharded local suite with
`python -m tools.run_m0_ci`. A green shard alone is **not** full acceptance;
all four shards and the Python matrix must pass on the same exact PR head
for M0 acceptance; this does not assert GitHub branch-protection requirements.
Sharding changes neither the tested evidence nor publication permissions.

Run `python tests/browser_m0_http.py` for independent native-HTTP browser checks (no fetch/crypto/history shims): 320/390/1280 screenshots, keyboard discovery, exact detail/comparison, versioned share/reload, no-JS tables and staged HTTP 404/retry. Read-only CI retains 14 screenshots and a source/dataset/method-bound receipt for seven days. The 240s HTTP job is separate from the 45s controlled-DOM shard watchdog. Inspect real PNGs before visual acceptance; local HTTP is not GitHub Pages.

Browser scripts require a separately available compatible Chromium and Playwright.
Do not label browser tests PASS when unavailable; HTTP/file navigation and a real
Pages-served revision require their own checks. The portable standalone HTML is
an intentionally duplicated **generated projection**, not a separate source of data.
The read-only Python builders hash-check both retained JSON members before generating
HTML, and `--check` never replaces an output. They perform no Wikimedia retrieval,
posting, permission change, paid inference or GitHub Pages deployment.

Discovery cards default to sorting by the **absolute** change in seven-day counts against the median of the previous four weeks. The Order by control also supports signed increase/decrease, final-week count, and original collection order. This is an ordering of **six selected series**, not a population-normalized ranking, a trend classifier or a claim of shared identity across editions. The chosen order (`o=`) is preserved in exact, version-bound links and invalid or duplicated values fail closed.

Version-bound links must fail closed on unknown dataset/method/window/edition/topic.
A snapshot error disables data-dependent controls; retry is explicit. A local `file:`
copy link is not a public URL. Source code and fixtures are not evidence of a live site.

## Self-contained static Pages candidate (not a deployment)

The source preview at `/site/` fetches `../evidence/`, which is **outside** a
Pages root that publishes only `site/`. Use the generated *release root* instead;
it contains `index.html`, `app.js`, `styles.css` and the pinned evidence ZIP
within the same root. The release-only JavaScript uses `./evidence/...` so it
resolves correctly from a GitHub Pages project subpath such as `/Dayflare/`.

```sh
python -m tools.build_static_release
python -m tools.build_static_release --check
python -m unittest discover -s tests -p 'test_*.py' -v
```

`Dayflare-M0-static-Pages-UNPUBLISHED.zip` is a deterministic distribution
artifact with a SHA-256 manifest. Failed evidence validation does not overwrite
an existing release candidate. HTTP smoke tests exercise all paths at a
`/Dayflare/` project root, but Chromium navigation, actual Pages provisioning,
deployment and public response verification remain independent release gates.
The candidate does not initiate publication, create infrastructure, infer
freshness or silently update historical measurements.

## Local evidence links in the release

`site/index.html` deliberately continues to point to repository-relative evidence
for source preview. `tools.build_static_release` rewrites only the generated ZIP:
its detail/footer source links open a styled `evidence.html` explainer, which links
to exact, pinned `provenance.json` and `README.md` records and `source.zip` **inside**
the Pages root. Git blob hashes pin both technical documents to PR #16's source
revision; changed or missing records prevent a build instead of silently producing
a broken or misleading site. A bounded local href/src validator rejects paths
outside the root and missing files/anchors. This is still not a deployed URL.


## Offline immutable release staging (still not deployed)

After a later-run reviewer has accepted an exact source revision, record its
independently approved `release-manifest.json` SHA-256 outside the candidate
being staged. A hash read solely from the ZIP under inspection is **not** an
independent approval pin. Build the deterministic candidate and stage the
reviewed bytes into a new destination (never replace the last-good directory):

```sh
python -m tools.build_static_release
python -m tools.stage_pages --archive Dayflare-M0-static-Pages-UNPUBLISHED.zip \
  --destination /tmp/dayflare-M0-reviewed \
  --expected-manifest-sha256 <approved-64-lowercase-hex>
python -m tools.stage_pages --check \
  --destination /tmp/dayflare-M0-reviewed \
  --expected-manifest-sha256 <approved-64-lowercase-hex>
```

The stage checks the separately approved manifest pin, complete asset hashes,
dataset/method/window, exact byte-for-byte reproduction from current source,
ZIP membership/size/modes and absence of symlinks or unexpected files. It
fails without overwriting an existing candidate. No Actions workflow deploys
this directory and it does not provision Pages or assert a public URL.
A future authorized deployment still requires exact served-byte and browser
verification under #12.

## Read-only accepted-master release artifact (NOT a deployment)

After a merge into `master`, the M0 workflow first requires **both** offline
Python acceptance versions, all four Chromium shards and the native HTTP Chromium
job to pass. Only then does its `candidate` job upload a seven-day artifact named
`m0-unpublished-<exact-master-commit>`, containing `dayflare-m0.zip`,
`release-manifest.json` and `release-receipt.json`. Pull requests and manual
runs on non-master branches cannot upload this release artifact.

The receipt records the exact source commit, archive SHA-256, manifest SHA-256,
dataset, method and observation window. Its status is
`UNAPPROVED_MASTER_CANDIDATE_NOT_DEPLOYED` with
`independent_approval=false` and `live_verified=false`: computed hashes are
**not** an independent approval and uploading a CI artifact is **not** Pages
deployment. Acceptance of its pinned manifest requires a later review against
the exact approved source. For a local reproduction from that exact clean
checkout, run:

```sh
python -m tools.m0_release_receipt --expected-commit "$(git rev-parse HEAD)" \
  --output /tmp/dayflare-M0-unapproved-candidate
```

This builder fails if tracked files differ from the specified commit, the source
evidence/manifest cannot be verified, or the destination already exists. The
existing `tools.stage_pages` still requires a separately approved manifest pin
before producing a reviewed local stage. Neither step enables Pages or asserts
`LIVE_VERIFIED`.
