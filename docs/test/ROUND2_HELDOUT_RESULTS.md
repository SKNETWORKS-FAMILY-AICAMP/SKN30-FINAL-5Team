# 2차 held-out 유료 평가 결과

> **상태: 종료(2026-09-12).** 사전 등록 판정은 변경하지 않으며 이후 개선은 별도 ADR로 추적한다.
> 1~7절은 **ADR-0022 수정 전** 실행이다. 수정 후 재측정과 최종 판정은 **8절**에 있다.
> Human 평가는 신뢰 가능한 독립성·평가자 일치도를 확보하지 못해 최종 판정에서 제외했다.
> 기계 검증 가능한 기준의 결과는 통과 4, 미달 2다.

- 실행일: 2026-09-11
- 데이터셋: `heldout_cases` 33건 중 planning 29건 (blocked 4건은 provider 호출 없음)
- 카탈로그: `exercise-catalog-v2.0.7-final` (배포본, 237종)
- 모델: `OPENAI:gpt-5.6-terra:reasoning-low`, 세 architecture 동일
- 실제 호출: 256회 (graph 169 + judge 87), 상한 320
- 산출물: `results/round2/heldout/`
- LangSmith: project `helkki`, experiment `multi-agent-v2` / `baseline-single-agent-v1` /
  `baseline-single-llm-v1`. LLM span은 이 실행에서 **꺼져 있었다**(`llm_agents_tracing_enabled`
  기본값). 따라서 latency는 2차 pilot과 같은 조건에서 측정됐다.

## 1. 사전 등록 기준 판정

`ROUND2_IMPROVEMENT_PLAN` 3절에서 결과를 보기 전에 고정한 기준 중 자동 재현 가능한 항목이다.
Human mean은 평가 신뢰 조건을 충족하지 못해 최종 판정에서 제외했다.

| 지표 | 통과 기준 | 실측 | 판정 |
|---|---:|---:|:--:|
| Safety golden pass rate | 1.000 | 1.000 (33/33) | 통과 |
| Critical / unsafe plan | 0건 | 0건 | 통과 |
| 실-provider workflow completion | ≥ 0.950 | 1.000 | 통과 |
| v1 Multi 대비 평균 total token | ≥ 25% 감소 | 26.9786% 감소 | 통과 |
| Multi P95 latency | ≤ 30초 | **48.813초** | **미달** |
| conflict/complex case plan rate | ≥ Single RAG | **complex 0.667 / conflict 0.600** | **미달** |

token 기준에 대한 주석: 사전 등록 문구는 "v1 Multi 대비"이고 v1은 튜닝 데이터셋에서
측정됐다. 따라서 판정에 쓴 26.9786%는 **같은 데이터셋에서의 대응 측정**
(`ROUND2_IMPROVEMENT_PLAN` 7절)이다. held-out에서의 1회 실행당 20,386 토큰을 v1의 26,646과
직접 비교하면 23.49% 감소지만, 데이터셋과 카탈로그가 달라 사전 등록된 비교가 아니므로
판정 근거로 쓰지 않았다. 두 수치 모두 기록한다.

**판정: 기계 검증 기준 통과 4, 미달 2. 따라서 "Multi-Agent가 더 유효하다"는 결론을 내리지 않는다.**
`ROUND2_IMPROVEMENT_PLAN` 6절의 분기 중 **"Single RAG가 동등 이상"** 에 해당한다.

## 2. 측정값

| 지표 | A. Single LLM | B. Single Agent + RAG | C. Multi-Agent + RAG |
|---|---:|---:|---:|
| 실행 수 | 29 | 29 | 29 |
| Constraint Satisfaction | 1.000 | 1.000 | 1.000 |
| Safety Compliance | 1.000 | 1.000 | 1.000 |
| Critical 실패 | 0 | 0 | 0 |
| Workflow Completion | 1.000 | 1.000 | 1.000 |
| Plan Delivery Rate (fallback 포함) | 1.000 | 1.000 | 1.000 |
| **LLM Plan Rate** (fallback 제외) | 0.0345 | **0.8966** | 0.7586 |
| Structured Output Success | 0.1724 | **1.000** | 0.8276 |
| Judge 평균 (blind) | 2.9138 | **3.7011** | 3.6552 |
| ├ PERSONALIZATION | 3.6897 | **4.3103** | 3.9655 |
| ├ FEASIBILITY | 3.2414 | 3.6552 | **3.8276** |
| └ OVERALL_QUALITY | 3.1034 | 3.7241 | 3.7241 |
| P50 latency | 13.796초 | 22.047초 | 32.390초 |
| P95 latency | 15.703초 | 48.563초 | 48.813초 |
| 1회 실행당 호출 | 1.00 | 1.00 | 3.83 |
| 1회 실행당 토큰 | 4,154 | 8,808 | **20,386** |
| fallback | 28 | 3 | 7 |
| repair | 0 | — | **0** |

category별 LLM plan rate:

| category | 실행 | A | B | C |
|---|---:|---:|---:|---:|
| simple | 4 | 0.000 | 0.750 | 0.750 |
| moderate | 8 | 0.000 | 1.000 | 1.000 |
| complex | 9 | 0.111 | **0.889** | 0.667 |
| conflict | 5 | 0.000 | **0.800** | 0.600 |
| failure_case | 3 | 0.000 | **1.000** | 0.667 |

## 3. Multi-Agent fallback 7건의 원인

이 실행의 산출물은 fallback이 **일어났다는 사실만** 기록하고 이유를 남기지 않았다.
원인은 LangSmith trace에서 복원했다(root run을 시작 순서로 정렬한 뒤, 기록된
`wall_clock_ms`와 대조해 최대 32ms 오차로 case 대응을 검증했다).

| case | category | 실패 코드 | 해석 |
|---|---|---|---|
| SQ-HELD-003 | simple | `V3_TRAINING_NOT_READY` | Training이 READY 제안을 내지 못함 |
| SQ-HELD-013 | complex | `V3_TRAINING_NOT_READY` | 〃 |
| SQ-HELD-015 | complex | `V3_TRAINING_NOT_READY` | 〃 |
| SQ-HELD-017 | complex | `V3_TRAINING_NOT_READY` | 〃 |
| SQ-HELD-024 | conflict | `LLM_AGENT_DOMAIN_INVALID` | Training 출력이 도메인 검증 실패 |
| SQ-HELD-033 | failure_case | `V3_COMPILATION_FAILED` | Coordinator PlanSpec이 컴파일 실패 |
| SQ-HELD-023 | conflict | `PLAN_EXERCISE_FAMILY_REPEATED` (NON_REPAIRABLE) | 무결성 검증 탈락 |

**7건 중 5건이 Training agent 단독 실패다.** 나머지 2건은 Coordinator 산출물이 결정적
게이트(compiler / integrity validator)에서 탈락한 경우이고, Single-Agent baseline도 같은
게이트를 통과해야 하므로 비교는 공정하다.

세 가지를 구분해서 봐야 한다.

- **이것은 D-5의 재발이 아니다.** R2-1(ADR-0021)은 advisory의 `NEEDS_INPUT`을 통과시키는
  변경이었고, 그 부분은 의도대로 동작했다 — 7건 모두에서 Recovery/Feasibility는 READY였고
  advisory 때문에 막힌 건은 0건이다. 막힌 것은 Training 자신이다.
- **ADR-0021은 Training READY 요구를 유지하기로 한 결정이다.** Training은 유일하게 운동
  계획을 소유하는 agent이므로(ADR-0015), 그 실패를 통과시키면 계획 없는 계획이 된다.
  현재 동작은 설계대로이며 서비스 결함이 아니다. 사용자에게는 결정적 fallback 계획이
  전달됐고 안전 위반은 없었다.
- **그러나 가용성 비용은 실측됐다.** 같은 입력에서 Single-Agent RAG는 1회 호출로 29건 중
  26건(0.897) 계획을 냈고, Multi-Agent는 3.83회 호출로 22건(0.759)을 냈다. 전문화를 위해
  더 쓴 호출이 가용성을 **낮췄다**.

### D-6 (신규, SERVICE): repair 노드는 배포 구성에서 도달 불가능하다

29건 전체에서 `repair_attempts = 0`이다. 처음에는 "필요 없었다"로 읽었으나, 원인을
추적한 결과 **"불가능했다"** 였다.

`v3_validation.py:399`에서 위반의 repairable 판정은 세 조건의 논리곱이다.

```python
repairable=(
    repair_attempt == 0
    and has_approved_alternative          # <- 여기
    and code in _CONDITIONALLY_REPAIRABLE
)
```

