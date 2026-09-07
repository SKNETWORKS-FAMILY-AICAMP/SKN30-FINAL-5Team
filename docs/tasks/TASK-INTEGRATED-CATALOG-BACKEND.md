# TASK-INTEGRATED-CATALOG-BACKEND: v2.0.7 통합 카탈로그 백엔드 적재·조회 계약

- Primary owner: backend development lead (data/AI authority delegated)
- Reviewers: backend owner, frontend owner, development lead, data lead
- 관련 요구사항: 2026-09 통합 운동 카탈로그 후속 인계 1~5번
- 관련 ADR: ADR-0004, ADR-0014
- 목표 브랜치: `develop`

## 배경과 사용자 가치

PR #269가 검수된 237개 운동, MET provenance, 집 생활도구 및 헬스장 시작 가이드를 포함한
v2.0.7 DRAFT bundle을 추가했다. 현재 백엔드는 MET를 입력으로 읽을 수만 있고 DB에 보존하지 않으며,
대표 근육을 목록/상세 API에 제공하지 않는다. 검수된 카탈로그의 정보를 손실 없이 적재하고 기존
클라이언트가 계속 동작하도록 additive 계약을 제공한다.

## 포함 범위

- v2.0.7 DRAFT catalog artifact의 237개 운동과 MET 6필드의 검증·원자적 적재
- MET nullable 컬럼 및 DRAFT importer 호환을 위한 Alembic migration
- 목록과 상세의 optional `body_focus_code` 노출
- 검증된 home bundle 및 gym starting guide의 advisory 상세 응답 연결
- stable-code, MET, guide 참조, 미승인 입력, 기존 응답 호환 importer/API 테스트

## 제외 범위

- catalog의 운영 승인·활성화·운영 DB 적재
- None. FITT agent context, Recovery ceiling, and integrity validation
  handoff items 6--10 are included after explicit development-lead and
  data/AI authorization.
- 운동 데이터, 안전 규칙, 장비 대체 관계의 신규 생성 또는 수정
- 프론트엔드 표시 구현

## 인수 조건

1. 통합 bundle의 catalog JSONL 237개 stable code와 MET 6필드가 새 DRAFT catalog version에 원자적으로 저장된다.
2. MET provenance의 review status가 `DOMAIN_APPROVED`가 아닌 경우 importer는 저장 전에 실패한다.
3. home/gym guide는 bundle hash·건수·검수 상태·exercise stable-code 참조를 검증하고, 검증 실패 시 상세 조회를 성공으로 위장하지 않는다.
4. `ExerciseListItem`와 `ExerciseDetailResponse`는 optional `body_focus_code`를 제공하며, 이전 필드와 응답 의미를 변경하지 않는다.
5. `primary_body_area_codes`는 기존대로 보조 부위 배열로 반환하며 대표 초점으로 대체하거나 추론하지 않는다.
6. migration downgrade는 새 MET 값이 존재할 때 forward-fix를 요구한다.

## 변경 예상 파일

- `backend/app/db/models/catalog.py`, `backend/app/db/repositories/catalog.py`
- `backend/migrations/versions/0048_integrated_catalog_v2_0_7.py`
- `backend/app/modules/catalog/{schemas.py,service.py,home_equipment.py}`
- `backend/app/api/v1/exercises.py`
- `backend/tests/{unit,integration,api}/...`
- `docs/{API_CONTRACT.md,DATA_MODEL.md}`
- `backend/app/domain/rules/fitt.py`, `backend/app/domain/agents/{retrieval.py,v3_contracts.py,v3_validation.py}`
- `backend/app/modules/decisions/v3_application.py`, `backend/app/integrations/langgraph/fallback.py`

## API 영향

기존 `GET /api/v1/exercises` 및 `GET /api/v1/exercises/{exercise_id}` 응답에 optional
`body_focus_code`를 추가한다. 상세 응답에 검수된 gym starting guide의 optional additive 필드를
추가한다. 기존 필드를 삭제·이름 변경·필수화하지 않는다.

## DB·마이그레이션 영향

`exercises`에 nullable MET 6개 컬럼과 review-status CHECK를 추가한다. DRAFT catalog version을
추가할 수 있게 importer만 확장하며, migration은 catalog 데이터를 적재·활성화하지 않는다.

## 안전·개인정보·보안 영향

MET와 장비 가이드는 검수된 reference/advisory 데이터다. 사용자 건강정보나 식별정보를 다루지
않으며, MET는 이번 작업에서 안전 판단 또는 처방을 변경하지 않는다. 미승인 또는 참조 무결성이
깨진 artifact는 fail-closed한다.

## 선행 관계와 차단 요소

PR #269 (`2ef5d75`)가 병합되어야 한다. v2.0.7은 DRAFT bundle이므로 운영 승격은 별도 정확한
승인 registry와 release task가 필요하다.

## 테스트 계획

- catalog importer 단위 테스트: 237 stable code, MET 6필드, 미승인 MET 거부, hash/count 변조
- repository 통합 테스트: nullable MET 저장·조회와 migration target
- API 테스트: body focus 및 home/gym advisory guide, 기존 null fallback
- backend formatter/linter/type checker와 변경 영역 pytest

## 수동 확인

전용 test DB에서 migration upgrade/downgrade/upgrade를 실행하고 DRAFT importer를 두 번 실행해
stable-code count, MET 값, guide reference와 멱등성을 확인한다. 운영 DB나 activation 명령은 실행하지 않는다.

## 알려진 제한과 후속 작업

## FITT follow-up (handoff 6--10)

The V3 pool projection loads the approved stable-code FITT reference and its
reviewed template. It carries source, policy, review status, F/I/T/type
context, and a deterministic per-exercise volume range to Training, Recovery,
and Feasibility. A missing or unapproved mapping is explicitly
`REVIEW_REQUIRED`; no range is inferred.

For approved strength mappings, the policy is: BEGINNER compound 2--3 x
8--12, BEGINNER isolation 2--3 x 10--15, INTERMEDIATE compound 2--4 x 8--12,
and INTERMEDIATE isolation 2--4 x 10--15. Defaults are deterministic values
inside those ranges and never substitute a maximum simply because it is a
maximum.

The same per-exercise upper values constrain RecoveryCeiling, compilation,
the downstream compiled-plan integrity validator, and deterministic fallback.
Recovery may only tighten a FITT upper bound. Fallback starts from an approved
default and clamps it downward to a tighter recovery ceiling; it never starts
from a maximum.

## Expanded test plan and manual verification

- Unit tests: CSV/template validation, all four strength-level ranges,
  missing/unapproved fail-closed handling, recovery tightening, compiled-plan
  rejection, and deterministic fallback default behavior.
- Golden/safety tests: an over-limit coordinator result is rejected by the
  compiled-plan integrity validator downstream of coordination; specialist
  ownership remains unchanged.
- PostgreSQL test DB only: run `upgrade head -> downgrade base -> upgrade
  head`, then run the integrated DRAFT importer twice and assert stable catalog
  row counts, MET provenance, guide references, and no duplicate catalog
  version/child rows. The test URL must name a database ending in `_test`.
