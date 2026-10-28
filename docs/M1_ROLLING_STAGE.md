# M1 local monotonic rolling candidate staging

Issue #18, following merged gate #27. **Offline candidate staging only**: no Wikimedia retrieval, source authentication, public release, automatic publishing, new scheduler, or change to the retained historical M0 data.

## Reproduce

On Linux/macOS with Python >=3.12, from the repository root:

```sh
python -m unittest discover -s tests -p 'test_stage_rolling_version.py' -v
python -m tools.rolling_window_gate candidate.json
python -m tools.stage_rolling_version candidate.json /path/to/local/stage
```

Use a candidate satisfying `docs/M1_ROLLING_WINDOW_GATE.md`. Never present the synthetic test candidates as measured Wikipedia data. This command prints a deterministic JSON result explicitly labeled `LOCAL_CANDIDATE_ONLY_NOT_PUBLISHED`.

The stage root contains a `current.json` pointer, one immutable `versions/<canonical-candidate-sha256>/` directory for each accepted local candidate (canonical candidate, gate-report, manifest), and an advisory lock file. The pointer references a SHA-addressed candidate and records edition-independent method/dataset/observation/retrieval identity. A local stage is not a published or source-authenticated revision. The reader must validate the pointer and manifest/checksums before using a version. The [opt-in local atlas exporter](M1_ROLLING_PREVIEW.md) now accepts `--from-stage` for **source-bound v2 current versions only**, verifies the retained bodies and emits a separate immutable preview under a shared staging lock. Candidate-only v1 cannot be rendered this way; **no public visitor site** consumes `current.json`.

## Failure model

The gate runs before any stage write. A process-level POSIX `flock` serializes cooperating writers, and an `os.replace` of fsynced `current.json` is the atomic visibility boundary. Candidate files and manifests are fsynced and read back before promotion. A rejected/incompatible/corrupt candidate, stale observation/retrieval revision, same-revision hash conflict, reused dataset ID or method change leaves the previous valid pointer untouched. Reusing identical bytes is idempotent. An interrupted promotion may leave an unreferenced immutable version or `.incoming-*` directory, but it cannot change the last accepted pointer; a retry reconciles an intact version. A later cleanup must not delete current or uniquely retained versions.

This design assumes a local filesystem with atomic `rename`/`replace`, durable `fsync`, and **all writers obeying the same lock**. It is not an adversarial multi-host transactional storage protocol; an external writer ignoring the lock, manipulated files or a hostile shared mount invalidate its guarantees. The implementation rejects links in its controlled root/artifacts, but does not claim to defend against privileged mutation of parent directories. Network shares and non-POSIX runners are not supported.

## Remaining D08/M1 gates

The separate rolling gate checks **self-reported** Wikimedia response URLs/hashes/statuses. Hashes of input bytes or receipt agreement cannot prove upstream transport origin or stable ID/title history. Actual retained bodies, identity/move evidence, dated target-runtime retrieval and licensing checks are outstanding. Staged local candidates must not silently replace public M0 or be called fresh observed Wikipedia trends. Publication after real-source verification belongs to the source-integrated pipeline (#13), with Pages approval and live-served byte verification separately under #12.
