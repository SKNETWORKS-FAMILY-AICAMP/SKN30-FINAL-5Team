# Home equipment variants v1 final

`backend_bundle/bundle_manifest.json` is the importer entry point. The bundle
contains only `DOMAIN_APPROVED` substitution guides and equipment-only
bodyweight variant relations. The catalog safety rules remain authoritative;
the relations must not be treated as pain or contraindication overrides.

Generate and validate from the repository root:

```bash
python3 data/scripts/build_home_equipment_variants_backend_bundle.py
python3 data/scripts/validate_home_equipment_variants_backend_bundle.py \
  data/generated/home-equipment-variants-v1-final/backend_bundle
```

The approval registry records that stretch-strap has no importable approved row,
and that the gap and validation reports are evidence only, never DB inputs.
