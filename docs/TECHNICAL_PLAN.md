# TECHNICAL_PLAN.md

## 1. 문서 목적

이 문서는 채택된 제품 결정을 구현 기술과 저장소 경계로 변환한다. 상세 컴포넌트 흐름은 `ARCHITECTURE.md`, 도메인 불변식은 `DOMAIN_RULES.md`, 외부 계약은 `API_CONTRACT.md`, 영속화는 `DATA_MODEL.md`를 따른다.

멀티 에이전트 핵심 흐름은 Training·Recovery·Safety·Feasibility 네 proposal의 병렬 실행과 Coordinator 최종 결정으로 확정한다. 에이전트 구현의 상세 필드·공개 요약은 증상 사용자 시나리오 검증 결과에 따라 추후 보완할 수 있다.

## 2. 확정 기술

| 영역 | 선택 |
|---|---|
| 모바일 | React Native, TypeScript, Expo Development Build |
| 백엔드 | Python 3.12+, FastAPI, Pydantic 2, `uv` |
| 데이터 | PostgreSQL 16 CI baseline, SQLAlchemy 2, Alembic |
| 인증 | Firebase Authentication과 provider adapter |
| 테스트 | pytest 계열, 프론트 도구는 초기화 PR에서 확정 |
| 배포 | FastAPI 단일 배포 단위 + 관리형 PostgreSQL + 모바일 빌드 |

Python package manager는 기반 구현에서 `uv`로 결정하고 `uv.lock`을 커밋한다. CI 기준 Python은 3.12, PostgreSQL은 16이다. 실제 배포 환경의 지원 minor와 upgrade 정책은 배포 provider를 정할 때 확정한다. Node package manager는 프론트엔드 초기화 PR에서 결정한다.

## 3. 기본 아키텍처

- 백엔드는 모듈형 모놀리스다.
- API request 안에서 결정 파이프라인을 동기 실행한다.
- Training·Recovery·Safety·Feasibility proposal 에이전트는 Python/Pydantic 기반 논리 모듈이며 MVP에서는 병렬 실행한다. Coordinator는 네 proposal을 취합하는 의장 모듈이다.
- PostgreSQL이 사용자·결정·주간 리포트의 단일 진실 공급원이다.
- 안전·통증 제외·시간·복귀·후보 선택은 결정적 Python 규칙이다.
- 요청 시간은 사용자가 명시적으로 변경하지 않는 한 유지하고, 다운시프트는 강도·부하·세트·반복·운동 유형·휴식 구성을 조정한다.
- 예상 시간과 0초부터 증가하는 실제 경과 시간은 정보값이며 완료는 운동 블록 체크로 계산한다.
- 체중 기반 예상 소모 칼로리는 참고용 추정치이며 진단·안전 판정의 단독 근거로 사용하지 않는다.
- 웨어러블·캘린더 어댑터는 MVP 범위에 포함하되 권한 거부·미연동 수동 체크인 폴백과 공식 수행 판정 분리를 보장한다. 캘린더는 수행 여부만 확인하고, 웨어러블 운동 데이터는 캘린더에 자동 등록하지 않는다. 수동 외부 기록은 MVP 이후로 분리한다.
- LLM은 검수 reason code의 설명 생성에만 선택적으로 사용한다.
- 주간 리포트는 요청 시 생성하므로 worker와 scheduler를 기본 도입하지 않는다.

기본안에 포함하지 않는 기술:

- Redis, Celery, Kafka
- Kubernetes
- agent별 microservice
- LangGraph
- vector database와 RAG
- 별도 object storage

필요성이 실제 요구사항과 측정으로 확인되면 ADR을 거쳐 추가한다.

## 4. 목표 저장소 구조

