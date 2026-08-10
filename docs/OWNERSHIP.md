# OWNERSHIP.md

## 1. 소유권 원칙

소유권은 단독 수정 권한이 아니라 primary review 책임을 의미한다. 공용 계약 변경은 소유자 한 명이 독단으로 확정할 수 없다.

## 2. 경로별 primary owner

| 경로 | Primary | 필수 협업 |
|---|---|---|
| `frontend/**` | 프론트엔드 | API 변경 시 백엔드 |
| `backend/app/api/**` | 백엔드 | 프론트엔드 |
| `backend/app/modules/identity/**` | 백엔드 | 개발팀장 |
| `backend/app/modules/workouts/**` | 백엔드 | 프론트엔드, 개발팀장 |
| `backend/app/modules/weekly_reports/**` | 백엔드 | PM, 개발팀장 |
| `backend/app/domain/agents/**` | 개발팀장·백엔드/데이터 | 백엔드 |
| `backend/app/domain/rules/**` | 개발팀장·백엔드/데이터 | PM, 외부 검수 |
| `backend/app/db/**`, `backend/migrations/**` | 백엔드 | 개발팀장 |
| `data/**` | 개발팀장·백엔드/데이터 | PM, 외부 검수 |
| `docs/product/**` | PM | 개발팀장 |
| `docs/API_CONTRACT.md` | 백엔드 | 프론트엔드, 개발팀장 |
| `docs/DATA_MODEL.md` | 백엔드 | 개발팀장 |
| `docs/DOMAIN_RULES.md` | 개발팀장 | PM, 외부 검수 |
| `docs/MVP_SCOPE.md` | PM | 개발팀장 |
| `docs/ARCHITECTURE.md` | 개발팀장 | 프론트, 백엔드 |
| `infra/**`, `.github/workflows/**` | 개발팀장 또는 지정 운영 담당 | 영향받는 담당자 |

## 3. 인터페이스 경계

- 프론트엔드는 OpenAPI와 API 예제만 의존하고 도메인 안전 로직을 복제하지 않는다.
- 프론트엔드는 상단 경과 타이머, 중앙 마스코트, 하단 운동 블록과 완료 제스처를 소유하지만 시간으로 완료를 추정하지 않는다.
- 백엔드는 운동 블록 순서와 상태 mutation을 제공하고 블록 완료 수로 세션 상태를 계산한다.
- 자세·설명 콘텐츠는 데이터 담당이 구조화하고 PM과 외부 검수자가 승인하며 프론트는 승인 버전을 표시한다.
- API route는 schema 검증과 service 호출만 담당한다.
- service는 use case와 transaction을 조정한다.
- domain은 FastAPI, ORM, Firebase, LLM SDK를 알지 않는다.
- repository는 DB 접근을 캡슐화하고 도메인 결정을 수행하지 않는다.
- integrations는 외부 provider를 캡슐화하고 도메인 상태를 직접 변경하지 않는다.
- data pipeline은 raw와 normalized를 분리하고 승인된 결과만 application seed로 승격한다.

## 4. 병렬 개발 인계물

| 제공자 | 소비자 | 인계물 |
|---|---|---|
| PM | 전원 | 요구사항 ID, 인수 조건, 문구 승인 |
| 백엔드 | 프론트 | OpenAPI, example, error/state matrix |
| 프론트 | 백엔드 | 실제 화면 상태와 idempotency 요구 |
| 개발팀장/데이터 | 백엔드 | agent schema, rule version, approved seed |
| 백엔드 | 개발팀장/데이터 | repository port, transaction contract |

## 5. 선택하지 않은 대안

기능마다 프론트·백엔드·데이터를 모두 공동 소유시키지 않는다. 공동 소유만 지정하면 리뷰 책임이 모호해진다. 반대로 경로 소유자가 모든 결정을 단독 승인하는 방식도 공용 계약과 안전 변경에는 적합하지 않다.

## 6. 아직 확정되지 않은 사항과 질문

- 팀원의 실제 이름과 GitHub handle
- 인프라 primary owner
- 외부 검수자의 승인 권한과 대리 절차
- 휴가 또는 부재 시 backup reviewer

이 항목이 정해지면 `.github/CODEOWNERS`를 실제 handle로 생성한다.
