# M1: identity-bundle → bounded title-scoped pageview seeds

This is a **local-only evidence handoff** for #13/#19. It connects the existing
M1 Action API identity-bundle gate to the existing one-shot Analytics collector;
it does **not** obtain Wikimedia responses, establish historical identity
continuity, or publish anything.

## Prerequisites

Acquire a **real, reviewed** `dayflare.identity-seeds.v1` input by stable
`(project,page_id)` and run `tools.m1_collect` into a unique output directory.
Re-verify its raw JSON evidence with `tools.m1_bundle_verify`. Do **not** use
`examples/synthetic_identity_seed.json` or synthetic M1 panels as real inputs.
Identity observations must be at most one UTC day old. Never infer ID from title.

```sh
python -m tools.m1_collect vetted-identities.json /tmp/identity-run-unique
python -m tools.m1_bundle_verify /tmp/identity-run-unique
python -m tools.m1_pageview_handoff /tmp/identity-run-unique /tmp/pageview-handoff-unique
cat /tmp/pageview-handoff-unique/handoff.json
# Only after independent provider/rights/identity review:
python -m tools.rolling_pageview_source collect \
  /tmp/pageview-handoff-unique/seeds.json /tmp/pageview-run-unique
python -m tools.rolling_pageview_source verify /tmp/pageview-run-unique
```

The handoff reopens and revalidates the **entire retained** identity bundle,
including each source body, manifest, schema, ID, title, date and receipt. It
produces canonical `seeds.json` and `handoff.json` in a unique, no-replace
directory, without network access. Duplicate normalized title claims within an
edition fail closed, even when page IDs differ. Redirects, recorded identity
events, stale/future title observations and unsupported subjects are excluded
with explicit reasons. An empty or >30-page selection fails rather than padding
missing pages or silently truncating the request budget.

`handoff.json` binds the identity bundle manifest SHA-256 and explicitly records
uncertain continuity, exclusions and `LOCAL_SEEDS_ONLY_NOT_PUBLISHED`. A verified
**current** `(project,page_id,title)` still does not prove that this title
belonged to that page throughout the preceding 35 days: Analytics is
**title-scoped**, while Action API `pageids` is ID-scoped. Treat the resulting
pageviews as title histories, not stable-page-ID trajectories. Missing title
or identity evidence does not mean zero views. Source-receipt hashes establish
internal consistency, **not independent upstream authentication**. Any moves,
redirects, page restorations, source rights and data usage require separate
review before promoting data to the public atlas.

Verification:

```sh
python -m unittest discover -s tests -p 'test_m1_pageview_handoff.py' -v
python -m compileall -q tools/m1_pageview_handoff.py tests/test_m1_pageview_handoff.py
```

Synthetic regression tests do **not** establish real Wikimedia collection,
website quality, browser readiness or publication. No CI scheduler or Pages
configuration is altered by this module.
