# Collect the next EN/RU identity observation by stable page ID

The retained [4 November 2026 baseline](../evidence/m1-identity-20261104/README.md)
contains 20 actual, curated Wikipedia page IDs. **A new observation must use those
same `(project, page_id)` keys**, not rediscover whichever titles happen to match
later. `tools.m1_identity_followup` reuses the pinned raw baseline, original
source/collection validators and the already merged no-JavaScript history viewer.

## One safe, explicit acquisition

On **5 November 2026 UTC or later**, from a fresh checkout with Python 3.12+:

```sh
python -m tools.m1_identity_followup /tmp/dayflare-next-identity-20261105 \
  --source-revision "$(git rev-parse HEAD)"
python -m http.server 8000 --directory /tmp/dayflare-next-identity-20261105
# Open http://localhost:8000/history/ (local only; not a live Pages site).
```

Run this command **once**, deliberately, when the source client can make normal
HTTPS Wikimedia requests. The destination must not exist. The tool *refuses* to
run on the baseline's UTC date, near midnight, with unreviewed baseline bytes,
with a changed 20-ID set, or with a non-UTC clock. There is no automatic retry,
new cron job, alternate account, background loop or Pages write. Network timeout,
429/503, invalid JSON, missing IDs and provider headers are governed by the
existing rate-limited `tools.m1_collect` transport and verified with the unchanged
`m1_bundle_verify`/`m1_source_verify` contracts.

The verified follow-up must contain **exactly the original 20 numeric-ID attempts**,
including unavailable requests, with unchanged editorial topic/subject/relation
and the matching pinned selection ID/date. A structurally valid 20-page bundle
with substituted IDs or scope is rejected before HTML creation or publication.

If a page ID no longer yields a valid current article, the collector records an
**unavailable attempt**. The history report must say *not observed in this
snapshot*, never deleted/zero/created. If the sample has no valid pages or spans
UTC days, the attempt fails and leaves no completed output. Continuous identity,
historical moves, resolved Wikidata equivalence, and pageview stitching cannot be
inferred from two isolated observations.

## Exact output / evidence boundary

The immutable output has:

| Path | Purpose |
| --- | --- |
| `baseline-panel.json` | Byte-identical original panel from the reviewed November 4 source capsule. |
| `identity-seeds.json` | Explicit fixed local-ID selection and the actual next UTC selection date. |
| `followup-source/` | New, complete current-page collection with 20 attempt receipts, raw decoded JSON bodies for retained IDs, source proof and hashes. |
| `history/index.html` | Offline, accessible before/after evidence explorer with keyboard index, exact source disclosures and mobile layout. |
| `history/history.json` | Machine-readable per-ID observations, source dates, change labels and unknown continuity. |
| `history/manifest.json`, `receipt.json`, `manifest.json` | Reproducible method/byte hashes, intended/obtained counts, explicit **UNPUBLISHED_SOURCE_REVIEW_REQUIRED** status. |

`manifest.json` is written last. An atomic no-replace directory promotion refuses
existing destinations even when created concurrently. Failure before promotion
leaves no public candidate. The source baseline and existing `gh-pages` files are
never modified. The selected 20 IDs were editorial, not representative. Recorded
HTTP source bytes and checksums authenticate *internal consistency*, **not** the
origin of the original Wikimedia transport. Raw bytes are decoded JSON responses;
compressed wire representations are not retained. No article prose or images.

The HTML deliberately has no pageview chart: this operation observes only identity
metadata. Use the separate [measured M1 atlas](../README.md) for historical daily
request counts, which do not have proven continuous page IDs.

## Acceptance and release

```sh
python -m unittest discover -s tests -p 'test_m1_identity_followup.py' -v
python -m compileall -q tools tests
```

Offline tests exercise the dated gate, fixed IDs, missing/duplicate IDs, source
mismatch, failed collection, candidate hashes, no-overwrite and deterministic
preparation. They use *mocked* provider responses, not newly retrieved coverage.
The existing M1 read-only CI runs these without calling Wikimedia. Before using
the next day's actual result in public: independently review every source body,
match byte hashes, verify CI and report dates, then review/merge the immutable
adoption PR in a **later run**. Inspect genuine desktop/320px/390px Chromium
screenshots of the real history output under local HTTP and verify share/links.
This new source is **not** auto-promoted to `gh-pages`, nor is Pages presumed enabled.

Related: [#145](https://github.com/drevendev/Dayflare/issues/145)
(two-date evidence), [#12](https://github.com/drevendev/Dayflare/issues/12)
(publication), and the [D03 method](../research/D03_IDENTITY_MODEL.md).

## GitHub-hosted, manually dispatched same-ID source acquisition

A separate permanent worker is **not** required. After this workflow change has
been reviewed and merged, open the existing GitHub Actions workflow
**M1 real EN/RU identity evidence (unpublished)**, choose **Run workflow** on
the accepted **master** branch and select `task = stable-id-followup`.
The default `task = discover` retains the original title-discovery experiment.
No run is scheduled or started by changing this workflow.

The explicit follow-up mode fails **before contacting Wikimedia** if it is
launched from a non-master branch, on 4 November UTC, or too close to midnight.
It reuses exactly the 20 approved numeric page IDs, the identified/paced
gzip-aware collector, the same date/scope/response validators and the immutable
history renderer. Every source file, the complete attempted-ID list (including
unavailable IDs), the generated HTML/JSON, the source revision, version and
receipt are checked before a **7-day, unpublished** Actions artifact is retained.

A successful Actions job means a consistent *local* historical candidate, **not**
proof of authentic network origin, visual acceptance of the newly measured report,
a source adoption PR, deployment, or LIVE_VERIFIED Pages. Download and preserve
the exact artifact while it is retained; independently inspect raw source bodies,
rights, dates, 320/390/1280 Chromium screenshots, and provenance before opening
an immutable source-adoption PR. PR review and later acceptance remain separate.
There are no new credentials, scheduled triggers, publication writes or retries.

A push to `master` preserves existing discovery behavior; unreviewed feature
branch pushes no longer trigger live discovery. Ordinary PR validation remains
read-only in `m1-validation.yml`, including the dispatch contract regression.
