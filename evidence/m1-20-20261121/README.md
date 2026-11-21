# Dayflare — retained EN/RU 20-title source evidence (2026-11-21)

**RETAINED, UNPUBLISHED / NOT LIVE.** This is a reproducible, offline copy of the successful [read-only scheduled run #44915307072](https://github.com/drevendev/Dayflare/actions/runs/44915307072), not an automatic Pages refresh, identity-continuity proof, country comparison, or representative Wikipedia-wide ranking.

**Measured scope:** 20 editorially selected observed page IDs: 10 en.wikipedia and 10 ru.wikipedia, two in each edition across culture, books, games, science, sport. Each has 35 complete title-scoped UTC daily requests (700 total) for **2026-10-15 through 2026-11-18**. All 20 endpoint requests reported HTTP 200; retrieved **2026-11-21T14:43:17Z**, method `v0-empirical-35d`, access `all-access`, agent `user` (not verified people). The Analytics endpoint observes requested titles, not page IDs; a separately observed page ID in the seed **does not establish rename/redirect/delete continuity** across these 35 days, nor cross-edition mapping, causes, importance or approval.

**Exact source retention:** `source.tar.xz` contains 20 decoded original JSON response bodies plus `seeds.json`, `source-receipt.json`, and `candidate.json`. This 9,272-byte XZ contains a sorted 194,560-byte USTAR with fixed metadata, 23 regular files and no links. SHA256 archive `682981f40b272749441c5164e650eb27136b9c1a4c583fddf7338793d493146d`; SHA256 candidate `33f01e00f00de72c58b2794e00b041011c940e8c69afee0870472877929090e9`; SHA256 seed `a32c03ef7daa8c21fe6a75b283281ed4972bf1ab0920b767581fe496a62c81d8`. Reported compressed-wire checksums are receipts only; original compressed wire bytes were not retained. Hashes/receipts do **not independently authenticate Wikimedia origin**.

From the repository root (Python 3.12+), with new absent destination paths, all **offline**:
```sh
python -m tools.m1_20_retained_source /tmp/dayflare-source-20261121
python -m tools.rolling_pageview_source verify /tmp/dayflare-source-20261121
python -m unittest discover -s tests -p 'test_m1_20_retained_source.py' -v
python -m tools.rolling_pageview_source stage /tmp/dayflare-source-20261121 /tmp/dayflare-stage-20261121
python -m tools.rolling_snapshot_preview --from-stage /tmp/dayflare-stage-20261121 /tmp/dayflare-preview-20261121
python -m http.server 8000 --directory /tmp/dayflare-preview-20261121
```
The standalone preview generated above remains a **LOCAL, NOT PUBLISHED** visitor path with actual 20-title history and evidence; it does not update the previously accepted 30-title offline atlas or live site. Source receipts are internally replayed and the unpacker refuses overwrite. Request-count data/metadata only, no Wikimedia article images or prose; verify provider rights before any eventual public release. [#12](https://github.com/drevendev/Dayflare/issues/12) owns later independent review, safe promotion, public server verification; preserve last valid publication on failure. Provider: https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/examples/page-metrics.html