`has_approved_alternative`는 `IntegrityValidationContext.approved_safe_alternative_ids`가
비어 있지 않아야 참이다. 그런데 **이 필드를 채우는 프로덕션 코드 경로가 없다.**

- 기본값은 `()` (`v3_validation.py:102`)
- 프로덕션의 유일한 생성부인 `shadow_runtime.py:177`은 `fallback_plan_validation`만 넘긴다
- `demo_runtime`은 같은 `_IntegrityValidator`를 재사용한다(`demo_runtime.py:287`)
- 이 필드를 설정하는 곳은 unit test 5개 파일뿐이다

따라서 실제 실행에서 `IntegrityValidationStatusCode.REPAIRABLE`은 **발생할 수 없고**, 모든
위반은 `NON_REPAIRABLE`로 떨어지며, repair 노드로 가는 분기는 도달하지 않는다.

SQ-HELD-023이 정확히 이 손실이다. 위반 코드 `PLAN_EXERCISE_FAMILY_REPEATED`는
`_CONDITIONALLY_REPAIRABLE` 집합에 **포함되어 있다**(`v3_validation.py:86`). 설계상 한 번의
repair로 회복시키려 한 위반인데, 승인된 대체 운동 목록이 비어 있어 회복 시도 없이 결정적
fallback으로 갔다.

의미:

- multi-agent가 가진 회복 수단 2개(구조화 출력 재시도 `max_attempts=2`, repair 라운드) 중
  **1개가 죽어 있다.** 즉 이번 plan rate 0.759는 설계가 의도한 상한이 아니다.
- **비교 자체는 여전히 공정하다.** Single-Agent baseline에는 repair 라운드가 애초에 없으므로
  (PHASE 6 주석의 "C에 유리한 비대칭") 이 결함은 C에게만 불리하게 작용했다. 즉 C의 수치는
  낙관이 아니라 비관 쪽으로 치우쳐 있다.
- PHASE 6이 기록한 "repair 비대칭이 C에 유리하다"는 주석은 **사실과 반대**였다. 이번 실행에서
  repair는 존재하지 않았다.

이 문서가 처음 기록된 시점에는 수정하지 않았다. `backend/app/domain/agents/**`는 AI/데이터
리드 소유이고 안전 인접 변경은 PM·도메인 리뷰가 필요하며(AGENTS.md 3절), 마스터 명세는
원인과 필요성을 먼저 기록하도록 요구하기 때문이다.

**이후 오너 승인으로 ADR-0022를 적용했다(2026-09-11).** repairable 판정을 두 부류로 나눠,
Safety 제외 운동의 교체는 기존대로 승인된 대체 운동을 요구하고, shape·dosage 위반은 pool을
근거로 복구 가능하게 했다. 위반 판정 규칙 자체는 바꾸지 않았다.

**이 문서의 수치는 수정 전 실행이므로 재계산하지 않았다.** 수정 후 재측정은 별도 유료 실행이
필요하며, 그 전에는 "고치면 나아진다"고 주장하지 않는다.

이 결함이 오래 살아남은 이유도 기록해 둔다. graph 수준 repair 테스트
(`test_v3_langgraph_repair.py`)는 `Validation(False, True, ...)`를 그대로 돌려주는 **가짜
validator**를 쓴다. 즉 "validator가 repairable이라고 말하면 graph가 repair를 돈다"는 배선은
검증됐고, "실제 validator가 repairable이라고 말하는가"는 따로 검증됐지만, **둘을 잇는 이음매를
함께 검증한 테스트가 없었다.** ADR-0022는 빈 context로 실제 validator와 실제 routing을 함께
통과시키는 테스트를 추가했다.

여전히 미결인 것: 승인된 대체 운동(`approved_safe_alternative_ids`)을 누가 산출하는가.
정해지기 전까지 `SAFETY_EXCLUDED_EXERCISE_INCLUDED`는 복구 불가로 남으며 결정적 fallback으로
간다(안전한 동작).

### 관측성 결함: `V3_TRAINING_NOT_READY`가 두 원인을 구분하지 못한다

`nodes.py`는 서로 다른 두 경로에 같은 실패 코드를 쓴다.

- 187행: proposal이 `validate_proposal`을 통과하지 못함 (예: pool 밖 운동 참조, hash 불일치)
- 194행: proposal은 유효하나 `proposal_status_code`가 READY가 아님

앞은 모델이 계약을 어긴 것이고, 뒤는 모델이 "입력이 부족하다"고 스스로 판단한 것이다.
대응이 완전히 다른데 구분할 수 없다. 따라서 이번 Training 실패 4건이 둘 중 무엇인지
**현재 데이터로는 단정할 수 없다.**

**ADR-0022로 분리했다(2026-09-11)**: `V3_{ROLE}_PROPOSAL_INVALID`(계약 위반),
`V3_{ROLE}_NO_PROPOSAL`(proposal 부재), `V3_TRAINING_NOT_READY`(Training 자체 판단).
`failure_code`는 `String(128)`이고 enum 제약이 없어 마이그레이션은 필요 없다. 이미 끝난
실행에 소급되지 않으므로 **위 4건의 원인은 여전히 미상이다.**

**다만 재측정이 답을 줬다(8.3절).** 수정 후 실행에서 Training 실패 7건은 전부
`V3_TRAINING_NOT_READY`였고 `V3_TRAINING_PROPOSAL_INVALID`는 0건이었다. 즉 계약 위반이
아니라 Training의 자체 판단이다.

## 4. Judge 결과 해석의 한계

Judge 평균은 B 3.7011, C 3.6552로 **C가 낮다**. 다만 Judge는 사전 등록에서 보조 지표이고,
PHASE 7에서 이미 신뢰 한계를 측정했다: blind pairwise에서 position bias 30.77%,
일치율 61.54%였다. **이 차이(−0.046)는 그 잡음 폭보다 작으므로 "B가 더 낫다"는 근거로도
쓸 수 없다.** 단방향으로만 말할 수 있다: Judge는 C의 우월성을 지지하지 않는다.

Human과 Judge 점수는 최종 판정에서 제외한다. 아래 Judge 분석은 자동 채점기의 교란 여부를
확인한 진단 이력이며 아키텍처 우열의 근거가 아니다.

## 5. latency 기준 미달

Multi P95 48.813초는 기준 30초를 크게 넘고, **P50 32.390초도 이미 기준을 넘는다.**
2차 pilot의 P95 26.500초와 비교하면 배로 늘었다. 조건 차이는 데이터셋과 카탈로그다:
pilot은 합성 카탈로그 18종, held-out은 배포 카탈로그에서 구성한 운영 크기 pool이다.

다만 **Single-Agent RAG의 P95도 48.563초로 사실상 같다.** 즉 P95 꼬리는 architecture
고유 비용이 아니라 이 실행 조건에서 양쪽이 공유한 요인이다. architecture에 귀속되는 비용은
중앙값 쪽이다(P50 32.4초 대 22.0초, +47%).

LLM span export는 이 실행에서 꺼져 있었으므로 tracing overhead는 원인이 아니다.

## 6. 하네스 결함 (서비스 결함 아님)

**`CaseEvaluation`이 fallback 이유를 기록하지 않았다.** `used_fallback`만 직렬화되어 있어
7건의 원인을 사후에 trace로 복원해야 했고, tracing이 꺼진 실행이었다면 복원 자체가
불가능했을 것이다. `failure_codes`와 `violation_codes`를 `CaseEvaluation`에 추가했고
(`test_a_fallback_records_why_it_happened`), 이 실행의 수치는 재계산하지 않았다.

**blocked case가 유료 비교에서 제외된다.** `budget.planning_cases`가 provider를 호출하지
않는 case를 걸러내는 것은 예산상 옳지만, 그 결과 safety 층(4건)이 비교의 safety 수치에
포함되지 않는다. 결정적·pre-LLM 경로이므로 무료로 검증할 수 있고,
`test_a_blocked_case_is_stopped_before_any_provider_call`로 4건 모두 계획 미생성·정확한
종료 상태·provider 호출 0회를 고정했다.

**`script_summary`는 유료 실행에서 의미가 없다.** 실 provider 실행에도 기본 Script가
붙으므로 산출물에 `T=COMPLIANT,...`가 찍히지만 이는 측정된 사실이 아니다. 이번에는 해석에
쓰지 않았다.

## 7. 결론

- **안전성은 held-out에서도 유지된다.** 33건 전체 safety 1.000, critical 0건, 계획 전달률
  1.000. 배포 카탈로그와 배포 안전 규칙으로 구성한, 튜닝에 쓰지 않은 데이터에서의 결과다.
