# TASK-CATALOG-V2_0_2-IMPORT: v2.0.2 카탈로그 적재 경로

- Primary owner: 백엔드 담당
- Reviewers: 개발팀장(설계 승인), AI·데이터 리드(산출물 계약), PM(안전 정책)
- 관련 요구사항: 운동 카탈로그 v2.0.2 통합 (PR #192)
- 관련 ADR: 미작성. 6절의 결정 항목은 ADR 또는 본 문서 승인으로 확정한다.
- 목표 브랜치: `feat/catalog-v2-0-2-import`

> 정책 정합성 메모(2026-09-02): `DISCOMFORT` 관계는 적재·감사 이력으로만 보존한다. 통증 Safety와
> 루틴 생성은 이 관계로 운동을 교체하거나 추천하지 않고 `contraindicated` 규칙으로 후보를 필터링한다.

6절의 결정 A1·B1·C1은 2026-08-30 프로젝트 오너(개발팀장 겸임) 승인으로 확정했고
착수 결과는 7절에 있다. **7.1의 카탈로그 콘텐츠 공백이 해소되기 전에는 v2.0.2를
적재할 수 없다.**

## 배경과 사용자 가치

PR #192로 `data/generated/exercise-catalog-v2.0.2-final/` 170건과 통증 대체 관계
1,104건이 확정됐다. 인계 문서는 `READY_FOR_PRODUCTION_IMPORT`로 판정했으나, 이는
데이터 검수 완료를 뜻하며 백엔드 적재 가능을 뜻하지 않는다. 현재 importer로는
v2.0.2 payload를 한 건도 넣을 수 없다.

적재가 완료되면 운동 수가 102건에서 170건으로 늘어 루틴 구성 후보가 넓어진다. 통증 대체 관계는
검수·감사 이력으로 보존하되 추천 입력으로 사용하지 않는다.

## 포함 범위

- v2.0.2 canonical payload 6종을 읽는 importer 경로
- `approvals.py`에 v2.0.2 승인 레코드 등록
- 적재를 막는 스키마 제약 6건 해소
- v2.0.1 → v2.0.2 전환 절차 (`DEPRECATED` 유지, activation 분리)

## 제외 범위

- media binary의 S3 업로드 (별도 작업)
- v2.0.1 산출물 삭제
- NRS 구간 정책(4–6 / 7–10) 자체의 재검토. PM·도메인 승인 대상이며 본 작업의 선행 조건이다.
- v2.0.2 intermediate 201건 산출물

## 인수 조건

1. 6종 payload의 manifest hash·byte count·record count·stable code FK를 적재 전에 검증한다.
2. catalog, lookup, exercise, goal/FITT, safety, alternative, media를 하나의 트랜잭션으로
   적재한다. 부분 성공을 남기지 않는다.
3. 검증 실패 시 전체 트랜잭션이 롤백되고 기존 활성 카탈로그가 그대로 유지된다.
4. v2.0.1 카탈로그와 이를 참조하는 루틴이 삭제되지 않는다.
5. 적재 후 `general_pool_included=true` 행만 기본 루틴 후보로 조회된다.
6. `DISCOMFORT` 관계가 적재되더라도 통증 Safety·루틴 생성 조회 경로에서 소비되지 않음을 검증한다.

## 변경 예상 파일

| 파일 | 변경 |
|---|---|
| `backend/app/modules/catalog/service.py` | v2.0.2 payload 로더, manifest 계약 분기 |
| `backend/app/modules/catalog/approvals.py` | v2.0.2 승인 레코드 5종 |
| `backend/app/modules/catalog/schemas.py` | v2.0.2 record 스키마 |
| `backend/app/db/models/catalog.py` | 제약 완화·컬럼 추가 |
| `backend/migrations/versions/00XX_*.py` | 4절 마이그레이션 |
| `backend/scripts/catalog_promote_v2.py` 또는 신규 스크립트 | v2.0.2 promote 경로 |
| `data/scripts/build_v2_0_2_backend_bundle.py` (신규) | 6종 payload 번들 빌더 |
| `docs/DATA_MODEL.md` | 스키마 변경 반영 |

3파일을 크게 넘으므로 구현 착수 전 개발팀장 승인이 필요하다.

## API 영향

없음. 새 컬럼은 내부 관계·카탈로그 테이블에 머물고 공개 응답 필드로 나가지 않는다.
운동 수가 늘어 목록 응답의 항목 수가 변하지만 필드 계약은 그대로다.

## DB·마이그레이션 영향

### 차단 항목과 해소 방향

| # | 차단 | 현재 상태 | 해소 |
|---:|---|---|---|
| 1 | 승인 레코드 부재 | `approvals.py`에 v2.0.1까지만 등록 | v2.0.2 5종 등록. 없으면 `production_eligible=false`로 조용히 적재되어 계획 생성에 쓰이지 않는다 |
| 2 | 번들 계약 불일치 | importer는 `bundle_manifest.json`과 파일 집합 완전 일치를 요구. v2.0.2는 `manifest.json` 하나에 `audit/` 다수 | 6절 결정 A |
| 3 | 대체 payload 필드 부족 | `reason_code`·`goal_preservation_code`·`rule_version`·`alternative_set_version_code`·`difficulty_delta`·`created_at` 없음 | 번들 빌드 단계에서 투영·보강 |
| 4 | media 102행 적재 불가 | `s3_key`가 NOT NULL + `^catalog-media/…` CHECK + UNIQUE인데 `UNAVAILABLE` 102행은 빈 값 | 6절 결정 B |
| 5 | `source_track_code` CHECK | `wger/kspo/gymvisual`만 허용. v2.0.2에 `pain_alternative_policy` 75건 | CHECK에 값 추가하는 additive 마이그레이션 |
| 6 | `record_type`·`family_code`·variant parent 컬럼 부재 | VARIANT 15건의 부모 관계를 받을 typed column 없음 | 6절 결정 C |

### 선행 마이그레이션

`0030_alternative_pain_area_key`가 적용되어 있어야 한다. unique key에
`pain_discomfort_area_code`가 없으면 v2.0.2 관계 1,104건 중 82건이 충돌로 유실된다.

### 데이터 계약 확인 필요

`general_pool_included`는 `true` 111건, `null` 59건이다. `null`을 `false`로 해석하는
규칙을 importer에 명시하고 `docs/DATA_MODEL.md`에 기록한다.

## 안전·개인정보·보안 영향

- 통증 부위·NRS 구간은 운동 identity와 분리해 관계에만 저장한다. catalog row에
  `pain_discomfort_area_code`를 저장하지 않는다.
- 대체 운동 적용 후 Safety veto를 독립적으로 재검사한다. 대체 관계의 존재가 Safety 통과를
  의미하지 않는다.
- 산출물에 사용자 식별자·원시 건강 데이터가 없음을 적재 전 확인한다.
- media rights가 `APPROVED`이고 `media_status=AVAILABLE`인 68건만 노출한다.

## 선행 관계와 차단 요소

1. **NRS 구간 변경(4–6 / 7–10)에 대한 PM·외부 도메인 검수 승인.** `DOMAIN_RULES.md`가
   승인 전 production 활성화를 금지한다. 미확보 상태에서 v2.0.2를 활성화하면 규칙 위반이다.
2. 마이그레이션 `0028`·`0029`·`0030` 적용.
3. 6절 결정 A·B·C에 대한 개발팀장 승인.
4. 통합 테스트용 `TEST_DATABASE_URL` 확보. 현재 DB 계약 검증 테스트 81건이 skip되고 있어
   본 작업의 인수 조건을 실행으로 확인할 수 없다.

## 테스트 계획

- 단위: v2.0.2 payload 스키마 검증, 승인 조회, `general_pool_included=null` 해석
- 통합(실 DB 필요): 6종 payload 단일 트랜잭션 적재, 검증 실패 시 전체 롤백,
  v2.0.1 `DEPRECATED` 유지, 170건 적재 후 FK orphan 0건
- 골든 시나리오: 무릎 불편 시 무릎 부하 운동 제외, `DISCOMFORT` 관계가 추천에 소비되지 않음,
  Safety veto가 coordinator 출력으로 뒤집히지 않음
- 계약: `pain_discomfort_area_code + condition_code` 조회가 사용자 입력과 일치하는
  관계만 반환

## 수동 확인

1. staging에 `alembic upgrade head` 적용 후 `alembic current` 확인
2. v2.0.2 적재를 `--activate` 없이 실행하고 카탈로그가 `DRAFT`로 남는지 확인
3. 적재 후 기존 사용자 루틴이 정상 조회되는지 확인
4. activation 후 신규 루틴 생성에서 170건 풀이 사용되는지 확인
5. 롤백 리허설: activation 되돌리고 v2.0.1로 복귀

## 6. 승인이 필요한 결정

구현 전 개발팀장이 확정해야 한다. 아래는 조사 결과에 기반한 권고안이며 결정이 아니다.

### 결정 A — 번들 계약

| 안 | 내용 | 장단 |
|---|---|---|
| A1 (권고) | v2.0.2용 번들 빌더를 만들어 canonical 6종만 담은 `bundle_manifest.json`을 생성 | 기존 importer 계약을 그대로 재사용. 빌더 1개 신규 |
| A2 | importer가 `manifest.json`의 `import_contract.canonical_payloads`를 직접 읽도록 확장 | 중간 산출물이 없어짐. importer에 두 번째 manifest 스키마가 생김 |

A1을 권고한다. importer는 이미 hash·byte·record count·파일 집합 완전 일치라는 fail-closed
계약을 갖고 있고, 이를 두 벌로 만들 이유가 없다.

### 결정 B — media 102행

| 안 | 내용 | 장단 |
|---|---|---|
| B1 (권고) | `AVAILABLE` 68행만 적재. `UNAVAILABLE` 102행은 미적재 | 스키마 변경 없음. "행이 없음 = 미디어 없음"이 명확. 프론트는 이미 `media_asset_key: null`을 처리 |
| B2 | `s3_key`를 nullable로 바꾸고 CHECK·UNIQUE를 조건부로 완화 | rights 검수 이력 102건을 DB에 보존. 마이그레이션과 제약 재설계 필요 |

B1을 권고한다. rights 검수 이력이 DB에 필요하다는 요구가 확인되면 B2로 전환한다.

### 결정 C — `record_type`·`family_code`·variant parent

| 안 | 내용 | 장단 |
|---|---|---|
| C1 (권고) | typed column 3개를 additive 마이그레이션으로 추가 | 조회·제약이 가능. VARIANT 관계를 FK로 표현 |
| C2 | `source_metadata` JSONB에 보존 | 마이그레이션 없음. 자주 조회되는 필드를 JSON에만 두는 것은 `AGENTS.md` 10절에 어긋남 |

C1을 권고한다. `AGENTS.md` 10절이 자주 조회되는 필드에 typed column을 요구한다.

## 7. 구현 착수 결과 (2026-08-30)

결정 A1·B1·C1은 프로젝트 오너 승인으로 확정했고, 착수 결과는 다음과 같다.

| 차단 | 상태 |
|---|---|
| 1. 승인 레코드 부재 | 미착수. 6번 payload가 확정되어야 해시를 고정할 수 있다 |
| 2. 번들 계약 | **해소.** `data/scripts/build_v2_0_2_backend_bundle.py` (A1) |
| 3. 대체 payload 필드 부족 | **해소.** 1,104건 투영 성공 |
| 4. media 102행 | **해소.** AVAILABLE 68건만 적재, backend loader 검증 통과 (B1) |
| 5. `source_track_code` CHECK | **해소.** migration 0031 |
| 6. record_type·family_code·variant parent | **해소.** migration 0031 (C1) |
| 7. v2.0.1 DEPRECATED 전환 | 미착수 |

### 7.1 새로 발견한 차단 요소: 카탈로그 콘텐츠 공백

패키저는 카탈로그 단계에서 의도적으로 실패한다. v2.0.2 `catalog/exercises.jsonl` 170건에
백엔드 계약이 요구하는 값이 없다.

| 필드 | 없는 건수 | 성격 |
|---|---:|---|
| `form_cues_ko` | 170 / 170 | 사용자에게 보이는 운동 지도 문구 |
| `default_rest_seconds` | 58 | FITT 휴식값 |
| `default_transition_seconds` | 17 | 운동 간 전환값 |

`audit/canonical_exercises_v2_final.jsonl`과 `..._refined.jsonl`에서 80건은 복구 가능하지만,
나머지 **90건**(`pain_alternative_policy` 75 + `VARIANT` 15)은 어떤 산출물에도 form cue가
없다. 지도 문구와 휴식값은 `data/AGENTS.md`가 명시 검수를 요구하는 내용이므로 패키저가
생성하지 않고 실패한다. 데이터 파이프라인에서 채워야 한다.

#### 상속으로 메울 수 없는 이유 (2026-08-30 조사)

90건이 파생 원본을 가리키고 있어 상속을 검토했으나, **두 집합 모두 상속이 틀린 답이다.**

- `pain_alternative_policy` 75건은 `alternative_source_base_stable_code`로 원본을 가리키지만
  전부 `original_posture_instructions_replaced=true`이고 `fixed_posture_code`
  (예: `SUPPORTED_SEATED_KNEES_NEUTRAL_UNWEIGHTED`)와 `fixed_support_code`를 새로 갖는다.
  통증 부위에 부하를 주지 않으려고 **자세를 의도적으로 바꾼 레코드**이므로, 원본의 form cue를
  붙이면 실제와 다른 자세를 안내하게 된다. 안전 방향으로 틀린다.
- `VARIANT` 15건은 대표 운동을 가리키지만 그 대표들의 form cue도 shipped 산출물에 없다(0/15).

두 집합 모두 `instruction_identity_status=USER_REVIEWED_NAME_ONLY`다. 이름만 검수됐고
지도 문구는 검수 대상이 아니었다. `instruction_summary_ko`는 170건 전부 있으나 짧은 요약이라
form cue를 대신하지 못하고, `setup_condition_ko`는 safe variant에서 비어 있다.

결론: 90건의 form cue는 **작성 + 검수**가 필요하다. 기계적 복구 경로가 없다.

#### stable_code 이중 밑줄 — 해소

`pain_alternative_policy` 75건은 파생 원본과 파생 사유를 이중 밑줄로 구분한다
(`<base>__knee_no_load_safe_v1`). `StableCode` 패턴을 `_{1,2}`로 좁게 넓혀 해소했다.
선행·후행 밑줄, 대문자, 3연속 이상은 그대로 거부한다. DB에 형식 CHECK가 없어 마이그레이션은
필요 없었다. 이 변경으로 패턴 위반 75건이 사라졌다.

### 7.2 매니페스트 무결성

착수 중 `manifest.json`의 30개 seal 중 12개가 검증되지 않는 것을 발견해 재봉인했다
(`V2_0_2_MANIFEST_RESEAL_2026_08_30`). 원인은 대체 payload 내용 변경 1건과 CSV 줄바꿈
정규화 11건이며 상세는 `data/scripts/reseal_v2_0_2_manifest.py` 문서와 커밋 메시지에 있다.
`--check`로 CI에서 드리프트를 검사할 수 있다.

### 7.3 검토 상태 불일치

`manifest.json`은 `status=PRODUCTION_APPROVED`, `production_eligible=true`인데
`audit/canonical_field_validation_report_v2_0_2.json`은
`status=VALIDATION_COMPLETE_WITH_REVIEW_REQUIRED`, `production_eligible=false`,
`review_required_count=131`, `instruction_review_required_count=31`,
`source_license_review_required_count=131`이다. 7.1의 콘텐츠 공백과 같은 방향을 가리킨다.
활성화 전에 어느 쪽이 사실인지 데이터 파트가 확정해야 한다.

## 알려진 제한과 후속 작업

- media binary 업로드는 본 작업 범위 밖이다. 68건 노출은 기존 S3 자산에 의존한다.
- v2.0.2 final의 `production_eligible`은 대체 payload 1,104건 모두 `false`다. 적재 시
  값은 파일이 아니라 `approvals.py` 조회 결과로 결정된다.
- `reports/V2_0_2_VARIANT_CATALOG_INTEGRATION.md`는 중간 201건 기준으로 작성되어 final
  170건과 어긋난다. 산출물 경로도 `final/audit/`로 이동했다. 문서 정리가 필요하다.
- v2.0.1 alternative 산출물은 585건으로 재생성됐고 승인 레코드는 재서명되지 않았다.
  v2.0.2가 활성화되면 이 미서명 상태는 해소된다.
