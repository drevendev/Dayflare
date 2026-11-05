# Actual Wikipedia identity observations: 4–5 November 2026

**20 selected EN/RU local page IDs on each UTC date, with zero observed title, QID, redirect or topic-assignment changes.** This is a historical comparison of current-page metadata, **not** an attention/pageview chart, proof of uninterrupted page identity, or a live website. The curated sample is not representative.

## Reproduce the real before/after report

From this repository's root, with Python 3.12 or newer:

```sh
python -m tools.m1_real_pair
python -m tools.m1_real_pair /tmp/dayflare-real-identity-history
python -m unittest discover -s tests -p 'test_m1_real_pair.py' -v
python -m http.server 8000 --directory /tmp/dayflare-real-identity-history
# Visit http://localhost:8000/ (local only).
```

The accepted `tools.m1_identity_history` renderer produces `index.html`, `history.json` and `manifest.json` from the two exact original panel inputs. Its no-JavaScript page provides an identity index, before/after source observations, per-ID anchors, exact evidence, stated UTC retrieval dates and keyboard access. New outputs are immutable; existing destinations are never overwritten. A missing/mutated source fails closed before output creation. The locally generated comparison is **BUILT, not DEPLOYED or LIVE_VERIFIED**.

## Exact source retention, without duplicating identical bytes

Baseline: [4 November retained capsule](../m1-identity-20261104/README.md), 20/20 identities retrieved 10:31:14–10:31:55 UTC.

Follow-up: [GitHub Actions run 41941385394](https://github.com/drevendev/Dayflare/actions/runs/41941385394), source commit `7404bc13456075a97c52441279ee34749cb89f55`, artifact `13377025842`, 20/20 identities retrieved 5 November **00:27:41–00:28:20 UTC**. Original ZIP 27,133 bytes, SHA-256 `a9a86646e7a7ae2b158ea3c269eb2fd900cace7a6d364ce6103af35e8c276863`. Its temporary artifact is not the permanent archive.

All **20 decoded raw API JSON responses are byte-identical** between these two actual collections. To avoid re-committing the same raw bodies, `source-delta.json` contains a **lossless zlib-compressed XOR delta** for the other four original 5 November files: `panel.json`, `collection-report.json`, `internal-consistency.json`, `bundle-manifest.json`. For each file, its original 4 November SHA-256, exact recovered 5 November SHA-256 and byte count are pinned in the delta; `provenance.json` independently pins the artifact, dates and metadata hashes. The delta SHA-256 is `64def4e4d21add65063d448f965d0bf9b86edfa186d0200f651c8fa11fe6aaff`.

`tools.m1_real_pair` reconstructs **exact original source bytes** from the accepted 4 November archive and the delta, then checks **all 24 original 5 November identity-source members** against the recovered *5 November* bundle manifest using the accepted source verifier. It validates the stable `(project, page_id)` inventory, editorial scope, original panel SHA-256 (`6da7fd25c2000484ac2f88f40632eefe3b69f57f662b9c0bc090e43cb2e20344`) and the canonical comparator's 20 unchanged observations. No second source bodies or observations are fabricated. The original compressed wire bodies were not retained; only decoded factual API JSON responses are preserved.

## Boundaries and acceptance

Hashes prove internal byte agreement, not independently authenticated Wikimedia transport. The two samples do **not** establish moves, deletions, title-history continuity, cross-edition equivalence, historical pageviews, or people/importance/causes. An unchanged title/QID at two moments does not imply no intervening event. No article prose, images, tracking, paid infrastructure, new collection, scheduler or Pages publication was added. See `provenance.json` for factual metadata rights and source references (MediaWiki Pageprops, Wikidata licensing, Wikimedia robot policy).

This is a **source adoption proposal** for [issue #145](https://github.com/drevendev/Dayflare/issues/145). It still requires exact-head CI, later independent PR acceptance and real 320/390/1280 Chromium mobile, keyboard, no-JS and screenshot inspection of the measured report. The public Pages milestone remains [issue #12](https://github.com/drevendev/Dayflare/issues/12), not LIVE_VERIFIED.
