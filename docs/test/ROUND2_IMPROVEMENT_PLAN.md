# 2차 멀티에이전트 품질 개선·평가 계획

## 1. 기준선과 목적

- 1차 기준선: commit `3b78731`, tag `evaluation-v1-baseline`
- 1차 결론: 안전성은 확인했지만 Multi-Agent의 비용 대비 우월성은 입증하지 못했다.
- 2차 목적: Safety 불변식을 유지하면서 D-5 가용성, advisory 반영, token/latency를 개선하고
  held-out Human 평가로 Single-Agent RAG 대비 실질적 품질 차이를 검증한다.
- 1차 산출물은 수정하지 않는다. 2차 산출물은 `results/round2/`와 별도 Phase 문서에 저장한다.

## 2. 개선 항목

| ID | 변경 | 기대 효과 | 안전 경계 |
|---|---|---|---|
| R2-1 | Training READY + advisory NEEDS_INPUT 허용 | 불필요한 fallback 감소 | Training/기술 실패는 계속 차단 |
| R2-2 | Recovery/Feasibility 역할별 최소 payload | 평균 token·latency 감소 | envelope/hash/allowlist 유지 |
| R2-3 | advisory status·code 처리 지침 강화 | Coordinator 조정 추적성 향상 | code를 하드 규칙으로 강제하지 않음 |
| R2-4 | prompt version 분리 | v1/v2 재현성 확보 | model/catalog/policy 고정 |

## 2.1 1차 발견 사항 반영 현황 (2026-09-11 확인)

| 1차 발견 | 1차 분류 | 2차 처리 | 확인 위치 |
|---|---|---|---|
| D-1 동일 입력 재현 불가 | SERVICE (LLM 고유) | **미해결, 의도적 보류** | 아래 참조 |
| D-2 계획 미생성 | TEST (하네스) | **하네스 정합 적용** | `scenario._reserved_ranking` |
| D-3 advisory code 무시 | 설계 결과, PM 검토 | R2-3 완료 | coordinator prompt v6 |
| D-4 기본 설정 | 정보 | 배포 설정 확정 | `LLM_AGENTS_REASONING_EFFORT=low` 추가 |
| D-5 advisory non-READY 차단 | 설계 결과, PM 검토 | R2-1 완료, ADR-0021 | `nodes.py`, `v3_contracts.py` |
| PHASE 6 token 3.6배 | 측정 | R2-2 완료 | 평균 total token 26.9786% 감소 |
| PHASE 6 latency 1.8배 | 측정 | reasoning_effort=low | P95 26.500초 |
| PHASE 6 PlanSpec 비중립 | 구조적 발견 | **미해결, 보류** | 아래 참조 |

보류 항목 2건의 사유:

- **D-1**: "동일 입력 → 동일 출력"은 plan 캐싱이나 seed 고정 같은 별도 설계가 필요하며
  2차 범위가 아니다. 결정적 경로(compiler, integrity validator, fallback)는 영향받지 않고,
  저장된 proposal로부터의 재구성은 성립한다. 재현성 요구 수준을 제품 요건으로 확정하는 것이
  선행 과제다.
- **PlanSpec 비중립성**: `PlanSpec`이 canonical 순서의 proposal_reference 3개를 구조적으로
  요구하므로 Single-Agent baseline은 contract adapter를 거쳐야 한다. 출력 계약 변경은
  별도 ADR 대상이며 2차 비교의 타당성에는 영향이 없다(양쪽 모두 동일 게이트 통과).

**D-2 하네스 정합의 실제 효과**: 순위를 선언한 case(14개 중 5개)에서만 동작한다. 나머지
9개는 ranking을 선언하지 않으므로 운영도 snapshot에 순위를 저장하지 않아 변화가 없다.
합성 카탈로그 기준 fallback 성공률은 0.50으로 그대로이며, 남은 격차의 주 원인은 **pool 구성이
아니라 합성 카탈로그가 얇다는 점**(18종 중 WARMUP 4 / COOLDOWN 4)이다. held-out 설계 시
카탈로그 선택을 명시적으로 결정해야 한다(6.1절).

## 3. 사전 등록 성공 기준

