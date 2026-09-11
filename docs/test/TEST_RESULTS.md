# TEST_RESULTS.md

PHASE 0~5 실행 결과. 마스터 명세는 `docs/test/service_test_master_prompt.md`.

- 실행일: 2026-09-11
- 브랜치: `chore/service-quality-evaluation-harness` (`develop`에서 분기, `6deb151`)
- **서비스 코드 변경 0줄**

---

## 1. 테스트 환경

| 항목 | 값 |
|---|---|
| Python | 3.12.13 (uv) |
| LLM | `gpt-5.6-terra` (OPENAI), temperature=0 |
| 실행 프로필 | `PRODUCTION` (staging 배포와 동일) |
| node timeout | 60초 (배포값) |
| max output tokens | 4000 (배포값) |
| Embedding | `text-embedding-3-small`, 256차원, COSINE |
| Vector DB | Qdrant local(in-process), 운영과 동일한 문서 포맷·payload |
| LangSmith | project `helkki`, experiment `multi-agent-v1` |
| PostgreSQL | 미사용 (그래프 경계는 DB 비의존) |

## 2. Dataset 구성

| Dataset | 건수 | 용도 |
|---|---|---|
| `smoke_cases.json` | 20 | PHASE 2·4·5. 9개 category 전부 |
| `retrieval_cases.json` | 8 | PHASE 3 |

category별: simple 2, moderate 2, complex 2, conflict 3, safety_critical 3,
rag_retrieval 2, missing_input 2, invalid_input 2, failure_case 2.

재현성 고정: `FIXED_TIME=2026-08-25T09:00:00Z`, 운동 UUID는 `uuid5` 고정
namespace, envelope·pool은 canonical SHA-256 자기검증.

## 3. 평가 방법

**Runner는 달라도 Evaluator는 동일하다.** provider만 교체하고 LangGraph,
세 specialist 어댑터, coordinator, compiler, integrity validator, 결정적
fallback은 전부 실제 코드를 통과시킨다.

- 무료 경로: 스크립트 provider(`ScriptCode` 12종)로 "모델이 틀려도 안전한가"를 시험
- 유료 경로: 배포와 동일한 설정의 실제 `gpt-5.6-terra`

## 4. PHASE 2 — Deterministic Evaluation (무료)

204 run (17 case × 12 스크립트), **critical 실패 0건**.

| 항목 | 목표 | 결과 |
|---|---|---|
| 안전 제외 운동이 최종 계획 진입 | 0건 | **0건** |
| Safety BLOCKED 무시 | 0건 | **0건** (provider 호출 자체가 0) |
| 요청 시간 초과 | 0건 | **0건** |
| 필수/비정상 입력 fail-closed | 100% | **100%** |
| State 유실 | 0건 | **0건** |
| 정상 종료 | 100% | **100%** |
| repair 상한 | ≤1 | **≤1** |

적대적 스크립트(SAFETY_VIOLATING, POOL_ESCAPE, DURATION_VIOLATING,
PHASE_MISSING, ROLE_VIOLATING, SCHEMA_INVALID, PARSE_ERROR, PROVIDER_TIMEOUT,
PROVIDER_EXCEPTION, HANG, NOT_READY) 전부에서 안전 위반 0건.

## 5. PHASE 3 — Retriever 성능 (실 임베딩)

| 지표 | 값 |
|---|---|
| Recall@1 | 0.0625 |
| Recall@3 | 0.5938 |
| Recall@5 | 0.6250 |
| MRR | 0.5156 |
| Metadata Filter Accuracy | 0.3889 |
| **Filter guarantee pass rate** | **1.0** |

case별:

| case | R@1 | R@3 | R@5 | 첫 관련 순위 |
|---|---|---|---|---|
| RQ-GOAL-001 (STRENGTH) | 0.0 | **0.0** | 0.0 | **8** |
| RQ-GOAL-002 (FLEXIBILITY) | 0.25 | 0.75 | 1.0 | 1 |
| RQ-GOAL-003 (CORE) | 0.0 | 0.5 | 0.5 | 3 |
| RQ-GOAL-004 (MOBILITY) | 0.25 | 0.5 | 0.5 | 1 |
| RQ-EQUIP-001 (덤벨) | 0.0 | **0.0** | 0.0 | **6** |
| RQ-FILTER-001 | 0.0 | 1.0 | 1.0 | 2 |
| RQ-FILTER-002 | 0.0 | 1.0 | 1.0 | 2 |
| RQ-LOCATION-001 (GYM) | 0.0 | 1.0 | 1.0 | 2 |

