# 문서 인덱스와 변경 규칙

## 1. 목적

이 문서는 팀원이 어떤 문서를 먼저 읽고, 충돌 시 무엇을 기준으로 삼으며, 어떤 변경에 누구의 승인이 필요한지 정의한다.

## 2. 문서 계층

| 우선순위 | 문서 | 역할 |
|---:|---|---|
| 1 | `AGENTS.md` | 저장소 전체 작업·안전·품질 규칙 |
| 2 | `docs/SERVICE_POLICY_SAFETY_AND_ADAPTATION_V1.md` | 최신 서비스 범위·안전·적응·데이터 정책 기준 |
| 3 | `docs/requirements/요구사항_정의서.ndjson` | 제품 요구사항과 기능·정책·비기능 기준 |
| 4 | `docs/MVP_SCOPE.md` | MVP 포함·제외 범위 |
| 5 | `docs/DOMAIN_RULES.md` | 안전·시간·주간 주기·상태 전이 불변식 |
| 6 | `docs/API_CONTRACT.md`, `docs/DATA_MODEL.md` | 외부 계약과 영속화 계약 |
| 7 | `docs/ARCHITECTURE.md`, `docs/TECHNICAL_PLAN.md` | 구성 요소 경계와 기술 선택 |
| 8 | `docs/IMPLEMENTATION_PLAN.md`, `docs/TRACEABILITY.md`, `docs/TEST_STRATEGY.md` | 구현 순서·추적성·검증 기준 |
| 9 | 작업 문서·ADR | 특정 변경의 범위와 결정 이력 |

최신 서비스 정책은 안전·적응·입력 최소화·수행 상태에 관한 하위 계약의 기준이다. 하위 문서의 이전 계약과 충돌하면 구현하지 않고 이 문서에 맞춰 갱신한다. 요구사항 정의서는 제품 범위와 기능 존재 여부의 기준이다. 같은 우선순위 문서끼리 충돌하면 개발팀장과 PM이 함께 결정한다. 건강·안전 규칙 충돌은 외부 도메인 검수 전까지 보수적 상태인 `NEEDS_INPUT`, `BLOCKED` 또는 `FAILED`로 남긴다.

멀티 에이전트 로직은 현재 설계 전 단계다. proposal·coordinator·공개 회의 요약의 상세 계약과 관련 테스트는 멀티 에이전트 로직 설계 후 확정하며, 설계 전 문서의 해당 항목은 잠정 상태로 표시한다. 결정적 안전 veto와 실패 안전 규칙은 설계 전에도 변경하지 않는다.

`PROPOSED` ADR은 문서 정합성을 위한 제안일 뿐 구현 승인을 뜻하지 않는다. 해당 변경의 필수 승인자가 확인하고 ADR이 `ACCEPTED`되거나 승인 증적이 연결되기 전에는 관련 API·DB·제품 정책을 동결된 계약으로 사용하지 않는다.

## 3. 핵심 문서

- `PROJECT_BRIEF.md`: 사용자 문제와 제품 원칙
- `SERVICE_POLICY_SAFETY_AND_ADAPTATION_V1.md`: 최신 안전·적응·데이터 정책 기준
- `MVP_SCOPE.md`: MVP 기능과 제외 범위
- `ARCHITECTURE.md`: 시스템·모듈·배포 구조
- `TECHNICAL_PLAN.md`: 기술 스택과 구현 제약
- `DOMAIN_RULES.md`: 결정적 도메인 규칙
- `API_CONTRACT.md`: `/api/v1` 계약
- `DATA_MODEL.md`: PostgreSQL 논리 모델
- `IMPLEMENTATION_PLAN.md`: 단계별 구현 계획
- `COLLABORATION_GUIDE.md`: Git, 이슈, PR, 리뷰 규칙
- `OWNERSHIP.md`: 역할별 소유권과 승인 경계
- `TEST_STRATEGY.md`: 테스트 계층과 필수 시나리오
- `LOCAL_DEVELOPMENT.md`: 로컬 환경 계약
- `DEMO_VERTICAL_SLICE.md`: 수직 슬라이스 데모 실행·초기화 절차와 합성 seed 경계
- `runbooks/account-deletion-operations.md`: 계정 삭제 one-shot 실행과 실패 복구 경계
- `TRACEABILITY.md`: 요구사항-계약-테스트 추적성
- `requirements/요구사항_정의서.ndjson`: 제품 요구사항 원문

## 4. 결정 기록

구현 중 기존 계약으로 답할 수 없는 구조적 결정은 `docs/adr/`에 ADR로 기록한다. 단순 작업 범위와 인수 조건은 `docs/tasks/` 템플릿을 사용한다.

## 5. 변경 승인

| 변경 | 필수 확인 |
|---|---|
| 제품 범위 | PM + 개발팀장 |
| 공개 API | 프론트엔드 + 백엔드 + 개발팀장 |
| DB 스키마 | 백엔드 + 개발팀장 |
| 안전·통증·복귀 규칙 | 개발팀장 + PM + 외부 도메인 검수 |
| 에이전트 계약·조정 우선순위 | 개발팀장 |
| 개인정보 수집·보존 | PM + 개발팀장, 출시 전 법률/개인정보 검토 |
| 배포·외부 서비스 | 개발팀장 + 실제 운영 담당 |

## 6. 선택하지 않은 방식

- 하나의 거대한 기획서: 변경 영향과 소유권을 추적하기 어렵다.
- 코드만 진실 공급원으로 사용: 구현 전 병렬 개발 계약이 사라진다.
- 모든 결정을 회의 기록에만 보존: 검색과 변경 이력 검증이 어렵다.

## 7. 아직 필요한 팀 입력

- GitHub 사용자명과 실제 `CODEOWNERS` 매핑
- 브랜치 보호 규칙을 설정할 저장소 관리자
- 외부 운동·보건 검수자와 승인 일정
- 배포 클라우드와 예산 담당자
