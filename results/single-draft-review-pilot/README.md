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

## Usage

The artifact records 13 provider attempts, 36,361 input tokens, and 5,180 output tokens.
Using the approved Round 3 reference ($2.00/M input and $12.00/M output), recorded usage is
`$0.134882`. Because shared retry telemetry retains only the final attempt's usage, this is a
lower bound rather than an invoice-equivalent total.

No direct identifiers, raw wearable records, or provider secrets are stored in the result.

