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
It checks every original M0 file against the existing root release manifest,
copies it unchanged, and adds/replaces **only** the separately dated M1 subtree.
Both original input trees remain untouched.

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
