# P1-E · 추천 이유 생성 — backend

## 목표

V3 결정 생성·재생성 결과에 Training, Recovery, Feasibility 제안과 결정적
SafetyPolicyEngine 결과를 근거로 한 공개 추천 이유를 생성하고, 결정과 같은 트랜잭션에 저장한다.

## 인수 조건

- V3 성공 응답은 `TRAINING`, `RECOVERY`, `SAFETY`, `FEASIBILITY`, `COORDINATOR` 고정 순서의
  `public_agent_summaries`를 제공한다. `SAFETY`는 LLM Agent가 아니라 SafetyPolicyEngine 결과의
  공개 투영이다.
- Agent의 `reason_codes`, `adjustment_codes`, `evidence_reference_codes`는 템플릿 선택과 선택적
  narration 입력에 연결하되 machine code를 공개 문장에 직접 삽입하지 않는다.
- Safety 요약은 제외된 운동 수와 적용된 recovery cap을 포함한다.
- 선택적 LLM narration은 이미 확정·검증된 문장 필드만 바꿀 수 있다. veto, provider 장애,
  비공개 payload 또는 출력 검증 실패 시 검수 템플릿으로 되돌아가며 운동 계획은 변하지 않는다.
- 설명 source와 template/prompt/model/fallback version은 기존 `decision_explanations`에 저장한다.
- 공개 API 필드와 DB 스키마는 변경하지 않는다.

## 변경 범위

- `backend/app/modules/decisions/explanations.py`
- `backend/app/modules/decisions/v3_creation.py`
- `backend/app/modules/decisions/v3_application.py`
- `backend/app/integrations/v3_application_composition.py`
- 관련 단위·통합·golden/safety fallback 테스트

## 위험과 대응

- Safety veto 우회: veto가 있으면 narration provider를 호출하지 않고 검수 문구만 사용한다.
- 개인정보 노출: 외부 payload는 machine code, 정수, 불리언, null만 허용하며 운동 UUID와 원시
  check-in을 포함하지 않는다.
- 호환성: 기존 optional 응답 필드와 `decision_explanations` 스키마를 그대로 사용한다.
- 재현성: V3 전용 template/prompt version과 fallback reason을 저장한다.
