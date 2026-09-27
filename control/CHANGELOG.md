# Dayflare Changelog and Decisions

This file records changes to project meaning and canonical control state. Git history
records file edits; this log records why those edits matter.

## 2026-09-24 — Repository bootstrap

- Initial base commit `a0c75877c599bccd9dd8c45e530e78f4c0a75e4c` established
  `master` and a minimal README.
- No runtime, data collector, deployment, or validated coverage was claimed.

## 2026-09-24 — Canonical controls proposed

- Declared GitHub/repository state as the sole canonical mutable project state.
- Pinned the operating-model source to
  `drevendev/EndlessZen@89adb273df5300626688866236b82f55949c2e10`.
- Adopted issue #1 plus its durable comments as bootstrap provenance rather than an
  equal mutable control plane.
- Reconciled D01 as OPEN and D02 as PARTIAL from their durable issue comments.
- Explicitly left D03 OPEN because no durable D03 result is present in GitHub.
- Declared D01 runtime verification the first queued production/research unit after
  these controls merge.

## 2026-09-27 — Provider-enforced Git ownership control verified

- Verified the actual connected GitHub surface rejects a stale sibling branch update:
  candidate B `128f4b66e5df08df6f836191236feaf6d48bbfbb`, built from the same parent
  as the existing probe head, was rejected by non-forced `update_ref` with HTTP 422
  `Update is not a fast forward`.
- Readback confirmed probe branch `ops/ownership-control-probe-20260927` remained at
  candidate A `9b38897b073594a694b414a98c48e4953827e5a4`.
- Adopted `GIT_REF_FAST_FORWARD_TRANSACTION` as the repository ownership/commit
  boundary: one complete Git commit from the exact observed branch head, followed by a
  non-forced ref update and readback.
- Sequential Contents API writes are not accepted as the ownership boundary for a
  coherent canonical multi-file mutation.
- The mechanism fences Git-backed state only; issue comments, settings, Pages
  configuration, releases, and other provider surfaces require separate gates.
- Corrected the state's recorded default-branch base to
  `555268a49b82960c31e15b0758ef4c5402147374`.
