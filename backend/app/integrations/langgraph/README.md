# V3 LangGraph runtime

This package assembles the accepted Safety-first V3 contracts as a stateless
`StateGraph`. It is disabled by default and is not connected to the V1/V2 decision
service.

Implementation baseline: `origin/develop@0c0f497d2ff1c545f2b0f208cd363ad928720c98`
(fetched 2026-08-25 before the worktree was created).

## Boundary

`V3GraphInput` receives only an immutable `ConstraintEnvelope`, an
`ExercisePoolSnapshot`, optional identifier-free `RegenerationContext`, version
codes, freshness confirmation, and injected ports. The graph never loads from
PostgreSQL or Qdrant and does not hold user identifiers, raw check-ins, wearable or
calendar samples, credentials, prompts, provider payloads, exception messages, or
chain-of-thought.

The conflict detector, compiler, integrity validator, meaningful-difference
validator, and deterministic fallback remain domain-owned injected ports. This
package deliberately does not define competing domain enums or Pydantic schemas.

## Execution and failures

The three specialist nodes fan out in one LangGraph superstep and merge through an
append reducer. Results are canonicalized with `SPECIALIST_AGENT_ORDER`, never
completion order. A missing, timed-out, invalid, `FAILED`, or `NEEDS_INPUT` branch
prevents Coordinator execution and routes to deterministic fallback.

LLM nodes call native async adapter methods inside `asyncio.timeout`. Cancellation
therefore propagates to the provider coroutine; no worker thread is left running.
Provider retries remain bounded by `LLM_AGENTS_MAX_ATTEMPTS`, and graph nodes do not
add another retry policy.

Conflict review is conditional and calls only affected specialist ports, at most
once. Coordinator repair is allowed only for a repairable integrity result and is
performed at most once. Fallback output passes through the same injected compiler
and validator.

The graph compiles with `checkpointer=False`, no store, and empty callbacks. Its
return value is the framework-neutral `V3GraphResult`; PostgreSQL persistence is a
later application step and remains the canonical source of truth.

## Staging demo composition

`build_v3_demo_runtime` is the concrete application composition boundary for the
`DEMO` execution profile. It returns a runtime only when the environment is
`staging` and all OpenAI, model allowlist, credential, and LangGraph gates are
enabled. It does not depend on shadow opt-in or production promotion evaluation.

Application code injects a `V3RootSnapshotLoaderPort` that owns PostgreSQL
eligibility, optional Qdrant ranking, PostgreSQL revalidation, and deterministic
pool fallback. `V3DemoRuntime.execute` and the `V3GraphRuntimePort`-compatible
`regenerate` method return a `V3DecisionPersistenceBundle`; database and Qdrant
handles are never passed into graph state or Agent inputs.

## Dependency

The project directly pins only `langgraph==1.2.11`, the stable release verified as
Python 3.12 compatible when this runtime was implemented. CLI, Server, Studio,
provider SDK, persistent-checkpoint, and tracing integrations are not direct
dependencies. Packages required transitively by base LangGraph remain lockfile
implementation details and are not imported by this runtime.