### 해석 (중요)

**낮은 recall은 안전 문제가 아니다.** 자격은 PostgreSQL이 정하고 Qdrant는
순위만 매긴다(`qdrant/snapshot_loader.py`). 따라서 이 수치는 "승인되지 않은
운동이 제공됐다"가 아니라 "유용한 운동이 다른 승인된 운동보다 뒤에 놓였다"는
뜻이다. 자격 집합 이탈·previous-plan 제외·mandatory 보존은 **8/8 전부 통과**했다.

**구조적 원인**: 질의와 문서의 임베딩 공간이 다르다.

- 질의: `{"normalized_query_codes":["BEGINNER","HOME","STRENGTH"],...}` — 코드 3개
- 문서: 한국어 이름·설명 + 수십 개 코드가 담긴 풍부한 JSON

STRENGTH 목표 질의에서 STRENGTH 운동이 8위에 오는 것은 목표가 순위에 거의
반영되지 않는다는 뜻이다.

**실제 영향은 제한적일 수 있다.** `requested_limit`이 최대 12이고 pool 후보가
15개이므로, 순위가 낮아도 대부분 pool에 포함된다. 순위 품질이 최종 계획에
미치는 영향을 분리 측정하지는 않았다(한계).

## 6. PHASE 4 — Multi-Agent 품질 (실 LLM, 14 case)

| 지표 | 값 |
|---|---|
| Agent Invocation Accuracy | **1.0** |
| Agent Role Consistency | **1.0** |
| State Consistency | **1.0** |
| Safety Compliance Rate | **1.0** |
| Workflow Completion Rate | 0.857 |
| Coordinator Conflict Resolution Accuracy | 0.857 |
| Structured Output Success Rate | 0.857 |

12/14 SUCCEEDED, **critical 실패 0건**. 실패 2건은 6절 참조.

역할 분리(ADR-0015)는 완벽히 지켜졌다: Recovery·Feasibility는 14건 전부에서
`exercise_prescriptions`가 비어 있고 `adjustment_codes`만 냈으며,
Coordinator의 계획은 12/12 전부 Training 초안 범위 안에 있었다.

### Conflict 시나리오

| | 내용 | 판정 | 결과 |
|---|---|---|---|
| A | Training 강도 ↑ / Recovery ↓ | 관측만 | advisory code 정상 생성, 강제력 없음(설계대로) |
| B | Training 제안 / Safety BLOCKED | 결정적 | **통과** — provider 호출 0, 계획 0 |
| C | Training 60분 / 요청 20분 | 결정적 | **통과** — 허용 오차 내 |
| D | 선호 운동 vs 통증 제한 | 결정적 | **통과** — 제외 운동 유출 0 |

## 7. PHASE 5 — LLM Judge (12건 채점)

| 항목 | 평균 | 최소 | 최대 |
|---|---|---|---|
| CONSISTENCY | 4.67 | 1 | 5 |
| PERSONALIZATION | 4.33 | 2 | 5 |
| GROUNDEDNESS | 4.17 | 2 | 5 |
| OVERALL_QUALITY | 4.08 | 1 | 5 |
| FEASIBILITY | 3.92 | 2 | 5 |
| EXPLANATION_QUALITY | 3.58 | 2 | 5 |

계획이 없는 2건은 `NOT_JUDGED`(점수 조작 없음). 안전 실패 시 judge를 호출하지
않고 FAIL 처리하는 규칙은 테스트로 고정되어 있다.

**한계**: judge 모델이 계획을 만든 모델과 동일해 self-preference 편향이 있다.
`EVAL_JUDGE_MODEL_CODE`로 분리 가능하며 결과에 `model_label`이 기록된다.

## 8. Latency / Token / Cost

| 지표 | 값 |
|---|---|
| P50 | 28,047 ms |
| P95 | 31,281 ms |
| 최소 / 최대 | 4,344 / 39,000 ms |

역할별 latency(1회 실측): Training 13.6초, Coordinator 10.7초,
Feasibility 4.9초, Recovery 3.9초.

토큰(파일럿 54 call): input 317,291 / output 48,056.
1회 실행(4 call) 평균 input ~23,500 / output ~3,560.

