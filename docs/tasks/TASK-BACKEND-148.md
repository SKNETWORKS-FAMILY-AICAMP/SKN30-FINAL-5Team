# TASK-BACKEND-148: V2 PostgreSQL 실제 릴리스 검증

- 현재 상태: `IN_PROGRESS`
- 우선순위: `P0`
- GitHub issue: `#148`
- Primary owner: 백엔드·데이터 개발팀장
- Reviewers: 백엔드 팀원, 데이터 담당
- 관련 요구사항: 기존 catalog·database·release 계약 유지; 새 요구사항 ID 없음
- 관련 ADR: `ADR-0014`
- 목표 브랜치: 이슈 전용 branch/worktree 또는 검증 evidence PR
- 승인자 역할: 백엔드·데이터 개발팀장
- 승인일: 2026-08-26

## 배경과 사용자 가치

V2 catalog의 코드와 migration이 병합됐어도 실제 전용 PostgreSQL 환경에서 migration round trip,
bundle import, activation과 공개 조회까지 재현하지 않으면 릴리스 준비를 주장할 수 없다. 이 작업은
DB 연결과 실제 명령 실행이 필요한 운영 검증을 개발팀장 책임으로 분리한다.

## 포함 범위

- 사용자 워킹트리와 분리된 clean worktree 준비
- 이름이 `_test`로 끝나는 전용 PostgreSQL DB 준비
- frozen dependency 환경 구성
- Alembic 단일 head 확인
- `upgrade head -> downgrade base -> upgrade head` 실제 round trip
- V2 bundle import와 DRAFT 확인
- catalog 102건, safety rule 394건, alternative 285건, goal tag 102건,
  prescription 137건 확인
- 명시적 activation과 단일 ACTIVE catalog 확인
- import/activation 멱등성 확인
- exercise list/detail과 media visibility 확인
- 전체 backend/data formatter, lint, mypy, test 실행
- `TASK-BACKEND-147` CI 자동화와 실제 명령 일치 확인
- 실행 증적과 rollback 절차 기록

## 제외 범위

- production DB와 실제 사용자 데이터
- 기존 사용자 dump 복원
- V3 production 활성화
- RDS, S3, KMS, IAM 구축
- 공개 API·DB schema 변경

## 인수 조건

1. 정확한 `origin/develop` SHA와 실행 환경을 기록한다.
2. 전용 PostgreSQL test DB에서 migration round trip이 성공한다.
3. V2 import 직후 DRAFT 및 승인된 exact count가 확인된다.
4. activation 이후 단일 ACTIVE catalog가 확인된다.
5. import와 activation 재실행이 멱등하다.
6. 미승인 media는 노출되지 않고 registry 승인 media만 노출된다.
7. formatter, linter, mypy, backend/data tests의 실제 결과를 기록한다.
8. 실패 또는 skip을 숨기지 않고 원인과 영향 범위를 기록한다.
9. rollback 또는 forward-fix 절차가 재현 가능하게 문서화된다.
10. `TASK-BACKEND-147`의 CI flow와 실제 검증 절차가 일치한다.

## 변경 예상 파일

- 검증 결과를 기록할 task 문서 또는 PR 본문
- 필요한 경우 release runbook
- CI와 실제 절차의 불일치가 발견된 경우 최소 수정 파일

## API 영향

공개 API 변경 없음. 기존 exercise list/detail 응답을 실제 DB에서 검증한다.

## DB·마이그레이션 영향

새 schema 변경 없음. current Alembic head의 upgrade/downgrade와 기존 V2 promotion transaction을
검증한다.

## 안전·개인정보·보안 영향

- 전용 test DB와 synthetic/approved catalog artifact만 사용한다.
- production connection string, token, 사용자 dump와 건강정보를 사용하거나 기록하지 않는다.
- 로그와 evidence에는 secret을 포함하지 않는다.

## 선행 관계와 차단 요소

