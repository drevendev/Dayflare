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
PUBLISHED**. They are not a verified public URL or a fresh feed. The exporter
never changes `current.json`, GitHub branches, `site/`, the accepted M0 dataset,
or a Pages deployment. A separate source-rights/identity review, controlled
release promotion and actual browser/HTTP verification are needed before the
rolling preview could become public product data. Source requests measure
request counts, not people, approval or causality; cross-edition rows are not
matched identities or national populations.
