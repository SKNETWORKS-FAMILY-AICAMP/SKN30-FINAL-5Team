# TASK-TEMP-FE7-WEEKLY-REPORT

## Scope

- Redesign the frontend weekly report into the six approved information blocks.
- Render only values already aggregated by the weekly-report API.
- Preserve report generation, acknowledgement, and next-plan application flows.
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
