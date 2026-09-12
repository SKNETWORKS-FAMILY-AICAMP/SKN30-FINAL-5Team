# ADR-0024: Coordinator PlanSpec의 서버 소유 identity

- 상태: ACCEPTED
- 날짜: 2026-09-12
- 소유자: 개발 리드 / AI·데이터 리드
- 승인자: 프로젝트 오너(사용자 요청, 2026-09-12)
- 관련 근거: `docs/test/ROUND2_HELDOUT_RESULTS.md` 13.3절

## 배경

Round 2 종료 전 두 건 표적 재실행에서 `SQ-HELD-018`은 기존 compilation 실패 대신
`LLM_AGENT_DOMAIN_INVALID`로 fallback됐다. Coordinator provider schema는 모델이 선택할 수 없는
schema version, envelope/pool hash, 요청 시간, 예상 시간, proposal reference, repair attempt와
plan hash까지 반환하도록 요구했다. 이 값은 모두 이미 검증된 `CoordinatorInput`에서 유일하게
결정되므로, 모델이 다시 생성하게 하면 계획 내용과 무관한 표기 오류로 전체 출력을 버릴 수 있다.

## 결정

Coordinator provider schema에서 다음 필드를 제외하고 adapter가 `CoordinatorInput`으로부터
결정적으로 채운다.

- `schema_version`
- `envelope_hash`
- `pool_hash`
- `requested_duration_minutes`
- `estimated_duration_seconds`
- `proposal_references`
- `repair_attempt`
- `plan_hash`

모델은 `action_code`, `exercise_prescriptions`, `decision_codes`, `public_summary_code`만 선택한다.
서버가 조립한 전체 `PlanSpec`은 기존 `validate_against`를 통과해야 하며, compiler가 catalog 기준
실제 시간을 다시 계산한 뒤 downstream integrity validator가 안전·시간·FITT·형태를 검증한다.

## 이유

오케스트레이션 identity를 모델 선택으로 취급할 이유가 없다. 서버 소유 값으로 고정하면 stochastic
표기 오류를 제거하고 동일 input/proposal에 대한 저장·재생 hash를 안정화한다. 운동 처방을
결정적으로 대체하거나 수정하지 않으므로 Training/Coordinator 역할과 ADR-0015 경계를 보존한다.

## 검토한 대안

### prompt만 강화

hash와 proposal reference를 모델이 정확히 복사하도록 요청해도 확률적 실패가 남고 token을 쓴다.

### Coordinator를 제거하고 Training 초안을 그대로 사용

Recovery·Feasibility advisory를 종합하는 현행 승인 구조를 바꾸므로 Round 2 종료 정리 범위를 넘는다.

### domain-invalid 세부 오류를 저장

원시 provider 출력이나 상세 validation 입력 보존은 내부 prompt·건강 context 비보존 원칙과 충돌할
수 있다. 이번 변경은 오류 데이터를 늘리지 않고 오류 원인 자체를 제거한다.

## 영향

- 공개 `PlanSpec` 저장 계약과 schema version은 바뀌지 않는다.
- API·DB migration은 없다.
- 안전 veto, 운동 제약 검증, 1회 repair 상한과 deterministic fallback은 바뀌지 않는다.
- Coordinator prompt version은 `v3-coordinator-prompt-v8`이다.
- ADR-0023과 family-aware 계획 변경을 함께 식별하는 authoritative 배포 런타임의 aggregate
  prompt version은 `v3-prompts-v7`이다.
- LLM payload에 새 사용자 정보는 추가하지 않는다.

## 검증

- 변조된 서버 소유 필드는 adapter가 신뢰하지 않고 canonical input 값으로 재구성한다.
- pool 밖 운동 같은 모델 소유 처방 위반은 이전과 같이 bounded retry 후 domain-invalid가 된다.
- async 초기 조정, repair, compiler, integrity, graph termination 회귀를 함께 실행한다.

구현 후 Coordinator·compiler·integrity·repair·fallback·routing 회귀 110건과 별도의
golden·safety veto·재현성·LLM fallback 회귀 290건이 통과했다. 전체 backend ruff와
`mypy backend/app` 219개 source file도 통과했다.

## 종료 후 표적 실측

오너 승인으로 `SQ-HELD-018`, `SQ-HELD-022`를 각각 20회, Multi-Agent·Judge 제외로 실행했다.
실제 호출은 159회였다. LLM 직접 계획 통과는 018이 16/20(0.800, Wilson 95% CI
0.5840~0.9193), 022가 19/20(0.950, 0.7639~0.9911), 전체 35/40(0.875,
0.7389~0.9454)이었다. 40건 모두 계획 전달·안전·workflow·constraint satisfaction을 통과했고
critical 실패는 0건이었다.

018의 fallback 4건은 모두 `LLM_AGENT_DOMAIN_INVALID`와 `V3_PLAN_SPEC_MISSING`이었고, 022의
fallback 1건은 `LLM_AGENT_DOMAIN_INVALID`였다. 서버 소유 identity 제거 뒤에도 모델 소유 계획
필드의 확률적 domain-invalid는 남으므로 ADR-0024는 완전 제거가 아니라 실패율 감소 장치로
해석한다. 이 결과는 Round 2 공식 판정을 변경하지 않는다.
