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

### Export distinct weekly signals for analysis

After independently verifying the retained capsule, export one row per selected title
without a new provider request or HTML build:

```sh
python -m tools.m1_30_signal_csv evidence/m1-30-20261124-source.xz.b64 signals.csv \
  --original-sha256 1721869d687dd5f1b08b9ba9dcd963f8477299151f7f1c5f24090222c14fc305 \
  --capsule-sha256 10d7fa4ed4b7c2bdab98d3c7d4c64a70d12b27aa15df5d4fd67f16194b93c543
```

The exporter checks the original retained bodies with the existing source verifier.
The 30 rows contain the five exact weekly totals, four-week median, signed
median delta, adjacent-week step and exact relative lift as a rational numerator
and denominator (multiply by 100 for percent; both blank for zero baseline).
The opposite-nonzero-sign flag distinguishes conflicting directions, not zero
ties or lifecycle classifications. The Nov 21 sample has seven such histories.
Rows retain observation/retrieval dates, dataset/method, title-scoped source filters,
source endpoint and body/candidate hashes. The output is local, selected-cohort
evidence, not an authenticated provider origin, live release or a ranking of people.
A synthetic receipt is rejected; an existing CSV is never overwritten.
