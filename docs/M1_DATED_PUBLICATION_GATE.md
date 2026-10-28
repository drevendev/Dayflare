# M1 dated static publication candidate (never a deployment)

Issues #18 and #12. This gate converts one **retained, source-consistent** 20-title
EN/RU Wikimedia Actions archive into a **reviewable, immutable, not-deployed**
static candidate. Its output is only \`index.html\`, \`.nojekyll\`, and
\`release-manifest.json\`; it does not touch the public M0 release, \`master\`,
\`gh-pages\`, Pages settings, or the existing hourly worker.

The existing M1 20-title CI workflow now runs the gate *after* collection,
retained-body verification, v2 local staging, two byte-identical visitor builds
and exact 700-observation checks. It bundles the existing \`artifacts/\` tree
into a temporary ZIP, revalidates every original response via the source
verifier and immutable stage replay, and includes
\`m1-release-candidate/\` in the **unpublished** successful workflow artifact.
A PR run is test evidence, **not** authorization for a public upload. The
candidate pin generated inside CI prevents accidental mismatch but is
**not** independent approval.

## Reproduce an accepted historical archive

From the repository root with Python 3.12+ and a saved successful original
M1 Actions archive ZIP extracted from the relevant accepted run:

\`\`\`sh
python -m unittest discover -s tests -p 'test_m1_publication_gate.py' -v
python -m tools.m1_publication_gate \
  --archive /path/to/retained-original-actions.zip \
  --expected-candidate-sha256 <64-hex-candidate-digest-approved-separately> \
  --destination /path/to/new-UNPUBLISHED-release
\`\`\`

The destination must not exist. The gate refuses archive path traversal,
duplicates, symlinks, non-regular entries, oversized bodies, missing or extra
members, and a candidate digest different from the supplied pin. Its
verification includes the original local \`current.json\`, complete immutable
source-bound v2 version, every retained decoded Wikimedia response, method and
window gate, candidate/receipt/seed agreement, and a **fresh source-recomputed**
preview byte-for-byte identical to both archived HTML copies and manifest.
Synthetic test provenance fails. A self-consistent receipt is **not**
cryptographic proof of Wikimedia transport origin or historical page-ID
continuity: those limits remain visible on the published-format page.

The dated static presentation changes only the three exact local-only
phrases that would be inaccurate after publication. Observed dates, original
source links, daily counts, weekly totals, uncertainty disclosures and method
version stay unchanged. The generated manifest says \`DATED_ARCHIVE_NOT_LIVE\`,
not \`DEPLOYED\`, and contains exact HTML/source SHA-256 values. No image,
article text or third-party creative assets are added.

For a *later* M1 update, pass the currently served M1 release manifest:

\`\`\`sh
python -m tools.m1_publication_gate \
  --archive /path/to/new-archive.zip \
  --expected-candidate-sha256 <reviewed-digest> \
  --previous-manifest /path/to/verified-previous-m1-release-manifest.json \
  --destination /path/to/new-UNPUBLISHED-release
\`\`\`

The gate orders complete observation-end dates first and retrieval instants
second. It refuses rollback, same-revision content collisions, dataset ID
reuse, changed method/coverage and unknown old schemas; unchanged exact
manifests are idempotent. **There is no automatic M0→M1 replacement**.
A first M1 candidate (without \`--previous-manifest\`) explicitly reports that
separate initial-publication approval is required. Even a favorable comparison
does **not** update GitHub or authorize a push.

## Outstanding publication and visitor gates

The current M0 \`gh-pages\` branch is an independent reviewed historical release,
and its manifest is not an M1 previous-manifest. Replacing it requires a
later separately reviewed transition, a fresh exact branch-head lease,
appropriate provider permissions and verified retained source rights. The
actual deployment method must preserve the prior valid branch on any
download/build/validation failure; it must never use a stale PR artifact as
a newer publication. GitHub Pages must be enabled by an authorized repository
administrator, and the served revision plus normal desktop/mobile/keyboard
browser experience must be verified before README calls the URL live.

There is no claim that an ordinary Actions archive proves public deployment or
actual independently authenticated transport; \`agent=user\` is only the
Wikimedia Pageviews filter, not verified human readers. English/Russian are
editions, not populations. This candidate does not freeze lifecycle labels,
resolve historical moves or cross-edition identity, send a digest or guarantee
that GitHub scheduled collection executes on time.
