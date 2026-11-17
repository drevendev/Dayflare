# Repository-retained normalized 30-title sample (not a release)

Issue #12. This is a **lossless, exact-byte copy of only the normalized candidate JSON** from the independently verified, unpublished 17 November 2026 real EN/RU source bundle. It preserves 30 selected title histories × 35 UTC days = 1,050 integer request counts, with source endpoint and raw-body checksum *references*, after the temporary Actions artifact expires. It is **not** a second raw evidence archive, proof of independent upstream authentication, a new Wikidata mapping, a Pages deployment, or an approved replacement for the 20-title release.

- Exact original normalized JSON: **m1-30-source/candidate.json** from successful Actions [run #44046865069](https://github.com/drevendev/Dayflare/actions/runs/44046865069), artifact #14312401439; original preserved ZIP SHA-256 **0473e8b52f90df70c227e648a06bbae1e833740844dff77f8c28ef1e32e2b0c4** (last verified locally 17 Nov).
- Candidate 76,346 UTF-8 bytes; SHA-256 **8c2c164d6bc35ca22786efba3a3581e76290a68de3a1006928acd79013c912f1**. Dataset **run-20261117-083055-361cff6a3eb7**, method **v0-empirical-35d**, observed 11 Oct–14 Nov 2026 UTC, collected 17 Nov 2026 at 08:30:55 UTC.
- **evidence/m1-30-20261117-candidate.xz.b64** is XZ level-9 + canonical Base64 armor of those **unchanged** JSON bytes, not a recomputed series. The Python module **tools.m1_30_retained_candidate** bounds decompression, pins the exact digest, checks full dates/identity/filter/source references, and never overwrites an extraction target.

From a clean repo checkout, run:

~~~sh
python -m tools.m1_30_retained_candidate --output /tmp/NEW-dayflare-30-candidate.json
python -m unittest tests.test_m1_30_retained_candidate -v
~~~

Or omit --output to validate only. The decoded bytes must hash to the exact digest above. An existing output is an error, not overwritten.

This **mitigates expiry only for the normalized candidate**, and does not retain the 148 original artifact files, HTTP response bodies, browser screenshots or standalone HTML. Those still require a distinct authorized durable archive transfer before the Actions artifact expires **17 Dec 2026**. Subject selection is editorial, not representative; per-title histories cannot establish page-ID continuity through prior moves/deletions, and agent=user is not unique human users. No public Pages availability or refresh is implied.
