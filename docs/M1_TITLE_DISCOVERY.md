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
