# Domain rule safety boundary

- Primary owner: development and data lead.
- Safety, pain exclusions, duration, weekly boundary, return mode, and final validation are deterministic.
- Do not invent medical thresholds. Unapproved values remain explicit configuration gaps.
- Every ruleset is versioned and referenced by decision records.
- LLM output never enters this boundary.
- Safety changes require PM review, external domain evidence where applicable, and invariant tests.
