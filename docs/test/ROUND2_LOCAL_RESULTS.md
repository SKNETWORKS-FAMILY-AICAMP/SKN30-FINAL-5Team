# 2차 품질 개선 로컬 검증 결과

- 기준일: 2026-09-11
- 작업 브랜치: `fix/v3-round2-quality-improvement`
- v1 기준선: `3b78731` / `evaluation-v1-baseline`
- 상태: 로컬 구현·검증 완료, 실-provider smoke는 외부 전송 재승인 대기

## 1. 구현 결과

- Training은 계속 유효한 `READY` proposal이 필수다.
- Recovery/Feasibility의 유효한 `NEEDS_INPUT`은 proposal로 보존되어 Coordinator에 전달된다.
- 누락, 명시적 `FAILED`, timeout, provider/schema/domain 오류, 잘못된 proposal은 기존처럼
  fallback 또는 계획 없는 종료로 간다.
- Coordinator input schema는 `v3-coordinator-input-v2`로 올렸다.
- Recovery/Feasibility/Coordinator prompt는 각각 v4/v4/v6으로 올렸다.
- 실행 단위 prompt version은 `v3-prompts-v2`, Multi-Agent LangSmith experiment는
  `multi-agent-v2`로 분리했다.
- Recovery는 pool identity만, Feasibility는 실행 가능성에 필요한 catalog 필드만 받는다.
- SafetyPolicyEngine, compiler, integrity validator, 공개 API, DB schema는 바꾸지 않았다.

## 2. Payload·예산 예측

14개 planning case에서 세 specialist의 canonical input payload를 합산했다.

| 지표 | v1 | v2 | 감소율 |
|---|---:|---:|---:|
| Specialist payload bytes | 687,132 | 344,808 | 49.8192% |
| 전체 평가 prompt token 예측(25% headroom 포함) | 1,327,202 | 918,722 | 30.7776% |
| Phase 4 pilot prompt token | 259,358 | 177,662 | 31.4993% |

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

91개 skip은 `TEST_DATABASE_URL` 또는 명시적 PostgreSQL/Qdrant 환경이 필요한 기존 integration
테스트와 plan 없는 Judge fixture 2건이다. 이번 변경에는 API/DB schema 영향이 없다.

## 5. 실-provider smoke 대기 사유

실행 요청은 provider process 생성 전에 정책 검토에서 차단되어 OpenAI/LangSmith 호출은 0건이다.
LangSmith span에는 직접 식별자나 원시 건강 정보는 없지만, `excluded_exercise_ids`, recovery ceiling,
목표·장소·요청 시간 등으로 건강 상태를 간접 추론할 수 있다. 따라서 다음 두 외부 전송을 각각
인지한 명시 승인이 필요하다.

1. 정규화된 평가 payload와 모델 응답을 OpenAI API로 전송
2. 같은 payload·응답·간접 건강 추론 가능 값을 LangSmith SaaS로 전송하고 span으로 보존

승인 후 tuning case 5건, Judge 제외, 최대 20회 호출로 smoke를 재개한다.
