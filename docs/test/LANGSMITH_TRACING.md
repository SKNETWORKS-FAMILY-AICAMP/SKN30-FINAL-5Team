# LANGSMITH_TRACING.md

멀티에이전트 루틴 생성 실행을 LangSmith에서 확인하기 위한 조사 결과와 한계.
측정 기준 커밋: `chore/service-quality-evaluation-harness`.

**요약**: 워크플로 전체(노드 15개)는 추적된다. LLM 호출은 기본적으로 차단되며,
ADR-0020의 명시적 옵트인에서만 provider span을 허용한다.

---

## 1. 실측 결과

`backend/tests/evaluation/test_tracing.py`가 실제 그래프를 tracer와 함께 실행해
확인한 내용이다. 추정이 아니라 측정값이다.

### 1.1 추적되는 것 (span 15개)

```
LangGraph
├─ validate_entry          → after_entry
├─ parallel_agents
│   ├─ agent_training      ← 역할별 독립 span
│   ├─ agent_recovery
│   └─ agent_feasibility
├─ collect_proposals       → after_agents
├─ coordinator_agent
├─ compile                 → after_compile
├─ validate                → after_validation
└─ finalize
```

각 노드의 input/output에 `ConstraintEnvelope`, `ExercisePoolSnapshot`,
세 proposal, Coordinator `PlanSpec`, integrity 판정 결과가 담긴다.
실패 경로(`fallback`, `terminal`)와 repair 경로도 동일하게 나타난다.

마스터 명세 PHASE 8이 요구한 항목 대비:

| 요구 항목 | LangSmith trace | 대체 경로 |
|---|---|---|
| Agent Input / Output | **가능** (노드 단위) | — |
| State | **가능** | — |
| Coordinator 결과 | **가능** | — |
| Retriever 결과 | 부분 (pool의 `RetrievalMetadata`) | `retrieval_metrics.json` |
| Error | **가능** (failure_codes) | — |
| Retry | **가능** (repair 노드 진입 여부) | `InvocationAudit.attempt_count` |
| Latency | 노드 단위 **가능** | `InvocationAudit.latency_ms` |
| **Token Usage** | **불가** | `InvocationAudit.input/output_token_count` |
| **Prompt / 모델 원문 응답** | 기본 OFF, 승인된 옵트인에서 가능 | — |

### 1.2 기본값에서 추적되지 않는 것과 그 이유

`backend/app/integrations/llm_agents/provider.py:188`

```python
with tracing_context(enabled=self.tracing_enabled):
    raw_output = await structured_model.ainvoke(...)
```

기본값은 `False`이므로 **provider 호출은 계속 명시적으로 tracing에서 제외된다.**
4회 LLM 호출이 발생한 실행에서 LLM span이 0개임을 테스트로 고정했고, 별도 실제
LangChain fake model probe에서 옵트인 시 LangSmith tracer가 붙는 것도 검증했다.

근거 문서:

- `docs/TECHNICAL_PLAN.md:65` — "checkpointer, 장기 memory, LangSmith SaaS 전송은
  별도 승인 없이는 포함하지 않는다."
- `docs/TECHNICAL_PLAN.md` — 기본 비활성화, ADR-0020 승인 후 평가·staging 옵트인
- `backend/app/integrations/README.md:21` — 동일 취지
- `docs/adr/0020-opt-in-langsmith-provider-tracing.md` — 옵트인 경계와 승인 조건

## 2. 지금 할 수 있는 것

`LANGSMITH_API_KEY`만 설정하면 1.1의 워크플로 trace를 얻을 수 있다. 승인된 실행에서
LLM span도 필요하면 `LLM_AGENTS_TRACING_ENABLED=true`를 추가한다.

```bash
export LANGSMITH_API_KEY=...          # 별도 발급 필요 (Secrets Manager에 없음)
export LANGSMITH_PROJECT=helkki-service-quality
export LLM_AGENTS_TRACING_ENABLED=false # 승인된 LLM span 실행에서만 true
export OPENAI_API_KEY=...             # docs/test/PAID_EVALUATION.md 참고
uv run python -m backend.tests.evaluation.paid_run_cli --confirm-spend
```

