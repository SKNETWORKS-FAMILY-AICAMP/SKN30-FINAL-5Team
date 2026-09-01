# TASK-BACKEND-149: API·PostgreSQL·Qdrant 로컬 Compose 구성

- 현재 상태: `BLOCKED` (정적 구성 검증 완료, staging Qdrant topology 승인·DB read-only 증적 대기)
- 우선순위: `P1`
- GitHub issue: `#149`
- Primary owner: 백엔드 팀원
- Reviewers: 백엔드·데이터 개발팀장, AI/data lead
- 관련 요구사항: 기존 local development·integration 계약 유지; 새 요구사항 ID 없음
- 관련 ADR: `ADR-0014`
- 목표 브랜치: 이슈 전용 branch/worktree
- 승인자 역할: 백엔드·데이터 개발팀장
- 승인일: 2026-08-26

## 배경과 사용자 가치

현재 API는 호스트에서 실행되고 PostgreSQL은 단발 `docker run`에 의존하며 Qdrant는 통합 코드만
존재한다. 개발팀장이 동일한 로컬 환경에서 API, PostgreSQL과 Qdrant를 실제 검증할 수 있도록
재현 가능한 실행 선언이 필요하다.

`infra/README.md`의 실행 설정 보류 게이트는 이 task 승인으로 **로컬 개발용 Dockerfile과
Compose 범위에서만** 해제한다. production deployment 승인은 포함하지 않는다.

백엔드 팀원은 코딩 에이전트로 선언 파일, 정적 테스트와 문서만 작성한다. 실제 Docker build/up,
DB/Qdrant 연결과 최종 검증은 개발팀장이 수행한다.

## 포함 범위

- backend Dockerfile과 `.dockerignore`
- `api`, `postgres`, `qdrant` 세 서비스의 Compose
- 서비스별 healthcheck와 startup dependency
- PostgreSQL/Qdrant volume 분리
- test/demo DB 분리와 configurable host port
- migration, V2 import, activation의 명시적 one-shot 명령
- secret 없는 env example과 실행/복구 runbook
- non-root API runtime
- production/V3/Qdrant/LLM flag의 안전한 기본값 정적 검증

## 제외 범위

- Redis, Celery, Kafka, scheduler, Kubernetes
- RDS, S3, KMS, IAM
- production deployment 선언
- 실제 secret과 provider credential
- 공개 API·DB schema 변경
- API startup에 숨겨진 migration/import/activation

## 인수 조건

1. Compose에는 `api`, `postgres`, `qdrant` 세 서비스만 필수로 존재한다.
2. PostgreSQL은 승인된 major version 16을 사용한다.
3. Qdrant는 repository README에서 검증한 고정 version 또는 digest를 사용한다.
4. 각 서비스에 적절한 healthcheck가 있다.
5. API startup은 PostgreSQL readiness를 고려한다.
6. migration, import와 activation은 명시적 one-shot 명령으로 분리한다.
7. 기본 실행 profile은 LEGACY다.
8. V3, Qdrant, LLM과 production promotion은 기본 비활성이다.
9. `.env`, dump와 git metadata는 Docker build context에 들어가지 않는다.
10. PostgreSQL과 Qdrant data volume은 분리된다.
11. test DB와 demo/local DB를 혼용하지 않는다.
12. 실제 Docker·DB·Qdrant 검증 전에는 task를 `COMPLETE`로 변경하지 않는다.

## 변경 예상 파일

- `backend/Dockerfile`
- `backend/.dockerignore`
- `infra/docker/compose.yaml`
- `infra/docker/.env.example`
- `infra/docker/README.md`
- `infra/README.md`
- 필요한 정적 설정 test
- 이 task 문서

## API 영향

공개 API 변경 없음. 기존 `/api/v1/health/live`와 `/api/v1/health/ready` 계약을 container
healthcheck에 재사용한다.

## DB·마이그레이션 영향

새 migration 없음. PostgreSQL container는 기존 Alembic과 V2 promotion 명령을 실행할 수 있어야
하지만 자동으로 schema/data를 변경하면 안 된다.

## 안전·개인정보·보안 영향

- 실제 secret을 image, Compose, env example과 로그에 포함하지 않는다.
- API는 non-root 사용자로 실행한다.
- healthcheck와 로그에 token, request body, 식별자 또는 건강정보를 포함하지 않는다.
- Qdrant는 derived index이며 PostgreSQL을 canonical source of truth로 유지한다.

## 선행 관계와 차단 요소

- `#147`, `#148`의 V2 release 절차가 확정돼야 one-shot 명령을 고정할 수 있다.
- 실제 Docker daemon, port와 volume 검증은 개발팀장이 수행한다.
- production deployment provider가 정해지지 않았으므로 로컬 범위를 넘지 않는다.

## 테스트 계획

코딩 에이전트가 수행 가능한 검사:

