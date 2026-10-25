# Culture and games: bounded historical title observations

The existing public M0 evidence contains only six **selected** EN/RU title histories
for three editorial areas. The observed 20-ID M1 panel contains culture and games
pages, but those metadata IDs cannot be used to reconstruct the historical title
series without move/redirect continuity evidence.

This focused, read-only 35-day **acquisition experiment** seeks four additional
selected title-level series: `Cinema` / `Кинематограф` and `Video_game` /
`Компьютерная_игра` for 11 August–14 September 2026 (35 complete UTC days).
It is not automatic refresh, page-ID identity tracking or a website deployment.
The latter pair may not map one-to-one; cross-edition titles are editorial candidates.

On a supported Wikimedia-access runtime, run:

```sh
python -m unittest tests.test_m1_cross_subject_views -v
python -m tools.m1_cross_subject_views
```

Output: `artifacts/m1_cross_subject_views/{sample.json,receipt.json,source-XX.json}`.
All four HTTP 200 responses and **35 complete, semantically validated days each**
are required to qualify this acquisition. Successful documented missing-zero dates
are normalized only by the existing D01 rule; failed requests remain unavailable.
The 35-day calculation reuses the D02 weekly-total/median/absolute and relative
change implementation (zero baseline => relative change unavailable). Inputs and
result are bounded to <=1 MiB/response, <=4 MiB aggregate, 20s timeout, sequential
requests with >=2s pacing (5s after an over-1-second request), no retry, strict
source checksums and no destination replacement. An incomplete run exits 2 and
retains an `INVALID_UNPUBLISHED` receipt; no consumer must treat its sample as data.

The PR-only GitHub Action retains evidence for seven days but **does not commit,
publicly serve, refresh or publish it**. Accepting a run requires fresh verification
of the exact head, source URLs/filters, 4 raw response hashes, complete-day
coverage, independently recomputed weekly metrics, rights and title/ID caveats.
Only later can a separate reviewed, versioned atlas data release incorporate it.
No invented source retrieval, fresh popularity, validated lifecycle classification
or representative subject coverage is claimed by this implementation alone.
