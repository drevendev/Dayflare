UNIT_ID: D01
SOURCE_REVISION: 5
SUPERSEDES: issue #1 D01 blocker characterization

# D01 — Target-runtime Wikimedia access probe

Status: SATISFIED
Evidence run date: 2026-09-29
Reconciled: 2026-09-30

## Question

Can Dayflare retrieve a bounded, usable Wikimedia Pageviews sample from the intended
GitHub Actions runtime while preserving request parameters, coverage, timing, and
checksums?

## Target-runtime evidence

Workflow run:
https://github.com/drevendev/Dayflare/actions/runs/36582733388

- workflow: `D01 Wikimedia runtime probe`
- head: `c3158250a17f180991ca45a3bf8a1709d7999ba8`
- conclusion: `success`
- observation window: 2026-09-01 through 2026-09-14 inclusive
- expected days per series: 14
- request count: 6
- target editions: English and Russian Wikipedia
- subject slices: science/technology, culture/literature, games/sport
- resolved observations: 84 / 84
- unresolved days: 0
- artifact: `11039818338`
- artifact digest:
  `sha256:119933b7e5fb3ab1eab53dabfeb02207b794dce7651ed92fb46d96461f4b4107`
- artifact expiry observed from GitHub: 2026-10-06T14:26:59Z
- normalized sample SHA-256:
  `07f7135062f3104c1afacf3d0d5ab4b5c92a5dea6e1f4004db0be05a8cb47c42`
- downloaded receipt.json SHA-256:
  `25e6ab90101b1badfaa60cc28152cd3d5fe67fc70d428ab0793d195ed1dfea43`
- downloaded sample.json SHA-256:
  `2455e67ad7244e5e6650b925f3dae6e866d03cb2e4057deb591fd75bd0eb20b0`

The artifact is temporary provider storage. The receipt below preserves the evidence
needed to reproduce or independently check this bounded probe after artifact expiry.

## Request receipts

| Project | Article | HTTP | Bytes | Raw response SHA-256 |
| --- | --- | ---: | ---: | --- |
| en.wikipedia.org | Artificial_intelligence | 200 | 2264 | `e21dd6f25f8e053fa8ab95250d20af819deccad553ec0178a2f568146cabc1d3` |
| en.wikipedia.org | The_Master_and_Margarita | 200 | 2265 | `31bec8bcce2e625d35026889e366e45fcabf95fe9bf88af33c19c1577425201e` |
| en.wikipedia.org | Chess | 200 | 1999 | `ca8e6206027cf1a164fa3315db8b34e46402b7df71d58e251b56cd8cb240eb0c` |
| ru.wikipedia.org | Искусственный_интеллект | 200 | 2559 | `3d5d0c1c1691ea8feb9f67a0962e5f1c7146d8bfddefc0476f8c4a6b8fe046e3` |
| ru.wikipedia.org | Мастер_и_Маргарита | 200 | 2391 | `42e0b247e9b0827787c2ac4ff7b5e29d9b986f3b51f05c2126952b1b4ee8ccaa` |
| ru.wikipedia.org | Шахматы | 200 | 2111 | `b98f7afc3c201ef6e2e987f85e5714a33cddfb69f4eb03e0870384004ca7451b` |

Every receipt in the downloaded artifact reported `semantic_valid=true`,
`normalized_complete=true`, and an empty `unresolved_days` list.

## Validation contract

The reusable probe accepts a successful series only when the HTTP 200 JSON payload is
structurally valid and each observed item matches the requested series semantics:

- normalized Wikimedia response project;
- exact requested article;
- `all-access`;
- `user` agent;
- `daily` granularity;
- valid in-window `YYYYMMDD00` timestamps with no duplicates;
- non-negative integer views (booleans are rejected).

Any semantic mismatch fails the whole requested series closed: no observed or
synthesized values are emitted and every requested day remains unresolved. Missing
dates inside an otherwise semantically valid HTTP 200 series may be normalized as
Wikimedia-documented omitted zeros with an explicit fill reason.

## Decision

D01 is satisfied for the research-phase access question: the intended GitHub Actions
runtime can retrieve and preserve a bounded EN/RU Wikimedia Pageviews sample with
inspectable coverage and checksums.

This does **not** establish representative topic coverage, validate D02 thresholds, or
prove that every future Wikimedia request will succeed. D02 must use a longer real-data
horizon and retain the same fail-closed acquisition semantics.