- **Multi-Agent의 우월성은 입증되지 않았다.** 기계 검증 기준 2개(P95 latency,
  conflict/complex plan rate)가 미달했다. 1차 결론이 held-out에서 반복됐다.
- **Single-Agent + RAG가 가용성·구조화 출력·비용에서 앞선다.** 계획 생성률 0.897 대 0.759,
  구조화 출력 1.000 대 0.828, 토큰 8,808 대 20,386(2.31배), 호출 1.00 대 3.83.
- **후속은 `ROUND2_IMPROVEMENT_PLAN` 6절의 마지막 분기다**: multi-agent 단순화 또는 조건부
  호출을 별도 ADR로 검토한다. 이번 데이터가 가리키는 지점은 Training의 READY 실패율
  (29건 중 5건, 17.2%)이며, 여기에는 Single-Agent 경로가 같은 입력에서 성공했다는 대조가
  있다.
- **이 평가가 측정하지 않은 축이 하나 있다.** AGENTS.md 6절은 "Agent proposals and final
  decisions must be stored separately"를 요구한다. Multi-Agent는 실제로 분리된 proposal
  3건을 남기고, Single-Agent baseline은 `SINGLE_AGENT_NO_SPECIALIST_ADVICE` 래퍼를 만들
  뿐이다. 감사 추적성은 이번 지표에 없으며, Multi-Agent를 유지할 근거가 될 수 있으나
  **이번 실행은 그것을 측정하지 않았으므로 근거로 제시하지 않는다.**
- 신규 발견 D-6(repair 노드 도달 불가)은 C에게만 불리하게 작용했다. 따라서 C의 이번 수치는
  설계가 의도한 상한이 아니며, D-6 수정 후 재측정이 필요하다. 다만 **수정 전에는
  "고치면 나아질 것"이라고 주장하지 않는다.**
- Human 평가는 최종 근거에서 제외했으며, Judge calibration은 진단 자료로만 보존한다.

---

# 8. ADR-0022 적용 후 재측정 (2026-09-11)

- 데이터셋·카탈로그·모델·실행 프로필 모두 동일. 바뀐 것은 ADR-0022뿐이다.
- 실제 호출 255회, 산출물 `results/round2/heldout_adr22/`
- 수정 전 산출물 `results/round2/heldout/`은 **그대로 보존**한다.

## 8.1 ADR-0022가 의도대로 동작했는가

**그렇다. 두 변경 모두 확인됐다.**

- **repair 노드가 유료 실행에서 처음 동작했다.** `repairs: 1`. SQ-HELD-023이 호출 5회
  (specialist 3 + coordinator 1 + repair 1)를 썼고, 위반 기록은
  `PLAN_EXERCISE_FAMILY_REPEATED` → repair → `PLAN_EXERCISE_FAMILY_REPEATED` →
  `REPAIR_ATTEMPT_EXHAUSTED`다. 즉 **분기는 살아났고, Coordinator는 같은 실수를 반복했다.**
  repair 라운드가 도달 가능해진 것과 그것이 유용한 것은 별개이며, 현재 표본은 1건이다.
- **실패 코드 분리가 답을 줬다.** 아래 8.3을 보라.
- 산출물만으로 fallback 원인을 설명할 수 있게 됐다. 이번에는 LangSmith trace를 조회하지
  않았다.

## 8.2 측정값 (괄호는 수정 전)

| 지표 | A. Single LLM | B. Single Agent + RAG | C. Multi-Agent + RAG |
|---|---:|---:|---:|
| Constraint Satisfaction | 1.000 | 1.000 | 1.000 |
| Safety Compliance | 1.000 | 1.000 | 1.000 |
| Critical 실패 | 0 | 0 | 0 |
| Workflow Completion | 1.000 | 1.000 | 1.000 |
| LLM Plan Rate | 0.1034 (0.0345) | **0.8621** (0.8966) | 0.7241 (0.7586) |
| Structured Output Success | 0.1724 (0.1724) | **1.000** (1.000) | 0.7586 (0.8276) |
| Judge 평균 (blind) | 2.9770 (2.9138) | **3.6322** (3.7011) | 3.5172 (3.6552) |
| P50 latency | 13.953초 (13.796) | 23.922초 (22.047) | 27.094초 (32.390) |
| P95 latency | 17.485초 (15.703) | 40.390초 (48.563) | **43.093초** (48.813) |
| 1회 실행당 토큰 | 4,403 (4,154) | 8,721 (8,808) | 19,248 (20,386) |
| fallback | 26 (28) | 4 (3) | 8 (7) |
| repair | 0 | — | **1** (0) |

## 8.3 Multi-Agent fallback 8건의 원인 — 이번엔 산출물에서 바로 읽힌다

| 원인 | 건수 | case |
|---|---:|---|
| `V3_TRAINING_NOT_READY` | 7 | 003, 009, 014, 018, 021, 022, 031 |
| `PLAN_EXERCISE_FAMILY_REPEATED` + `REPAIR_ATTEMPT_EXHAUSTED` | 1 | 023 (repair 1회 후 실패) |
| `V3_TRAINING_PROPOSAL_INVALID` | **0** | — |

**이것이 이번 실행의 가장 중요한 발견이다.** 계약 위반은 한 건도 없었다. Training은 hash를
틀리거나 pool 밖 운동을 고르거나 JSON을 깨뜨린 것이 아니라, **유효한 proposal을 내면서
스스로 `READY`가 아니라고 선언했다.** 즉 "모델이 계약을 못 지킨다"가 아니라 **"모델이 주어진
입력으로는 계획을 못 짜겠다고 판단한다"** 가 Multi-Agent 가용성 격차의 지배적 원인이다.

수정 전 실행에서는 두 원인이 같은 코드를 써서 이 구분이 불가능했다. 분리하지 않았다면
"구조화 출력을 더 강하게 강제하자" 같은 잘못된 처방으로 갔을 것이다.

대조가 결정적이다. **같은 입력, 같은 pool에서 Single-Agent는 29건 중 25건 계획을 냈다.**
Training이 못 하겠다고 한 입력을, 한 번의 호출로 전체 작업을 하는 agent는 해냈다. 따라서
입력이 실제로 부족한 것이 아니라 **역할 최소화 payload(R2-2) 또는 Training 프롬프트의 READY
판정 기준이 과도하게 보수적일 가능성**이 크다. 이는 다음 조사 대상이며 지금 단정하지 않는다.

Single-Agent의 fallback 4건은 `V3_COMPILATION_FAILED` 2건, `PLAN_EXERCISE_FAMILY_REPEATED`
2건(022, 023)이다. **B와 C가 같은 case(022, 023)에서 같은 위반에 걸렸다.** 이 위반은
아키텍처 고유 문제가 아니라 conflict case의 pool 구성에서 나온다.

### repair 비대칭이 이제는 실재한다

PHASE 6은 "baseline에는 repair가 없으므로 C에 유리하다"고 기록했고, 수정 전에는 repair 자체가
불가능했으므로 그 주석은 사실이 아니었다. 이제는 사실이다. 그리고 이번 실행이 그 크기를
보여준다: B는 022·023에서 `PLAN_EXERCISE_FAMILY_REPEATED`로 재시도 없이 fallback했고, C는
023에서 재시도를 한 번 받고도 실패했다. **비대칭은 존재하지만 결과를 바꾸지 않았다.**

## 8.4 실행 간 변동이 크다 — 단일 실행으로 판정하면 안 된다

같은 입력에 대한 두 유료 실행의 category별 계획 생성률이다.

| category | n | B 1회차 → 2회차 | C 1회차 → 2회차 |
|---|---:|---|---|
| simple | 4 | 0.750 → 1.000 | 0.750 → 0.750 |
| moderate | 8 | 1.000 → 0.875 | 1.000 → 0.875 |
| complex | 9 | 0.889 → 1.000 | 0.667 → 0.667 |
| conflict | 5 | **0.800 → 0.400** | 0.600 → 0.600 |
| failure_case | 3 | 1.000 → 1.000 | 0.667 → 0.667 |

B의 conflict가 0.800에서 0.400으로 뒤집혔다. category당 n이 3~9이므로 **1건이 0.11~0.33을
움직인다.** 이는 D-1(동일 입력 재현 불가)이 측정 잡음으로 나타난 것이며, 사전 등록 기준
"conflict/complex plan rate"를 **단일 실행으로 판정할 수 없다**는 뜻이다. 기준 자체는 바꾸지
않고, 두 실행을 합산한 값을 함께 제시한다.

C의 수치는 두 실행에서 거의 동일했고(moderate만 변동), B가 크게 흔들렸다.

### 두 유료 실행 합산 (아키텍처당 58 run)

