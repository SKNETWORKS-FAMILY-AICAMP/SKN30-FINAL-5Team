# Weekly report narration Agent

`WeeklyReportNarrationAgent` is an optional interpretation boundary. It receives
only the immutable deterministic aggregate snapshot and the already calculated
counts/rates; it never reads repositories, raw health data, identifiers, or
workout-plan Agent inputs.

The V3 Training, Recovery, Feasibility, and Coordinator contracts are deliberately
not reused because they own exercise plan construction and safety constraints.
The narration Agent instead reuses the application's provider-neutral narration
adapter and is allowed to replace only `summary`, `decision_summary`, and
`next_action` wording. Counts, rates, reason codes, pattern data, and adjustment
direction always remain the values calculated by `WeeklyReportService`.

Every result is stored in the existing `agent_summaries` JSON field with its source,
model/prompt version, and fallback reason. Provider timeout, provider failure, bad
JSON, invalid slots, or unsafe output falls back to the pre-existing deterministic
template. The report API therefore remains available when LLM narration is disabled
or unavailable.
