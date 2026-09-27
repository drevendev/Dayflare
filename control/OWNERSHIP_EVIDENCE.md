# Ownership-control capability evidence

Observed and executed: 2026-09-27
Repository: `drevendev/Dayflare`
Authenticated actor: `andy-zen-dev`
Operating-model source: `drevendev/EndlessZen@89adb273df5300626688866236b82f55949c2e10`

## Question

Can the connected GitHub surface reject a stale competing repository writer strongly
enough to serve as the ownership boundary for one Git-backed semantic commit?

## Trial

Default branch head before the trial:

`555268a49b82960c31e15b0758ef4c5402147374`

Probe branch:

`ops/ownership-control-probe-20260927`

Existing candidate A on that branch:

`9b38897b073594a694b414a98c48e4953827e5a4`

Candidate A has parent
`555268a49b82960c31e15b0758ef4c5402147374`.

A fresh candidate B was created as a sibling commit from the same parent, using the
default branch tree unchanged:

`128f4b66e5df08df6f836191236feaf6d48bbfbb`

The worker then attempted to move the already-A probe branch to candidate B using
GitHub's ref update with `force=false`.

Observed provider response:

`HTTP 422: Update is not a fast forward`

Immediate readback showed that the probe branch still pointed to candidate A:

`9b38897b073594a694b414a98c48e4953827e5a4`

No force update was attempted.

## Finding

**Established:** on this connected GitHub execution surface, a non-forced branch ref
update rejects a stale sibling commit and leaves the newer/current ref unchanged.

## Adopted control

For repository-canonical mutations, the writer must:

1. read the exact current work-branch head;
2. build the entire semantic change as one Git tree/commit whose parent is that head;
3. update the branch ref with `force=false`;
4. read the ref back and require the expected commit;
5. on non-fast-forward/conflict or ambiguous response, stop affected writes and
   re-orient from the new ref.

This gives the artifact/registry/changelog/state package one provider-enforced Git
commit boundary rather than several independently writable files.

## Limits

This evidence is intentionally narrow.

- It proves Git-ref stale-writer rejection, not global serialization of every GitHub
  API surface.
- It does not fence issue comments, repository/Pages settings, releases, deployment
  environment changes, or other provider-side mutations.
- It does not make several separate API writes atomic.
- It does not authorize force-push.
- A branch commit still requires later review/PR/merge gates before it changes the
  default branch.

Those limits remain explicit so later runs do not silently promote this trial into a
stronger guarantee than was actually exercised.