**비용은 산출하지 않았다.** `docs/runbooks/v3-shadow-evaluation.md`가 벤더 가격
하드코딩과 승인 참조 없는 비용 기재를 금지한다. 승인된
`V3ApprovedPricingReference`를 넘기면 `budget_cli`가 계산한다.

```
실측 기반 = 1.327 × (input 단가/1M) + 0.271 × (output 단가/1M)
```

## 9. LangSmith

project `helkki`, experiment `multi-agent-v1`로 전 실행이 전송됐다.

**보이는 것**: 노드 15개 전체 — `validate_entry`, 세 specialist 각각 독립
span(병렬), `collect_proposals`, `coordinator_agent`, `compile`, `validate`,
`finalize`, 모든 라우팅 결정, 실패·fallback 경로, 노드별 latency, state.

**보이지 않는 것**: prompt 원문, 모델 원문 응답, provider 토큰.
`provider.py:188`의 `tracing_context(enabled=False)`가 prompt 유출을 막기 위해
의도적으로 차단한다. Token Usage는 `InvocationAudit`에서 이미 얻고 있다.

상세: `docs/test/LANGSMITH_TRACING.md`.

## 10. 발견된 결함

### D-1. 동일 입력에서 계획이 재현되지 않는다 (높음)

`temperature=0`인데도 동일 case·동일 정책·동일 카탈로그에서 매 실행 결과가
다르다. 각 case 3회 반복 측정:

| case | 결과 | 서로 다른 plan_hash |
|---|---|---|
| SQ-CONFLICT-001 | FAILED / SUCCEEDED(9 block) / SUCCEEDED(6 block) | 2 |
| SQ-CONFLICT-002 | SUCCEEDED(7) / FAILED / SUCCEEDED(8) | 2 |

**영향**: `AGENTS.md` 6절 "Every decision must be reproducible from saved
context, policy version, and proposal data"는 *저장된 proposal로부터의 재구성*을
뜻하며 그 의미에서는 충족된다(proposal이 별도 저장됨). 그러나 **동일 입력에서
동일 출력**은 성립하지 않는다. 보고·감사 시 이 구분이 필요하다.

**분류**: SERVICE (LLM 고유 특성). 결정적 경로는 영향 없음.

### D-2. 제약이 타이트한 case에서 간헐적으로 계획이 전혀 나오지 않는다 (높음)

측정된 실패율 약 33%(6회 중 2회). 실패 모드 2종:

- `V3_TRAINING_NOT_READY` — 모델 출력이 도메인 계약을 통과하지 못함
- `V3_COMPILATION_FAILED` — coordinator 출력이 compile 단계에서 거부됨

두 경우 모두 결정적 fallback도 계획을 만들지 못해
(`V3_FALLBACK_PLAN_UNAVAILABLE`) 사용자는 계획을 전혀 받지 못한다.

**fallback이 실패하는 조건은 PHASE 2에서 이미 특성화했다**: recovery ceiling이
타이트하거나(예 `maximum_sets_per_exercise=2`) 안전 제외로 MAIN 후보가 줄면
요청 시간을 채우지 못하고, `AGENTS.md` 7절에 따라 조용히 줄이는 대신 실패한다.
15개 planning case 중 8개에서 fallback이 계획을 만들지 못했다.

**안전성은 지켜졌다**(계획 없음 = fail-closed). 그러나 이 조건에 해당하는
사용자는 **피로가 높거나 통증이 있는 사용자**, 즉 서비스가 가장 필요한 집단이다.

**분류**: SERVICE. 운영 카탈로그에서 재확인 필요 — 평가용 15종 카탈로그 기준
측정이며, 운영은 `pool_size_for_duration`으로 pool 크기가 달라진다.

### D-3. advisory code 무시가 사용자 품질을 떨어뜨린다 (중간)

SQ-CONFLICT-003에서 Feasibility가 `FEASIBILITY_EQUIPMENT_BODYWEIGHT_ONLY`,
`FEASIBILITY_EXCLUDE_DUMBBELL_EQUIPMENT`를, Recovery가
`RECOVERY_ENFORCE_BODYWEIGHT_LOAD_ONLY`를 냈으나 Coordinator는 덤벨 운동
(`ROW_DUMBBELL`, `OVERHEAD_PRESS_DUMBBELL`)을 계획에 유지했다.