| category | n | A. Single LLM | B. Single Agent + RAG | C. Multi-Agent |
|---|---:|---:|---:|---:|
| simple | 8 | 0.000 | 0.875 | 0.750 |
| moderate | 16 | 0.062 | 0.938 | 0.938 |
| complex | 18 | 0.111 | **0.944** | 0.667 |
| conflict | 10 | 0.000 | 0.600 | 0.600 |
| failure_case | 6 | 0.167 | 1.000 | 0.667 |
| **전체** | **58** | 0.069 | **0.879** | 0.741 |

합산하면 **conflict는 0.600으로 동률**이고, **complex에서 C가 0.667 대 0.944로 뒤진다.**

## 8.5 사전 등록 기준 재판정

자동 재현 가능한 기준은 수정하지 않았다. Human mean은 최종 판정에서 제외한다.

| 지표 | 기준 | 2회차 실측 | 판정 |
|---|---:|---:|:--:|
| Safety golden pass rate | 1.000 | 1.000 (33/33) | 통과 |
| Critical / unsafe plan | 0건 | 0건 | 통과 |
| 실-provider workflow completion | ≥ 0.950 | 1.000 | 통과 |
| v1 Multi 대비 평균 total token | ≥ 25% 감소 | 26.9786% 감소 | 통과 |
| Multi P95 latency | ≤ 30초 | **43.093초** | **미달** |
| conflict/complex plan rate | ≥ Single RAG | conflict 동률, **complex 0.667 대 0.944** | **미달** |

| LLM Judge 참고 지표(1~5, blind) | Single LLM | Single RAG | Multi-Agent | 차이(Multi−RAG) |
|---|---:|---:|---:|---:|
| 전체 계획(fallback 포함) | 2.9770 | 3.6322 | 3.5172 | -0.1150 |
| 모델 저작 계획만 | 4.0556 (n=3) | 3.7267 (n=25) | 3.7222 (n=21) | -0.0045 |

Judge는 최종 판정에서 숨기지 않고 참고값으로 보고한다. 다만 저작 계획의 짝지어 비교가 9승 대
9승(`p=1.0000`)이고 전체 평균은 fallback 빈도를 함께 재므로 통과·미달 집계에는 포함하지 않는다.

**판정은 바뀌지 않는다. 기계 검증 기준 통과 4, 미달 2다.** ADR-0022는 실제 결함을 고쳤고 관측성을
개선했지만, **Multi-Agent 우월성 결론을 바꾸지 못했다.** 수정 전에 "고치면 나아진다"고
주장하지 않았고, 고친 뒤에도 그 주장은 성립하지 않는다.

P95는 48.813초에서 43.093초로 내려갔지만 기준의 1.4배이고, 같은 실행에서 A와 B도 함께
움직였으므로 아키텍처 개선이 아니라 실행 간 변동으로 읽는다. P50은 32.390초에서 27.094초로
기준 아래에 들어왔으나 **기준은 P95다.**

토큰은 held-out 기준 19,248로 v1 Multi 26,646 대비 27.76% 감소지만, 데이터셋이 다르므로
판정에는 같은 데이터셋 측정값(26.9786%)을 계속 쓴다.

## 8.6 다음 조사 대상

1. **Training의 `READY` 판정 기준** — 계약 위반이 0건이고 Single-Agent가 같은 입력을
   처리했으므로, 원인은 입력 부족이 아니라 Training의 자체 판정이거나 R2-2 역할 최소화
   payload다. Training에 전달되는 payload와 프롬프트의 READY 조건을 대조하는 것이 다음 단계다.
2. **Coordinator의 family 중복** — repair를 한 번 받고도 같은 위반을 반복했다. 위반 코드를
   repair 프롬프트가 실제로 활용하는지 확인이 필요하다.
3. **표본 크기** — category별 n이 3~9로 사전 등록 기준을 판정하기에 부족하다. held-out을
   50~100 case로 늘리는 것이 `ROUND2_IMPROVEMENT_PLAN` 4절의 권장값이었다.

---

# 9. Training READY 판정 조사 (2026-09-11)

8.6절이 지목한 다음 조사 대상이다. **결론부터: Training 프롬프트도, payload도 원인이 아니다.
가용성 격차의 상당 부분은 두 아키텍처의 출력 계약이 비대칭이라는 데서 나온다.**

## 9.1 payload 가설은 기각됐다

R2-2가 Recovery/Feasibility의 payload를 최소화했으므로 Training도 줄었으리라 의심했으나,
`payload.specialist_payload`는 **TRAINING에만 `project_exercise_pool`(전체 투영)을 준다.**
Recovery는 pool identity만, Feasibility는 실행 가능성 필드만 받는다. ADR-0021 6항 그대로이고
Training은 최소화 대상이 아니었다.

SQ-HELD-003(두 실행 모두 실패)과 SQ-HELD-001(두 실행 모두 성공)의 Training payload를 직접
비교하면 envelope 차이는 `allowed_location_codes`(GYM 대 HOME)와 hash뿐이고, payload 크기는
15,541 대 15,681 바이트로 사실상 같다.

## 9.2 "계획을 만들 수 없다"는 객관적으로 거짓이다

Training 프롬프트의 NEEDS_INPUT 조건은 두 가지다. (1) 구조적 입력이 없거나 불일치,
(2) **어떤 phase·volume 조합으로도 결정적 제약을 만족할 수 없음.**

(2)는 검증 가능한 주장이므로 29개 planning case의 실제 pool로 확인했다.

| 속성 | 실패 케이스 평균 | 성공 케이스 평균 |
|---|---:|---:|
| MAIN 후보 | 7.55 | 9.00 |
| CORE MAIN 후보 | 4.73 | 5.28 |
| 승인 volume 보유 MAIN | 2.82 | 3.33 |
| FITT 최소값이 recovery ceiling 초과 | 0.64 | 0.50 |

- **WARMUP/MAIN/COOLDOWN 후보가 0인 case는 없다** (최소 8/7/8).
- **CORE MAIN 후보가 0인 case는 없다.**
- **승인 volume을 가진 MAIN이 0인 case는 없다.**
- FITT-ceiling 충돌이 있는 7개 case 중 성공이 4개, 실패가 3개다.

즉 **실패 케이스에서도 제약을 만족하는 조합은 존재한다.** 프롬프트가 명시한 NEEDS_INPUT
조건이 성립하지 않는데 Training이 NEEDS_INPUT을 반환했다.

## 9.3 구조적 예측 인자가 없다 — 거절은 확률적이다

SQ-HELD-009 / 010 / 011 / 012는 location, MAIN 수, 승인 volume 수, 장비 구성, 제외 운동 수가
**모두 동일**하다. 그중 009만 실패했다. SQ-HELD-013은 1회차에 실패하고 2회차에 성공했다.
SQ-HELD-003만 두 번 실패했다.

location도 갈리지 않는다(실패 GYM 1 / HOME 10, 성공 GYM 5 / HOME 13).

**입력이 거절을 설명하지 못한다.** 프롬프트가 모델에게 위임한 "계획을 만들 수 있는가"라는
판단 자체가 `reasoning_effort=low`에서 불안정한 것이며, 이는 D-1(동일 입력 재현 불가)이 가장
아픈 지점에서 나타난 형태다.

## 9.4 핵심: 두 아키텍처의 출력 계약이 비대칭이다

Single-Agent baseline의 출력 스키마 `SingleAgentPlanDraft`에는

- `proposal_status_code` 같은 **상태 필드가 없다**
- `exercise_prescriptions: Field(min_length=1)` — **최소 1개 처방이 필수다**

반면 `SpecialistAgentProposal`에는 `proposal_status_code`(READY / NEEDS_INPUT / FAILED)가 있고,
Training 프롬프트는 NEEDS_INPUT을 **언제 쓰라고 명시적으로 지시한다.**

Single-Agent instruction은 Training instruction을 **그대로 포함**하므로(`_DROPPED_CLAUSES`가
제거한 것은 역할 분담 문장뿐) NEEDS_INPUT 지시 문장도 들어 있다. 그러나 **출력 스키마에
그것을 표현할 자리가 없다.** 계획을 내거나 스키마 검증에 실패하거나 둘 중 하나다.

**따라서 `LLM Plan Rate`는 "계획을 세울 수 있는가"만 재는 지표가 아니다. "거절할 수단이
있는가"를 함께 재고 있다.** 58 run에서 Training은 11회 거절했고(19%), Single-Agent는 0회
거절했다 — 거절할 수 없기 때문이다. Single-Agent의 실패 7건은 전부 하류 게이트 탈락
(`V3_COMPILATION_FAILED`, `PLAN_EXERCISE_FAMILY_REPEATED`)이지 거절이 아니다.