| 지표 | 통과 기준 |
|---|---:|
| Safety golden pass rate | 1.000 |
| Critical / unsafe plan | 0건 |
| 실-provider workflow completion | 0.950 이상 |
| Multi - Single RAG Human mean | +0.20 이상 |
| v1 Multi 대비 평균 total token | 25% 이상 감소 |
| Multi P95 latency | 30초 이하 |
| conflict/complex case plan rate | Single RAG 이상 |

한 기준이라도 미달하면 “Multi-Agent가 더 유효하다”는 결론을 내리지 않는다. Judge 점수는 보조
지표이며 Human 결과를 대체하지 않는다.

## 4. 데이터와 비교 통제

- 기존 20 case는 구현 회귀와 tuning에만 사용한다.
- held-out은 최소 30 case, 권장 50~100 case로 구성한다.
- safety, conflict, limited-time, missing wearable, recovery, equipment/location, provider failure를
  층화한다.
- Multi-Agent와 Single-Agent RAG는 같은 model version, catalog, policy, 요청 snapshot,
  compiler, validator를 사용한다.
- 표시 순서를 무작위화하고 architecture label을 숨긴다.
- PM과 개발리드는 합의 전 독립 점수를 각각 남긴다.

## 5. 실행 게이트

1. 계약·unit·privacy·golden/safety 테스트
2. 기존 20 case 오프라인 회귀
3. 실-provider 5~10 case smoke 및 LangSmith span 확인
4. 10~20 case 유료 pilot, 실패·token·latency 검토
5. held-out 전체 실행
6. 독립 blind Human 평가
7. Judge calibration을 별도 산출
8. 성공 기준 판정과 최종 보고

유료 단계마다 실제 run 수, 예상 최대 호출 수, 사용 model을 manifest에 기록한다. smoke 또는 pilot에서
unsafe plan, critical failure, privacy 위반이 1건이라도 나오면 전체 실행을 중단한다.

## 6. 결과 판정

- 모든 기준 통과: Multi-Agent v2 승격 후보
- 안전 통과, 품질/비용 미달: 서비스 안전성은 유지하되 architecture 우월성 결론 보류
- 가용성만 개선: D-5 수정은 유지하고 prompt/구조는 추가 실험
- Single RAG가 동등 이상: multi-agent 단순화 또는 조건부 호출을 후속 ADR로 검토

## 6.1 held-out 카탈로그 결정 (착수 전 확정 필요)

held-out은 `provider failure`를 층화에 포함하므로 fallback 경로가 의도적으로 실행된다.
합성 카탈로그에서는 그 경로의 성공률이 운영보다 비관적이므로, 사전 등록 기준
"workflow completion 0.950 이상"과 "conflict/complex plan rate"가 운영에 존재하지 않는
조건 때문에 미달할 수 있다.

| 선택지 | 내용 | 영향 |
|---|---|---|
| A | **배포 카탈로그(v2.0.7-final, 237종)** 에서 held-out pool 구성 | fallback 수치가 운영 대표성을 가짐. 카탈로그 로더는 이미 있음(`production_catalog.py`) |
| B | 합성 카탈로그 유지 | 세 architecture에 동일 적용되므로 **비교는 유효**하나 절대 수치는 비관적. 사전 등록 기준 판정에 주석 필요 |

미결정 상태로 held-out을 실행하면 결과 해석이 사후 조정되므로 착수 전에 고정한다.

**결정(2026-09-11): A 채택.** 사용 카탈로그는 **`exercise-catalog-v2.0.7-final`** 이다.

카탈로그 버전 선택에서 한 번 틀렸던 기록을 남긴다. 최초 `production_catalog.py`는
`approvals.py`의 최신 승인 항목을 배포본으로 가정해 v2.0.8을 읽었다. `approvals.py`는 승인된
artifact 레지스트리이고 배포는 어떤 promotion 명령을 실행했는지로 정해진다.
`infra/deployment/README.md`는 v2.0.7만 릴리스 경로로 문서화하며 v2.0.8 절이 없고, 배포된 FITT
참조도 `v2_0_7_fitt_stable_code_mapping.csv`에 고정되어 있다.

