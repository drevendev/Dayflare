## Compact source capsule (offline, not a publication)

The 30-title Actions ZIP includes duplicate stages, HTML and screenshots. The optional
source capsule preserves only the 33 exact UTF-8 source members (candidate, seeds,
source receipt and 30 decoded response bodies) as a bounded XZ/base64 text file. It is
**not** the original Actions ZIP or browser receipt. Keep those separately. No new
provider request is needed. Independently review the original ZIP pin before packing
and the capsule pin before replay. A pin asserted inside the capsule is not proof
that its members originated from that ZIP; review the exact byte round-trip first.

```sh
python -m tools.m1_30_source_capsule pack original.zip source.xz.b64 \
  --original-sha256 ORIGINAL_SHA256
python -m tools.m1_30_source_capsule replay source.xz.b64 new-preview \
  --original-sha256 ORIGINAL_SHA256 --capsule-sha256 CAPSULE_SHA256
```

Use a new destination. Replay calls the existing source verifier and renderer with
the historical retrieval timestamp. It does not certify independent provider origin,
new browser acceptance, page-ID continuity, release or Pages deployment. Keep the
older retained dated evidence unchanged. The current capsule schema is bounded to
30 titles and does not enroll new trust automatically.

```sh
python -m unittest discover -s tests -p 'test_m1_30_source_capsule.py' -v
```
