# TASK-BACKEND-002: DRAFT 운동 카탈로그 core importer

- Primary owner: 백엔드
- Reviewers: 개발팀장, 데이터 담당
- 관련 요구사항: `NFR-001`, `NFR-003`, `NFR-005`, `NFR-006`
- 관련 ADR: `ADR-0001`
- 목표 브랜치: `feat/backend-catalog-core-importer`

## 배경과 사용자 가치

운동 데이터 파이프라인이 만든 DRAFT manifest와 JSONL을 애플리케이션 DB 계약에 맞게
검증하고, local/test 환경에서만 재현 가능하게 적재한다. 검증 실패나 운영 환경 오사용은
부분 적재 없이 차단해 미검수 카탈로그가 사용자 추천으로 이어지지 않게 한다.

## 포함 범위

- catalog version과 exercise core SQLAlchemy model
- body area, movement pattern, training type, body focus, equipment, location lookup
- exercise-body/equipment/location 관계
- repository와 application importer service
- manifest·JSONL Pydantic schema와 `StrEnum` 기반 MVP v1 코드 집합
- manifest schema version, 상태, hash, byte/record count 검증
- artifact directory 경계 검증과 all-or-nothing transaction
- version_code와 manifest hash 기반 멱등 import 및 충돌 차단
- Alembic migration과 downgrade
- unit, repository, PostgreSQL integration test
- local/test 환경의 DRAFT import

## 제외 범위

- 공개 exercise API
- routine, recommendation, alternative, safety rule 적재
- agent 또는 Coordinator
- production seed 승격
- `data/generated/**` 수정
- Firebase, 사용자, 프로필, 동의
- 새 production dependency
- 안전 reason code와 미확정 의료·운동 임계값

## 인수 조건

1. 정상 DRAFT manifest와 JSONL을 local/test DB에 원자적으로 적재한다.
2. 동일 version/hash 재실행은 중복 행을 만들지 않는다.
3. 동일 version_code의 다른 manifest hash를 거부한다.
4. 파일 hash 또는 byte count가 다르면 거부한다.
5. record count가 다르면 거부한다.
6. manifest 경로가 artifact directory 밖이면 거부한다.
7. catalog version 안의 중복 stable_code를 거부한다.
8. production과 staging 환경에서는 DRAFT importer를 거부한다.
9. importer 실패 시 catalog와 exercise의 부분 행이 남지 않는다.
10. 전용 `*_test` PostgreSQL DB에서 migration upgrade/downgrade/upgrade가 성공한다.
11. `production_eligible=false`와 `DOMAIN_APPROVED`를 production-safe 상태로 해석하지 않는다.

## 변경 예상 파일

- `docs/tasks/TASK-BACKEND-002.md`
- `docs/DATA_MODEL.md`
- `backend/app/modules/catalog/**`
- `backend/app/db/models/**`
- `backend/app/db/repositories/**`
- `backend/migrations/env.py`
- `backend/migrations/versions/0002_catalog_core.py`
- `backend/tests/unit/**`
- `backend/tests/integration/**`

## API 영향

공개 endpoint, 요청·응답 필드와 공통 오류 코드를 추가하거나 변경하지 않는다. Pydantic
`StrEnum`은 importer 내부 입력 경계에서만 사용한다.

## DB·마이그레이션 영향

PostgreSQL에 catalog version, exercise core, lookup과 관계 테이블을 추가한다. machine code는
PostgreSQL ENUM 대신 문자열 CHECK 또는 lookup FK로 검증한다. UUID, FK, UNIQUE를 명시하고,
JSONB는 form cue와 schema version이 있는 manifest metadata에만 사용한다. downgrade는 이번
revision이 만든 테이블을 역순으로 제거한다.

## 안전·개인정보·보안 영향

- importer는 local/test에서만 허용하고 staging/production에서는 fail-closed한다.
- manifest 상대 경로를 resolve한 뒤 artifact directory 내부인지 검증한다.
- 원천 파일 내용, 사용자 정보, 인증 정보와 건강 데이터를 로그에 기록하지 않는다.
- 이번 작업은 안전 규칙을 해석하거나 임계값을 추가하지 않는다.

## 선행 관계와 차단 요소

- 시작 Alembic head는 최신 develop의 `0001_backend_baseline`이다.
- 승인된 taxonomy registry hash와 실제 산출물 schema가 일치해야 한다.
- source/license 정보를 산출물 근거 없이 추정해야 하면 구현을 중단한다.
- 병렬 PR이 migration head를 변경하면 임의 병합하지 않고 재기준화한다.

## 테스트 계획

- manifest/JSONL schema, hash, byte/count, 경로, 중복 코드 unit test
- importer 환경 guard와 멱등·manifest 충돌 unit test
- PostgreSQL repository 적재와 transaction rollback integration test
- Alembic upgrade/downgrade/upgrade integration test
- ruff, mypy, 전체 pytest와 관련 data pipeline test

## 수동 확인

1. local/test 설정과 전용 PostgreSQL DB를 준비한다.
2. 최신 DRAFT catalog artifact directory를 importer에 전달한다.
3. catalog version, exercise, lookup, 관계 행 수를 확인한다.
4. 같은 artifact를 다시 적재해 행 수가 변하지 않는지 확인한다.
5. production 설정에서 같은 요청이 DB 접근 전에 거부되는지 확인한다.

## 알려진 제한과 후속 작업

- DRAFT 데이터는 사용자 추천이나 공개 API에서 조회하지 않는다.
- production 승격과 외부 도메인 검수 증적은 별도 작업이다.
- alternatives, safety rules, goal tag 관계는 후속 importer에서 추가한다.
- 사용자 표시명은 PM 승인 데이터로 별도 관리하며 machine code를 대체하지 않는다.
