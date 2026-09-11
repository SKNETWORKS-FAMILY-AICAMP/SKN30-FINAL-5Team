# 2차 품질 개선 로컬 검증 결과

- 기준일: 2026-09-11
- 작업 브랜치: `fix/v3-round2-quality-improvement`
- v1 기준선: `3b78731` / `evaluation-v1-baseline`
- 상태: 실-provider 최종 pilot 14/14 통과, held-out 2차 평가 준비 가능

## 1. 구현 결과

- Training은 계속 유효한 `READY` proposal이 필수다.
- Recovery/Feasibility의 유효한 `NEEDS_INPUT`은 proposal로 보존되어 Coordinator에 전달된다.
- 누락, 명시적 `FAILED`, timeout, provider/schema/domain 오류, 잘못된 proposal은 기존처럼
  fallback 또는 계획 없는 종료로 간다.
- Coordinator input schema는 `v3-coordinator-input-v2`로 올렸다.
- Recovery/Feasibility/Coordinator prompt는 각각 v4/v4/v6으로 올렸다.
- 실행 단위 prompt version은 최초 `v3-prompts-v2`, Training 보정 후 `v3-prompts-v3`,
  Coordinator payload 축약 후 `v3-prompts-v4`이며 Multi-Agent LangSmith experiment는
  `multi-agent-v2`로 분리했다.
- Recovery는 pool identity만, Feasibility는 실행 가능성에 필요한 catalog 필드만 받는다.
- Coordinator는 운동 선택 metadata를 중복 수신하지 않고 Training 초안의 시간·phase·FITT volume
  확인에 필요한 최소 pool projection만 받는다.
- 구조화 agent 호출의 `reasoning_effort`를 `low`로 고정했다.
- SafetyPolicyEngine, compiler, integrity validator, 공개 API, DB schema는 바꾸지 않았다.

## 2. Payload·예산 예측

14개 planning case에서 세 specialist의 canonical input payload를 합산했다.

| 지표 | v1 | v2 | 감소율 |
|---|---:|---:|---:|
| Specialist payload bytes | 687,132 | 344,808 | 49.8192% |
| 전체 평가 prompt token 예측(25% headroom 포함) | 1,327,202 | 832,982 | 37.2377% |
| Phase 4 pilot prompt token | 259,358 | 160,514 | 38.1110% |

payload byte는 tokenizer를 거치기 전 canonical JSON 크기이며 실제 token 결과를 대체하지 않는다.
실제 total token 25% 감소 기준은 provider smoke와 held-out 평가에서 다시 판정한다.

## 3. 오프라인 비교

- 대상: 기존 planning case 14개, Single LLM / Single-Agent RAG / Multi-Agent
- 결과: 세 architecture 모두 14/14 plan delivery, safety 1.0, critical 0건
- Multi-Agent: 14/14 LLM plan path, fallback 0건, workflow 1.0
- 산출물: `results/round2/offline/`

기존 case는 tuning/regression 용도이므로 이 결과로 architecture 우월성을 주장하지 않는다.

## 4. 자동 검증

- 변경 영역 contract/routing/prompt/privacy: 62 passed
- V3 + LangChain unit: 397 passed, 999 deselected
- golden + evaluation: 436 passed, 2 skipped, local Qdrant warning 1개
- 전체 suite: 2,268 passed, 91 skipped, local Qdrant warning 1개
- Ruff format: 814 files formatted
- Ruff check: passed
- mypy: 219 source files passed
- Training 후속 보정 범위(V3/LangChain/evaluation): 468 passed, 2 skipped,
  local Qdrant warning 1개
- 최종 reasoning/payload/deployment 회귀: 547 passed, 2 skipped,
  local Qdrant warning 1개

91개 skip은 `TEST_DATABASE_URL` 또는 명시적 PostgreSQL/Qdrant 환경이 필요한 기존 integration
테스트와 plan 없는 Judge fixture 2건이다. 이번 변경에는 API/DB schema 영향이 없다.

## 5. 실-provider smoke와 원인 분석

PM·개발리드 권한자의 외부 전송 승인 후 OpenAI와 LangSmith를 사용해 tuning case 5건을
Judge 없이 최대 20회 호출로 실행했다. 최초 결과는 4/5 통과, safety 1.0, critical 0건이었다.
`SQ-MODERATE-001`만 fallback 후 계획 없이 종료됐으며 실패 코드는
`V3_TRAINING_NOT_READY`, `V3_FALLBACK_PLAN_UNAVAILABLE`이었다.

