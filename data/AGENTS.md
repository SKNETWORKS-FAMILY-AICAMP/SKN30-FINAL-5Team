# Data working rules

- Primary owner: development and data lead.
- Preserve source URL/reference, license, retrieval date, normalization version, and review status.
- Keep `raw`, `normalized`, and `generated` artifacts separate.
- Never promote data to production use without `DOMAIN_APPROVED` status and review evidence.
- Exercise alternatives, pain conflicts, recovery content, and FITT values require explicit review.
- Do not use arbitrary MET/RPE mappings or infer medical contraindications.
- Scripts must be reproducible and validation must fail closed on required fields.
- Do not place user health data or direct identifiers under `data/`.