- `TASK-BACKEND-147`과 병렬 진행할 수 있으나 최종 완료는 두 절차가 일치해야 한다.
- 실제 PostgreSQL 16 실행 환경이 필요하다.
- DB 이름이 `_test`로 끝나지 않으면 실행하지 않는다.

## 테스트 계획

- Ruff format/check
- mypy
- 전체 pytest
- data pipeline unittest
- Alembic upgrade/downgrade round trip
- V2 release-flow PostgreSQL integration test
- exercise list/detail 수동 API 확인

## 수동 확인

명령별 exit code, 실행 SHA, DB 종류와 이름, migration head, import count, catalog 상태, media visibility,
test pass/skip/fail 수를 기록한다. 실행하지 않은 검사는 통과로 표시하지 않는다.

## 알려진 제한과 후속 작업

- 이 검증은 production migration 승인이 아니다.
- 실제 Docker/Qdrant 통합은 `#149`, V3 staging provider evidence는 `#150`에서 수행한다.
- RDS와 S3 운영 경계는 별도 승인 task가 필요하다.

## 2026-08-26 실제 검증 증적

### 기준과 환경

- 기준 commit: `c682b992b7286fbad506298329762314fc4d911c`
- branch: `codex/148-v2-postgresql-release`
- PostgreSQL: `16.14`
- Docker Engine: `29.6.2`
- package manager: `uv 0.11.2`
- 전용 DB: `exercise_app_v2_release_20260826_test`
- 검증 전 public schema table count: `0`

기존 사용자 checkout의 미커밋 파일과 `exercise_app.dump`는 읽거나 복원하지 않았다. PostgreSQL
container credential은 process environment에만 전달했고 출력·문서·fixture에 기록하지 않았다.

### Migration

- Alembic single head: `0027_catalog_media_assets`
- `upgrade head`: 성공
- `downgrade base`: 성공
- 두 번째 `upgrade head`: 성공

### V2 import와 activation

Activation 없는 첫 import 결과:

| 항목 | 결과 |
|---|---:|
| catalog status | `DRAFT` |
| exercises | 102 |
| safety rules | 394 |
| alternatives | 285 |
| goal tags | 102 |
| prescription profiles | 137 |
| media assets | 0 |

명시적 activation 후 `exercise-catalog-v2.0.0-final`만 `ACTIVE`이며
`production_eligible=true`, `activated_at` non-null을 확인했다. 같은 bundle import와 activation을
다시 실행한 뒤에도 ACTIVE catalog는 하나이고 모든 record count가 동일해 멱등성을 확인했다.

실제 DB의 `ExerciseReadService` list/detail 조회 결과:

- catalog version: `exercise-catalog-v2.0.0-final`
- 첫 page 100건과 next cursor 반환
- list의 `media_asset_key` 전부 null
- detail의 `media_asset_key` null

현재 승인 bundle에는 media artifact가 0건이다. Registry 승인 media 노출과 미승인 media 비노출은
전체 PostgreSQL integration suite의 synthetic media fixture로 회귀 검증됐다.

### 실행한 테스트

| 명령 | 결과 |
|---|---|
| `uv sync --frozen --group dev` | 113 packages 설치 성공 |
| `uv run ruff format --check backend data/scripts` | 477 files already formatted |
| `uv run ruff check backend data/scripts` | 통과 |
| `uv run mypy` | 277 source files, 문제 없음 |
| `uv run pytest -q` | 1394 passed, skip 없음 |
| `uv run python -m unittest discover -s data/scripts/tests` | 117 passed |

### Rollback과 남은 완료 게이트

동일한 빈 test DB에서 `downgrade base`와 재-upgrade를 실제 확인했다. 운영 rollback 승인이 아니며
production migration에는 별도 release review가 필요하다. 검증 DB는 후속 CI 비교와 증적 재현을 위해
현재 유지한다.

`#147`의 V2 CI 자동화 PR이 아직 없어 실제 검증 명령과 CI 절차의 일치 여부를 확인하지 못했다.
따라서 이 task는 `COMPLETE`가 아니며 #147 PR 검증 후 상태와 병합 근거를 갱신해야 한다.
