# M1 current-title candidate discovery

This experimental bridge turns a **curated, biased selection of titles**, not
a top-pages list, into candidate numeric \`(project,page_id)\` seeds for
\`tools.m1_collect\`. The included 20 EN/RU titles across culture, books,
games, science and sport are **unverified editorial candidates**, not 20
actually retrieved pages or measured public attention.

\`\`\`sh
python -m unittest discover -s tests -p 'test_m1_title_discovery.py' -v
python -m tools.m1_title_discovery examples/m1_curated_cross_subject_enru.json evidence/m1-title-new
python -m tools.m1_title_discovery --verify examples/m1_curated_cross_subject_enru.json evidence/m1-title-new
python -m tools.m1_collect evidence/m1-title-new/identity-seeds.json evidence/m1-id-new
\`\`\`

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

## Target-runtime evidence run (not a website release)

The dedicated [M1 Wikimedia evidence workflow](../.github/workflows/m1-real-identity-evidence.yml)
runs against the exact checked-out commit after changes to this source pipeline (and
may be dispatched on demand after acceptance). It uses **read-only** GitHub
permissions, no secrets or token persistence, and never writes into `master` or
Pages. A single run makes at most **20 curated title requests + 20 independent
numeric-ID requests**, sequentially; the code enforces 10-second timeouts,
1 MiB/request and 8 MiB totals per stage, a 2-second ordinary gap and a
5-second gap after a slow (>1s) Action API response. A 429/5xx/network failure
aborts instead of retrying or replacing prior good data.

It retains two independently validated directories and a versioned run receipt
as a 7-day **UNPUBLISHED** Actions artifact. The receipt reports intended titles,
current candidate IDs, independently retained IDs, exclusions, actual EN/RU
subject coverage, source commit and exact manifest hashes. Download and review
the raw responses, title/ID agreement, rights, ambiguity and real runtime
coverage before adopting a versioned dataset or enabling public display. An
artifact or passing Actions workflow **does not** establish provider-origin
authenticity on its own, a historical ID/pageview trajectory or LIVE_VERIFIED
Pages. Missing candidates remain unavailable, never zero. If the job fails,
no new success artifact is uploaded and the previous publication remains
untouched.

The CI run is an evidence acquisition mechanism, **not** a second Dayflare worker
or an auto-publisher. Confirm the run and its artifact at the exact commit. Do
not treat local synthetic fixtures or source checks alone as successful target
runtime acquisition.
