# TASK-TEMP-FE7-WEEKLY-REPORT

## Scope

- Redesign the frontend weekly report into the six approved information blocks.
- Render only values already aggregated by the weekly-report API.
- Preserve report generation and server acknowledgement/finalization gates; automate acknowledgement and next-plan application on detail view.
- Keep safety-stop messaging serious and non-playful.

## Expected files

- `frontend/src/api/types.ts`
- `frontend/src/features/weekly/WeeklyReportScreen.tsx`
- `frontend/src/features/weekly/WeeklyReportSummary.tsx`
- `frontend/src/features/preview/backendPreview.ts`
- `frontend/tests/WeeklyReportScreen.test.tsx`

## Risks

- API: additive optional read fields only; no request or endpoint changes.
- Database: none.
- Security/privacy: no new user data is collected or logged.
- Compatibility: older reports without the new aggregate fields must still render.

## Acceptance checks

- Header, goal, workout record, strengths/improvements, adjustment, and coach blocks render in order.
- Prior-week delta and calories are hidden when the API value is absent.
- The client does not derive aggregate participation or workout statistics.
- Safety-stop records use a serious tone.
- Loading, error, generation, acknowledgement, and next-plan flows remain covered.

## 2026-09-08 report layout refinement

- Owner: frontend; scope authorized by the project owner's weekly-report UI request.
- Reuse the report's existing mascot assets in the masthead, aligned with the page title.
  Put the speech bubble at the selected-week date height and the intro copy outside
  cards on the left. Goal progress is the first information card.
- Keep goal progress and the workout count cards; always show the separate safety-stop
  count without using it to hide mascots or change the report layout.
- Show only total workout time, estimated calories, and most-performed training type
  below the counts. Missing optional API values remain absent; zero is a valid value.
- Use API-provided rates, counts, totals, deltas, and insight codes. Percentage and
  duration formatting are presentation only; the frontend does not aggregate statistics.
- Use warm reflection cards and a brown coach card. Show the server's next action once.
- Keep time, calories, and most-performed training type in three horizontal columns
  on phones as well. Let values wrap without truncating server content.
- Omit the redundant report-ready badge; center a vector back chevron in its button.
- Use the calendar's shared partial marker glyph and colors, plus a pale pink circle
  with an exclamation mark for safety stops. Compact the coach card without clipping text.
- Changes: summary component, masthead/week header, component tests, this task document.
- API, database, dependencies, and data collection/logging: no changes.
- Manual checks: preview gallery → Weekly report (API), generate a closed-week report,
  inspect at narrow phone and tablet widths, then verify automatic acknowledgement and next-plan application.
  Check a safety-stop report and legacy reports with missing optional metrics as well.
- Validation: frontend formatter/linter/type checker, weekly report and calendar component
  suites, and Android/iOS production exports. The responsive test covers the report's
  measured width and enlarged text independently of the browser window width.
- Validation result: 27 weekly-report/calendar component tests passed; formatting,
  lint, type checking, and Android/iOS production exports passed.
- Browser visual checks: generated the closed-week mock report in the existing preview
  gallery at 390px and 360px. Verified title/mascot and date/bubble alignment, the first
  goal card, horizontal metrics, partial/safety markers, and the compact coach card.
  Native-device and real-backend visual verification remain outside these checks.

## 2026-09-08 automatic report application

- Project owner decision: remove the separate acknowledgement button and automatically
  apply the report. This supersedes the previous manual-confirmation UX.
- Implementation: after successful detail load/generation, save acknowledgement through
  the existing POST, then request the eligible next week's initial plan. Keep GET read-only,
  server finalization/safety gates, report generation, and historical report access.
- Files: report screen, `useWeeklyReportApplication.ts`, typed API endpoint wrappers,
  screen/endpoint/gallery tests, and AGENTS/domain/API/data-model/architecture/MVP policy descriptions.
- No API payload, database schema, dependency, or security/privacy changes.
- Retry acknowledgement with the same timestamp/key. Retry initial plans with the report
  UUID as the stable key, including screen re-entry after a lost response. Do not auto-loop
  on errors or request a plan after leaving during pending acknowledgement.
- Reuse an already applied plan; never create retroactive plans for historical reports.
- Show a retry button only on failure. A server draft remains a draft in the UI.
- Verification: automatic load/generation, acknowledgement-before-plan ordering,
  StrictMode/rerenders, network failure/retry, unmount, response mismatch, historical weeks,
  existing plans, and idempotency headers. Run formatter, lint, typecheck, component/API
  tests and Android/iOS production exports.
- Manual check: open or generate the previous closed week's report; verify no confirmation
  button, automatic application status, and the server plan on Home. Simulate a failed
  request and verify the report remains readable and only retry is offered.
- Results: 78 frontend tests passed (weekly report, calendar, endpoint, and gallery suites);
  56 existing backend weekly-report/weekly-plan domain, service, and API tests passed.
  Formatter, typecheck, and Android/iOS production exports passed. Lint exited successfully
  with one unrelated existing `BirthDateField.tsx` dependency warning. The gallery suite
  also emitted act warnings for other screens; all its assertions passed.
- Limitations: no native-device or live-backend end-to-end verification in this change.

## 2026-09-08 mascot/card overlap

- Remove the `함께 봐요` speech bubble and its unused styles.
- Anchor the existing right-side mascot to the masthead's bottom, extending behind
  the first goal card. The report body paints above it so the card hides its lower body,
  including when the introduction wraps on a narrow screen.
- Files: `WeeklyReportScreen.tsx`, its component test, and this task document.
- API, database, automatic application, and security/privacy behavior are unchanged.
- Verify the overlap and absence of the bubble at 390px and 360px; run frontend
  formatter, lint, typecheck, report/calendar component tests, and production exports.
- Validation: 35 report/calendar tests, formatting, typecheck, and Android/iOS exports
  passed; lint has only the existing unrelated BirthDateField dependency warning.
  Visually verified the card overlap and removed bubble at 360px.
- Follow-up: lift the mascot by 16px to expose more of its upper body. Per the owner's
  instruction, this position-only refinement uses visual/diff checks without rerunning
  builds or tests. Native-device verification remains unperformed.