두 카탈로그는 같은 237종을 담지만 fallback이 계획 시간을 계산하는 필드가 다르다
(`default_rest_seconds` 14종, `default_work_seconds` 13종, `family_code` 12종). 따라서 D-2
재확인을 v2.0.7로 다시 수행했고 **결론은 유지된다**(14 case × 12 slice = 1.00, 제외 8배까지 동일).
`test_the_replay_uses_the_catalog_the_service_deploys`가 재발을 막는다.

## 7. 진행 현황 (2026-09-11)

- R2-1~R2-4 구현 완료
- 오프라인 회귀와 전체 자동 테스트 통과
- specialist payload byte 49.8192% 감소
- Training intensity 의미 보정 후 tuning smoke 5/5, 실패 케이스 반복 3/3 통과
- `reasoning_effort=low`와 Coordinator 최소 payload를 적용한 최종 pilot 14/14 통과
- 최종 pilot safety 1.0, critical/fallback/repair 0건, P95 26.500초
- v1 Multi 대비 평균 total token 26.9786% 감소
- 1차 발견 사항 반영 현황 확인 완료(2.1절): D-5·D-3·D-4·token·latency 반영, D-1과
  PlanSpec 비중립성은 사유를 남기고 보류
- D-2 하네스 정합 적용(`scenario._reserved_ranking`), 회귀 434 passed / 2 skipped
- **held-out dataset 고정 완료**: 33 case, `datasets/heldout_cases.json`,
  카탈로그 `exercise-catalog-v2.0.7-final`
  - 층화: simple 4 / moderate 8 / complex 9 / conflict 5 / safety_critical 4 / failure_case 3
  - 제외 운동은 배포 안전 규칙(`safety/safety_rules.jsonl`)에서 도출하며 직접 작성하지 않는다
  - pool은 배포 카탈로그를 운영 eligibility로 거른 뒤 snapshot loader가 크기·phase를 정한다
    (121 eligible → 15종 등)
  - tuning 20건과 case_id·내용 모두 겹치지 않음을 테스트로 고정
- 오프라인 3-architecture 배관 점검: 29 planning case 전부 계획 생성, critical 0,
  세 architecture 결과 동일(fallback 8건도 동일)
- **held-out 유료 실행 완료(2026-09-11)**: 29 planning case × 3 architecture, 실 호출 256회.
  결과와 사전 등록 기준 판정은 `docs/test/ROUND2_HELDOUT_RESULTS.md`.
  - 통과: safety 1.000(33/33), critical 0건, workflow completion 1.000, token −26.9786%
  - 미달: Multi P95 48.813초(기준 30초), conflict/complex plan rate 0.600/0.667
    (Single RAG 0.800/0.889)
  - 미판정: Human mean(+0.20) — 독립 blind 평가 미실시
  - 판정: 6절의 **"Single RAG가 동등 이상"** 분기. Multi-Agent 우월성 결론 보류
  - Multi fallback 7건 중 5건이 Training agent 단독 실패(`V3_TRAINING_NOT_READY` 4,
    `LLM_AGENT_DOMAIN_INVALID` 1). advisory 차단은 0건이므로 D-5 재발이 아니다
- **D-6 발견 및 수정, 재측정 완료(2026-09-11)**: ADR-0022. repair 노드가 배포 구성에서
  도달 불가능했고(승인 대체 운동 목록을 아무도 채우지 않음), specialist 실패 코드가 계약
  위반과 자체 판단을 구분하지 못했다. 둘 다 고친 뒤 held-out을 재실행했다(255 호출,
  `results/round2/heldout_adr22/`).
  - ADR-0022는 의도대로 동작: repair 1회 실제 발생(SQ-HELD-023), 실패 코드 분리 확인
  - **판정은 바뀌지 않음**: P95 43.093초(기준 30초) 미달, complex plan rate 0.667 대 0.944 미달
  - **가용성 격차의 지배적 원인 확정**: Training 실패 7건 전부 `V3_TRAINING_NOT_READY`이고
    `V3_TRAINING_PROPOSAL_INVALID`는 **0건**. 계약 위반이 아니라 Training의 자체 판단이며,
    같은 입력을 Single-Agent는 29건 중 25건 처리했다. R2-2 역할 최소화 payload 또는
    Training 프롬프트의 READY 조건이 다음 조사 대상이다
  - **실행 간 변동이 크다**: B의 conflict plan rate가 0.800 → 0.400으로 뒤집혔다. category별
    n이 3~9라 1건이 0.11~0.33을 움직이므로 단일 실행으로는 판정할 수 없다. 두 실행 합산
    (58 run)은 B 0.879 대 C 0.741, conflict는 0.600 동률, complex는 0.944 대 0.667
