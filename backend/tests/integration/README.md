# Integration tests

PostgreSQL repository, transaction, migration, 전체 use case 통합 테스트 위치입니다.

## B1 PostgreSQL release flow

`test_demo_vertical_slice.py::test_release_v1_full_postgresql_vertical_flow`는 출시 전 핵심 수직 흐름을
실제 PostgreSQL과 실제 FastAPI application/repository로 검증한다. 외부 Firebase 서명 검증만 합성
stub으로 대체하며 bearer 인증과 내부 사용자 연결 경계는 그대로 통과한다.

검증 순서는 다음과 같다.

1. 미인증 요청 거부와 합성 인증 사용자 연결
2. 온보딩
3. 기본 루틴 생성
4. 수동 당일 체크인
5. Decision 생성
6. `FINAL_ROUTINE` 명시적 선택
7. 운동 세션 생성·시작
8. 모든 블록 완료와 공식 `COMPLETED` 확정·피드백
9. 별도 세션의 명시적 `NOT_COMPLETED`와 미수행 이유 저장·벌점 없음
10. 닫힌 주간 리포트 생성과 완료·미수행 집계
11. 명시적 acknowledgement
12. acknowledgement된 리포트를 근거로 다음 주 계획 최종 확정

### 인수 조건

- `TEST_DATABASE_URL`은 이름이 `_test`로 끝나는 실제 PostgreSQL 데이터베이스여야 한다.
- 전체 Alembic chain을 `upgrade head -> downgrade base -> upgrade head`로 적용한 뒤 테스트한다.
- release test 안에서 PostgreSQL dialect와 `alembic_version`의 현재 head를 확인한다.
- V1 공개 HTTP 요청·응답 필드만 사용하며 agent class, proposal 구현 또는 Coordinator 내부 구조를
  import하거나 대체하지 않는다.
- 완료 상태는 명시적 운동 블록 체크만으로 확정한다.
- 미수행은 단일 machine-readable 이유를 저장하고 벌점을 적용하지 않는다.
- 닫힌 주 리포트는 두 공식 상태를 집계하고 acknowledgement 뒤 다음 계획을 `finalized=true`로
  생성한다.
- 실제 token, 이메일, 이름, 생년월일 또는 원시 건강·웨어러블 데이터는 fixture에 저장하지 않는다.

이 경계 덕분에 멀티에이전트 V2가 도입돼도 V1 공개 응답 계약을 유지하는 동안 같은 release test를
수정 없이 재사용한다. V2 전용 필드는 이 테스트의 assertion에 추가하지 않는다.

### 로컬 실행

빈 전용 PostgreSQL test DB를 준비한 뒤 저장소 루트에서 실행한다.

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://exercise_app:test_only_password@localhost:5432/exercise_app_release_test"
$env:DATABASE_URL = $env:TEST_DATABASE_URL
uv run alembic -c backend/alembic.ini upgrade head
uv run alembic -c backend/alembic.ini downgrade base
uv run alembic -c backend/alembic.ini upgrade head
uv run pytest backend/tests/integration/test_demo_vertical_slice.py::test_release_v1_full_postgresql_vertical_flow -q
```

CI에서는 `backend` workflow의 `postgresql-release-flow` job이 PostgreSQL 16 service에서 같은 순서를
독립적으로 실행한다. `TEST_DATABASE_URL`이 없으면 일반 개발 환경의 integration test는 skip하지만,
CI job에는 값이 항상 설정되므로 skip은 실패로 취급한다.
