# GIF motion review report

## Scope and method

- Reviewed source catalog: `data/normalized/v2_0_6_exercise_catalog.csv`
- Reviewed media: all 237 files in `data/media/videos/`
- For every GIF, inspected all animation frames against `source_identity`, current Korean/English exercise text, and Gym Visual source name/instructions.
- Result: all 237 catalog records have exactly one GIF whose source ID matches `source_identity`. File-ID completeness does not prove that the GIF motion and catalog text describe the same exercise.

The review found 6 confirmed catalog-text corrections, 2 source/GIF conflicts that cannot be resolved without choosing a canonical source, and 4 foam-roller records requiring domain review.

## Confirmed catalog text corrections

| source_identity | stable_code | GIF motion and source evidence | current conflicting text | review result |
| --- | --- | --- | --- | --- |
| 0137 | `body_up` | Floor body-up / triceps-extension motion; source name is `body-up` | Korean name and steps describe a bench-supported donkey kick | Replace Korean name, steps, and form cues after final copy approval |
| 0613 | `side_lying_quadriceps_stretch_mobility_stretch_bodyweight` | Side-lying quadriceps stretch; source name and target are quadriceps | Korean name and steps call it a hamstring stretch | Correct Korean name and steps to quadriceps stretching |
| 1512 | `quadruped_quadriceps_stretch_mobility_stretch_bodyweight` | Quadruped bent-knee quadriceps stretch; source target is quadriceps | Korean name calls it a hamstring stretch | Correct Korean name and steps to quadriceps stretching |
| 1564 | `intermediate_hip_flexor_and_quad_stretch` | Hip-flexor/quadriceps stretch; source target is quadriceps | Korean name and steps call it a hamstring stretch | Correct Korean name and steps to hip-flexor/quadriceps stretching |
| 2204 | `foam_roller_thigh_stretch` | Forearm-plank roller body saw; source name is `roller body saw` | Korean/English name and steps describe thigh rolling | Correct catalog text to body saw or replace the GIF |
| 2206 | `foam_roller_calf_stretch_2206` | Roller reverse-crunch motion; source name is `roller reverse crunch` | Korean/English name and steps describe calf rolling | Correct catalog text to roller reverse crunch or replace the GIF |

## Media/source conflict: no automatic catalog correction

| source_identity | stable_code | conflict | required decision |
| --- | --- | --- | --- |
| 0130 | `bench_hip_extension` | Source name and steps are bench hip extension/hip thrust, while the GIF is a bench-supported leg hip-extension motion resembling a donkey kick | Choose whether the source title/instructions or the GIF is canonical; current catalog text follows the source, so changing it without a decision would alter approved meaning |
| 0514 | `bodyweight_squat` | Source name/instructions call it a jump squat, while all GIF frames show a standard squat without an airborne phase | Keep the current bodyweight-squat catalog text; source metadata, not catalog text, conflicts with the media |

## Ambiguous foam-roller candidates requiring domain review

| source_identity | stable_code | current catalog text | source name/instructions | observed GIF |
| --- | --- | --- | --- | --- |
| 2203 | `foam_roller_hamstring_stretch` | seated hamstring rolling | seated shoulder flexor/depressor/retractor | seated roller movement; catalog and source describe different movements |
| 2205 | `foam_roller_outer_thigh_stretch_2205` | outer-thigh rolling | roller hip/lat stretch | side-supported lateral roller movement; target location cannot be resolved safely from frames alone |
| 2207 | `foam_roller_outer_thigh_stretch_2207` | outer-thigh rolling | roller side-lat stretch | side-supported lateral roller movement; target location cannot be resolved safely from frames alone |
| 2209 | `foam_roller_calf_stretch_2209` | seated calf rolling | seated single-leg shoulder flexor/depressor/retractor | seated roller movement; catalog and source describe different movements |

## Benign source-name differences retained

The remaining 9 name differences are source version suffixes or spelling variants with matching GIF motion: `0096`, `0121`, `0199`, `0287`, `0317`, `0513`, `0705`, `1369`, and `3552`.

## No changes made

This report is a review artifact only. No exercise name, instruction, form cue, safety rule, alternative, media file, or source mapping was changed.
