# Preserve a real 30-title EN/RU atlas outside expiring CI artifacts

Issue #12. **Offline, unpublished evidence preservation; not an accepted or deployed release.** This is a separate 30-editorially-selected-title, 35-day source snapshot, not an update to the independently accepted 20-title archive under `gh-pages/m1/`. No Pages write, privileged token, source re-query, live freshness assertion, lifecycle classification, or historical page-ID continuity is introduced.

## Reproduce from a successful Actions run

Save the **original** successful `m1-30-local-pageviews-*` artifact ZIP from the read-only `M1 real EN/RU identity evidence` workflow (not an HTML-only download), then run:

```sh
python -m unittest tests.test_m1_30_archive -v
python -m tools.m1_30_archive /path/to/original-actions.zip /path/to/NEW-preserved-30.zip
sha256sum /path/to/NEW-preserved-30.zip
```

The destination must not exist. The output is a deterministic, ZIP-contained snapshot of the original source files, decoded Wikimedia API bodies, 30 candidate histories, gate/seed/identity receipts, static offline HTML, browser screenshots and verification receipts. Its additional `archive-manifest.json` binds every original member by SHA-256, with source commit, dataset ID, observation window and exact HTML checksum. The ZIP and its independently recorded digest can be stored in a durable, separately reviewed release; **creating the ZIP does not persist it in GitHub or change public Pages**. A later release acceptance must independently pin the ZIP digest, perform consumer/rights review and preserve the last accepted 20-title release.

The exporter rejects absent, modified or duplicate raw sources, altered daily counts, mismatched candidate, versioned stage, identity/HTML/browser pins, missing 35-day windows or subjects, 320/390/1280 screenshot failures, unsafe ZIP paths, source size excess and overwriting existing output. It reads no secrets and uses no network.

## Actual source verification (2026-11-17)

At commit `62a50e564ed0dd55dacb66f5de9a5970e17121a9`, real [workflow #44046865069](https://github.com/drevendev/Dayflare/actions/runs/44046865069) produced [artifact #14312401439](https://github.com/drevendev/Dayflare/actions/runs/44046865069/artifacts/14312401439), expiring 2026-12-17. Independently reproduced locally from those archived source bytes:

- Dataset ID `run-20261117-083055-361cff6a3eb7`, candidate SHA-256 `8c2c164d6bc35ca22786efba3a3581e76290a68de3a1006928acd79013c912f1`.
- EN and RU Wikipedia: 3 selected pages × 5 subjects × 2 editions = **30 complete title histories**, 1,050 exact daily observations over 2026-10-11–2026-11-14 UTC.
- HTML SHA-256 `0262703952c5f8d1c70781c60f054ebfdbc048c9e602030a3d3e660bcc579c08`; local Chromium evidence includes 320, 390 and 1280 px screenshots.
- Original Actions artifact ZIP SHA-256 `86133de1ed074266b172c1aa682a4cdbbaa01b3799061e78d9f9acb37d00032d`.

The archive reports **source bytes and runtime-reported HTTP transport, not cryptographic proof that Wikimedia served them**. Selection is biased, titles do not prove historic page-ID continuity, and `agent=user` does not verify unique human readers. Every preserved HTML headline must remain marked as a dated local preview until a separate authorized public review and verified Pages deployment.

## Verify a saved preservation ZIP and extract its offline atlas

A consumer can now validate an already-built preserved ZIP without Wikimedia
access or GitHub Actions, then open its *existing* standalone HTML. The exact ZIP
SHA-256 must come from an independent reviewed handoff; an archive's embedded
manifest is not its own trust anchor. The command re-verifies every member,
30 distinct source histories, 35 observed UTC days per title, source/identity
linkage, and all three browser screenshot receipts before writing any HTML:

```sh
python -m unittest discover -s tests -p 'test_m1_30_consume.py' -v
python -m tools.m1_30_consume /path/to/preserved.zip \
  --expected-sha256 0473e8b52f90df70c227e648a06bbae1e833740844dff77f8c28ef1e32e2b0c4 \
  --html-out /path/to/NEW-dayflare-30.html
# Open the new HTML offline. Existing output files are never overwritten.
```

The digest shown is for the **specific 17 November 2026 example** built from
Actions run #44046865069 / artifact #14312401439, not a generic allowlist.
Different future archives require their own independent digest. Invalid pins,
unknown entries, missing/corrupt raw data, forged status, malformed ZIP paths,
or existing destinations fail closed. Extracting the reader does **not** approve
upstream authentication, change the accepted 20-title release, deploy Pages,
or claim the snapshot is live or representative.

## Git-retained original decoded Pageviews bodies (partial preservation)

The immutable `evidence/m1-30-20261117-raw-pages.xz.b64` is a **separate
source-body capsule** containing the exact decoded response bytes of all 30
2026-11-17 EN/RU Wikimedia Pageviews requests. It was extracted from the
original validated Actions bundle, not reconstructed from normalized counts.
Its source file is checked against the existing independently pinned
`evidence/m1-30-20261117-candidate.xz.b64`.

From a clean checkout, no network/third-party packages needed:

```sh
python -m unittest tests.test_m1_30_raw_archive -v
python -m tools.m1_30_raw_archive
python -m tools.m1_30_raw_archive --output /tmp/dayflare-new-raw-30
# Exactly 30 original JSON bodies, each checked against candidate per-body SHA-256.
# Output directory must not already exist. Never overwrite existing raw evidence.
```

This capsule is 7,681 bytes of canonical base64 armor (5,760 decoded XZ
bytes), representing 30 original JSON bodies totalling 159,888 bytes.
Each body's original SHA-256, request date/filter/URL and exact 35 daily values
are cross-checked against the retained normalized candidate. The capsule's
decoded JSON manifest is pinned to SHA-256
`9cbed114a098d15ba3e53d9127506b8596954fce2e752de8eab5ee814d7c957d`
and the compressed XZ to
`dcdb125bc3b3d4c65e9e8715a7377e870e3b1bd6dc460c04825c704514f37fd0`.

**Partial only:** the compact capsule does *not* retain the original
transport-level wire gzip bytes, complete source/identity/seed receipts, stage
duplications, 320/390/1280 Chromium screenshots, or the full 148-original-file
archive. [Actions artifact #14312401439](https://github.com/drevendev/Dayflare/actions/runs/44046865069/artifacts/14312401439)
still expires on **2026-12-17**. Keep the independently verified complete
ZIP and digest under #12; this Git-retained subset does not establish provider
authenticity, public release approval, Pages provisioning or LIVE_VERIFIED.