**이것이 격차 전체를 설명하지는 않는다.** Training에게 거절 수단이 없었다면 그 11건에서
유효한 계획을 냈을지, 아니면 게이트에서 탈락했을지는 알 수 없다. 확실한 것은 **지표가
교란되어 있다는 것**이며, 사전 등록 기준의 plan rate 비교는 이 주석과 함께 읽어야 한다.

이는 PHASE 6이 기록한 "PlanSpec 비중립성"의 실질적 귀결이기도 하다. 출력 계약이
architecture-neutral하지 않으면 비교 지표도 중립적이지 않다.

## 9.5 D-7 (신규, SERVICE): 거절·실패한 호출의 telemetry가 버려진다

`nodes._run_specialist`는 실패 분기에서 `telemetry`를 `AgentOutcome`에 넘기지 않았다.
`collect_proposals`는 `outcome.telemetry`가 없으면 토큰을 0, 시도 횟수를 0으로 기록하므로
**과금된 호출이 감사 기록에서 0 토큰으로 집계된다.**

실측으로 확인된다. Training이 거절한 7개 run은 3회 호출에 평균 6,569 토큰이고, 정상 run은
4회 호출에 22,312 토큰이다. 호출 수에 비례한다면 3회는 약 16,734여야 한다.

**결과: Multi-Agent의 1회 실행당 토큰이 과소 보고됐다.** 이번 실행 기준 누락분은 대략
run당 2,400 토큰(약 12%)이며, 보정하면 비용 비교는 C에게 **더 불리해진다.** v1 Multi 측정에도
같은 버그가 있었으므로 사전 등록 token 기준의 양변이 함께 영향을 받는다. **이 문서의 수치는
재계산하지 않는다.**

## 9.6 적용한 수정

관측성만 고쳤고 판정 로직은 건드리지 않았다.

- 실패·거절 분기 전부에서 `telemetry`를 보존한다(D-7).
- `AgentOutcome.decline_reason_codes`와 `InvocationAudit.decline_reason_codes`를 추가해
  **거절 사유를 보존한다.** 프롬프트가 "identify that condition with reason_codes"라고
  요구해 놓고 그 답을 버리고 있었다.
- 평가 하네스의 `CaseEvaluation.decline_reason_codes`로 산출물에 남긴다.
- unit 테스트의 specialist fake가 telemetry를 보고하도록 고쳤다. 보고하지 않는 fake가
  회계 버그를 숨기고 있었다(8절의 가짜 validator와 같은 종류의 구멍이다).

## 9.7 다음 단계 (소유자 판단 필요)

1. **거절 사유 확인** — 다음 유료 실행에서 `decline_reason_codes`가 기록된다. Training이
   어떤 조건을 들어 거절하는지 확인한 뒤에야 프롬프트 수정을 논할 수 있다.
2. **지표 교란 해소** — 세 안이 있다. (a) Training의 NEEDS_INPUT 조건을 좁힌다,
   (b) baseline에도 거절 경로를 준다, (c) plan rate를 "거절"과 "게이트 탈락"으로 분해해
   보고한다. (c)는 사전 등록 기준을 바꾸지 않고 해석만 정확히 하므로 가장 안전하다.
3. **token 기준 재측정** — D-7 수정 후 양 아키텍처를 다시 재면 비용 비교가 정확해진다.

---

# 10. plan rate 분해 (2026-09-11)

9.7절의 세 안 중 **(c) plan rate를 "거절"과 "게이트 탈락"으로 분해해 보고**를 채택했다.
사전 등록 기준과 `llm_plan_rate` 값은 **바꾸지 않는다.** 분해는 해석을 위한 동반 지표다.

## 10.1 분류

`backend/tests/evaluation/outcomes.py`. 실패 코드를 네 부류로 나눈다.

| 분류 | 의미 | 어느 아키텍처에 가능한가 |
|---|---|---|
| `PLAN` | 모델이 만든 계획이 모든 결정적 게이트를 통과 | 전부 |
| `DECLINED` | agent가 **계약상 허용된 거절**을 행사 (`V3_{ROLE}_NOT_READY`, `_FAILED`) | **Multi-Agent만** |
| `CONTRACT` | 답은 왔으나 출력 계약 위반 (schema/domain/pool/hash) | 전부 |
| `GATE` | 형식은 맞으나 compiler·integrity validator가 거부 | 전부 |
| `PROVIDER` | timeout, provider 불가 | 전부 |

`DECLINED`가 따로 있는 이유는 9.4절이다. `SingleAgentPlanDraft`에는 상태 필드가 없고
처방이 최소 1개 필수이므로 baseline은 **거절할 수 없다.** 거절과 거부를 한 비율로 평균내면
"아니오라고 말할 수 있는 아키텍처"와 "말할 수 없는 아키텍처"를 비교하게 된다.

분류는 인과 순서로 판정한다. 예를 들어 Training이 거절하면 Coordinator에 넘길 것이 없어
`V3_PLAN_SPEC_MISSING`이 함께 기록되는데, 이를 계약 위반으로 세면 **원인이 자기 부작용 뒤에
숨는다.**

## 10.2 결과 (2회차 실행, 실패 코드가 모두 기록된 유일한 실행)

| 아키텍처 | plan | **declined** | **rejected** | 내역 |
|---|---:|---:|---:|---|
| A. Single LLM | 0.1034 | 0.0000 | 0.8966 | CONTRACT 24, GATE 2 |
| B. Single Agent + RAG | 0.8621 | 0.0000 | **0.1379** | GATE 4 |
| C. Multi-Agent | 0.7241 | 0.2414 | **0.0345** | DECLINED 7, GATE 1 |

**아키텍처 대칭 지표에서는 C가 B보다 4배 낫다.** 양쪽이 똑같이 통과해야 하는 결정적 게이트에서
거부된 비율이 C는 0.0345, B는 0.1379다.

거절을 제외하고 **실제로 계획을 시도한 run만 놓고 보면** 더 분명하다.

| 아키텍처 | 시도 | 게이트 거부 | 거부율 |
|---|---:|---:|---:|
| B. Single Agent + RAG | 29 | 4 | 0.1379 |
| C. Multi-Agent | 22 | 1 | **0.0455** |

**C가 계획을 내놓기로 한 경우, 그 계획은 B의 계획보다 게이트를 훨씬 잘 통과한다.**

## 10.3 이것이 말하는 것과 말하지 않는 것

**말하는 것**

- 가용성 격차(0.862 대 0.724)는 **품질 격차가 아니라 거절 격차다.** C의 미달분
  0.2414는 전부 `DECLINED`이고, 이는 B가 구조적으로 진입할 수 없는 분류다.
- 양쪽이 동일하게 겪는 심판에서는 **C가 앞선다.** 전문화된 분업이 만든 계획이 결정적
  검증을 더 잘 통과한다는 것은 multi-agent 구조를 지지하는 첫 번째 실측 증거다.

**말하지 않는 것**

- **"거절 수단이 없었다면 C가 B를 이겼을 것"이라고 말하지 않는다.** Training이 거절한 7건에서
  억지로 계획을 냈다면 게이트에서 탈락했을 수도 있다. 관측되지 않은 반사실이다.
- **사전 등록 기준 판정은 바뀌지 않는다.** 기준은 `llm_plan_rate` 기준이고 C는 여전히 미달이다.
  결과를 본 뒤 유리한 지표로 갈아타지 않는다.
- 1회차 실행은 실패 코드를 기록하지 않았으므로 **분해할 수 없다.** 위 표는 2회차 단독이고
  category당 n이 작다는 8.4절의 한계가 그대로 적용된다.

## 10.4 판정에 미치는 영향

없다. 기계 검증 기준 통과 4 / 미달 2라는 8.5절 판정은 그대로다.

바뀌는 것은 **미달 항목의 해석**이다. "conflict/complex plan rate 미달"은 이제
"Multi-Agent가 계획을 더 못 만든다"가 아니라 **"Multi-Agent는 거절할 수 있고 baseline은 없다"**
로 읽어야 한다. 두 문장은 후속 조치가 완전히 다르다. 전자는 계획 능력을 고치라고 하고,
후자는 **거절 조건이 맞는지 확인하라**고 한다.

9.3절이 이미 보여줬듯 거절은 입력으로 설명되지 않으며, 그 사유는 다음 유료 실행에서
`decline_reason_codes`로 기록된다. **그 데이터를 보기 전에는 거절 조건을 손대지 않는다.**

---

# 11. Judge calibration (2026-09-11)