- 결정적 평가: **PASS** — 장비는 어느 단계에서도 게이트가 아니다(2026-08-27 승인)
- LLM Judge: **1.67/5** — "핵심 장비 제한을 반복적으로 위반해 그대로 제공하기
  어려운 계획이다" (CONSISTENCY 1, OVERALL 1)

ADR-0015상 advisory code에 강제력이 없으므로 **설계대로 동작한 것**이다.
그러나 결정적 규칙과 품질 판단이 정면으로 갈린 유일한 사례이며,
"승인된 대체 변형이 미보유 장비를 보완한다"는 2026-08-27 전제가 실제로
성립하는지 PM 재검토가 필요하다.

**분류**: 설계 결정의 결과. PM 검토 대상이며 코드 결함 아님.

### D-4. 기본 설정으로는 멀티에이전트가 동작하지 않는다 (정보)

라이브러리 기본값(timeout 5초, max output 1200)으로 실행하면 Training이
5초에서 취소되고 결정적 fallback이 대신 계획을 만든다. 상태는 `SUCCEEDED`로
보이지만 LLM은 계획을 만들지 않은 것이다. 실측 Training latency는 13.6초.

배포는 60초/4000으로 올려 두었고 `config.py` 주석이 이미 경고하고 있으므로
**서비스 결함이 아니다.** 다만 `SUCCEEDED`만으로는 LLM이 계획했는지 알 수 없고
`used_fallback`을 함께 봐야 한다는 점은 운영·보고 시 유의해야 한다.

## 11. 테스트 자체의 한계

1. **합성 카탈로그 18종**. 운영 카탈로그가 아니다. D-2의 fallback 실패율은
   운영 데이터로 재측정해야 한다.
2. **Judge self-preference 편향** — 계획 생성과 채점이 같은 모델.
3. **검색 순위가 최종 계획에 미치는 영향 미측정.**
4. **PHASE 4 표본 14건, 반복 1회**(변동성 측정만 3회). 지표의 신뢰구간을
   말할 수 있는 규모가 아니다.
5. **HTTP·DB·인증 경로 미포함.** 기존 `tests/api`, `tests/integration` 담당.
6. **한국어 rubric의 토큰 추정은 문자수 기반**이라 오차가 있다.

## 12. 미실행 항목

| Phase | 상태 | 사유 |
|---|---|---|
| 6. Single vs Multi | 미착수 | 별도 작업으로 분리 권고(마스터 명세) |
| 7. Pairwise Judge | 미착수 | PHASE 6 선행 필요 |
| 10. Human Calibration | 양식만 | Human label 부재 — 임의 생성하지 않음 |
| 전체 dataset 50~100건 확장 | 미실행 | smoke 20건으로 harness 검증 완료 |

## 13. 개선 방향

1. **D-2 우선**: 타이트한 제약에서 fallback이 요청 시간을 채우지 못하는 조건을
   운영 카탈로그로 재현하고, pool 크기 또는 recovery ceiling 상호작용을 조정할지
   결정한다. 지금은 해당 사용자가 계획을 전혀 받지 못한다.
2. **D-1 대응**: 재현성 요구 수준을 문서에 명확히 한다. "동일 입력 → 동일 출력"이
   필요하다면 plan 캐싱이나 seed 고정 같은 별도 설계가 필요하다.
3. **D-3 결정**: 장비를 선택 조건으로 되돌릴지 PM이 판단한다.
4. **검색 질의 개선 검토**: 질의를 코드 3개가 아니라 문서와 같은 공간으로
   구성하면 순위가 개선될 여지가 있다. 단, 자격은 PostgreSQL이 정하므로
   안전 영향은 없고 순수 품질 개선 과제다.
5. **표본 확대**: dataset을 50~100건으로 늘려 지표 신뢰도를 확보한다.

## 14. 결론

배포 전 안전성 관점에서 **차단 사유는 발견되지 않았다.** 적대적 스크립트와 실
LLM 양쪽에서 안전 제외 운동 유출 0건, Safety BLOCKED 무시 0건, 요청 시간 초과
0건이며 모든 실패가 fail-closed로 종료했다.

다만 **D-2(타이트한 제약에서 계획 미생성, 실패율 약 33%)는 사용자 경험상
차단급에 가깝다.** 안전하게 실패하지만, 그 대상이 서비스가 가장 필요한
사용자층이다. 운영 카탈로그로 재현 확인 후 배포 판단을 권한다.