```text
project/
├─ AGENTS.md
├─ README.md
├─ docs/
│  ├─ README.md
│  ├─ PROJECT_BRIEF.md
│  ├─ MVP_SCOPE.md
│  ├─ ARCHITECTURE.md
│  ├─ TECHNICAL_PLAN.md
│  ├─ DOMAIN_RULES.md
│  ├─ API_CONTRACT.md
│  ├─ DATA_MODEL.md
│  ├─ IMPLEMENTATION_PLAN.md
│  ├─ COLLABORATION_GUIDE.md
│  ├─ OWNERSHIP.md
│  ├─ TEST_STRATEGY.md
│  ├─ LOCAL_DEVELOPMENT.md
│  ├─ TRACEABILITY.md
│  ├─ adr/
│  ├─ tasks/
│  ├─ product/
│  └─ references/
├─ frontend/
│  ├─ AGENTS.md
│  ├─ src/
│  │  ├─ app/
│  │  ├─ features/
│  │  ├─ components/
│  │  ├─ api/
│  │  ├─ storage/
│  │  └─ assets/
│  └─ tests/
├─ backend/
│  ├─ AGENTS.md
│  ├─ app/
│  │  ├─ api/v1/
│  │  ├─ core/
│  │  ├─ modules/
│  │  │  ├─ identity/
│  │  │  ├─ profiles/
│  │  │  ├─ catalog/
│  │  │  ├─ routines/
│  │  │  ├─ checkins/
│  │  │  ├─ decisions/
│  │  │  ├─ workouts/
│  │  │  └─ weekly_reports/
│  │  ├─ domain/
│  │  │  ├─ agents/
│  │  │  │  ├─ training.py
│  │  │  │  ├─ recovery.py
│  │  │  │  ├─ safety.py
│  │  │  │  ├─ feasibility.py
│  │  │  │  └─ coordinator.py
│  │  │  └─ rules/
│  │  ├─ db/
│  │  │  ├─ models/
│  │  │  └─ repositories/
│  │  └─ integrations/
│  ├─ migrations/
│  └─ tests/
│     ├─ unit/
│     ├─ api/
│     ├─ integration/
│     └─ scenarios/
├─ data/
│  ├─ AGENTS.md
│  ├─ raw/
│  ├─ normalized/
│  ├─ generated/
│  ├─ scripts/
│  └─ validation/
├─ infra/
│  ├─ docker/
│  └─ deployment/
└─ .github/
   ├─ ISSUE_TEMPLATE/
   ├─ PULL_REQUEST_TEMPLATE.md
   └─ workflows/
```

현재 단계에는 디렉터리 목적을 설명하는 문서만 둔다. 애플리케이션 파일과 실행 설정은 각 구현 PR에서 생성한다.

## 5. 계층 규칙

```text
api -> application service -> domain -> port
                              ^
repository/integration -------|
```

- route: 인증 컨텍스트, schema 검증, HTTP 변환
- application service: use case, transaction, idempotency
- domain: entity, value object, rule, agent, coordinator
- repository: PostgreSQL persistence
- integration: Firebase, provider OAuth, 선택적 LLM

도메인은 FastAPI, SQLAlchemy model, 외부 SDK를 import하지 않는다. route는 repository나 LLM adapter를 직접 호출하지 않는다.

### 5.1 운동 실행 UI와 상태

- 루틴은 근력·유산소 등 운동 유형과 상체·하체 등 초점을 가진다.
- 각 plan item은 운동명, 세트·반복 또는 유산소 권장 목표, 순서, 자세·설명 콘텐츠를 가진 운동 블록이다.
- 클라이언트는 최상단 0초 경과 타이머, 중앙 마스코트, 하단 순서형 블록을 렌더링한다.
- 체크·격파·좌측 밀기 제스처는 동일한 item completion mutation을 호출한다.
- 경과 시간은 정보값이고 세션 상태는 PENDING/COMPLETED 블록 수로 계산한다.

## 6. 멀티에이전트 기술 계약

공통 입력 `DecisionContext`:

- user/profile snapshot
- active routine와 weekly state
- daily check-in
- recent app workout outcomes와 miss reasons
- return mode
- catalog/policy/safety/duration versions
- optional normalized wearable summary
- available duration, location, equipment, schedule, preference/avoidance constraints

공통 출력 `AgentProposal`:

- agent_type
- proposal_status
- recommended_action
- requested_duration_minutes
- estimated_duration_seconds
- duration_adjustment_source_code
- intensity_delta
- required_goal_tags
- preferred/excluded exercise IDs
- hard constraint codes
- reason codes
- evidence references
- policy version

Agent별 책임:

- `TrainingAgent`: 목표·진척·FITT 관점의 후보와 조정 의견
- `RecoveryAgent`: 회복 상태와 강도 조정 의견
- `SafetyAgent`: `PASS / NEEDS_INPUT / REVISE / BLOCKED`와 위험 운동·수정 의견
- `FeasibilityAgent`: 시간·장소·장비·일정·선호를 반영한 실행 가능한 후보·대체안
- `Coordinator`: 네 proposal의 우선순위를 종합해 최종 루틴·FITT 조정·변경 이유 결정

opaque confidence 점수는 MVP에서 사용하지 않는다. 입력 완전성과 proposal 상태를 명시한다. Coordinator는 공통 기본 후보 ID 중 최종 루틴 한 개만 선택한다.

## 7. API 원칙

