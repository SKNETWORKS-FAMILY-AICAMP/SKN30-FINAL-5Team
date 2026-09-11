# ADR-0021: V3 advisory readiness와 역할별 최소 payload

- 상태: ACCEPTED
- 날짜: 2026-09-11
- 소유자: AI/data lead
- 승인자: 개발리드·PM 권한 보유 프로젝트 오너(2026-09-11 대화 승인)
- 관련 ADR: ADR-0015의 specialist readiness 부분을 좁게 수정하며, 나머지 결정은 유지한다.

## 배경

1차 서비스 품질 평가에서 Feasibility가 `NEEDS_INPUT`을 반환한 3개 run이 Coordinator를
건너뛰었다. Training은 유효한 계획을 반환했고 Recovery·Feasibility의 내용은 ADR-0015상
advisory인데도, 세 proposal의 `READY` 여부가 모두 하드 게이트로 동작했다. 이 경로는
안전 위반을 만들지는 않았지만 결정적 fallback으로 전환되면서 개인화 품질과 가용성을 낮췄다.

동시에 Recovery와 Feasibility는 운동 계획을 소유하지 않는데도 Training과 같은 전체 운동
pool projection을 받아 불필요한 입력 토큰을 사용했다.

## 결정

1. Training은 계속 필수 계획 소유자다. Training proposal은 반드시 유효한 `READY`여야 한다.
2. Recovery와 Feasibility는 유효한 `READY` 또는 `NEEDS_INPUT` proposal을 Coordinator에
   전달할 수 있다. `NEEDS_INPUT`은 advisory 부재를 나타낼 뿐 안전·계획 생성 veto가 아니다.
3. specialist 누락, provider/timeout/schema/domain 오류, 명시적 `FAILED`, 잘못된 hash·role·pool은
   기존처럼 Coordinator를 실행하지 않고 검증 가능한 결정적 fallback 또는 계획 없는 종료로 간다.
4. Coordinator는 세 역할의 proposal을 canonical order로 모두 받아야 한다. advisory
   `NEEDS_INPUT`을 임의의 권고로 보완하지 않고 Training 초안과 결정적 envelope를 사용한다.
5. SafetyPolicyEngine, ConstraintEnvelope, compiler, 하류 integrity validator는 변경하지 않는다.
   advisory code에 새 결정론적 강제 계층을 추가하지 않는다.
6. 역할별 최소 payload를 사용한다. Training과 Coordinator는 계획 조립에 필요한 전체 승인 pool을
   받는다. Recovery는 envelope와 pool identity/allowlist만, Feasibility는 실행 가능성 판단에 필요한
   시간·장소·장비·phase 메타데이터만 받는다.

## 이유

- advisory의 의미와 가용성 게이트를 일치시키면서도 필수 Training 및 기술 실패의 fail-closed
  경계를 유지한다.
- 안전 권한은 LLM 응답 가용성이 아니라 결정적 envelope와 최종 validator에 계속 둔다.
- 역할과 무관한 catalog/FITT 필드를 제거해 비용과 지연을 줄이면서 입력 최소화 원칙을 강화한다.

## 선택하지 않은 대안

- 모든 non-READY/실패를 허용: 필수 Training 또는 기술 실패를 부분 proposal로 우회하므로 거부한다.
- Recovery/Feasibility를 제거: 이번 평가의 목표인 multi-agent 구조 자체를 바꾸므로 보류한다.
- advisory code를 결정적으로 강제: ADR-0015의 책임 분리와 충돌하고 중복 안전 계층을 만들므로 거부한다.
- Coordinator에도 축약 pool만 제공: plan 조립·repair에 필요한 catalog timing과 FITT 경계를 잃을 수 있어
  이번 변경에는 포함하지 않는다.

## 결과

- Coordinator input은 세 proposal을 유지하되 역할별 허용 status가 달라진다.
- 공개 API와 DB schema는 바뀌지 않는다.
- prompt version과 평가 baseline version을 올리고 v1 결과와 분리해 2차 평가한다.
- `NEEDS_INPUT` advisory는 proposal 및 invocation evidence에 그대로 남아 재현 가능하다.

## 미확정 사항

- Coordinator pool 자체의 추가 축약은 2차 token profile을 본 뒤 별도 결정한다.
- Recovery/Feasibility 제거 또는 조건부 호출은 multi-agent 구조 비교 결과가 충분할 때 재검토한다.
