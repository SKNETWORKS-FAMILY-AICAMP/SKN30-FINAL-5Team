# AGENTS.md

## 1. Project overview

This repository implements a personalized multi-agent exercise wellness service for exercise beginners and returning users.

The core product flow is:

1. Onboarding and base routine creation
2. Daily condition check-in
3. Independent agent proposals
4. Coordinated routine adjustment
5. Workout execution
6. Completion or skip feedback
7. Weekly report and user acknowledgement
8. Feedback applied to the next weekly plan and later daily decisions

The product does not diagnose, treat, or prescribe for medical conditions.

## 2. Sources of truth

Before modifying code, read the relevant documents:

- `AGENTS.md`: repository-wide rules
- Closest nested `AGENTS.md`: module-specific rules
- `docs/README.md`: document priority and approval rules
- `docs/ARCHITECTURE.md`: system boundaries
- `docs/DOMAIN_RULES.md`: product invariants
- `docs/API_CONTRACT.md`: frontend/backend contracts
- `docs/DATA_MODEL.md`: persistence contract
- `docs/COLLABORATION_GUIDE.md`: Git, issue, PR, and review workflow
- Current issue or task document: acceptance criteria

When these documents conflict, stop and request clarification. Do not silently choose one.

## 3. Team ownership

- `frontend/**`: frontend owner
- `backend/app/api/**`: backend owner
- `backend/app/db/**`: backend owner
- `backend/migrations/**`: backend owner
- `backend/app/domain/agents/**`: AI/data lead
- `backend/app/domain/rules/**`: AI/data lead; safety changes also require PM and domain review
- `data/**`: AI/data lead
- `docs/product/**`: PM
- Architecture and shared contracts: development lead approval required

Do not edit another owner's area unless the task explicitly authorizes it.

## 4. Working rules

- One issue must have one primary owner.
- Use one branch and one worktree per issue.
- Do not mix unrelated refactoring with feature work.
- Prefer small pull requests that can be reviewed independently.
- Do not change public API fields without updating the API contract.
- Do not change database schemas without an Alembic migration.
- Do not add a production dependency without explaining why it is required.
- Do not edit generated files manually.
- Do not overwrite another contributor's uncommitted work.
- Do not use `git push --force` on shared branches.
- Do not commit directly to `main` or `develop`.

## 5. Required workflow

Before coding:

1. Read this file and the closest nested `AGENTS.md`.
2. Read the issue and acceptance criteria.
3. Inspect existing implementation and tests.
4. State the files expected to change.
5. Identify API, database, security, and compatibility risks.
6. For changes affecting more than three files, write a short implementation plan.

During coding:

1. Stay within the assigned scope.
2. Preserve existing API and database compatibility unless the issue explicitly changes it.
3. Add or update tests with the implementation.
4. Reuse existing services, schemas, and utilities before creating new abstractions.
5. Keep business rules outside API route handlers.
6. Keep external integrations behind adapter modules.
7. Stop if an undocumented architectural decision is required.

After coding:

1. Run the required formatter, linter, type checker, and tests.
2. Review the diff for unintended files.
3. Update documentation when behavior or contracts changed.
4. Report changed files, tests run, limitations, and remaining risks.
5. Do not claim completion if required tests did not pass.

## 6. Architecture boundaries

Frontend:

- Handles display, local interaction, workout timers, and mascot animations.
- Does not reproduce backend decision logic.
- Uses typed API clients and shared response contracts.
- Must provide loading, empty, error, and permission-denied states.

Backend:

- FastAPI routes validate requests and delegate to services.
- Business logic belongs in domain or service modules.
- Database access belongs in repository modules.
- External services belong in integration adapters.
- API routes must not call LLM providers directly.

Multi-agent domain:

- Agents return structured proposals, not unvalidated free text.
- Safety decisions must be rule-based and deterministic.
- LLM output must never override an explicit safety veto.
- Every decision must be reproducible from saved context, policy version, and proposal data.
- LLM failures must fall back to deterministic rules or templates.
- Agent proposals and final decisions must be stored separately.

Data:

- Preserve data source and license metadata.
- Do not treat unverified external exercise data as production-safe.
- Exercise alternatives and contraindication rules require explicit review.
- Raw source data and normalized application data must remain separate.

## 7. Product invariants

