# M1 identity laboratory — synthetic companion

Explore page IDs, title changes, separate redirects and uncertain Wikidata mapping.
The [main M0 atlas](../site/README.md) uses real historical pageview observations;
this optional identity laboratory uses **fictional engineering fixtures only**.
It is not additional measured coverage, a live atlas or a public release.

## Run locally

From the repository root with Python 3.12+ and Node.js:

```sh
python -m pip install -r requirements-test.txt
python -m tools.m1_build_preview --check
python -m unittest discover -s tests -p 'test_m1_*.py' -v
node tests/js_m1_share.cjs
python -m http.server 8000
# Visit http://127.0.0.1:8000/site/m1-preview/
```

Regenerate intentional fixture changes with `python -m tools.m1_build_preview`,
then inspect the diff and run `--check`. The builder requires synthetic evidence,
validates the identity panel, creates deterministic JSON/manifest bytes and embeds
the dataset SHA-256 in the HTML. It does not modify the main M0 release bundle.

## Working interactions

Filter EN/RU editions and subjects, search title/topic/page ID, inspect dated title
and continuity traces, then share the selected identity. Local share URLs bind
schema, panel, dataset SHA-256, filters and optional `(edition,page_id)`. Any
parameterized share requires all version fields exactly once. Unknown/duplicate
parameters, version mismatch, missing identity or contradictory filters show an
explicit recovery state; no newer same-ID page is silently substituted.

The recovery action appears before disabled discovery controls and receives
keyboard focus. History navigation rebuilds state from the URL, clears ghost
selection and restores compatible controls. Russian card/detail titles carry
`lang=ru`, English titles `lang=en`. Exact textual facts do not depend on hover,
dragging, chart interpretation or colour. CSS includes narrow layouts, focus styles
and reduced-motion handling.

Coverage is a count of fixture identities, not popularity. An absent edition/subject
cell reads **Not included**, never zero visits. The unresolved seventh intention
has no invented identity. On invalid data, counts become unavailable rather than
zero. Data loads through a 256 KiB bounded stream, SHA-256 verification and a
12-second request/body deadline. Failure exposes Retry; successful retry restores
the view. Clipboard failure leaves a manually selectable URL.

All assets are local, DOM content is text-only, and no tracking, external services,
images, Wikimedia requests or posting occur. Fictional source links are not
presented as verified evidence. Without JavaScript, the laboratory explains its
limitation; the separate real M0 atlas retains its exact-value no-JS tables.

## What each test proves

`tests/js_m1_share.cjs` exercises the actual app in a minimal Node DOM VM: versioned
restore/history, Russian language attributes, coverage, streaming limits, tamper,
timeout and retry. It is **not a browser or visual acceptance test**.

For ordinary HTTP navigation in Chromium:

```sh
python -m pip install playwright==1.55.0
python -m playwright install chromium
python tests/m1/browser_preview.py
```

The browser script serves local source and checks 1280/390/320 px, filter/detail
focus, share/reload, empty and incompatible states, separately injected corrupted
responses with retry, no-JS messaging and horizontal overflow. It writes actual
screenshots to `evidence/local-m1-browser/`. Optional `CHROMIUM_EXECUTABLE` selects
an already installed browser, not a navigation-policy bypass. The script lives
under `tests/m1/` so it does not alter M0's strict browser-shard inventory.

The read-only [M1 workflow](../.github/workflows/m1-validation.yml) executes these
contracts at the exact proposed revision and retains screenshots for seven days.
Its result must be read; a workflow file is not a passing run. Inspect real rendered
screenshots before visual acceptance. Locally on 2026-10-22, normal Chromium HTTP
navigation returned `ERR_BLOCKED_BY_ADMINISTRATOR`: VISUAL_NOT_VERIFIED, no screenshot
acceptance and no bypass. Hosted execution is an independent environment.

M0's actual HTTP/public-release acceptance stays in #21/#12. Source adoption does
not close real panel #19/#14 or turn this synthetic companion into the public
milestone. See [identity evidence contract](M1_IDENTITY_PANEL.md) and the
[single roadmap](../control/STATE_AND_QUEUE.md).
