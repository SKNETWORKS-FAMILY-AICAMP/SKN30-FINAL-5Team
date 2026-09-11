# 2차 held-out 유료 평가 결과

> 1~7절은 **ADR-0022 수정 전** 실행이다. 수정 후 재측정과 최종 판정은 **8절**에 있다.
> 두 실행의 판정 결과는 같다: 사전 등록 기준 2개 미달, 1개 미판정.

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

`ROUND2_IMPROVEMENT_PLAN` 3절에서 결과를 보기 전에 고정한 기준이다. 기준은 수정하지 않았다.

| 지표 | 통과 기준 | 실측 | 판정 |
|---|---:|---:|:--:|
| Safety golden pass rate | 1.000 | 1.000 (33/33) | 통과 |
| Critical / unsafe plan | 0건 | 0건 | 통과 |
| 실-provider workflow completion | ≥ 0.950 | 1.000 | 통과 |
| Multi − Single RAG **Human** mean | ≥ +0.20 | 미측정 | **미판정** |
| v1 Multi 대비 평균 total token | ≥ 25% 감소 | 26.9786% 감소 | 통과 |
| Multi P95 latency | ≤ 30초 | **48.813초** | **미달** |
| conflict/complex case plan rate | ≥ Single RAG | **complex 0.667 / conflict 0.600** | **미달** |

token 기준에 대한 주석: 사전 등록 문구는 "v1 Multi 대비"이고 v1은 튜닝 데이터셋에서
측정됐다. 따라서 판정에 쓴 26.9786%는 **같은 데이터셋에서의 대응 측정**
(`ROUND2_IMPROVEMENT_PLAN` 7절)이다. held-out에서의 1회 실행당 20,386 토큰을 v1의 26,646과
직접 비교하면 23.49% 감소지만, 데이터셋과 카탈로그가 달라 사전 등록된 비교가 아니므로
판정 근거로 쓰지 않았다. 두 수치 모두 기록한다.

**판정: 2개 기준 미달, 1개 미판정. 따라서 "Multi-Agent가 더 유효하다"는 결론을 내리지 않는다.**
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

기준 4(Human mean +0.20 이상)는 **여전히 미측정**이며, Judge 점수로 대체하지 않는다.
PM과 개발리드의 독립 blind 평가가 남아 있다.

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
- **Multi-Agent의 우월성은 입증되지 않았다.** 사전 등록 기준 2개 미달(P95 latency,
  conflict/complex plan rate), 1개 미판정(Human). 1차 결론이 held-out에서 반복됐다.
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
- 남은 게이트: 독립 blind Human 평가(6), Judge calibration(7). **둘 다 사람이 필요하며
  이 실행으로 대체되지 않는다.**

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

기준은 수정하지 않았다.

| 지표 | 기준 | 2회차 실측 | 판정 |
|---|---:|---:|:--:|
| Safety golden pass rate | 1.000 | 1.000 (33/33) | 통과 |
| Critical / unsafe plan | 0건 | 0건 | 통과 |
| 실-provider workflow completion | ≥ 0.950 | 1.000 | 통과 |
| Multi − Single RAG **Human** mean | ≥ +0.20 | 미측정 | **미판정** |
| v1 Multi 대비 평균 total token | ≥ 25% 감소 | 26.9786% 감소 | 통과 |
| Multi P95 latency | ≤ 30초 | **43.093초** | **미달** |
| conflict/complex plan rate | ≥ Single RAG | conflict 동률, **complex 0.667 대 0.944** | **미달** |

**판정은 바뀌지 않는다. 2개 미달, 1개 미판정.** ADR-0022는 실제 결함을 고쳤고 관측성을
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
