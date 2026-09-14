# TASK-DATA-004: 데이터 안전 golden scenario 검증

> 상태: `SUPERSEDED` — 통증 시 Alternative 후보 선택 시나리오는 2026-09-02 폐지됐다. 이 문서는
> 당시의 데이터 검증 기록이며 현재 Safety 정책은 `contraindicated` 필터와 Safety-approved Pool을 사용한다.

- Primary owner: 개발 리드·백엔드/데이터 리드
- 관련 문서: `docs/TEST_STRATEGY.md`, `docs/DOMAIN_RULES.md` 4.3,
  `backend/tests/scenarios/README.md`

## 목적

백엔드 결정 서비스가 아직 구현되지 않은 상태에서 애플리케이션 동작을 임의로 만들지 않고,
현재 카탈로그·안전 규칙·대체 관계만으로 검증 가능한 안전 시나리오를 결정적으로 평가한다.

## 범위

- 정상 상태에서 원래 운동 유지 가능성
- 무릎 MILD에서 충돌 운동 제외와 장소·장비를 충족하는 대체 후보
- 무릎 MODERATE에서 안전 후보가 없을 때 fallback 요구
- 안전 규칙이 제외한 coordinator 제안 후보의 veto
- 장소·장비 부족 시 대체 관계가 있어도 선택하지 않음
- 입력·결과 해시와 policy/catalog/rules/alternatives 버전 추적

## 제외 범위

- 시간 downshift, 웨어러블 fallback, LLM fallback 등 아직 구현되지 않은 백엔드 결정 로직
- API, DB, 프론트엔드 변경
- 정식 데이터 보고서 작성
- 운영 승인

## 인수 조건

1. 모든 시나리오 결과가 입력과 기대값으로 재현된다.
2. 제외된 운동이나 더 어려운 대체 운동은 선택되지 않는다.
3. 장소와 장비 조건을 모두 충족한 대체 후보만 남는다.
4. 안전 후보가 없으면 임의 운동을 선택하지 않고 `FALLBACK_REQUIRED`를 반환한다.
5. 결과는 `production_eligible=false`이며 입력 해시 변조를 탐지한다.
6. 전체 데이터 테스트와 정적 검사가 통과한다.