The following rules must not be changed without development lead and PM approval:

- The default user experience shows one final recommended routine. A REST opt-out may be offered, but lighter and original routines are not public plan alternatives.
- The system must support users without wearable devices.
- Wearable data reduces input burden but is not mandatory.
- A downshift preserves the user's requested duration and lowers load, intensity, sets, repetitions, exercise difficulty/type, or rest structure; the system must not shorten duration without explicit user input.
- Official workout completion status comes from explicit in-app exercise-block completion, not elapsed time, wearable data, or external workouts.
- A closed weekly report must be acknowledged before the next weekly plan is finalized.
- Missed workouts are learning signals, not penalties.
- A user selecting rest must not receive additional pressure notifications that day.
- The mascot must not express disappointment when a workout is skipped.
- Pain and abnormal-response screens must use a serious, non-playful tone.
- The service must avoid diagnosis, treatment, and medical prescription language.

## 8. Health and privacy rules

Never:

- Log authentication tokens, emails, full names, or raw health records.
- Send direct identifiers, calendar text, GPS routes, or raw wearable samples to an LLM.
- Store secrets in source code, fixtures, screenshots, or documentation.
- Use wearable data as the sole basis for a safety decision.
- Infer a medical condition from wearable or check-in data.
- Return internal agent prompts or hidden reasoning to the client.

Use only the minimum normalized values required for the decision.

## 9. API rules

- All API paths use `/api/v1`.
- Request and response bodies use Pydantic schemas.
- Public response fields are backward-compatible.
- New response fields should be optional when possible.
- Timestamps use ISO 8601 with timezone information.
- IDs use UUIDs.
- Enumerations use stable machine-readable codes.
- User-facing Korean labels must not be used as database keys.
- Error responses use the repository's common error schema.
- Every mutation endpoint must consider idempotency.

When an API changes:

1. Update the OpenAPI/Pydantic contract.
2. Update API examples.
3. Update frontend mocks or generated clients.
4. Add compatibility tests.
5. Obtain review from frontend and backend owners.

## 10. Database rules

- PostgreSQL is the source of truth.
- Schema changes require Alembic migrations.
- Migrations must include a safe rollback or documented forward-fix strategy.
- Frequently queried fields use typed columns rather than JSON only.
- JSONB is reserved for flexible proposal, context, and metadata fields.
- Foreign keys and uniqueness constraints must be explicit.
- Do not delete or rename a production column in the same release that stops writing it.
- Agent decision records must retain graph, policy, and prompt versions.

## 11. Testing requirements

At minimum, run tests for the modified area.

Backend changes:

- Formatter and linter
- Type checker
- Unit tests
- Relevant API or integration tests

Frontend changes:

- Formatter and linter
- Type checker
- Component tests for modified behavior
- Production build

Agent or exercise-rule changes:

- Unit tests
- Golden scenario tests
- Safety invariant tests
- LLM fallback tests when applicable

Required golden scenarios:

1. Healthy condition returns the original routine as the final recommendation.
2. Limited time creates a goal-preserving downshift.
3. Knee discomfort excludes knee-load movements while preserving an appropriate goal.
4. Wearable data missing uses manual check-in fallback.
5. LLM failure returns a deterministic result.
6. Safety veto cannot be overridden by coordinator output.

## 12. Code review rules

Flag the following as high priority:

- Breaking changes to API response fields
- Database changes without migrations
- Safety rules implemented only through an LLM
- Health or identifying data written to logs
- Agent decisions that cannot be reproduced from stored inputs
- Frontend duplication of backend decision logic
- Wearable-only user flows without manual fallback
- Unrelated refactoring inside a feature pull request
- Generated code edited manually
- Missing tests for a business-rule change

For each finding, identify the violated invariant and provide a safe correction path.

## 13. Definition of done

A task is complete only when:

- Acceptance criteria are satisfied.
- Required tests pass.
- API and database contracts are updated.
- No secrets or sensitive health data appear in logs or diffs.
- Error and fallback paths are implemented.
- Relevant documentation is updated.
- The pull request includes a test summary and risk assessment.

## 14. Agent response format

After completing work, report:

- Summary
- Files changed
- Tests run and results
- API or schema changes
- Security or privacy impact
- Known limitations
- Manual verification steps

Never state that tests passed unless they were actually executed.
