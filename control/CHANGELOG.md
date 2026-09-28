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

## 2026-09-28 — D06 Pages/CI feasibility decision

- Accepted the static-first GitHub Actions -> versioned static artifacts -> GitHub Pages
  architecture as feasible under explicit v0 project gates.
- Removed the unsupported assumption of broad Actions artifact-storage headroom:
  owner plan and current shared Actions/Packages usage remain runtime observations.
- Made request receipts/checksums/publication metadata durable in versioned publication
  state; raw HTTP bodies are supplementary artifacts capped at 2 MiB/run with 7-day
  retention.
- Kept the v0 Pages site gate at 50 MiB, warning transfer budget at 20 GB/month, and
  fail-closed last-valid-publication behavior.
- Recorded Pages publishing-source configuration as an external maintain/admin
  capability gate; the connected worker currently has write permission.
- Marked D06 DECIDED / IMPLEMENTATION VERIFICATION PENDING. The next evidence is an
  Actions dry run measuring real Wikimedia request/runtime/artifact sizes and the
  deployment path, not another provider-documentation pass.
