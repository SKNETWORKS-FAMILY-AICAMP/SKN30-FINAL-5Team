# ADR-0025: 후보 생성·교차 검토·제한 조정 멀티에이전트 실험

- 상태: ACCEPTED
- 날짜: 2026-09-15
- 소유자: AI/data lead
- 승인자: 프로젝트 오너(2026-09-15 대화에서 관련 ADR 일괄 승인)
- 관련: ADR-0015, ADR-0021, ADR-0023, ADR-0024

## 배경

Round 2·3 비교에서 현행 Multi-Agent는 Single-Agent+RAG보다 더 많은 호출과 토큰을 사용했지만
계획 품질 우위를 보이지 못했다. Training만 계획을 소유하고 Recovery·Feasibility 권고는 최종
선택에 인과적으로 연결되지 않으며, Coordinator가 유효한 Training 계획을 다시 작성해 새로운
계약 실패 지점을 만든 것이 주요 원인이다.

## 결정

운영 V3를 즉시 변경하지 않고 평가 전용 `MULTI_AGENT_CANDIDATE_REVIEW` 구조를 검증한다.

1. Training 단계는 동일 envelope와 pool을 참조하는 서로 다른 후보 두 개를 제출한다.
2. Recovery와 Feasibility는 두 후보를 모두 순위화하고, 후보에 대한 제한 조정만 제안한다.
3. 허용 조정은 세트 감소, 반복 감소, 휴식 증가처럼 기존 값을 보수적으로만 바꾸는 명령이다.
4. Coordinator는 후보 ID와 Specialist가 실제 제출한 조정 ID만 선택한다. 운동 처방을 다시 쓰지 않는다.
5. 서버가 선택·조정을 결정적으로 적용해 기존 `PlanSpec`을 만들고, 기존 compiler와 integrity
   validator가 Safety envelope, 승인 pool, 시간, 장소, Recovery ceiling을 다시 검사한다.
6. 장비 보유 여부는 후보 생성·리뷰·선택 조건이 아니다.
7. 후보, 리뷰, 선택, 적용 조정은 각각 canonical hash를 가져 위조와 사후 변경을 탐지한다.

## 실험 경계

- 이번 증분은 `backend/tests/evaluation/**`와 문서만 변경한다.
- 공개 API, DB schema, 운영 graph, 안전·통증·회복 규칙은 변경하지 않는다.
- 무료 구조·안전 회귀를 통과하기 전 유료 provider 평가를 실행하지 않는다.
- 운영 전환은 별도 ADR과 API/DB·영속화 영향 검토가 필요하다.

## 인수 조건

- 두 후보가 처방상 실제로 달라야 한다.
- Specialist는 존재하는 후보만 평가하고 조정할 수 있다.
- Coordinator는 리뷰에 없는 조정을 만들거나 후보 처방을 다시 쓸 수 없다.
- 완화 방향의 조정과 서로 충돌하는 조정은 거부된다.
- 선택 결과는 기존 compiler와 downstream integrity validator를 우회하지 않는다.
- Safety 제외 운동, pool 이탈, 시간·회복 상한 위반은 최종 계획으로 전달되지 않는다.

## 보안·개인정보·호환성

새 외부 입력은 없다. 실험 계약은 기존 비식별 envelope·pool·처방만 참조하며 직접 식별자와 원시
건강정보를 추가하지 않는다. 운영 API·DB와 기존 저장 레코드에는 영향이 없다.

## 후속 결정

무료 검증 후 실제 모델용 adapter와 blinded 평가 rubric을 별도 증분으로 추가한다. 운영 승격은
Specialist 개입률, 후보 변경률, 안전·전달률, 지연·토큰과 Single-Agent+RAG paired 결과를 함께
검토한 뒤 결정한다.
