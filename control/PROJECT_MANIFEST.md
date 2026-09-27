# Dayflare Project Manifest

## Identity

- Project: Dayflare
- Repository: `drevendev/Dayflare`
- Canonical project state: repository-canonical
- Operating-model source: `drevendev/EndlessZen@89adb273df5300626688866236b82f55949c2e10`
- Current profile: research
- Initial product anchor: issue #1

## Goal

Build a broadly useful visual atlas of changing public attention. The first bounded
source scope is English and Russian Wikipedia. A visitor should be able to discover
topics that are rising, returning, or fading, inspect the evidence, compare language
editions, and share a precise view.

The primary journey is:

`overview -> discover a change -> inspect a topic -> compare -> share`

## Architecture boundary

`scheduled CI -> collect -> validate -> calculate -> versioned static artifacts -> GitHub Pages`

Routine collection and calculation belong in reproducible scripts. Visitors must not
need an agent or paid inference per request. Failed ingestion must not replace the last
valid publication.

## Authority and boundaries

The owner authorizes end-to-end development of Dayflare in this repository. Provider
permissions still gate individual operations. The scheduled worker must verify the
connected identity and current permissions before writes.

Dayflare is the only development target for this worker. Other repositories may be
read when directly useful, but are not mutation targets.

No parallel Google Drive control plane is authorized. Repository files, Issues, PRs,
commits, checks, and Pages are the durable project surfaces.

## Ownership, commit boundary, and schedule lifecycle

OWNERSHIP_CONTROL: GIT_REF_FAST_FORWARD_TRANSACTION
OWNERSHIP_EVIDENCE: `control/OWNERSHIP_EVIDENCE.md`
SCHEDULE_LIFECYCLE_OWNER: owner/operator outside the ordinary worker
STOP_ACTION: only an explicit owner instruction may pause, disable, delete, retire, or replace the recurring worker

Canonical repository mutations use a provider-enforced Git ref boundary. A writer must
read the exact current work-branch head, build the complete intended tree as one commit
whose parent is that observed head, and publish it only with a non-forced ref update.
A stale sibling update is rejected by GitHub as non-fast-forward; on rejection or an
ambiguous response, the writer stops affected writes, reads the ref again, and
re-orients. Routine canonical multi-file changes must not use a sequence of Contents API
writes as the ownership boundary.

Protected resources under this control are repository-canonical control files, research
registry/artifacts/changelog changes, implementation files, and workflow/publication
inputs that belong to one semantic commit. The scheduled worker, manual recovery, and
other project writers must use the same ref transaction when mutating those resources.
Issue comments, repository settings, Pages settings, releases, and other provider
surfaces are not fenced by this Git ref mechanism and require their own capability/gate
before they can satisfy an acceptance criterion.

The control has no lease and no client-side lock token. Safe handoff is the Git ref
itself: once another commit advances the observed branch head, a writer still based on
the prior head can no longer publish a sibling commit with `force=false`. Force-push is
not an ownership-recovery mechanism.

## Measurement invariants

- Absence from a top-N list is not zero views.
- Candidate discovery and full-history acquisition are separate stages.
- Equivalent metrics and complete windows are compared.
- Missing data, redirects, page moves, automated traffic, tiny denominators, and
  recurring calendar effects remain explicit.
- Topic identity is never inferred by title alone when stronger identifiers exist.
- Attention is not importance, approval, truth, unique people, or causation.
- Cross-language comparisons describe Wikipedia editions, not countries or populations.
- Missing mappings remain missing.
- Method changes are versioned rather than silently rewriting meaning.

## Research phase

The initial research registry is D01-D08 in `research/REGISTRY.md`. D01 and D02 are
the current leading gates. D03 must be revalidated and persisted before it can be
treated as a durable decision.

Research findings distinguish established, reasoned, assumed, and unknown evidence.
A research unit must change a decision, constraint, test, backlog item, or explicitly
record a non-decision.

## Transition to engineering

The project may transition from the research profile to the engineering profile only
after D08 establishes a small ordered implementation backlog with evidence,
dependencies, non-goals, and acceptance checks, and the earlier research gates needed
by that backlog are satisfied or explicitly bounded.

The transition is a recorded project decision; it does not erase research work.

## Completion gates

Dayflare is not complete until all of the following are demonstrated:

- architecture and data path are implemented and reproducible;
- required research questions are answered or explicitly marked not decidable;
- source provenance and method versions are inspectable;
- incomplete/stale data behavior is explicit and tested;
- the public interface is usable on mobile and by keyboard and has a reduced-motion path;
- exact values and source evidence are available without relying on visual encoding;
- publication preserves the last valid build on ingestion failure;
- relevant consistency and simplicity reviews have passed;
- at least one consumer-perspective review of the public artifact has passed;
- no critical blocker remains.

Completion does not authorize this scheduled worker to disable its own schedule.
