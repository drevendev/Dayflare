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

The initial research registry is D01-D08 in `research/REGISTRY.md`. D01 remains the
leading runtime-evidence gate and D02 remains partial pending the real D01 sample.
D03 is a durable decided research result in `research/D03_IDENTITY_MODEL.md`; any
future semantic change to that identity model must be versioned.

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
