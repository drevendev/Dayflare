UNIT_ID: D06
CREATED_BY_RUN: 2026-09-27T07:20Z
SOURCE_REVISION: 2
SUPERSEDES: —

# D06 — GitHub Pages / Actions feasibility and operating budgets

## Decision

Dayflare's intended static-first architecture is feasible within current GitHub Actions
and GitHub Pages limits with wide headroom, provided the first release remains bounded.

One activation blocker is explicit: the connected maintainer `andy-zen-dev` currently
has repository permission `write`, while GitHub requires `maintain` or `admin` to
configure a Pages publishing source. The worker can author and test the workflow, but it
must not claim a live Pages deployment until that repository setting is enabled by an
authorized maintainer/admin or independently verified as already configured.

This is a design-level decision. D01 still has to measure actual Wikimedia response
sizes/runtime, and the first Pages dry run must measure the generated artifact before
budgets are widened.

## Observed repository state

Observed 2026-09-27:

- repository: `drevendev/Dayflare`;
- visibility: public;
- authenticated actor: `andy-zen-dev`;
- repository permission: `write`;
- default branch head: `555268a49b82960c31e15b0758ef4c5402147374`;
- default branch currently has no `.github/` directory or Pages workflow.

## Primary provider evidence

Reviewed 2026-09-27:

1. GitHub Pages limits:
   https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
   - published site <= 1 GB;
   - Pages deployments time out after 10 minutes;
   - soft bandwidth limit 100 GB/month;
   - soft 10 builds/hour limit does not apply when a custom Actions workflow builds
     and publishes the site.

2. GitHub Actions limits:
   https://docs.github.com/en/actions/reference/limits
   - a GitHub-hosted job may execute for up to 6 hours;
   - workflow limits are far above Dayflare's intended one-daily-run shape.

3. Scheduled workflow semantics:
   https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
   - scheduled workflows run from the default branch;
   - schedules can be delayed, especially near the start of an hour, and sufficiently
     loaded periods can drop queued jobs;
   - public-repository schedules are automatically disabled after 60 days without
     repository activity.

4. Custom Pages workflows:
   https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
   - deployment requires at least `pages: write` and `id-token: write`;
   - the normal target environment is `github-pages`.

5. Publishing-source permission:
   https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site
   - configuring a Pages publishing source requires repository maintain/admin
     permission.

6. Actions retention:
   https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository
   - artifacts and logs default to 90-day retention;
   - public repositories may configure retention only from 1 to 90 days;
   - GitHub's checks/workflow-run/status retention policy changes on 2026-10-01, so
     workflow history must not be the sole durable provenance store.

7. Actions billing/usage:
   https://docs.github.com/en/actions/concepts/billing-and-usage
   - standard GitHub-hosted runners are free for public repositories.

## V0 self-imposed budgets

These are Dayflare safety budgets, not claims about provider maxima.

### Request budget

- One normal collection run per day.
- Candidate schedule: 04:17 UTC, deliberately away from minute 0.
- Also expose `workflow_dispatch` for controlled manual recovery.
- Maximum 600 Wikimedia requests per run.
- Keep source traffic sequential or equivalently bounded to <= 1 request/second with
  retry/backoff.
- Collector job timeout: 20 minutes.

A 600-request ceiling is enough for a few hundred page-edition histories plus bounded
candidate-discovery calls. D01 must measure actual latency and response sizes before the
ceiling is increased.

### Evidence and artifact storage

Do not accumulate unbounded raw source history in Git.

- Raw HTTP bodies + request receipts: Actions artifact, hard cap 10 MiB/run.
- Raw artifact retention: 30 days.
- Worst-case retained raw-artifact budget at the project cap: about 300 MiB before
  expiry.
- Persist request checksums, coverage, endpoint parameters, source version and method
  version in the versioned publication manifest; logs are supplementary evidence only.
- Reconstruct the bounded public history from Wikimedia on each successful run rather
  than using Git as an append-only raw-data warehouse.
- Public observation retention for v0: at most 90 daily observation days.
- Hard publication gate: generated Pages site <= 50 MiB during v0.

The 50 MiB project gate is intentionally far below the current 1 GB Pages site limit
and leaves room to revise the representation without approaching provider limits.

### Transfer budget

Keep data chunked instead of making every visitor download the full retained corpus.

- Initial route: <= 1 MiB compressed for HTML, app shell and overview data combined.
- One topic-detail data chunk: <= 100 KiB compressed.
- Dayflare warning budget: 20 GB/month served transfer.

The project warning budget leaves 5x headroom below GitHub Pages' current soft
100 GB/month limit. Crossing the Dayflare warning budget requires measuring traffic and
payloads before adding more data, not merely accepting the provider ceiling.

### Build/deployment budget

- Self-imposed build budget: < 5 minutes.
- Self-imposed deploy budget: < 5 minutes.
- Use one publication concurrency group so two runs cannot publish concurrently.
- Do not use the provider's 6-hour job ceiling as a normal operating budget.

## Failure and publication semantics

The v0 pipeline remains:

`schedule/manual -> collect staging -> validate -> calculate -> build static artifact -> deploy`

Publication is fail-closed. A failed source request, incomplete required window, schema
violation, calculation failure or budget breach does not replace the live site. The
last valid Pages deployment remains available.

Every valid snapshot must carry:

- `observed_through`;
- `retrieved_at`;
- `published_at`;
- source/API semantics version;
- Dayflare method version;
- coverage/completeness state;
- receipt/checksum references.

That lets the already-published client show an old last-successful observation as stale
without requiring a failed ingestion run to overwrite the site.

Scheduled execution time is not observation time. If a scheduled run is delayed or
dropped, the next successful run explicitly targets/backfills the missing complete
observation window. It must not silently substitute the time at which the job happened
to execute.

## Consequences for implementation

The first engineering slice for this decision should:

1. author a bounded collector workflow without enabling live Pages publication;
2. measure D01 request count, bytes and elapsed time on GitHub Actions;
3. build the static artifact and assert the budgets above;
4. only after Pages source configuration is enabled, add the deploy job with minimum
   required permissions;
5. verify failed-ingestion fallback by forcing a validation failure and confirming the
   previous publication remains unchanged.

## Status

**D06: design decision established; deployment verification pending.**

The architecture fits current provider limits. Remaining evidence is implementation
verification, not an unresolved architecture question. The explicit external capability
gate is initial Pages source configuration under maintain/admin authority.
