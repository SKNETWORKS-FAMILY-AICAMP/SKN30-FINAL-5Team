# Weekly report narration Agent

`WeeklyReportNarrationAgent` is an optional interpretation boundary. It receives
only the immutable deterministic aggregate snapshot and the already calculated
counts/rates; it never reads repositories, raw health data, identifiers, or
workout-plan Agent inputs.

The V3 Training, Recovery, Feasibility, and Coordinator contracts are deliberately
not reused because they own exercise plan construction and safety constraints.
The narration Agent instead reuses the application's provider-neutral OpenAI
Responses adapter. It writes only the section-four adjustment explanation, the
four section-five recommendation axes (`intensity`, `volume`, `duration`, and
`pain_response`), and the section-six coach message. Counts, rates, condition
trend, reason codes, performed-plan data, and adjustment direction always remain
the values calculated by `WeeklyReportService`.

Every result is stored in the existing `agent_summaries` JSON field with its source,
model/prompt version, fallback reason, and the four recommendation strings. The
provider receives only identifier-free normalized aggregate codes and counts; it
does not receive pain areas, scores, free text, or raw check-ins. Provider timeout,
provider failure, bad JSON, invalid slots, or unsafe output falls back to reviewed
deterministic templates. The report API therefore remains available when LLM
narration is disabled or unavailable.
