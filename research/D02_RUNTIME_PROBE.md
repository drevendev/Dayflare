# D02: bounded 35-day measurement probe

Status: implementation candidate; D02 remains **PARTIAL**, not a validated public
signal or a completed research gate. This document specifies execution and acceptance;
GitHub PRs, checks and Actions artifacts own the actual run/merge facts.

## Outcome and scope

Reproduce raw volume, absolute change and baseline-relative lift from five complete
7-day UTC windows. Use the six fixed EN/RU D01 candidates across science/technology,
culture/literature and games/sport for **2026-08-11 through 2026-09-14**. This is a
historical, selection-biased experiment, not current attention or representative
coverage. It does not discover top-N topics or equate absent topics with zero.

The existing implementation and finite-input regression tests are retained from
`research/d02-35day-probe@d271c8a6d6c361d9fbfc7c6d2673ea79ea79a3f9`.
The method structure comes from [issue #1's D02 decision](https://github.com/drevendev/Dayflare/issues/1#issuecomment-5816960976).
The runtime workflow and offline integration tests adopt the earlier unpublished
`dayflare-d02-runtime-path` and `dayflare-d02-offline-main-integration` recovery patches;
this checked-in copy is the canonical implementation, not a dependency on those files.

## Run and inspect

From the repository root, with Python 3.12 or newer and no third-party packages:

```sh
python -m unittest discover -s tests -p 'test_d0*.py' -v
python -m tools.d02_probe
```

The module invocation is intentional: `python tools/d02_probe.py` does not reliably
put the repository root on Python's import path. Offline tests mock HTTP transport
with explicitly synthetic values and must never be cited as successful retrieval.

A real run writes `artifacts/d02/sample.json` and `artifacts/d02/receipt.json`.
The receipt includes exact requests, filters, observation and retrieval times,
response checksums, coverage, normalized sample checksum and per-series metrics.
The sample checksum covers canonical UTF-8 JSON bytes **excluding the final newline**.
Exit 0 requires six semantically valid HTTP 200 responses and all 210 requested days
resolved. Exit 2 preserves failure receipts and unavailable metrics; it is not PASS.

`V` is the newest 7-day total. `H1..H4` are the preceding totals, newest first;
`B = median(H1,H2,H3,H4)`, `delta = V-B`, and `relative_lift = (V-B)/B`.
A zero baseline yields `null` lift, never an epsilon-adjusted percentage. The emitted
weekly-total array is ordered oldest to current. All thresholds remain unfrozen.

## Target-runtime path and budget

`.github/workflows/d02-runtime-probe.yml` runs relevant pull requests at their exact
head SHA, relevant master pushes and manual dispatch once the workflow is available
on the default branch. It executes tests before live retrieval, has read-only
repository permissions, does not persist checkout credentials and never publishes
Pages or changes repository settings. It is **not** a universal required status check.

Each live probe makes six sequential requests, with a 30-second timeout per request,
no retry loop, a 5-minute job limit and per-PR/ref concurrency cancellation. Only the
two D02 evidence JSON files are uploaded, with 7-day retention, including on failures.
Before retention expires, record accepted sample/response checksums and coverage in a
reviewed durable research result; do not equate a green Actions run with D02 closure.

Primary documentation rechecked 2026-10-06:
[Wikimedia access policy](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html)
requires client identification and advises sequential requests; API data is CC0, not
article text/images. [GitHub workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
describes PR/push execution and the default-branch requirement for manual dispatch.

## Acceptance and remaining work

A later acceptance run must inspect the exact PR head and current base, execute the
D01/D02 regression suite, inspect the actual Actions result and receipt, independently
recompute the sample checksum/weekly metrics, and reject missing or failed evidence.
The workflow file alone proves neither retrieval nor deployment.

Preserve D01's accepted normalization rule: omitted dates are documented zeros only
inside a successful, structurally and semantically validated series. HTTP/parse or
identity failures remain unavailable. `agent=user` is not verified humans; measured
attention is not importance, approval, unique people or causation.

Non-goals: no lifecycle classification in the real six-series output, no threshold
freezing, no source expansion, no identity stitching, no public milestone or Pages
release. D03 still requires stable page identities and explicit continuity/mapping
states before cross-snapshot topic histories. Low/new/renamed/returning/seasonal and
automation counterexamples, numerical extremes, and the older-normal/quiet windows
still need the broader D02 evaluation. The separate parameterized lifecycle helper is
an experiment; its synthetic tests are not a production labeling policy.