- 모든 경로는 `/api/v1`
- Pydantic request/response
- UUID와 timezone-aware ISO 8601
- 영문 machine code
- mutation `Idempotency-Key`
- 공통 오류 envelope
- OpenAPI를 구현 후 기계 판독 가능한 계약으로 사용
- 공개 필드 변경 시 frontend mock/client와 compatibility test 동시 변경

핵심 API 영역:

- `/me`, `/me/onboarding`, `/me/identities`, `/me` deletion
- `/routines`, `/weeks`, `/weekly-reports`
- `/daily-contexts`, `/decisions`, decision selection
- `/workout-sessions`, item completion, timer events, additional activities, safety events, finish/not-completed feedback
- `/calendar`, `/wearables`, `/me/consents`

## 8. 데이터 원칙

- 주요 관계와 검색 필드는 typed column
- proposal/input snapshot/metadata에만 JSONB
- FK, uniqueness, CHECK 명시
- catalog, policy, safety, duration, coordinator version 저장
- agent proposal과 final result 분리
- source/license/review status 없는 exercise는 production 후보에서 제외
- raw와 normalized data 분리

스키마 변경은 항상 Alembic migration과 rollback 또는 forward-fix 설명을 포함한다.

## 9. 인증과 보안

- Google은 Firebase provider를 사용한다.
- Kakao/Naver는 backend provider adapter가 OAuth 결과를 검증하고 Firebase custom token을 발급하는 경계를 사용한다.
- FastAPI는 최종 Firebase ID Token만 세션 권한으로 인정한다.
- provider subject는 `user_identities`에 연결한다.
- 토큰, 이메일, 이름, 원시 건강 기록을 로그에 남기지 않는다.
- direct identifier, calendar text, GPS route, raw wearable sample을 LLM에 보내지 않는다.
- 계정 삭제는 즉시 접근 차단, 운영 DB 7일, backup 30일을 목표로 한다.

## 10. 로컬 환경

최소 구성:

- React Native/Expo Development Build
- FastAPI
- PostgreSQL

외부 인증은 test project 또는 adapter stub을 사용한다. LLM과 웨어러블이 없어도 골든 시나리오가 실행돼야 한다. Docker/Compose는 기반 구현 단계에서 실제 port, healthcheck, secret reference가 확정된 후 작성한다.

## 11. MVP 배포

- 모바일 앱 빌드 배포
- HTTPS FastAPI 단일 서비스
- 관리형 PostgreSQL
- 플랫폼 기본 로그와 health check
- secret manager 또는 배포 플랫폼 secret 기능

클라우드 공급자와 region은 미확정이다. 파일 저장소, queue, worker는 실제 사용 기능이 생길 때 추가한다.

## 12. 구현 순서

1. 계약과 enum 동결
2. 저장소·도구 기반
3. auth/onboarding/catalog/Google·Kakao·Naver provider
4. 시간·안전 규칙과 승인 seed
5. routine/candidate/Training·Recovery·Safety·Feasibility/Coordinator
6. decision 저장과 API
7. 모바일 수직 슬라이스
8. partial/miss/safety/return
9. weekly report와 next-plan gate
10. 선택적 LLM
11. 핵심 MVP 승인 후 확장 웨어러블 제공자

상세 선행 관계는 `IMPLEMENTATION_PLAN.md`를 따른다.

## 13. 테스트

- backend unit/API/integration
- frontend type/component/build
- OpenAPI compatibility
- PostgreSQL migration
- golden scenario, 증상 사용자 Safety 의견 반영, 역할 분리, Single-Agent 대비, LLM fallback, reproducibility
- deletion and sensitive log checks

필수 케이스와 CI 구분은 `TEST_STRATEGY.md`를 따른다.

## 14. 대안과 제외 이유

- Flutter: 구현 전 팀의 React Native 경험이 전혀 없을 때만 1회 재검토한다. 중간 전환은 금지한다.
- GraphQL: 현재 resource와 state transition은 REST가 단순하다.
- async decision job: MVP 결정은 짧고 즉시 응답이 핵심이다.
- provider별 세션 체계: Firebase 단일 권한 토큰이 backend 경계를 단순화한다.

## 15. 아직 확정되지 않은 사항

- production Python patch와 PostgreSQL minor version
- 실제 deployment provider와 staging 분리 여부
- logging/monitoring provider
- 소셜 provider 앱 심사·secret 소유자
- 성능 SLO

## 16. 팀 확인 질문

- 프론트엔드 기반 PR에서 어떤 Node package manager를 표준으로 할 것인가?
- staging과 production DB를 처음부터 분리할 것인가?
- OpenAPI client는 생성 코드를 커밋할지 CI artifact로 만들지?
