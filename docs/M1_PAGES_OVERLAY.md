# M1 Pages overlay: preserve the verified M0 release

Issue #12. This is **release-preparation tooling only**, not an automatic
deployment, Pages activation, provider attestation or replacement of the
existing M0 root. Keep the current M0 gh-pages root intact; stage the first
20-title dated M1 atlas at m1/index.html for a separate later review.

## Inputs and review boundary

Use an **accepted, source-verified** M1 CI evidence archive, including the
retained source/receipt/stage and root HTML. Replay that archive through
python -m tools.m1_publication_gate first, with an independently reviewed
candidate SHA-256. Do not treat an arbitrary hand-authored three-file folder
as source-authenticated. Record the resulting release-manifest SHA-256.
Accept source rights, identity limitations and the exact date before a Pages PR.

Export the exact accepted gh-pages commit as a **plain file tree**, with
no Git metadata directory. For example, in a local checkout:

    git archive gh-pages | tar -x -C /tmp/dayflare-current-pages

Then, from a checkout of the accepted Dayflare implementation:

    python -m tools.m1_pages_overlay \
      --current-pages /tmp/dayflare-current-pages \
      --candidate /tmp/source-gated-m1-release \
      --destination /tmp/dayflare-next-pages \
      --expected-candidate-sha256 <independently-verified-64-hex-candidate> \
      --expected-manifest-sha256 <independently-verified-64-hex-release-manifest>
    python -m unittest discover -s tests -p 'test_m1_pages_overlay.py' -v

All three paths must be distinct; the destination must not already exist.
The command rejects symlinks/special files, unexpected candidate members,
wrong pins, invalid timestamps, corrupted M0 root assets, M1 version collisions,
method changes, older M1 windows, and any attempt to overwrite a staged tree.
It checks every manifest-listed M0 asset against the existing root release
manifest and copies it unchanged. The separate, non-served GitHub Actions file
`.github/workflows/m1-release-candidate.yml` is accepted only at an
independently reviewed **exact Git blob** or through the earlier reviewed
two-manifest-pin template with an externally accepted current manifest digest.
The currently accepted, **invariant native-review workflow** is Git blob
`e4b1a73dcfcdd70e14366c3d5a67121913a6a999` (gh-pages PR #206,
independently approved exact head `7ee96d17b32ead9374753dfe0f4f54a5032bc47b`).
Its bytes stay identical across later dated releases: it derives a provisional
candidate-local digest for structural tests, then requires a native owner
GitHub Review of the exact PR head and manifest SHA-256 before final acceptance.
This prevents per-release workflow-code/allowlist edits without granting
automatic trust to a candidate's self-declared metadata. The previous accepted
exact workflow blobs and the older externally pinned template remain supported
for historical release preservation. Modified workflow logic or permissions,
additional unapproved metadata paths, corrupted M0 assets, and unreviewed
release heads are still rejected. The workflow remains outside the M0 asset
manifest; it must be copied byte-for-byte. A future workflow change requires
a new separate exact-head approval and explicit pin adoption, never automatic
GitHub-branch enrollment.

The rolling M1 release remains a strict three-file candidate:
`m1/index.html`, `m1/.nojekyll`, and `m1/release-manifest.json`.
The separate, accepted two-date identity explorer
`m1/identity-20261105.html` (gh-pages PR #153, Git blob SHA-1
`5dfa72c6caa846365e0143267c0446309df90a17`) is **not** a member
of that rolling candidate. It is preserved byte-for-byte on refresh only
when its exact Git blob matches the pinned, path-specific supplement
allowlist. Unknown `m1/` members, altered explorer bytes or additional
files in the newly source-gated rolling candidate fail before staging.
Only the three accepted rolling release members change in place. For each
newer independently accepted staging candidate, the preceding M1 release's
**exact** three bytestrings are also retained at
`m1/archives/<source-candidate-sha256>/{index.html,.nojekyll,release-manifest.json}`.
The source-candidate SHA-256 in the path is checked against the archived
manifest, and that manifest is checked against the exact archived HTML.
Existing archived releases are revalidated and copied unchanged; malformed,
incomplete, overwritten or nonmonotonic archives abort the entire stage.
The deliberately bounded policy retains at most **three prior versions**;
a fourth refresh is rejected until a separately reviewed retention migration
is defined. No archive is silently evicted. Both source trees and separately
reviewed supplemental evidence remain untouched.

The mutable `m1/index.html` is complemented by a **byte-identical current
archive** at `m1/archives/<current-source-candidate-sha256>/index.html`,
created during the same source-verified staging step. Up to **three previous**
versions remain under their own hashes; neither active nor previous paths
are silently replaced or evicted. On the mutable M1 page, JavaScript enhances
topic, filtered-view and pair Share links to target the same-origin immutable
current archive. Already-archived pages use their own relative query URLs,
so they do not accidentally nest archives. Without JavaScript, exact tables
and relative history links remain usable, but the mutable entrypoint's
copied query link is not promised to survive later refreshes; use a known
archive address for a durable URL. This is static routing, with no backend.

