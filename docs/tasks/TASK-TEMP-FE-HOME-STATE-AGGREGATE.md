# Home state aggregate frontend integration

- Status: complete
- Owner: frontend
- Base: `origin/develop` at `905d263`

## Objective

Restore the Home entry state from `GET /api/v1/home?local_date=YYYY-MM-DD`
instead of independently combining the daily decision, workout-session list,
and session detail responses in the client.

## Implementation plan

1. Add the reviewed aggregate response and endpoint to the typed API client.
2. Replace only `MainFlow`'s restart/Home-entry recovery read with the aggregate
   response while preserving decision mutation race protection and the optional
   weekly-plan revision read.
3. Surface aggregate loading, empty, error, and permission-denied states through
   `HomeContainer`; keep its routine/context and weekly-progress reads unchanged.
4. Update transport and restart-recovery tests to verify the aggregate request,
   no legacy recovery composition, resumable/completed sessions, empty state,
   retry, and permission handling.
5. Run frontend format, lint, typecheck, targeted tests, and production exports.

## Compatibility and risk notes

- No backend or public API contract changes are made by this task.
- Existing check-in, decision, routine, and workout-session mutations remain on
  their dedicated endpoints.
- A successful empty aggregate response is authoritative, but it may replace
  flow state only when no newer in-memory decision has won the existing race.
- The weekly session list remains necessary for progress rendering and is not
  replaced by the daily aggregate session.
- Permission failures must not expose a retry action; other transient failures
  remain retryable.

## Acceptance criteria

- Home recovery performs one `/home?local_date=...` request and does not perform
  the legacy daily decision/list/detail composition.
- The decision and session displayed together come directly from one aggregate
  response, including null, resumable, stopped, and completed states.
- Loading, empty, retryable error, and permission-denied states are represented.
- Existing mutation flows and weekly progress behavior remain intact.
- Required frontend verification passes and the final diff contains no backend
  changes.

## Verification

- `npm.cmd run typecheck` — passed.
- ESLint on all changed frontend source and test files — passed.
- Prettier check on all changed frontend source and test files — passed.
- `npm.cmd test -- --runInBand tests/apiEndpoints.test.ts tests/mainFlowRestore.test.tsx`
  — 2 suites and 13 tests passed.
- Production export was intentionally deferred because another workspace build
  was active and the shared drive had no free capacity; no export artifacts
  were created by this worktree.
