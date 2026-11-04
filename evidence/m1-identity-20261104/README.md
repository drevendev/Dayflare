# Real EN/RU identity baseline — 4 November 2026

This retained source is **one historical metadata observation**, not pageviews,
verified continuous identity, a two-date comparison or a live publication.
It keeps 20 actual current-page ID re-queries across English and Russian Wikipedia
and five editorial subjects: culture, books, games, science and sport.
Each edition/subject cell contains two observed pages. Selection is not representative.

## Origin and exact retention

Original [Actions run 41814628479](https://github.com/drevendev/Dayflare/actions/runs/41814628479),
source `90c0f4db491680246d73190bac1545f021779c07`, artifact `13314391318`.
The original 27,115-byte downloaded ZIP matches GitHub's reported SHA-256
`be8b859c6d1803672300f75436fb620891aee434cb4d5507146e417f0b6c9995`.
The provider's temporary archive expires on 11 November 2026; these repository
bytes do not depend on that retention period.

`source.zip` is a **deterministic data-only repack**, not the original ZIP. It retains
all 24 files beneath the original `m1-identity/` prefix, with each file's bytes
unchanged. The unrelated title-discovery directory and outer run-summary file
are omitted, not independently certified by this capsule.

| Retained fact | Value |
| --- | --- |
| Actual observation date (UTC) | 2026-11-04 |
| First / last ID request (UTC) | 10:31:14 / 10:31:55 |
| Intended / obtained IDs | 20 / 20 |
| Capsule / decoded member bytes | 15,547 / 45,118 |
| Retained decoded raw response bytes | 5,966 |
| Members | original panel, collection report, consistency proof, bundle manifest and 20 raw JSON bodies |
| Capsule SHA-256 | `dc2af08e39296b901e323285793eb0c6268219dab6aac887f4596fc8d881765a` |

The panel's `selected_at=2026-10-24` and old panel name are **selection metadata**,
not this observation's date. Do not relabel it as an October observation.
[provenance.json](provenance.json) records the exact artifact, repack and scope.

## Verify and browse

From the repository root, with Python 3.12 or newer:

```sh
python -m tools.m1_retained_identity
python -m tools.m1_retained_identity /tmp/dayflare-real-baseline
python -m tools.m1_retained_identity --check /tmp/dayflare-real-baseline
python -m http.server 8000 --directory /tmp/dayflare-real-baseline
# Open http://localhost:8000/ — local preview, not a public deployment.
```

The adapter pins the capsule and provenance, validates a bounded exact ZIP
inventory, and reuses the existing D03, raw-source and bundle verifiers. It
recomputes agreement of IDs, titles, QIDs, source endpoints, timestamps, hashes,
byte totals and coverage. It never downloads fresh data. A source mismatch fails
before creating a preview; an existing output is never replaced.

## Rights and measurement boundaries

Only factual API metadata is retained. No article prose, images, credentials or
private operational data are included. API access is not a license for article
content or images. Wikidata structured identifiers are CC0; this is not a blanket
relicensing statement for all Wikipedia content. Primary references checked
4 November 2026:

- [MediaWiki page properties](https://www.mediawiki.org/wiki/API:Pageprops).
- [Wikidata licensing](https://www.wikidata.org/wiki/Wikidata:Licensing).
- [Wikimedia robot policy](https://wikitech.wikimedia.org/wiki/Robot_policy).

The existing collector's pacing, compression, request/byte/time limits remain
unchanged. This adoption makes **zero new Wikimedia requests**. Retained raw files
are decoded JSON entities, not compressed wire bodies. Checksums and replays prove
internal byte agreement, **not independent authentication of the original transport**.
Current IDs/QIDs do not prove old title-scoped pageview histories, move/delete
continuity or cross-edition equivalence. Unresolved mappings stay unresolved.

## Next source, not an invented comparison

Issue [#145](https://github.com/drevendev/Dayflare/issues/145) still needs a genuine
second UTC observation date. The 24 October source run returned no downloadable
artifacts during this adoption; its retained site projection cannot recreate lost
raw responses. The exported `source/panel.json` preserves the original schema
accepted by the history comparator. Keep this baseline immutable and compare it
with a separately acquired, validated later panel. No retention scheduler, live
posting, auto-publishing or Pages provisioning is introduced here.