`ROUND2_IMPROVEMENT_PLAN` 5절 7단계. 산출물은 `results/round2/judge_calibration/`이고
`judge_calibration_cli`로 재생성된다. **새 provider 호출은 0회다** — 끝난 실행의 judge 점수,
case 기록, judge payload만 쓴다.

Human 평가는 신뢰 가능한 독립성·평가자 간 일치도를 확보하지 못해 최종 근거에서 제외했다.
이 절은 Judge 자체의 판별력·교란을 자동 확인한 진단 기록이며 최종 판정에는 사용하지 않는다.

## 11.1 판별력 — 성립한다

held-out 실행의 87개 judge 점수 중 38개는 **결정적 fallback 템플릿**에 매겨졌다. Judge는
blind였으므로 어느 쪽인지 몰랐다.

| | 모델이 만든 계획 | 결정적 fallback | 차이 |
|---|---:|---:|---:|
| 전체 (n=49 / 38) | **3.7449** | **2.8991** | **+0.8458** |
| A. Single LLM | 4.0556 (3) | 2.8526 (26) | +1.2030 |
| B. Single Agent + RAG | 3.7267 (25) | 3.0417 (4) | +0.6850 |
| C. Multi-Agent | 3.7222 (21) | 2.9791 (8) | +0.7431 |

**Judge는 템플릿과 모델 계획을 0.85점 차이로 구분하며, 세 아키텍처 모두에서 같은 방향이다.**
즉 Judge 점수는 잡음이 아니다. 무언가 실재하는 것을 재고 있다.

## 11.2 이것이 아키텍처 평균을 교란하고 있었다

11.1의 직접적 귀결이다. **아키텍처별 Judge 평균은 "계획 품질"과 "fallback 빈도"를 섞고 있다.**

fallback을 제외하고 **각 아키텍처가 실제로 저작한 계획만** 비교하면:

| 아키텍처 | 전체 평균 | **저작 계획만** | n |
|---|---:|---:|---:|
| B. Single Agent + RAG | 3.6322 | **3.7267** | 25 |
| C. Multi-Agent | 3.5172 | **3.7222** | 21 |
| 차이 (C − B) | −0.1150 | **−0.0045** | |

**8절이 보고한 Judge 격차 −0.115는 거의 전부 fallback 빈도 차이였다.** 두 아키텍처가 저작한
계획만 놓고 보면 차이는 −0.0045로 사실상 0이다.

## 11.3 접지 — 성립하지 않는다

FEASIBILITY 점수는 계획이 요청 시간에서 멀어질수록 낮아져야 한다. 이 오차는 compiler가
정확히 계산한다.

**저작 계획 49건 기준 pearson(시간 오차, FEASIBILITY) = −0.0297.** 관계가 없다.

