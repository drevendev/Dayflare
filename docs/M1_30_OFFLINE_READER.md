# Offline 30-title EN/RU atlas from retained normalized data

**UNPUBLISHED LOCAL READER — NOT PAGES / NOT LIVE.** Advances #12 and complements the pinned 30-title normalized candidate in [M1_30_RETAINED_CANDIDATE.md](M1_30_RETAINED_CANDIDATE.md).

The reader is a single standalone HTML file, generated without an API call or external assets from the repository-retained exact-byte candidate. It offers 30 selected titles across English/Russian Wikipedia, 35 observed UTC dates each (1,050 request values), a numeric final-week difference against the **median of four earlier seven-day totals**, search/edition filtering, keyboard-selectable ordering by absolute weekly difference or signed increase/decrease, expandable 35-day exact-value tables, two-series same-window comparisons, a downloadable exact 35-day paired CSV (UTC date, stable local IDs, request counts, dataset and method), a zero-based side-by-side five-week comparison chart with a shared scale and an exact accessible table, and dataset/method/ID-bound URL restoration. The CSV link appears only for two distinct valid histories and needs JavaScript. It is generated offline from the same pinned daily values and never requests a server. Every history and table exists in static HTML without JavaScript; interactive filtering and comparison need JavaScript.

From a clean checkout, using **Python 3.10+**:

```sh
python -m tools.m1_30_retained_candidate
python -m unittest tests.test_m1_30_retained_candidate tests.test_m1_30_reader -v
python -m tools.m1_30_reader --output /tmp/dayflare-30-offline.html
# Open the resulting new HTML locally. An existing destination is rejected.
```

Input is pinned to dataset `run-20261117-083055-361cff6a3eb7`, method `v0-empirical-35d`, observation **2026-10-11–2026-11-14 UTC**, retrieved **2026-11-17 08:30:55 UTC**. The builder first calls the existing fail-closed validator for the exactly retained 76,346-byte JSON (SHA-256 `8c2c164d6bc35ca22786efba3a3581e76290a68de3a1006928acd79013c912f1`). It writes a new output exclusively, never replaces an accepted file or triggers a collector, workflow or deployment.

**Measured-change ordering:** The default card order ranks absolute differences between the final seven-day total and the median of the four preceding complete weeks. Signed increase/decrease ordering moves the highest/lowest differences first; it does not classify topics as rising, returning or fading. With JavaScript disabled, all cards remain in the original absolute-difference order.

**Interpretation/coverage:** These are editor-selected *title-scoped* request histories, not a representative top-N list, country trends, unique humans, approval, causes or independent evidence of topic identity through historic moves. The `agent=user` query filter does **not** prove the requests are human. Cross-edition comparisons are requests with equal filters/windows, not populations or automatic shared-topic matches. Source endpoint and raw-body checksum *references* remain, but the original 148-member HTTP/browser evidence archive is not persisted by this reader. Its separately accepted 20-title `gh-pages/m1` release remains authoritative for that release. Local share URLs only work when recipients possess the identical HTML at the same path. No Pages availability, published recency or source-origin authentication is asserted.

**Comparison chart:** Five paired weekly bars use the **same zero-based numeric scale** across both selected articles (not independently normalized sparklines). Legend names the A/B series and colors; the exact five-week request table remains the authoritative accessible alternative, and the existing 35-day CSV still exports unrounded source values. Empty/invalid comparisons show neither a chart nor an export. This chart does not infer causes, equal populations or validated rising/fading labels.

**Verification scope:** deterministic Python structure/numeric/safety regression tests run offline. Real local-HTTP Chromium testing must separately cover 320/390/1280 widths, measured-change sort directions, keyboard/focus, share restore, incompatible URLs, empty results, comparison table, exact 35-row paired CSV download and invalid-pair reset, no-JS and horizontal overflow. No new visual or public HTTP acceptance is implied by a passing Python test. Keep #12 open for independently reviewed full-source preservation before Actions expiry **2026-12-17** and actual Pages release acceptance.