Experiment 이름은 `backend/tests/evaluation/tracing.py`에 고정되어 있다:
`multi-agent-v1`, `baseline-single-agent-v1`, `multi-agent-scripted-offline-v1`.

키가 없으면 tracing만 꺼진 채 평가는 그대로 수행된다. 마스터 명세의
"LangSmith 연결이 없어도 로컬 Evaluation은 수행 가능" 요구를 만족한다.

## 3. 승인 상태

### 3.1 구현 및 외부 전송 승인 완료

`provider.py`의 tracing context와 model callback을 `LLM_AGENTS_TRACING_ENABLED`로
함께 게이트했다. 이 기능의 실제 활성화에 필요한 **두 가지 승인을 모두 확보했다.**

1. **소유권**: `backend/app/integrations/**`는 개발팀장 승인 영역이며
   공유 계약에 해당한다 (`AGENTS.md` 3절).
2. **개인정보 정책**: `docs/TECHNICAL_PLAN.md`가 명시적으로 금지한 SaaS 전송을
   여는 변경이므로 PM 검토가 필요하다 (`AGENTS.md` 3절, 8절).

적용 형태:

```python
# provider.py
with tracing_context(enabled=self.tracing_enabled):
    ...
```

기본값 `False`를 유지하고 production compose에도 ON 값을 추가하지 않았다. 따라서 production
동작은 바뀌지 않는다. 개발팀장·PM 승인은 2026-09-11 확보했으며 ADR-0020은 `ACCEPTED`다.

### 3.2 전송되는 데이터의 성격

워크플로 trace만 켜도 다음이 LangSmith(외부 SaaS)로 나간다.

포함되지 않는 것 (설계상 보장):

- 생년월일, 만 나이, 이름, 이메일, 사용자 ID, 기기 ID
- 원시 웨어러블 샘플, GPS, 캘린더 텍스트
- 기본값에서는 prompt 원문, 모델 원문 응답

포함되는 것:

- `excluded_exercise_ids` — **불편 부위를 간접적으로 드러낸다**
- `recovery_ceiling` — **피로/컨디션 수준을 간접적으로 드러낸다**
- `safety_required_action_code` — REST/STOP 여부
- 요청 시간, 목표, 장소, 승인된 운동 후보 목록
- 옵트인 시 prompt 원문과 모델 원문 응답

직접 식별자는 없으나 **건강 관련 추론이 가능한 값이 포함된다.** 단독으로
개인을 특정할 수는 없지만, `AGENTS.md` 8절이 다루는 범주에 인접한다.
켜기 전 PM 확인을 권한다.

## 4. 권고

| 목적 | 권고 |
|---|---|
| 멀티에이전트 실행 흐름 확인 | **지금 가능.** LangSmith 키만 설정 |
| 노드별 latency·경로·실패 원인 | **지금 가능** |
| Token / Cost 집계 | LangSmith 불필요. `InvocationAudit` 사용 |
| prompt·모델 응답 확인 | 구현·승인 완료. 승인된 평가 실행에서만 옵트인 |

옵트인을 켜지 않아도 마스터 명세 PHASE 8의 요구 항목 대부분이 충족된다. Token Usage는
trace가 아니라 `InvocationAudit`에서 이미 얻고 있다.

## 5. 승인 후 실측 결과

2026-09-11 `helkki` project의 `multi-agent-v1` experiment로 `SQ-SIMPLE-001` 한 건을 실행했다.
로컬 결과는 `SUCCEEDED`, provider 4회, input/output 24,140/3,332 tokens, 27.328초였고 repair와
fallback은 없었다. LangSmith UI에서 Feasibility, Recovery, Training, Coordinator 각각의
`ChatOpenAI gpt-5.6-terra` child span과 27.47K token root 집계를 확인했다.

상세: `docs/test/PHASE8_LANGSMITH_LLM_SPAN.md`.
