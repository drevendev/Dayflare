# M1 rolling source → local static visitor preview

Issue #18 / #13. A source-verified **local-only** preview now connects the
bounded 35-day retained-body evidence collector to a usable, readable,
JavaScript-free atlas. It does **not** change the public M0 site, schedule a
collector, validate historical page-ID continuity, or activate GitHub Pages.

After a reviewed EN/RU seed has been collected and verified, run from the
repository root (Python 3.12+):

```sh
python -m tools.rolling_pageview_source verify path/to/source-bundle
python -m tools.rolling_snapshot_preview path/to/source-bundle path/to/new-preview
python -m http.server 8000
# Browse http://localhost:8000/path/to/new-preview/ from the repository root.
python -m unittest discover -s tests -p 'test_rolling_snapshot_preview.py' -v
```

### Inspect a real-source CI atlas without publishing it

The existing [bounded 20-title Wikimedia acquisition workflow](../.github/workflows/m1-curated-rolling-pageviews.yml) runs only on its listed pull-request file changes or explicit `workflow_dispatch`. It has **no scheduled/publication side effect**. If all 20 edition/title histories (700 exact dated observations) pass collection, retained-response verification and source-bound v2 staging, it now exports the **current** immutable stage to `artifacts/m1-curated-preview/`. It independently exports the same stage again, requires byte-identical HTML and preview-manifest files, checks the candidate/pointer/receipt/HTML SHA-256 binding, and checks 20 discoverable cards with 20 linked detail sections. Failure aborts the run; there is no partial or fallback published page.

On a successful run, download the `m1-curated-rolling-<commit>-<attempt>` ZIP artifact from that workflow's **Actions** run (retained for seven days), then extract it. **The ZIP strips the `artifacts/` prefix.** New builds provide an `index.html` directly at the extracted ZIP root, byte-identical to `m1-curated-preview/index.html` and checked against the `m1-curated-preview/preview-manifest.json` HTML SHA-256. Open `index.html` in a browser without installing dependencies; `START_HERE.txt` also records the observation end, retrieval time, dataset ID and candidate checksum. The previously successful 28 October 2026 artifact (run 40643747842) predates the ZIP-root entrypoint: in *that* archive open `m1-curated-preview/index.html` (not `artifacts/m1-curated-preview/index.html`). Optional: run `python -m http.server` from the extracted root and visit `/index.html`. Each archive also includes reviewed seeds, exact retained decoded source JSON bodies, receipts, a current pointer and immutable source-bound version for independent replay. The second-build comparison copy is deleted after verification and is not uploaded.

**This is a dated, editorially selected local evidence preview**, not the public Dayflare URL or a continuously updated product. Source receipts report the executing runtime's transport and are not independently signed by Wikimedia. Title-scoped histories do not prove historical continuity of the supplied current numeric page IDs. The HTML labels those limits, observation/retrieval dates, EN/RU edition scope, and exact evidence links. A failed provider response, incomplete window or staging error prevents the artifact rather than treating missing observations as zero; it never replaces the existing public M0 release or `gh-pages`. Human source/rights and identity review, approved publication and actual served-revision/browser checks remain separate gates.

### Rebuild the last accepted local version

A source-aware v2 stage retains its exact verified source bytes under an
immutable digest. An operator can rebuild the same visitor interface **even
after the original acquisition directory is deleted**:

```sh
python -m tools.rolling_pageview_source stage path/to/source-bundle local-stage
python -m tools.rolling_snapshot_preview --from-stage local-stage path/to/new-preview
python -m unittest discover -s tests -p 'test_rolling_snapshot_preview.py' -v
```

The exporter validates `current.json`, the staged candidate/gate report/manifest,
all copied receipt/seed/raw-body members, and their correspondence **at the
recorded retrieval instant**. It requires source-bound v2; candidate-only v1,
missing/corrupt current pointers or altered retained responses fail closed.
It takes the same POSIX advisory lock as the staging writer while verifying
and atomically exporting, so a cooperative refresh cannot select a newer
pointer halfway through the export. The output is a new, non-overwritable
local directory; earlier previews and the stage pointer are never replaced
by this command. This is archival replay, **not a live refresh** or a substitute
for independent Wikimedia transport/source-rights verification.

The preview directory must **not exist**; neither a failed source verification
nor a competing output overwrites earlier previews. The generated directory
contains only `index.html` and `preview-manifest.json`, with the byte-exact HTML
SHA-256 and source-candidate SHA-256. Repeated builds from identical verified
inputs produce identical files. Rendering has no network or external CSS/JS.

The first screen has a working discovery link for every selected title, its
last complete seven-day total, the exact baseline median of the preceding four
seven-day totals, absolute change and approximate baseline-relative change.
Zero baselines display *Unavailable* instead of an invented infinity/epsilon.
A same-window comparison table exposes the five exact weekly values. Topic
sections expose all 35 individual UTC daily observations, exact source URL,
request time and retained decoded-body SHA-256. Native links, skip navigation,
visible keyboard focus, mobile scrolling tables, exact values without color,
and reduced-motion support work without JavaScript.

**Publication gates remain separate.** `verify_bundle` checks retained raw JSON
against the candidate, seed and receipt; the exporter rereads bounded source
bytes and refuses a changed candidate/seed before output. A source bundle can
still self-report its origin, and hashes do not independently prove its HTTPS
provenance or history of the supplied current page ID. Synthetic injected tests
are boldly marked synthetic. All previews are boldly marked **LOCAL / NOT
PUBLISHED**. They are not a verified public URL or a fresh feed. Neither exporter
changes `current.json`, GitHub branches, `site/`, the accepted M0 dataset,
or a Pages deployment. A separate source-rights/identity review, controlled
release promotion and actual browser/HTTP verification are needed before the
rolling preview could become public product data. Source requests measure
request counts, not people, approval or causality; cross-edition rows are not
matched identities or national populations.
