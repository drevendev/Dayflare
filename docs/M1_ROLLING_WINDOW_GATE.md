# M1 rolling candidate: offline completeness gate

Issue: #18, under #13. This is a tested **offline input gate**, not a collector, immutable stage, refresh scheduler, new public atlas dataset, or Pages deployment. The existing historical M0 dataset and D02 methodology do not change.

## Run

From repository root, Python 3.12+:

    python -m unittest discover -s tests -p 'test_rolling_window_gate.py' -v
    python -m tools.rolling_window_gate path/to/real-rolling-candidate.json > /tmp/rolling-gate-report.json

Nonzero exit rejects the candidate. The command never writes a dataset, publication pointer, site, or history. Output is canonical JSON for the supplied candidate.

## Candidate contract: dayflare.rolling-candidate.v1

A candidate object has exactly: schema_version, dataset_id, method_version, retrieved_at, provider_lag_days, observation_end, and series. IDs and versions use bounded nonempty ASCII tokens. Retrieved and request times are explicit UTC second-precision timestamps. Provider lag is an explicit **1–7 days**, not a frozen Wikimedia freshness guarantee.

Each series contains a stable local (project,page_id), observed title, matching all-access/user filter parameters, an HTTPS source receipt, and 35 daily records. Its receipt includes an exact Wikimedia per-article URL with edition, title, filters, and dates; UTC requested_at, HTTP 200, lowercase body_sha256, and bounded response_bytes. These fields are **reported input**, not independently authenticated upstream bodies, stable-identity resolution, licensing or title history.

The candidate covers five consecutive seven-day periods, ending no later than today_utc minus the configured provider lag minus one day, and no more than 90 days before the run. Each series must contain exactly those 35 **observed** UTC days in chronological order. Explicit reported zero views is valid; absent, inferred, or unobserved values never become zero. agent=user is not verified human traffic. This tool never stitches identities by title or pairs EN/RU topics.

Inputs are bounded to 2 MiB, 1–30 series, per-response reported size <=1 MiB, en.wikipedia/ru.wikipedia, and positive safe page IDs. Repeated local (edition,page_id) keys, incompatible filters, wrong endpoint/window, missing/duplicate/out-of-order days, invalid/nonfinite/boolean counts, future/stale windows and retrievals, oversized or duplicate-key JSON, and unexpected fields fail closed.

## Evidence and next acceptance

The report contains a canonical input SHA-256, explicit observation/retrieval times and counts, provenance_status=self_reported_not_independently_verified and publication_status=NOT_STAGED_NOT_DEPLOYED. Hashes attest only repeatability of supplied content, not source authenticity. All checked-in tests are synthetic and cannot establish a real 20-identity subject panel.

Follow-up #18 still needs independent retained-source/body and identity verification, failure-preserving immutable version staging with monotonic pointer and crash/concurrency controls, plus an actual target-runtime acquisition receipt. #13 owns rolling-refresh integration; #12 separately requires an authorized deployment and actual live-served verification. This change neither schedules collection nor freezes rising/returning/fading thresholds.