LangSmith trace의 역할별 구조화 출력에서 다음을 확인했다.

- Training: `NEEDS_INPUT`, reason `NO_INTENSITY_COMPATIBLE_EXERCISE`
- Recovery: `READY`, `RECOVERY_CONSTRAINTS_PRESERVED`
- Feasibility: `READY`, `FEASIBILITY_CONSTRAINTS_PRESERVED`

해당 pool의 FITT reference intensity는 `MODERATE`, recovery ceiling은 `LOW`였다. 계약상 FITT
intensity는 운동 적격성 필터가 아니고 최종 prescription intensity를 recovery ceiling 안에서
별도로 선택해야 한다. Training이 두 값을 같은 적격성 축으로 해석한 것이 직접 원인이었다.

## 6. Training 보정과 재검증

- Training prompt를 `v3-training-prompt-v10`으로 올렸다.
- FITT intensity는 reference metadata이며 운동 제외 조건이 아님을 명시했다.
- downshift는 prescription intensity와 volume으로 표현하도록 명시했다.
- `NEEDS_INPUT`은 실제 필수 입력 누락·불일치 또는 deterministic constraint를 만족할 조합이
  정말 없는 경우로 제한했다.
- 유료 CLI에 반복 가능한 `--case-id` 필터를 추가해 실패 케이스만 저비용으로 재검증할 수 있게 했다.

실-provider 결과:

| 실행 | 통과 | 호출 | fallback | critical | 결과 경로 |
|---|---:|---:|---:|---:|---|
| `SQ-MODERATE-001` 3회 반복 | 3/3 | 12 | 0 | 0 | `results/round2/paid_smoke_retry/` |
| tuning smoke 5건 재실행 | 5/5 | 20 | 0 | 0 | `results/round2/paid_smoke_v3/` |

5건 재실행의 workflow completion, structured output, safety compliance, role consistency,
state consistency, conflict resolution accuracy는 모두 1.0이었다. P50은 23,250ms, P95는
34,500ms이고 input/output token 합계는 각각 87,741/16,771이다. 이 smoke는 tuning set
검증이므로 architecture 우월성의 근거로 사용하지 않으며, 다음 판정은 미사용 held-out set으로 한다.

## 7. Token·latency 보정과 최종 pilot

첫 14개 provider pilot은 전부 성공했지만 P95가 33.375초로 사전 기준 30초를 초과했고,
v1 Multi 대비 평균 total token 감소율도 22.2053%로 25% 기준에 미달했다. LangSmith 역할별
P95는 Training 18.720초, Coordinator 15.267초로 두 직렬 단계가 병목이었다.

구조화 호출의 provider-default 추론량 변동을 없애기 위해 `reasoning_effort=low`를 명시했다.
5건 smoke에서 5/5 성공을 유지하며 P95가 25.578초로 낮아졌다. 이어 Coordinator가 새 운동을
선택하지 않는 계약에 맞춰 선택용 catalog metadata를 제거하고, 시간 산정·phase·FITT volume
필드만 유지했다. 최종 prompt aggregate version은 `v3-prompts-v4`다.

최종 14개 provider pilot 결과:

| 지표 | 결과 | 사전 기준 | 판정 |
|---|---:|---:|---|
| workflow completion | 14/14 = 1.000 | 0.950 이상 | 통과 |
| safety compliance | 1.000 | 1.000 | 통과 |
| critical / unsafe plan | 0건 | 0 | 통과 |
| fallback / repair | 0 / 0 | 관찰 | 이상 없음 |
| P50 / P95 latency | 23.672초 / 26.500초 | P95 30초 이하 | 통과 |
| 평균 total token | 19,456.93 | v1 대비 25% 이상 감소 | 통과 |
| v1 Multi 평균 total token | 26,645.50 | 기준선 | - |
| token 감소율 | 26.9786% | 25% 이상 | 통과 |

최종 산출물은 `results/round2/paid_pilot_final/`에 저장했다. 이 결과는 기존 tuning dataset에
대한 gate 판정이며, Multi-Agent가 Single-Agent RAG보다 우수하다는 결론은 최소 30개 held-out
실행과 독립 blind Human 평가 전에는 내리지 않는다.