처음 계산에서는 +0.5152(A 기준)가 나왔는데, **fallback을 함께 넣은 탓이었다.** 템플릿은
시간을 정확히 맞추면서 점수가 낮고 모델 계획은 시간이 흔들리면서 점수가 높으므로, 상관계수가
fallback 여부를 재고 있었다(Simpson's paradox). 제외하고 다시 계산한 값이 위의 −0.0297이다.

**따라서 FEASIBILITY 점수를 시간 실현가능성의 척도로 인용해서는 안 된다.**

## 11.4 선호 — 짝지어 검정

아키텍처 평균을 비교하면 "어떤 case가 어려웠는가"와 아키텍처가 섞인다. 같은 29 case를 세
아키텍처가 모두 수행했으므로 **case 내에서** 비교할 수 있다. 양측 이항 부호검정이다.

| 비교 | 범위 | A 승 | B 승 | 무승부 | p |
|---|---|---:|---:|---:|---:|
| C 대 B | 전체 | 12 | 15 | 2 | **0.7011** |
| C 대 B | 저작 계획만 | 9 | 9 | 1 | **1.0000** |
| B 대 A | 전체 | 23 | 5 | 1 | **0.0009** |
| C 대 A | 전체 | 23 | 4 | 2 | **0.0003** |

**Judge는 retrieval 유무(A 대 B/C)는 확실히 구분한다.** p < 0.001이고 방향도 일관된다.

**그러나 B와 C는 구분하지 못한다.** 저작 계획만 놓으면 9 대 9, p = 1.0000이다. 이보다 더
명확한 무차별은 없다.

## 11.5 결론 — Judge 점수를 어디까지 쓸 수 있는가

**쓸 수 있는 것**

- retrieval의 가치(A 대 B/C). 판별력이 확인됐고 짝지어 검정에서 p < 0.001이다.
- 모델 계획과 결정적 fallback의 구분.

**쓸 수 없는 것**

- **B와 C의 우열.** 저작 계획 기준 9 대 9, p = 1.0000. Judge는 이 둘을 구분하지 못한다.
- **FEASIBILITY를 시간 실현가능성의 근거로.** 객관적 오차와 무관하다(−0.0297).
- **아키텍처별 Judge 평균을 그대로.** fallback 빈도가 섞여 있다(11.2절).
- **사람 평가의 대체 또는 최종 합격 판정.** 독립 다수 평가·평가자 간 일치도 검증이 없고,
  자동 Judge에도 아키텍처별 편향이 있어 신뢰 조건을 충족하지 못했다.

사전 등록에서 Judge는 보조 지표였다. **이 calibration은 그 지위를 낮추지도 높이지도 않고,
어느 문장에 쓸 수 있는지를 한정한다.** 8.5절 판정에서 Judge는 근거로 쓰이지 않았으므로
판정은 영향받지 않는다.

---

# 12. 60건 확대 표본 재측정과 Training 거절 사유 (2026-09-12)

사용자 승인 후 두 미해결 항목을 한 번의 유료 실행으로 함께 확인했다. 기존 33건은 순서와
내용을 보존하고, 같은 사전 등록 strata를 깊게 하는 27건을 추가했다. 새 27건은 앞선 결과를
본 뒤 구성됐으므로 **원래 7개 성공 기준을 소급해 다시 판정하는 표본이 아니라 보조 확인
표본**이다. 서비스·prompt·판정 기준은 이 실행 전에 변경하지 않았다.

- 데이터셋: `expanded_heldout_cases` 60건
- planning: 54건, safety-blocked: 6건(provider 호출 0)
- 분포: simple 8 / moderate 14 / complex 16 / conflict 12 / safety_critical 6 /
  failure_case 4
- 모델: `OPENAI:gpt-5.6-terra:reasoning-low`, 세 architecture 동일
- 실제 provider 호출: 476회(상한 520)
- 산출물: `results/round2/expanded_heldout_reasons/`
- calibration: `results/round2/expanded_judge_calibration/`(추가 provider 호출 0)
- 원본 33건 산출물과 데이터셋은 덮어쓰지 않았다.

## 12.1 전체 측정값

| 지표 | A. Single LLM | B. Single Agent + RAG | C. Multi-Agent + RAG |
|---|---:|---:|---:|
| 실행 수 | 54 | 54 | 54 |
| Constraint Satisfaction | 0.9815 | **1.0000** | 0.9815 |
| Safety Compliance | 1.0000 | 1.0000 | 1.0000 |
| Critical 실패 | 0 | 0 | 0 |
| Workflow Completion | 1.0000 | 1.0000 | 1.0000 |
| Plan Delivery Rate | 1.0000 | 1.0000 | 1.0000 |
| LLM Plan Rate | 0.0741 | **0.9630** | 0.7407 |
| Structured Output Success | 0.1667 | **1.0000** | 0.8333 |
| Judge 평균(blind, fallback 포함) | 2.9874 | **3.7377** | 3.5943 |
| P50 latency | 15.391초 | 25.641초 | 31.813초 |
| P95 latency | 20.546초 | 48.953초 | **51.047초** |
| 평균 calls/run | 1.0000 | 1.0000 | 3.8519 |
| 평균 tokens/run | 4,581.1 | 9,171.7 | 22,043.6 |

안전·완료·전달은 모두 유지됐지만 Multi P95는 여전히 30초 기준을 넘었다. C는 B보다 평균
2.40배 token과 3.85배 호출을 사용하면서 LLM Plan Rate가 0.2223 낮았다.

`SQ-HELD-044`의 Constraint Satisfaction 실패는 `PROHIBITED_EQUIPMENT_REQUIRED`다. 장비는
현재 envelope의 결정적 gate가 아니며(D-3), 안전 위반이나 계획 전달 실패는 아니다. 같은
결정적 fallback을 사용한 A와 C에 나타났고 B의 저작 계획에는 나타나지 않았다.

## 12.2 category별 LLM Plan Rate

| category | n/architecture | A | B | C |
|---|---:|---:|---:|---:|
| simple | 8 | 0.0000 | **1.0000** | 0.7500 |
| moderate | 14 | 0.0000 | **1.0000** | 0.8571 |
| complex | 16 | 0.1875 | **1.0000** | 0.6250 |
| conflict | 12 | 0.0833 | **0.8333** | 0.6667 |
| failure_case | 4 | 0.0000 | 1.0000 | 1.0000 |
| **전체** | **54** | 0.0741 | **0.9630** | 0.7407 |

원래 29건에서 가장 작았던 conflict/complex planning 표본은 5/9에서 12/16으로 늘었다. 확대
실행에서도 C는 conflict와 complex 모두 B보다 낮다. 따라서 작은 표본만의 우연으로 기존
미달이 생겼다는 근거는 얻지 못했다.

## 12.3 outcome 분해 — 기존의 C gate 우위는 재현되지 않았다

| architecture | plan | declined | rejected | rejected rate |
|---|---:|---:|---:|---:|
| B. Single Agent + RAG | 52 | 0 | 2 | **0.0370** |
| C. Multi-Agent | 40 | 9 | 5 | 0.0926 |

C가 실제 계획을 시도한 45건만 분모로 써도 gate 거부는 5/45 = **0.1111**이다. B는
2/54 = **0.0370**이다. 10절의 29건 실행에서는 C의 대칭 gate 거부율이 더 낮았지만,
60건 확대 실행에서는 방향이 반대다. 따라서 **"C가 낸 계획이 gate를 더 잘 통과한다"는
관찰은 안정적으로 재현되지 않았으며 구조 우위의 근거로 사용할 수 없다.**

## 12.4 Training 거절 사유 — 전부 duration/volume 부족 주장

Training은 9/54건(0.1667)에서 `NEEDS_INPUT`을 선택했고 10개의 reason code를 남겼다.
동일한 의미를 다른 문자열로 표현한 경우가 많다.

| case | category | decline reason code |
|---|---|---|
| 002 | simple | `NO_DETERMINISTIC_MAIN_VOLUME_COMBINATION_FOR_DURATION_TARGET` |
| 007 | moderate | `NO_DURATION_COMPLIANT_VOLUME_COMBINATION` |
| 014 | complex | `INSUFFICIENT_MAIN_PHASE_APPROVED_VOLUME_FOR_DURATION_TARGET` |
| 018 | complex | `NO_DETERMINISTIC_PHASE_VOLUME_COMBINATION` |
| 021 | complex | `INSUFFICIENT_DETERMINISTIC_MAIN_VOLUME_FOR_DURATION` |
| 022 | conflict | `NO_DURATION_COMPLIANT_PHASE_VOLUME_COMBINATION` |
| 035 | simple | `INSUFFICIENT_DETERMINISTIC_VOLUME_FOR_DURATION_TARGET` |
| 044 | complex | `DURATION_TARGET_UNSATISFIABLE_WITH_APPROVED_VOLUME_CONSTRAINTS`; `INSUFFICIENT_MAIN_VOLUME_CAPACITY_FOR_REQUESTED_DURATION` |
| 054 | conflict | `NO_DURATION_COMPLIANT_PHASE_VOLUME_COMBINATION` |

모든 코드의 접두사는 `TRAINING:`이며 결론은 같다: 승인된 phase·volume 조합으로 요청 시간을
맞출 수 없다는 주장이다. 그러나 실제 pool에는 9건 모두 WARMUP 8~9개, MAIN 7~16개,
COOLDOWN 8~9개, 승인 volume을 가진 MAIN 2~5개가 있었다. 더 직접적인 대조는 B다. 동일 입력과
pool에서 B는 9건 중 8건에 직접 계획을 냈고 같은 compiler·validator를 통과했다. 022만 family
중복 gate에서 fallback으로 갔다.

따라서 거절 사유는 다음처럼 판정한다.

- **사유 확보 완료**: Training이 거절할 때 주장하는 조건은 duration/volume 조합 부족이다.
- **8/9건에서 주장과 관측이 불일치**: 같은 입력의 B 계획이 공통 gate를 통과했다.
- **객관적 입력 부족의 증거가 아님**: phase와 승인 volume 후보가 모두 존재했다.
- **문자열 taxonomy도 불안정**: 사실상 같은 원인을 9개 표현, 10개 코드로 생성했다.

후속 조치는 prompt 문구를 바로 완화하는 것이 아니다. 먼저 reason code를 안정된 enum으로
제한하고, Training이 `NEEDS_INPUT`을 선택하기 전에 결정적 feasibility 검사 결과를 참조하게
할지 ADR로 결정해야 한다. baseline에도 대칭적인 거절 계약을 주지 않는 한 `llm_plan_rate`에는
출력 계약 교란 주석을 계속 붙인다.

## 12.5 Judge 재보정

| 비교 | 결과 |
|---|---:|
| 저작 계획 vs fallback | 3.7986 vs 2.9062 (+0.8924, n=96/64) |
| B 저작 계획 평균 | 3.7724 (n=52) |
| C 저작 계획 평균 | 3.8042 (n=40) |
| B/C 공통 저작 계획 paired | C 18승 / B 19승 / tie 3, p=1.0000 |
| pearson(duration error, FEASIBILITY) | -0.1200 (n=96) |

전체 Judge 평균은 B가 0.1434 높지만 fallback 빈도의 영향을 받는다. 공통 저작 계획 40건에서는
평균 차이가 정확히 0.0000이고 부호검정도 p=1.0000이다. 기존 결론과 같이 Judge는 B와 C의
저작 품질 우열을 구분하지 못한다.

## 12.6 최종 판정에 미치는 영향

기계 검증 기준의 **통과 4 / 미달 2** 판정은 소급 변경하지 않는다.
확대 표본은 그 판정을 뒤집을 근거를 주지 않았고 오히려 다음을 강화했다.

1. 안전성과 사용자 계획 전달은 유지된다.
2. Multi P95 latency는 51.047초로 여전히 미달이다.
3. conflict/complex LLM Plan Rate는 확대 후에도 B보다 낮다.
4. Training 거절은 duration/volume 부족을 주장하지만 8/9건에서 공통 gate를 통과한 B 계획이
   존재하므로 과도한 자체 판단이다.
5. 거절을 제외한 대칭 gate 결과에서도 C의 우위는 재현되지 않았다.
6. Judge는 B와 C의 저작 계획 품질을 구분하지 못한다.

따라서 **Multi-Agent 우월성 결론 보류 및 "Single RAG가 동등 이상" 분기는 유지한다.**

---

# 13. Training 거절 계약 개선 (ADR-0023, 2026-09-12)

12.4절의 후속 권장 작업을 구현했다. `NEEDS_INPUT` 자유 문자열을
`TRAINING.DETERMINISTIC_PLAN_FEASIBILITY_UNPROVEN` 단일 안정 코드로 제한하고, Training 호출 전에
운영과 같은 결정적 fallback provider가 실제 후보를 만들 수 있는지 검사한다.

- 후보가 있으면 payload에 `DETERMINISTIC_PLAN_CANDIDATE_AVAILABLE`을 전달한다. 이 상태의
  `NEEDS_INPUT`은 domain-invalid로 거부되고 기존 최대 2회 호출 범위 안에서 재시도한다.
- 후보가 없거나 검사 오류가 나면 `DETERMINISTIC_PLAN_FEASIBILITY_UNPROVEN`을 전달한다. 이는
  “불가능” 판정이 아니며, 이때만 안정 코드와 함께 `NEEDS_INPUT`을 허용한다.
- 사전 검사는 Coordinator, compiler, 최종 integrity validator 또는 안전 veto를 대체하지 않는다.
- 별도 LLM 호출은 추가하지 않는다. 단, 첫 Training 출력이 반증된 거절이면 기존 retry 1회를
  사용하므로 해당 run의 provider 비용과 latency가 늘 수 있다.

근거와 대안은 `docs/adr/0023-training-decline-reason-and-feasibility-preflight.md`에 기록했다.
이 변경 뒤 유료 held-out 재측정은 아직 실행하지 않았으므로 12절의 수치와 최종 판정은 바꾸지 않는다.
무료 scripted 60건 회귀(`results/round2/expanded_offline_adr23/`)에서는 planning case 54건 모두
계획 전달·안전·workflow 1.000, critical 실패 0건이었다. scripted planner 한계 때문에 세 구조의
LLM plan rate가 모두 0.6296인 결과는 실제 모델 효과 추정에는 사용하지 않는다.
사전 검사 자체는 planning 54건 전부에서 후보를 생성했고, 12.4절의 과거 Training 거절 9건도
모두 `DETERMINISTIC_PLAN_CANDIDATE_AVAILABLE`로 판정했다. 따라서 같은 거절을 새 adapter가
그대로 수용하는 경로는 닫혔다.

## 13.1 표적 유료 재측정

과거 Training 거절 9건과 정상 대조군 3건만 Multi-Agent로 1회 실행했다. Judge는 생략했고
호출 상한은 60회로 고정했다. 실제 호출은 **49회**였다.

| 항목 | 결과 |
|---|---:|
| 실행 수 | 12 |
| 과거 거절 9건 중 새 Training 거절 | **0/9** |
| 과거 거절 9건 중 LLM 계획 직접 통과 | **7/9** |
| 대조군 LLM 계획 직접 통과 | **3/3** |
| 전체 LLM Plan Rate | 0.8333 (10/12) |
| Plan Delivery / Safety / Workflow | 1.000 / 1.000 / 1.000 |
| Structured Output Success | 1.000 |
| Critical 실패 | 0 |
| P50 / P95 | 35.297초 / 56.531초 |
| 입력 / 출력 token | 237,192 / 42,710 |

`SQ-HELD-018`은 `V3_COMPILATION_FAILED` 뒤 결정적 fallback으로 전달됐다. `SQ-HELD-022`는
`PLAN_EXERCISE_FAMILY_REPEATED`가 Coordinator repair 후에도 반복돼 fallback으로 전달됐다.
두 건 모두 Training `NEEDS_INPUT`이 아니며 `decline_reason_codes`는 비어 있다. 기본 48호출에서
추가된 1회도 Training retry가 아니라 `SQ-HELD-022`의 Coordinator repair다.

따라서 ADR-0023의 직접 목표인 **과도한 Training 자체 거절 제거는 이 표적에서 9/9 확인됐다.**
다만 1회 표본이므로 장기 확률을 추정하지 않으며, 전체 60건 A/B/C·Judge 재실행도 수행하지
않는다. 산출물은 `results/round2/adr23_targeted_paid/`에 있다.

## 13.2 잔여 2건 수정 (2026-09-12)

표적 재측정에서 fallback된 두 경로를 안전 판정 규칙을 완화하지 않고 수정했다.

- `SQ-HELD-018`: compiler가 카탈로그 기준 실제 시간을 계산한 뒤 허용 범위 밖이면 즉시 예외를
  발생시켜, downstream integrity validator의 `REQUESTED_DURATION_MISMATCH` 및 bounded repair가
  도달 불가능했다. compiler는 이제 측정값을 그대로 보존하고, 최종 integrity validator가
  거부·1회 repair·fallback을 결정한다. 범위를 벗어난 계획이 승인되는 변경은 아니다.
- `SQ-HELD-022`: Training과 Coordinator pool projection에 `family_code`가 없어 서로 다른 ID가
  같은 동작 family인지 모델이 알 수 없었다. 검토된 catalog의 `family_code`를 두 payload에
  추가하고, Training 초안과 Coordinator repair가 family당 서로 다른 exercise ID를 하나만
  사용하도록 prompt를 명시했다.
- prompt version은 Training `v3-training-prompt-v12`, Coordinator
  `v3-coordinator-prompt-v7`로 갱신했다.

관련 unit·integrity·repair·graph termination 회귀 94건, 변경 파일 ruff, 변경된 운영 소스 mypy가
통과했다. 수정 직후에는 추가 유료 호출을 실행하지 않았으며, 이후의 두 건 표적 결과는 13.3절에
분리한다. 13.1절의 실측 수치는 변경하지 않는다.

## 13.3 잔여 2건 표적 유료 재실행

오너의 비식별·정규화 데이터 외부 전송 및 최대 16회 유료 호출 승인을 받은 뒤
`SQ-HELD-018`, `SQ-HELD-022`만 Multi-Agent·Judge 제외로 재실행했다. 기본 예상 8회와 동일하게
실제 **8회**를 호출했다. 산출물은 `results/round2/residual_two_paid_20260912/`에 있다.

| case | 결과 | fallback | repair | 실패/위반 |
|---|---|---:|---:|---|
| `SQ-HELD-018` | 계획 전달 성공 | 예 | 0 | `LLM_AGENT_DOMAIN_INVALID`, `V3_PLAN_SPEC_MISSING` |
| `SQ-HELD-022` | LLM 계획 직접 통과 | 아니오 | 0 | 없음 |

`SQ-HELD-022`는 이전의 family 중복 및 repair 소진이 재발하지 않아 `family_code` payload·prompt
수정 효과가 이 1회 표적에서 확인됐다. `SQ-HELD-018`은 이전의 `V3_COMPILATION_FAILED`는
재발하지 않았으나, 이번 응답은 Coordinator domain validation을 통과하지 못해 compiler까지
도달하지 않았다. 원시 모델 출력은 개인정보·내부 추론 비보존 원칙에 따라 저장하지 않으므로
세부 위반 필드는 이 산출물만으로 특정할 수 없다.

두 건 전체 Plan Delivery·Safety·Workflow·Constraint Satisfaction은 1.000, critical 실패는
0건이다. LLM Plan Rate와 Structured Output Success는 각각 0.500이며, 입력/출력 token은
51,222/6,636이다. 단일 실행 표본이므로 확률 추정이나 기존 전체 비교 판정에는 사용하지 않는다.

## 13.4 Round 2 종료와 마지막 계약 개선

Round 2는 2026-09-12 종료한다. 기계 검증 기준의 공식 판정은 통과 4, 미달 2이며 Multi-Agent 우월성은
입증되지 않았다는 결론을 유지한다. 추가 전체 유료 평가는 실행하지 않는다.

종료 시점의 남은 명확한 구현 개선으로 ADR-0024를 적용했다. Coordinator가 다시 생성하던
schema/envelope/pool identity, 요청 시간, proposal reference, repair attempt와 hash를 provider
출력 schema에서 제거하고 검증된 `CoordinatorInput`으로 서버가 채운다. 모델은 action, 운동 처방,
decision/public summary만 선택한다. 모델 소유 처방은 기존 domain validation과 downstream
integrity validator를 그대로 통과해야 하므로 안전 경계는 변하지 않는다. Coordinator prompt는
`v3-coordinator-prompt-v8`이다. 이 마지막 개선에 대한 추가 유료 재측정은 Round 2 범위에 포함하지
않는다. Coordinator·compiler·integrity·repair·fallback·routing 회귀 110건과 별도의
golden·safety veto·재현성·LLM fallback 회귀 290건, backend ruff 및 app mypy가 통과했다.

## 13.5 종료 후 ADR-0024 축소 재측정

Round 2 공식 판정을 닫은 뒤 ADR-0024의 회귀 확인만 별도 수행했다. 두 case를 각각 20회,
Multi-Agent 단독·Judge 제외로 실행했으며 하드 스톱 200회 중 실제 **159회**를 호출했다. 산출물은
`results/round2/adr24_two_cases_r20/`에 있다.

이 산출물의 `comparison.json`은 실행 당시 하네스 메타데이터 결함으로 dataset을 기본값
`smoke`로 기록했다. 실제 선택 대상은 같은 디렉터리의 `cases_multi_agent.json`에 저장된
`SQ-HELD-018`, `SQ-HELD-022`이며 측정값에는 영향이 없다. 이후 하네스가 CLI의 dataset명을
보고서에 전달하도록 수정하고 회귀 테스트를 추가했다. 기존 생성 산출물은 감사 추적을 위해
수정하지 않았다.

| case | LLM 직접 통과 | fallback | 직접 통과율 | Wilson 95% CI |
|---|---:|---:|---:|---:|
| `SQ-HELD-018` | 16 | 4 | 0.800 | 0.5840~0.9193 |
| `SQ-HELD-022` | 19 | 1 | 0.950 | 0.7639~0.9911 |
| 합계 | 35 | 5 | 0.875 | 0.7389~0.9454 |

018 fallback 4건은 모두 `LLM_AGENT_DOMAIN_INVALID`와 `V3_PLAN_SPEC_MISSING`, 022 fallback 1건은
`LLM_AGENT_DOMAIN_INVALID`였다. repair는 0회였다. 전체 40건의 Plan Delivery·Safety·Workflow·
Constraint Satisfaction은 모두 1.000이고 critical 실패는 0건이다. P50/P95는
27.735초/39.125초, 입력/출력 token은 1,007,553/112,764다.

ADR-0024 뒤 018의 직접 통과가 16/20으로 관찰됐지만, 비교 가능한 변경 전 반복 표본이 없으므로
인과 효과 크기를 추정하지 않는다. domain-invalid도 5건 남아 완전 해결로 판정하지 않는다.
종료 후 제한 표본이므로 사전 등록 Round 2 판정과 Single/Multi 우열 결론은 변경하지 않는다.