The generator and synthetic local-HTTP Chromium regression cover active
share -> immutable history/pair and restoration after a test root refresh;
byte-exact overlay and failure rollback have unit coverage. **Real Pages HTTP,
live link availability and deployment are not established** until #12's
authorized provisioning and served-version inspection. A failed staging
refresh leaves the earlier static publication intact.

A successful result is STAGED_NOT_DEPLOYED. Inspect the new directory,
compare the accepted source/manifest/pins and the diff against the fresh
gh-pages HEAD, then submit a **separate focused PR to gh-pages**. Merge only
after later exact-head review, source validation and permitted checks; do not
auto-merge from the staging run. Never force-push a branch or use a hidden PAT.

The existing gh-pages root is M0 and stays the default landing page; M1 is a
dated, selected sample at the /Dayflare/m1/ path *only if* an authorized Pages
source is enabled and the branch actually deploys. For a newer accepted M1
version, stage against the current source tree and compare its previous
m1/release-manifest.json; an older/equal conflicting revision is rejected.
On any error there is no new output release and the previous tree is untouched.
This is not a durable across-run queue or an auto-refresh publication policy.

## Honest release state

GitHub Actions ZIPs and staging files prove neither a public URL nor
Wikimedia's independently signed origin. The release retains its dated source
and title-scoped/historical-ID caveats, not a live feed or a popularity ranking.
If Pages is not provisioned, STAGED_NOT_DEPLOYED remains the only supported
status. The owner-selected Pages source is **Deploy from a branch → gh-pages →
/(root)**; the connected account currently lacks administration permission.

After an authorized deployment, verify served HTML and manifest SHA-256,
real HTTP content types, navigation/share restoration, narrow mobile,
keyboard/reduced-motion and error states; only then update the public README
and report LIVE_VERIFIED. The M1 overlay does **not** supersede those checks.

## Real M0 + M1 artifact integration (read-only)

The existing `.github/workflows/m1-curated-rolling-pageviews.yml` now stages
a **combined unpublished Pages candidate** after retaining the independently
source-gated M1 ZIP. It reads the exact `gh-pages` commit using `git ls-remote`,
fetches that commit without credentials, verifies `FETCH_HEAD`, exports its
plain file tree via `git archive`, and runs `tools.m1_pages_overlay` using
the source-candidate and generated release-manifest SHA-256 pins. The remote
`gh-pages` ref is checked again before the resulting receipt is retained.

The separate `m1-pages-overlay-*` Actions artifact contains the staged M0 root,
the additive `m1/index.html`, `m1/.nojekyll`,
`m1/release-manifest.json`, and an external
`m1-pages-stage-receipt.json` with the source `gh-pages` commit,
implementation commit, M0 asset digests, M1 source pins, and dated observation.
The original raw source archive is uploaded **first**, so failure to fetch or
stage the Pages tree does not erase the successful source archive. This
integration neither creates a Git branch/PR nor writes to Pages.

Before submitting a **separate** `gh-pages` PR, compare its latest head to the
receipt's `pages_base_commit`, inspect every file diff, and rerun the additive
gate if the branch has advanced. Never merge an unreviewed or changed candidate,
and never label the artifact DEPLOYED or LIVE_VERIFIED. An administrator's
branch-source Pages activation is still required.


## Keep the public first-screen dates aligned with accepted M1

After a **separately reviewed and accepted** publication-branch M1 release,
synchronize the README using the independent native-review manifest pin as
documented in its quickstart. Then, from the same reviewed export, synchronize
the root landing's visible observation/retrieval dates (a local change only):

    python -m tools.m1_home_window_sync \
      --accepted-m1 /tmp/dayflare-reviewed-pages/m1 \
      --expected-manifest-sha256 <independently-reviewed-M1-manifest-SHA-256>
    python -m tools.m1_home_window_sync \
      --accepted-m1 /tmp/dayflare-reviewed-pages/m1 \
      --expected-manifest-sha256 <independently-reviewed-M1-manifest-SHA-256> --write

The first command is a read-only consistency check and exits nonzero when
updates are needed. The second changes only the semantic
`site/index.html#accepted-window` paragraph. Both require a
manifest independently pinned outside the archive, matching HTML bytes, the
**already updated** README marker, canonical existing homepage dates, and
monotonic observation/retrieval revision. Older releases, tampering, ambiguous
markers and mismatched inputs leave the homepage unchanged. CI's existing
`test_m0_showcase.py` cross-source check rejects drift if either
README or homepage is updated alone. The output leaf and every output parent
are rejected when symlinked or a Windows reparse point, with a fresh check
before creating the temporary file and immediately before replacement. This
is a best-effort local guard, **not** a filesystem sandbox: a hostile concurrent
directory swap between the final check and rename is not atomically excluded.
Run on a trusted, non-concurrently modified checkout. Review and commit both
together in a normal PR; this command never deploys Pages or attests upstream
identity.
