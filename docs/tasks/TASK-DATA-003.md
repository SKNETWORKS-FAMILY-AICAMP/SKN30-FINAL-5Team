# TASK-DATA-003: MVP 운동 대체 관계 DRAFT 생성

- Primary owner: 개발 리드·백엔드/데이터 리드
- 관련 문서: `docs/DATA_MODEL.md` 5.7~5.8, `docs/DOMAIN_RULES.md` 4.3,
  `docs/MVP_SCOPE.md` 11.4, `data/AGENTS.md`
- 목표 브랜치: `feat/data-001-pipeline-bootstrap`

## 배경

MVP 카탈로그 50개와 안전 제외 규칙 277개는 준비됐지만 `exercise_alternatives`가 없어
충돌 운동을 제거한 뒤 목표 보존형 대체 후보를 찾을 수 없다. 외부 전문가 상시 검토가
어려운 조건을 반영해 에이전트 단독 DRAFT 정책으로 관계를 만들되 운영 승인을 주장하지
않는다.

## 포함 범위

- 동일한 검토 목표 그룹 안에서 방향성 있는 대체 관계 생성
- 대체 난이도가 원래 운동보다 높지 않도록 제한
- 장비·장소·난이도 변경 사유의 기계 판독 가능 기록
- 무릎 불편 시 하체 목표 보존을 위한 무릎 중심·엉덩관절 중심 패턴의 교차 관계
- 기존 안전 규칙과 결합한 MILD/MODERATE 후보 커버리지 보고
- 카탈로그·정책·안전 규칙 입력 해시 추적
- 변조·누락·중복·미등록 운동을 거부하는 fail-closed 검증

## 제외 범위

- 외부 운동·의료 전문가 승인
- 사용자 상태에 대한 진단·치료·재활 판단
- API, DB schema, migration 또는 운영 DB 적재
- 프론트엔드 노출과 실제 루틴 자동 교체
- 안전 규칙을 우회하는 대체 선택

## 인수 조건

1. 관계의 양 끝 운동이 최신 50개 DRAFT 카탈로그 안에 존재한다.
2. 자기 자신을 대체하거나 더 어려운 운동으로 대체하는 관계가 없다.
3. 관계는 방향성이 있고 `reason_code`, `goal_preservation_code`, `difficulty_delta`를 가진다.
4. 모든 결과는 `review_method_code=AGENT_ONLY`, `production_eligible=false`다.
5. `DOMAIN_APPROVED`는 `PIPELINE_COMPATIBILITY_ONLY`로 명시한다.
6. 무릎 MILD에서 KNEE_DOMINANT 운동마다 안전 필터 후 하체 대체 후보가 하나 이상 있다.
7. 무릎 MODERATE에서 목표 보존이 불가능하면 관계를 안전하다고 강제하지 않고
   RECOVERY/REST fallback 필요성을 보고한다.
8. 입력·출력 해시 검증과 단위 테스트가 통과한다.
9. API와 DB 계약은 변경하지 않는다.

## 위험

- 같은 movement pattern이라도 세부 운동 목적은 다를 수 있다. 따라서 명시적인 목표 그룹을
  정책에 고정하고 자동 근육명 추론을 금지한다.
- 대체 관계 자체는 최종 안전 판정이 아니다. 현재 불편 부위, 심각도, 장소, 장비를 적용해
  안전 규칙으로 다시 필터링해야 한다.
- 에이전트 DRAFT는 전문가 승인으로 승격할 수 없다.

## 테스트

- 정책 그룹·카탈로그 참조 무결성
- 자기 대체·난이도 상승·중복 관계 거부
- 방향성 관계 생성
- 무릎 MILD 대체 커버리지와 MODERATE fallback 보고
- 출력 해시 변조 탐지
- 전체 데이터 스크립트 ruff, format, mypy, unit test
