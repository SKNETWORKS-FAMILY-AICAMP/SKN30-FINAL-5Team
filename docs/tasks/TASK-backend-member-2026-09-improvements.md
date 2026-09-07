# TASK-backend-member-2026-09-improvements: 2026-09 백엔드 팀원 개선 작업

- Primary owner: backend member
- Reviewers: backend owner, development/data lead (agent and rule changes), frontend owner (public API compatibility)
- 관련 요구사항: BM-1~BM-6, F004, POL-008~POL-013
- 관련 ADR: ADR-0004, ADR-0015, ADR-0017
- 목표 브랜치: `feat/backend-member-2026-09-improvements` → `develop`

## 배경과 사용자 가치

Daily Check-in 시간, 운동 상세 콘텐츠, HOME 장비 대체, 장소 선택, 계획 이름 및 완료 세션 kcal 추정의
2026-09 개선을 하나의 백엔드 팀원 작업으로 제공한다.

## 포함 범위

`docs/tasks/2026-09-improvements/BACKEND-MEMBER.md`의 BM-1~BM-6 전체와 각 작업에 명시된
호환 가능한 API·도메인 규칙 문서 갱신.

## 제외 범위

각 BM 블록의 제외 범위를 그대로 적용한다. DB migration, 프론트엔드 구현, 웨어러블 kcal 수집,
주간 kcal 합계 노출은 포함하지 않는다.

## 인수 조건

BACKEND-MEMBER.md의 BM-1~BM-6 인수 조건 전체. 90분 정책과 MET kcal 상세는 이번 작업의
명시적 사용자 진행 승인에 따라 관련 source-of-truth에 함께 확정한다.

## 변경 예상 파일

BM-1~BM-6에 열거된 backend source, backend tests, `docs/API_CONTRACT.md`,
`docs/DOMAIN_RULES.md`, `docs/DATA_MODEL.md`, `docs/SERVICE_POLICY_SAFETY_AND_ADAPTATION_V1.md`,
`docs/adr/0004-safety-calorie-privacy-retention.md`.

## API 영향

새 공개 응답 필드는 optional로 추가한다. 기존 request·response 필드의 read/write 호환을 유지한다.
BM-3은 `location_code` optional query를 사용한다. 이 endpoint는 대체 운동 표시 전용이며 현재
당일 check-in을 조회하는 catalog 공개 service가 없다. 미지정은 기존 목록을 반환해 구버전 클라이언트를
보호하고, 신규 클라이언트의 GYM/OUTDOOR 요청만 빈 목록으로 제한한다.

## DB·마이그레이션 영향

없음. 기존 세션 kcal 컬럼을 채우며 새 스키마를 만들지 않는다.

## 안전·개인정보·보안 영향

시간 요청 보존, Safety envelope, Recovery ceiling 및 공식 블록 완료 기준을 유지한다. kcal은
MET·체중·완료 블록 누적 시간 기반의 비의료적 추정치이며 안전 입력으로 사용하지 않는다. 식별자나
원시 건강 정보를 로그에 남기지 않는다.

## 선행 관계와 차단 요소

G3, G4, G5, G7은 2026-09-07 확정됐다. BM-1을 먼저 완료한 후 BM-2~BM-6을 순차 진행한다.

## 테스트 계획

각 BM에 명시된 unit/API/golden/regression 테스트와 `ruff format`, `ruff check`, `mypy`를 실행한다.

## 수동 확인

90분 Check-in, HOME/GYM 변형 조회, 기본 Check-in 장소 목록, 운동 상세 단계/주의사항, 완료·중단
세션 kcal 응답을 API에서 확인한다.

## 알려진 제한과 후속 작업

프론트 표시(FE-1/2/4/6/10), 주간 kcal 합계(BL-4), legacy 프로필 장소 필드 제거(BL-7)는 별도
담당 작업이다.
