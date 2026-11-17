# M1 current-title candidate discovery

This experimental bridge turns a **curated, biased selection of titles**, not
a top-pages list, into candidate numeric \`(project,page_id)\` seeds for
\`tools.m1_collect\`. The original 20 EN/RU titles across culture, books, games, science and sport
remain the editorial reference for earlier evidence. The distinct
`examples/m1_curated_expanded_30_enru.json` retains all 20 selections and adds
five EN/RU pairs (photography, science fiction, Minecraft, DNA and tennis).
At selection time, all 30 were **unverified editorial candidates**; a
later source run must be inspected separately. Current page metadata never
establishes stable historical identity or measured public attention.

**2026-11-16 actual runtime follow-up (unpublished):** [master source run 43797600325](https://github.com/drevendev/Dayflare/actions/runs/43797600325) for commit `36b9598f` retained **29/30** current title candidates and **29/29** successful independent numeric-ID re-queries. The Russian short title `ДНК` was **excluded as a redirect**, as required by fail-closed source handling (raw `m1-title/raw/18.json`, SHA-256 `3f3af299dac2f0f24f0dbad7ad2d0efa897900537e2ea9209b2876a501dde033`). The editorial **next-run candidate** is the full Russian article title `Дезоксирибонуклеиновая кислота`; its existence as a Wikipedia article does **not** yet prove Action API acceptance or a retained page ID. This correction neither modifies the prior receipt nor upgrades 29 identities into 30, and adds no pageview history. Inspect a subsequent exact-head master evidence run and raw-body/rights acceptance before revising measured coverage.

\`\`\`sh
python -m unittest discover -s tests -p 'test_m1_title_discovery.py' -v
python -m tools.m1_title_discovery examples/m1_curated_cross_subject_enru.json evidence/m1-title-new
python -m tools.m1_title_discovery --verify examples/m1_curated_cross_subject_enru.json evidence/m1-title-new
python -m tools.m1_collect evidence/m1-title-new/identity-seeds.json evidence/m1-id-new
\`\`\`

For the expanded candidate panel, substitute
`examples/m1_curated_expanded_30_enru.json` and use a **new** destination.
The accepted 20-title pageview atlas and manifest are unchanged. New candidate
discovery is not a release or a new measured pageview history.

The destination must have an existing real parent and **must not exist**.
Discovery stores exact Action API response bodies, per-request URL, UTC
observation time, SHA-256, exclusions and a versioned LOCAL_ONLY receipt.
Offline replay checks source/seed consistency and declared inventory; it cannot
authenticate network origin, network timestamps, source rights or historical
continuity. Redirects, normalizations, missing pages, duplicate IDs and
ambiguous responses never become assumed identities. The batch stops on unsafe
inputs; retries and automatic title stitching are intentionally absent.

The existing \`m1_collect\` independently re-queries every obtained numeric
ID before validation. No live provider retrieval, historical moves/deletes
evaluation, publication, Pages deployment, or user study is implied by this
feature. Preserve D03 and the unresolved broader real coverage work in #19.

## 2026-11-16: complete 30/30 current-ID evidence; no pageview promotion

The corrected exact-master [Action API run 43809220786](https://github.com/drevendev/Dayflare/actions/runs/43809220786)
at commit `6609af6b9de41f2520819779579cedfdf98436d1` completed on
2026-11-16 05:19 UTC. **30 titles were requested, 30 current numeric page IDs
were obtained, and all 30 were independently re-queried; no exclusion.**
Three current metadata candidates were retained for each edition/subject
cell. RU DNA was observed as `Дезоксирибонуклеиновая кислота`, current
`ru.wikipedia` page ID **10889**. The 29/30 predecessor remains a separate,
unchanged historical receipt.

[Unpublished source artifact #14199229965](https://github.com/drevendev/Dayflare/actions/runs/43809220786)
expires 2026-11-23 05:19 UTC. The downloaded ZIP's SHA-256 is
`4a44f9dbfa4b620bd0aa91e32c0a30b6afe823e38b8fa1e3a28561ea19a1d01c`.
Local replay independently checked all 30 title response hashes and
ID/title fields, all 30 re-query response hashes and ID/title fields,
and every file listed in the identity manifest. The run receipt's
discovery and identity hashes match its retained files. These checks
confirm **internal consistency of recorded provider bytes**, not
cryptographic upstream-origin authentication, durable cross-day page-ID
continuity, historical Analytics title continuity, pageview coverage,
or a reviewed public website.

An additional success-only job in the **same read-only evidence workflow**
now proposes a 30-title historical candidate. Only after a fresh complete
30/30 identity source bundle is reverified does it construct current
title-scoped Analytics seeds using `m1_pageview_handoff`, collect exactly
30 separate 35-day histories, source-verify/stage them, build deterministic
offline HTML, check 30 discovery/detail links and retain an **unpublished**
30-day artifact on future successful runs (subject to repository Actions retention settings). Partial identity or pageview failure produces no
successful new artifact; existing archives/Pages are not mutated. The accepted-master [run 43824410141](https://github.com/drevendev/Dayflare/actions/runs/43824410141) on 2026-11-16 reported 30 complete 35-day title-scoped histories (1,050 daily requests, 2026-10-10–2026-11-13 UTC) in a **seven-day artifact created before this change**. Its retained raw-source hashes and a local visitor preview were inspected; the long Russian heading mobile overflow was separately repaired in merged PR #267. The artifact is still **UNPUBLISHED**; source consistency does not independently authenticate upstream origin, historical page-ID continuity or a Pages deployment. Historical title changes
remain unverified, and the existing 20-title accepted atlas is untouched.

## Target-runtime evidence run (not a website release)

The dedicated [M1 Wikimedia evidence workflow](../.github/workflows/m1-real-identity-evidence.yml)
runs against the exact checked-out commit after changes to this source pipeline (and
may be dispatched on demand after acceptance). It uses **read-only** GitHub
permissions, no secrets or token persistence, and never writes into `master` or
Pages. The default accepted-master acquisition makes at most **30 curated title requests + 30 independent
numeric-ID requests**, sequentially; the code enforces 10-second timeouts,
1 MiB/request and 8 MiB totals per stage, a 2-second ordinary gap and a
5-second gap after a slow (>1s) Action API response. A 429/5xx/network failure
aborts instead of retrying or replacing prior good data.

It retains two independently validated directories and a versioned run receipt
as a success-only **30-day UNPUBLISHED** Actions artifact on future accepted-master runs (subject to repository retention settings); earlier seven-day artifacts retain their original expiration. The receipt reports 30 intended titles, current candidate IDs, independently
retained IDs, exclusions, actual EN/RU
subject coverage, source commit and exact manifest hashes. Download and review
the raw responses, title/ID agreement, rights, ambiguity and real runtime
coverage before adopting a versioned dataset or enabling public display. An
artifact or passing Actions workflow **does not** establish provider-origin
authenticity on its own, a historical ID/pageview trajectory or LIVE_VERIFIED
Pages. Missing candidates remain unavailable, never zero. If the job fails,
no new success artifact is uploaded and the previous publication remains
untouched.

The manually dispatched `stable-id-followup` mode intentionally remains bound
to the earlier separately accepted 20-ID historical baseline; it is **not**
expanded. Excluded or unavailable titles are unknown, not zero views.

The CI run is an evidence acquisition mechanism, **not** a second Dayflare worker
or an auto-publisher. Confirm the run and its artifact at the exact commit. Do
not treat local synthetic fixtures or source checks alone as successful target
runtime acquisition.
