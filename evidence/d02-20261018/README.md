# Retained D02 historical evidence

This directory preserves two exact JSON members from GitHub Actions
[run 39112409117](https://github.com/drevendev/Dayflare/actions/runs/39112409117),
artifact `12130838093`, produced by collector head
`ae3299e6af43460fcd2a8bf9b7727df5bdd8a92f`.
Retrieval finished **18 October 2026, 08:41:26 UTC**; observations remain
**11 August–14 September 2026**. Six selected series, 35 complete UTC dates each,
210 normalized observations; not current or representative coverage.

## Reproduce without a network request

```sh
python -m tools.verify_d02_artifacts --retained evidence/d02-20261018
python -m unittest discover -s tests -p 'test_*.py' -v
```

`source.zip` contains **only `sample.json` and `receipt.json`**. The read-only command
bounds archive/member sizes, reads JSON in memory without extraction, checks hashes
and recomputes all weekly values. The ordinary all-PR test suite includes this real
fixture as well as separately labelled synthetic corruption controls.

The original Actions archive expires on **25 October 2026**. This capsule retains the
original member bytes, deterministically repacked with DEFLATE level 9, member order
sample/receipt, timestamp 2026-10-18 08:41:28 and Unix regular-file mode 0644.
It is **not the original Actions ZIP**. `provenance.json` records separate archive
and member hashes, the native source IDs and the recovery boundary. Member hashes
establish consistency of these files, not a new upstream authenticity signature.

## Measured comparisons

Current week: **8–14 September**. Baseline: median of the four preceding seven-day
totals from 11 August through 7 September. Source filters: `all-access`, `user`, `daily`.

| Edition / article | Current week | Median baseline | Absolute change |
| --- | ---: | ---: | ---: |
| EN / Artificial intelligence | 125894 | 81756 | +44138 |
| EN / The Master and Margarita | 9662 | 9993 | -331 |
| EN / Chess | 19804 | 18369.5 | +1434.5 |
| RU / Искусственный интеллект | 14595 | 8645 | +5950 |
| RU / Мастер и Маргарита | 5222 | 5222.5 | -0.5 |
| RU / Шахматы | 2965 | 2927 | +38 |

Normalized sample SHA-256 (canonical UTF-8 JSON, excluding its final newline):
`69b6d5b83e761a0536de7ddd64569a859d75a279c4bb2607ed96e38e3d9423b0`.
The complete file hash is different because it includes that newline.

## Limits and rights

Raw HTTP bodies are not retained. Their reported hashes are preserved in the receipt
but cannot be recomputed from normalized rows. This collector run predates the later
HTTP Content-Length guard; a reported complete-body flag is not independent framing
verification. The retained sample matches the previously accepted normalized digest
and its calculations are reproducible; it is not a new acquisition or claim of current data.

There are no stable page-ID observations in this sample. Do not join other snapshots
by title, force EN/RU entity equivalence or infer deletion/restore continuity. D03 stays
binding. `agent=user` is not verified humans; edition counts are not populations,
importance, approval or causes. No validated lifecycle classification is assigned.

Wikimedia Analytics API data is [CC0](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html).
No article text or images are included or relicensed. The code/data pipeline and
public atlas still require separate source acceptance and publication; this directory
only advances the retained-evidence portion of #7/#9.
