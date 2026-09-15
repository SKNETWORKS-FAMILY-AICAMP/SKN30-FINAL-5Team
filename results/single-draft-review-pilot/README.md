# Architecture E paid pilot

Date: 2026-09-15  
Model: `OPENAI:gpt-5.6-terra:reasoning-low`  
Dataset: `heldout_cases_v2`  
Cases: `SQ-HELD-001`, `SQ-HELD-013`, `SQ-HELD-022`

## First run

The B plan was generated once per case and shared with E, so the comparison contains no
generation variance. B and E both delivered direct plans in 3/3 cases. E made no accepted
change: two cases completed with `NO_CHANGE`, while one Recovery critic exhausted structured
output retries and E preserved the valid original draft. The no-regression design therefore
worked, but this run provides no evidence of a quality improvement.

The run exposed an input omission: critics received the validated draft and catalog records
for its exercises, but not the normalized constraint envelope. The adapter was subsequently
updated to include the existing privacy-projected envelope. Equipment ownership remains
absent from that projection and is not a review condition. A rerun after that correction is
required before judging critic usefulness.

## Envelope-corrected rerun

`summary-v2-envelope.json` is the corrected three-case rerun. B and E again delivered direct
plans in 3/3 cases and E preserved the exact shared draft in every case. Two cases completed
with `NO_CHANGE`; one Feasibility critic exhausted schema retries and the original remained
deliverable. There were no accepted patches, so this sample still provides no evidence of a
quality improvement.

The rerun also showed that a Coordinator call is wasteful when both critics return an empty
patch list. E now short-circuits that path and finalizes the original draft without invoking
the Coordinator. A Coordinator is used only when at least one critic submits a patch.

The first corrected attempt stopped locally on the third case because the privacy guard did
not recognize a renamed catalog path and treated catalog `body_focus_code` as user health
data. The path now uses the established `exercise_pool` name, and a regression test verifies
that catalog body-focus codes remain allowed while user body-area values remain protected.
No result artifact was written for the interrupted attempt.

## Usage

The artifact records 13 provider attempts, 36,361 input tokens, and 5,180 output tokens.
Using the approved Round 3 reference ($2.00/M input and $12.00/M output), recorded usage is
`$0.134882`. Because shared retry telemetry retains only the final attempt's usage, this is a
lower bound rather than an invoice-equivalent total.

No direct identifiers, raw wearable records, or provider secrets are stored in the result.

The corrected artifact records 13 provider attempts and a `$0.176152` recorded-usage lower
bound under the same approved pricing reference. Retry telemetry limitations still apply.

## Expanded intervention-rate run

`summary-expanded-8.json` covers eight shared-draft cases: one simple, two moderate, two
complex, and three conflict cases. B and E retained a direct plan in all eight. E changed
zero plans. Four critic pairs completed and both returned no patches; the other four had one
schema-invalid critic and preserved the original. The no-change fast path correctly skipped
Coordinator, so every case recorded three roles rather than four.

Because E produced no changed plan, a B-vs-E blind quality judge would compare identical
plans and cannot measure critic value. No judge call was made. This run supports E's
no-regression property but provides no evidence that the critics improve final routine
quality under the current prompt and input contract.

The expanded artifact records 32 attempts, 104,695 input tokens, and 16,504 output tokens,
for a `$0.407438` recorded-usage lower bound. Across the three stored E artifacts the recorded
lower bound is `$0.718472`. One interrupted envelope run wrote no artifact, so neither that
sum nor retry telemetry should be represented as the provider invoice total.