- YAML/Compose 구조 정적 검증
- 필수 service와 healthcheck 검사
- 안전한 flag 기본값 검사
- Docker context 제외 파일 검사
- one-shot 명령 분리 검사
- formatter/linter/type checker와 DB 비의존 unit test

개발팀장이 수행할 검사:

- Docker image build
- `docker compose config`와 `up`
- API/PostgreSQL/Qdrant readiness
- migration/import/activation one-shot 명령
- 재시작과 volume 재사용
- Qdrant 장애 시 deterministic fallback

## 수동 확인

개발팀장은 clean environment에서 build/up/readiness, V2 migration/import/activation, Qdrant 중단
fallback, 종료와 재시작을 확인하고 실제 명령과 결과를 PR에 기록한다.

## 알려진 제한과 후속 작업

- 로컬 Compose는 production 배포 품질이나 운영 승인 증거가 아니다.
- RDS/S3/KMS/IAM과 secret delivery는 별도 architecture/deployment task가 필요하다.
- V3 실제 staging evidence는 `#150`에서 수행한다.

## 2026-08-27 staging readiness 재검증

### 기준과 정적 결과

- 기준 commit: `2431aa533d2e9693079e0489ca340d8854a39b9e`
- branch: `chore/149-qdrant-staging-readiness`
- staging PostgreSQL: Compose에 추가하지 않음. 외부 Aurora `DATABASE_URL` 유지
- Qdrant image: `qdrant/qdrant:v1.18.2`와 sha256 digest 고정
- persistence: `qdrant_data:/qdrant/storage`
- health: Qdrant `/readyz` 200 검사 후 API가 `service_healthy`로 대기
- exposure: Qdrant 6333/6334는 Compose network `expose`만 사용하고 host `ports` 없음
- safe defaults: `QDRANT_ENABLED=false`, `V3_PRODUCTION_PROMOTION_APPROVED=false`
- Compose 정적 해석: 비밀값 없는 process placeholder를 설정한 `config --quiet` 성공
- Docker/Qdrant runtime health: Docker daemon이 실행 중이지 않아 미실행

Compose interpolation은 서비스의 `env_file`을 읽지 않는다. 따라서 repository root에서 실행할 때는
`docker compose --env-file infra/deployment/.env.staging -f
infra/deployment/compose.staging.yaml config --quiet`처럼 deployment env file을 명시해야 한다. 이 파일과
그 값은 커밋하거나 증적에 복사하지 않는다.

### BLOCKED: staging Qdrant topology

현재 Compose endpoint는 `http://qdrant:6333`, `QDRANT_TLS_ENABLED=false`다. 그러나 application
`Settings`는 `APP_ENV=staging`에서 `QDRANT_ENABLED=true`이면 HTTPS와 `QDRANT_API_KEY`를 모두
요구한다. 따라서 현재 in-Compose endpoint로 #150의 실제 index build를 실행할 수 없다.

이 task는 validation을 완화하거나 임의의 key/TLS 설정을 추가하지 않는다. 다음 중 하나를 백엔드
개발팀장과 보안/인프라 owner가 승인해야 한다.

1. 인증·TLS가 구성된 외부 staging Qdrant
2. 내부 Compose Qdrant를 위한 명시적 보안 예외 또는 설계 변경
3. Compose Qdrant 자체에 인증·TLS를 적용한 승인 구성

### staging DB read-only 결과와 #150 인계

현재 작업 환경에는 staging `DATABASE_URL`, deployment `.env.staging` 또는 AWS credential 환경
변수가 제공되지 않았다. 기본 작업 트리의 `backend/.env`는 key 존재 여부만 민감정보 없이 확인했으며
`APP_ENV`가 staging이 아니고 `DATABASE_URL`도 local/Compose endpoint였다. 해당 파일은 수정하지 않았고
staging 증적으로 사용하지 않았다. 따라서 Aurora에 연결하지 않았고, 기존 registry 0행 정보도 실제
staging DB에서 재확인하지 못했다. 다음 값은
확인 전까지 `UNKNOWN`이며 과거 #150의 v2.0.0 local/test evidence로 대체하지 않는다.

- ACTIVE catalog UUID와 version
- `exercise-catalog-v2.0.1-final` 활성·production eligibility·승인 상태
- 활성 카탈로그의 indexable exercise/예상 point 수
- `vector_index_registry` 전체 및 상태별 행 수
- 기존 v2.0.0 ACTIVE index 존재 여부

#150 담당자는 `infra/deployment/README.md`의 read-only query 결과, 승인된 Qdrant endpoint 형태,
TLS/API-key 적용 여부와 실제 `/readyz` 결과를 받은 뒤에만 build preflight를 시작한다. 현재 실제 build
실행 가능 여부는 **BLOCKED**다. 이 확인 단계에서 catalog/registry를 변경하거나 provider를 호출하거나
collection/alias를 생성·전환하지 않는다.