- **Training READY 조사 및 plan rate 분해 완료(2026-09-11)**: 9~10절.
  - payload 가설 기각: `specialist_payload`는 TRAINING에만 전체 pool을 준다(R2-2 대상 아님)
  - 프롬프트 조건도 객관적으로 성립하지 않음: 실패 case 전부 WARMUP/MAIN/COOLDOWN 후보,
    CORE, 승인 volume을 보유. 구조가 동일한 4개 case 중 1개만 실패 → 거절은 확률적
  - **원인은 출력 계약 비대칭**: `SingleAgentPlanDraft`에는 상태 필드가 없고 처방이 최소 1개
    필수라 baseline은 거절할 수 없다. `llm_plan_rate`는 "거절 수단 유무"를 함께 재고 있었다
  - **(c)안 채택**: 사전 등록 기준·값은 그대로 두고 `outcomes.py`로 분해해 병기
  - 분해 결과(2회차): 아키텍처 대칭 지표인 게이트 거부율은 **C 0.0345 대 B 0.1379**.
    계획을 시도한 run만 보면 C 0.0455 대 B 0.1379 — **C가 낸 계획이 게이트를 더 잘 통과한다**
  - **판정은 불변**: 미달 항목의 해석만 바뀐다
- **D-7 수정**: 실패·거절 분기가 telemetry를 버려 과금된 호출이 0 토큰으로 집계됐다.
  Multi-Agent 토큰이 run당 약 12% 과소 보고됐고, 보정하면 비용 비교는 C에게 더 불리하다
- **Judge calibration 완료(2026-09-11)**: 11절, `results/round2/judge_calibration/`.
  provider 호출 0회. 독립 blind Human 평가는 오너 판단으로 생략됐으므로 사람 일치는 판정하지
  않고, 사람 라벨 없이 확인 가능한 세 가지로 Judge의 사용 범위를 한정했다.
  - **판별력 성립**: blind 상태에서 모델 계획 3.7449 대 결정적 fallback 2.8991(+0.8458),
    세 아키텍처 모두 같은 방향. Judge는 잡음이 아니다
  - **아키텍처 평균이 교란돼 있었다**: fallback 빈도가 섞인다. 저작 계획만 비교하면
    C 3.7222 대 B 3.7267로 차이는 **−0.0045**, 8절의 −0.115는 거의 전부 fallback 빈도였다
  - **접지 실패**: 저작 계획 49건에서 pearson(시간 오차, FEASIBILITY) = −0.0297.
    FEASIBILITY를 시간 실현가능성의 근거로 인용할 수 없다
  - **짝지어 부호검정**: C 대 B는 저작 계획 기준 9 대 9, **p = 1.0000** — Judge는 둘을 구분하지
    못한다. 반면 B 대 A는 p = 0.0009, C 대 A는 p = 0.0003으로 retrieval 가치는 명확히 구분한다
  - 1차 편향(Multi-Agent +0.33)은 조건이 달라 **빼지 않고 기록만** 한다
- 다음 게이트: 8단계 성공 기준 판정과 최종 보고

### 하네스 한계 (held-out 해석 시 유의)

스크립트 provider용 `planner.compose_prescriptions`는 배포 카탈로그에서 긴 세션의
요청 시간을 채우지 못해 29건 중 8건이 결정적 fallback으로 넘어간다(45분 요청에서
1,358초 구성 등). **오프라인 배관 점검에만 영향이 있고 유료 실행에는 영향이 없다**:
실제 모델은 MAIN 반복으로 시간을 채우며 2차 pilot 14/14에서 fallback 0건이었다.
세 architecture에 동일하게 적용되므로 비교 속성도 유지된다.
- 상세: `docs/test/ROUND2_LOCAL_RESULTS.md`
