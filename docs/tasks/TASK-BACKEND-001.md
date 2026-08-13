# TASK-BACKEND-001: 백엔드 공통 기반과 개발 착수 게이트

- Primary owner: 백엔드
- Reviewers: 개발팀장, API 계약 영향 시 프론트엔드
- 관련 요구사항: `NFR-001`, `NFR-002`, `NFR-003`, `NFR-005`, `NFR-006`
- 관련 ADR: `ADR-0001`, `ADR-0003`, `ADR-0004`, `ADR-0007`
- 목표 브랜치: `feat/backend-development-readiness`

## 배경과 사용자 가치

백엔드에는 모듈 경계 문서만 있고 실행 가능한 애플리케이션, DB migration, 테스트와 CI가 없다. 기능 개발자가 같은 설정·오류·DB·검증 경계를 재사용할 수 있도록 최소 기반을 먼저 만든다.

## 포함 범위

- Python package manager와 CI runtime 결정
- FastAPI app factory와 `/api/v1` router
- liveness/readiness, 공통 오류 envelope, `X-Request-ID`
- 요청 body·header를 기록하지 않는 구조화 로그
- SQLAlchemy engine/session과 빈 Alembic baseline
- DRAFT 카탈로그의 production 사용 차단
- unit/API test와 PostgreSQL migration CI

## 제외 범위

- 사용자·인증·동의 테이블
- 운동 카탈로그의 실제 DB 적재
- 루틴·체크인·결정·에이전트·운동 세션 구현
- Firebase·소셜·웨어러블·캘린더 실제 provider 연결
- 안전·복귀·시간 정책값 추가
- production 배포 provider 선택

## 인수 조건

1. `uv sync --frozen --group dev`로 개발 환경을 재현한다.
2. Python 3.12를 CI 기준 runtime으로 사용한다.
3. `/api/v1/health/live`는 DB 연결 없이 200을 반환한다.
4. `/api/v1/health/ready`는 DB가 준비되면 200, 실패하면 공통 오류의 `503 DATABASE_UNAVAILABLE`을 반환한다.
5. 모든 응답에 서버가 생성한 UUID `X-Request-ID`가 있다.
6. 오류 응답과 로그에 DB URL, token, email, full name, request body와 stack trace를 노출하지 않는다.
7. Alembic baseline을 PostgreSQL에서 upgrade, downgrade, upgrade할 수 있다.
8. production 환경은 catalog manifest가 없거나 `review.production_eligible=true`가 아니면 시작하지 않는다.
9. formatter, linter, type checker, unit/API test와 migration CI가 구성된다.

## 변경 예상 파일

- `pyproject.toml`, `uv.lock`
- `backend/app/**`
- `backend/alembic.ini`, `backend/migrations/**`
- `backend/tests/**`
- `backend/.env.example`, `backend/README.md`
- `.github/workflows/backend.yml`
- 관련 개발·기술·테스트 문서

## API 영향

기존 계약에 정의된 health endpoint를 처음 구현하고 성공 응답과 503 응답을 구체화한다. 다른 공개 API는 추가하거나 변경하지 않는다.

## DB·마이그레이션 영향

애플리케이션 테이블이 없는 Alembic baseline만 추가한다. 제품 테이블은 기능별 계약·migration에서 추가한다. downgrade는 baseline 이전 상태로 돌아간다.

## 안전·개인정보·보안 영향

- request body·Authorization·DB URL을 로그에 기록하지 않는다.
- production에서 미승인 데이터 사용을 fail-closed로 차단한다.
- 건강·사용자 데이터를 수집하거나 저장하지 않는다.

## 선행 관계와 차단 요소

- package manager는 저장소에 이미 사용 중인 `uv`로 결정한다.
- CI 기준 Python은 기술 계약의 최소 버전인 3.12로 결정한다.
- PostgreSQL CI baseline은 16으로 결정한다. 실제 배포 지원 버전은 배포 ADR에서 확정한다.
- 로컬 PostgreSQL 또는 Docker가 없으면 실제 migration 왕복 검증은 CI에서 수행한다.

## 테스트 계획

- settings와 production catalog gate unit test
- live/ready/request ID/error envelope API test
- Alembic revision 구조와 offline SQL 검사
- CI PostgreSQL에서 upgrade/downgrade/upgrade
- ruff, mypy, pytest

## 수동 확인

1. `uv sync --frozen --group dev`
2. `uv run uvicorn backend.app.main:app --reload`
3. `/api/v1/health/live`와 `/api/v1/health/ready` 확인

## 알려진 제한과 후속 작업

- 실제 product table과 repository는 후속 기능 task에서 추가한다.
- Firebase와 외부 provider 설정은 adapter task에서 추가한다.
- 로컬 Compose는 Docker daemon과 port·credential 정책을 검증한 후 별도 task로 추가한다.
