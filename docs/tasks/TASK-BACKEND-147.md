# TASK-BACKEND-147: V2 catalog release-flow CI 자동화

- 현재 상태: `IN_PROGRESS` (코드 작성 완료, PostgreSQL CI·개발팀장 검증 대기)
- 우선순위: `P0`
- GitHub issue: `#147`
- Primary owner: 백엔드 팀원
- Reviewers: 백엔드·데이터 개발팀장, 데이터 담당
- 관련 요구사항: 기존 catalog·migration·media 승인 계약 유지; 새 요구사항 ID 없음
- 관련 ADR: `ADR-0014`
- 목표 브랜치: 이슈 전용 branch/worktree
- 승인자 역할: 백엔드·데이터 개발팀장
- 승인일: 2026-08-26

## 배경과 사용자 가치

V2 catalog promotion과 reviewed media persistence는 `origin/develop@7e72f00`에 병합됐다. 현재
PostgreSQL release-flow job은 V1 수직 슬라이스만 명시적으로 실행하므로 V2 migration, exact-match
bundle import, DRAFT 유지, activation, 멱등성과 media visibility를 CI의 반복 가능한 릴리스 게이트로
고정해야 한다.

백엔드 팀원은 코딩 에이전트로 코드·테스트·CI·문서만 작성한다. 실제 PostgreSQL 연결, migration
적용과 최종 결과 확인은 개발팀장이 수행한다.

## 포함 범위

- 기존 V1 release flow를 보존한 V2 전용 PostgreSQL CI flow
- Alembic current head 적용
- 승인된 V2 bundle import 후 DRAFT 상태 확인
- catalog 102건, safety rule 394건, alternative 285건, goal tag 102건,
  prescription 137건 exact count 검증
- 명시적 activation 후 단일 ACTIVE catalog 확인
- import와 activation 재실행의 멱등성 검증
- 잘못된 hash, byte count, record count, artifact version의 fail-closed 검증
- 미승인 media 비노출과 registry 승인 media의 canonical key 노출 검증
- 실패 시 부분 적재가 남지 않는 transaction 검증
- 개발팀장용 release verification runbook

## 제외 범위

- production DB와 실제 사용자 데이터
- Docker, Qdrant, OpenAI, AWS 실제 연결
- V3 production 활성화
- 공개 API 필드 또는 DB schema 변경
- V1/merged importer의 동작 변경

## 인수 조건

1. 기존 V1 PostgreSQL release-flow를 삭제하거나 약화하지 않는다.
2. PostgreSQL 16과 이름이 `_test`로 끝나는 전용 DB에서만 실행한다.
3. V2 import 직후 catalog는 DRAFT다.
4. 승인된 exact count 다섯 항목이 모두 일치한다.
5. activation 이후 ACTIVE catalog는 하나뿐이다.
6. 동일 bundle 재실행은 중복 행을 만들지 않는다.
7. 승인 metadata 또는 artifact 무결성이 다르면 activation 전에 실패한다.
8. 미승인 media와 누락 media는 공개 조회에서 노출되지 않는다.
9. 실패한 import transaction은 부분 데이터를 남기지 않는다.
10. 실제 PostgreSQL 검증 전에는 task를 `COMPLETE`로 변경하지 않는다.

## 변경 예상 파일

- `.github/workflows/backend.yml` 또는 별도 backend release workflow
- `backend/tests/integration/test_catalog_*`
- 필요한 최소 test fixture 또는 helper
- `backend/app/modules/catalog/README.md` 또는 별도 release runbook
- 이 task 문서

## API 영향

공개 API field와 endpoint를 변경하지 않는다. 기존 exercise list/detail의 nullable media 계약을
회귀 검증한다.

## DB·마이그레이션 영향

새 migration을 만들지 않는다. 현재 migration head와 V2 import/activation 경계를 검증한다.

## 안전·개인정보·보안 영향

- synthetic catalog fixture와 전용 test DB만 사용한다.
- secret, 사용자 식별자, 건강정보, dump를 workflow나 fixture에 넣지 않는다.
- 승인되지 않은 운동 또는 media가 노출되지 않도록 fail-closed assertion을 유지한다.

## 선행 관계와 차단 요소

- 기준 branch는 `origin/develop@7e72f00` 이상이다.
- 실제 DB 검증은 `TASK-BACKEND-148`의 개발팀장이 수행한다.
- CI와 실제 릴리스 절차가 다르면 두 task 모두 완료할 수 없다.

## 테스트 계획

코딩 에이전트가 수행 가능한 DB 비의존 검사:

- formatter
- linter
- type checker
- 관련 unit test
- workflow와 설정 정적 검증

개발팀장이 수행할 검사:

- PostgreSQL integration test
- migration round trip
- V2 import, activation, 멱등성 및 media visibility
- 전체 backend/data test suite

## 수동 확인

개발팀장은 전용 PostgreSQL DB에서 workflow와 같은 명령을 실행하고 기준 SHA, migration head,
record count, ACTIVE catalog, media visibility와 rollback 결과를 PR에 기록한다.

## 알려진 제한과 후속 작업

- GitHub Actions 성공은 production 배포 승인이 아니다.
- Docker/Qdrant/V3 staging 검증은 `#149`, `#150`에서 별도로 수행한다.
- 실제 media artifact 업로드와 S3 delivery는 이 task의 범위가 아니다.
