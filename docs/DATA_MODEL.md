# DATA_MODEL.md

## 1. 문서 목적

이 문서는 MVP의 PostgreSQL 논리 모델, 핵심 관계, 무결성 제약, 버전 및 삭제 정책을 정의한다.

실제 SQLAlchemy 모델과 Alembic 마이그레이션은 이 문서와 API 계약이 승인된 다음 작성한다.

멀티 에이전트 핵심 흐름은 [ADR-0007](adr/0007-multi-agent-structure-correction.md)에 따라 Training·Recovery·Safety·Feasibility 네 proposal의 병렬 실행과 Coordinator 최종 결정으로 확정한다. `agent_proposals`, 조정 결과, 공개 요약의 세부 JSON 구조와 버전 필드는 증상 사용자 시나리오 검증 결과에 따라 추후 보완할 수 있으며, 독립적인 최종 Safety 재검사 결과는 저장하지 않는다. 외부 연동·무료 체험·개인정보 보유기간의 상위 경계는 `ACCEPTED` ADR-0003·0004와 POL-013을 따르며, 관련 컬럼은 실제 migration과 호환성 검토가 승인되기 전까지 논리 모델이다. 결정 재현에 필요한 입력·정책·카탈로그·그래프 버전과 안전 veto 기록은 현재 확정한다.

---

## 2. 설계 원칙

- PostgreSQL을 단일 진실 공급원으로 사용한다.
- 공개 ID와 주요 도메인 ID는 UUID를 사용한다.
- 모든 서버 시각은 timezone-aware timestamp로 저장한다.
- 일일 결정과 알림 차단은 사용자 timezone의 local_date를 기준으로 한다.
- 자주 조회하거나 제약이 필요한 값은 일반 컬럼과 관계 테이블로 저장한다.
- JSONB는 불변 입력 스냅샷, 에이전트 proposal, 확장 메타데이터에만 제한적으로 사용한다.
- 에이전트 proposal과 최종 결정은 별도 테이블에 저장한다.
- 운동 카탈로그, 정책, 안전 규칙, 시간 계산 규칙에는 버전을 부여한다.
- 직접 식별자와 인증 제공자의 프로필 정보를 최소화한다.
- 인증 provider의 subject는 provider-neutral identity 테이블에 저장하되 이메일, 전체 이름, 인증 토큰은 운동 도메인 DB에 복제하지 않는다.
- 계정 삭제 시 사용자 연결 데이터를 삭제하며 가명 처리한 decision log를 기본 보존하지 않는다.
- 원천 운동 데이터와 정규화된 애플리케이션 데이터는 분리한다.

---

## 3. 공통 컬럼 규칙

| 용도 | 타입·규칙 |
|---|---|
| ID | UUID |
| 생성·수정 시각 | timestamptz |
| 사용자 로컬 날짜 | date |
| 머신 코드 | 안정적인 영문 대문자 코드 |
| 가변 메타데이터 | JSONB, 명확한 schema_version 필수 |
| 낙관적 잠금 | version 정수 |
| 소프트 상태 | 명시적인 status_code |

PostgreSQL ENUM을 광범위하게 사용하지 않는다. 자주 변경될 수 있는 제품 코드는 문자열 CHECK 또는 코드 테이블로 관리한다. 신체 부위와 같이 참조 무결성이 중요한 코드는 lookup table을 사용한다.

---

## 4. 사용자와 인증

### 4.1 users

| 컬럼 | 설명 |
|---|---|
| id | 내부 사용자 UUID, PK |
| status_code | ACTIVE, DORMANT, DELETION_PENDING, DISABLED |
| code_set_version | identity machine code 집합 버전. 최초 값은 `identity-mvp-v1` |
| last_active_at | 인증된 서비스 활동 시각 |
| created_at | 생성 시각 |
| updated_at | 수정 시각 |
| deletion_requested_at | 삭제 요청 시각, nullable |
| ai_trial_started_at | AI 코치 무료 체험 시작 시각 |
| ai_trial_ends_at | AI 코치 무료 체험 종료 시각 |
| premium_status_code | NOT_AVAILABLE in MVP, 향후 구독 상태 |

이메일, 전체 이름, 비밀번호, ID Token은 저장하지 않는다.

### 4.2 user_identities

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_id | users FK |
| provider_code | FIREBASE, GOOGLE, KAKAO, NAVER |
| provider_subject | provider가 발급한 불변 subject |
| firebase_subject | 최종 Firebase 사용자 연결 subject |
| code_set_version | identity machine code 집합 버전. 최초 값은 `identity-mvp-v1` |
| created_at | 연결 시각 |
| revoked_at | 연결 해제 시각, nullable |

활성 identity의 `(provider_code, provider_subject)`와 `firebase_subject`는 유일해야 한다. provider access/refresh token, 이메일, 전체 이름은 저장하지 않는다.

첫 인증 수직 슬라이스의 `identity-mvp-v1` provider code는 실제 사용하는 `FIREBASE`만
검증한다. 문서에 예약된 `GOOGLE`, `KAKAO`, `NAVER` 연결은 해당 adapter가 구현될 때 기존 code를
변경하지 않고 새 code-set version과 CHECK migration으로 추가한다.

### 4.3 user_profiles

| 컬럼 | 설명 |
|---|---|
| user_id | users FK, PK |
| protected_birthdate | 생년월일 AES-GCM/KMS 암호화 envelope, NOT NULL, 프로필 서비스 접근 제한 |
| nickname | 사용자 표시용 닉네임 |
| primary_goal_code | 운동 목표 코드 |
| experience_level_code | 운동 경험 |
| timezone | IANA timezone |
| preferred_location_code | 기본 장소 |
| default_requested_duration_minutes | 사용자의 기본 희망 운동 시간 |
| desired_weekly_workout_count | 주간 희망 운동 횟수 |
| coaching_style_code | SUPPORTIVE, CONCISE, ENERGETIC |
| height_cm | 선택, 현재 핵심 판단에 사용하지 않음 |
| weight_kg | 선택, 체중 기반 칼로리 추정에만 사용 |
| sex_code | 선택, 현재 핵심 판단에 사용하지 않음 |
| profile_version | 낙관적 잠금 버전 |
| created_at | 생성 시각 |
| updated_at | 수정 시각 |

`protected_birthdate`는 수정 가능한 생년월일 원본값의 암호화 envelope다. 서버는 복호화한 값을 사용자 timezone의 로컬 날짜를 기준으로 일시 계산해 만 14세 이상 이용 자격을 검증하고 프로필 표시값을 만든다. 평문 생년월일과 만 나이는 DB에 저장하지 않는다. 수정 결과가 만 14세 미만이면 이용을 차단한다.

nickname은 중복을 허용하는 표시값이며 인증·리소스 소유권에 사용하지 않는다. 키와 성별은 MVP 핵심 결정에 사용하지 않는다. 체중은 선택 입력이며 제공된 경우에만 체중 기반 예상 소모 칼로리 추정에 사용하고, 진단·안전 판정에는 사용하지 않는다.

### 4.3.1 user_consents

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_id | users FK |
| consent_type_code | GENERAL_PERSONAL_DATA, SENSITIVE_DATA, WEARABLE_INTEGRATION, CALENDAR_INTEGRATION, MARKETING |
| granted | 현재 동의 여부 |
| policy_version | 동의 문서 버전 |
| granted_at | 동의 시각, nullable |
| revoked_at | 철회 시각, nullable |
| created_at | 생성 시각 |
| updated_at | 수정 시각 |

user_id와 consent_type_code 조합은 유일하다. `user_consents`는 사용자별 동의 유형의 현재 상태만 보관하며 과거 변경 이력은 저장하지 않는다. 동의·철회 상태가 변경되면 현재 상태 갱신과 `user_consent_events` append를 하나의 트랜잭션으로 처리한다. 동일한 멱등 재시도는 중복 event를 만들지 않는다. 철회 시 해당 처리와 외부 동기화를 즉시 중단하고, 연동 해제와 사용자 데이터 삭제는 별도 작업으로 기록한다.

### 4.3.2 user_consent_events

동의·철회 mutation의 append-only 이력이다. 정상 처리에서는 기존 event를 수정하거나 삭제하지 않는다.

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_id | users FK |
| consent_type_code | user_consents와 동일한 동의 유형 코드 |
| event_code | GRANTED 또는 REVOKED |
| policy_version | 적용한 동의 문서 버전 |
| occurred_at | 사용자가 동의·철회한 시각 |
| created_at | 서버 저장 시각 |

동일 mutation의 재시도는 API 멱등성 키 또는 서버가 식별한 동일 요청 기준으로 기존 결과를 반환하고 event를 중복 추가하지 않는다. 계정 삭제 시 이력의 삭제·보유 처리는 사용자 연결 데이터 삭제 정책을 따른다.

### 4.3.2.1 mutation_idempotency_records

온보딩·동의 mutation의 최초 성공 응답을 동일하게 재현하기 위한 사용자별 멱등성 기록이다.
`(user_id, endpoint_code, idempotency_key)`는 유일하며 요청 본문 SHA-256, 버전이 있는 응답
JSONB와 생성 시각을 저장한다. 같은 키의 다른 요청 hash는 거부하고 계정 삭제 시 함께 삭제한다.
요청 원문, 생년월일, 인증 토큰은 저장하지 않는다.

### 4.3.3 생년월일 개인정보 처리

- API 응답 제외
- 애플리케이션 로그 제외
- 분석 이벤트 제외
- decision snapshot에는 생년월일과 만 나이를 저장하지 않음
- LLM·에이전트에는 생년월일과 만 나이를 전달하지 않음
- 프로필 응답에는 계산된 만 나이만 표시
- 가입 자격 확인과 프로필 표시 외에는 만 나이를 사용하지 않음
- 구체적인 암호화 키 관리와 접근 제어 구현은 클라우드 확정 후 결정
- 계정 삭제 시 운영 DB 7일 이내 삭제
- 백업 30일 이내 만료

### 4.4 user_equipment

| 컬럼 | 설명 |
|---|---|
| user_id | users FK |
| equipment_code | equipment FK |
| created_at | 등록 시각 |

PK는 user_id와 equipment_code의 조합이다.

### 4.5 user_attention_areas

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_id | users FK |
| body_area_code | body_areas FK |
| is_active | 현재 주의 부위인지 |
| created_at | 생성 시각 |
| updated_at | 수정 시각 |

이 테이블은 사용자가 직접 입력한 지속적인 주의 부위다. 질환이나 진단명을 저장하지 않는다.

### 4.6 user_preferred_exercise_types

| 컬럼 | 설명 |
|---|---|
| user_id | users FK |
| exercise_type_code | 운동 유형 코드 |
| created_at | 등록 시각 |

PK는 user_id와 exercise_type_code의 조합이다.

---

## 5. 운동 카탈로그

### 5.1 catalog_versions

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| version_code | 사람이 읽을 수 있는 유일 버전 |
| status_code | DRAFT, ACTIVE, DEPRECATED. 첫 importer slice는 DRAFT만 생성 |
| manifest_schema_version | 검증한 seed manifest schema version |
| generator_version | seed를 만든 generator version |
| code_set_version | importer가 검증한 machine code 집합 버전. 최초 값은 `mvp-v1` |
| source_manifest_hash | `seed_manifest.json` 원문 byte의 SHA-256 |
| source_track_code | 기존 산출물의 source track machine code (`wger`, `kspo`) |
| review_status_code | 산출물 검수 상태. 최초 importer는 DOMAIN_APPROVED만 입력 가능 |
| review_method_code | 검수 방법. 최초 importer는 AGENT_ONLY |
| status_interpretation_code | 검수 상태 해석. 최초 importer는 PIPELINE_COMPATIBILITY_ONLY |
| production_eligible | 운영 사용 가능 여부. DRAFT importer 행은 반드시 false |
| exercise_record_count | manifest와 검증한 exercise record 수 |
| manifest_metadata | 검증된 manifest 전체의 versioned metadata JSONB |
| activated_at | 활성화 시각 |
| created_at | 생성 시각 |

한 시점에 하나의 ACTIVE 버전만 허용한다. 운영 사용 가능한 ACTIVE version은
`review_status_code=DOMAIN_APPROVED`, `review_method_code=DOMAIN_REVIEWER`,
`status_interpretation_code=PRODUCTION_APPROVED`, `production_eligible=true`,
`activated_at IS NOT NULL`을 모두 만족해야 한다. DRAFT importer는 계속 `AGENT_ONLY`,
`PIPELINE_COMPATIBILITY_ONLY`, `production_eligible=false`만 생성한다.

`DOMAIN_APPROVED`는 파이프라인 호환 상태이며 그 문자열만으로 ACTIVE 또는 production-safe로
승격하지 않는다. `production_eligible=false`인 version은 사용자 추천에 사용할 수 없다.
동일한 `version_code`와 동일한 `source_manifest_hash` 재적재는 멱등 처리하고, 동일
`version_code`에 다른 hash가 들어오면 fail-closed한다.

### 5.2 exercises

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| catalog_version_id | catalog_versions FK |
| stable_code | 카탈로그 내 안정적 코드 |
| name_ko | 한국어 표시명 |
| name_en | 선택적 영문명 |
| training_type_code | STRENGTH, CARDIO, MOBILITY 등 |
| body_focus_code | body_focuses FK |
| primary_movement_pattern_code | movement_patterns FK |
| difficulty_code | 난이도 |
| beginner_suitable | 초보자 적합 여부 |
| timing_mode_code | REPS 또는 DURATION |
| default_seconds_per_rep | 반복 기반 시간 추정값, nullable |
| default_work_seconds | 시간 기반 동작 기본값, nullable |
| default_rest_seconds | 세트 간 휴식 |
| default_transition_seconds | 10~20초 범위 |
| recovery_eligible | 회복안 후보 여부 |
| instruction_summary_ko | 블록에서 펼쳐볼 자세·수행 설명 |
| form_cues_ko | 검수된 핵심 자세 포인트 JSONB |
| instruction_media_asset_key | 검수된 이미지·애니메이션 참조, nullable |
| mascot_animation_asset_key | 운동 실행 중앙 마스코트 애니메이션 참조, nullable |
| instruction_content_version | 설명 콘텐츠 버전 |
| review_status_code | DRAFT, TECH_REVIEWED, DOMAIN_APPROVED, REJECTED, DEPRECATED |
| source_track_code | 기존 산출물 source track machine code |
| source_identity | source 안의 운동 불변 식별자 |
| created_at | 생성 시각 |
| updated_at | 수정 시각 |

UNIQUE 제약은 catalog_version_id와 stable_code 조합에 둔다.

프로덕션 후보는 review_status_code가 DOMAIN_APPROVED인 운동만 사용한다.

### 5.3 lookup tables

다음 lookup table은 code를 PK로 사용하고 사용자 표시명은 별도 컬럼으로 둔다.

- body_areas
- movement_patterns
- training_types
- body_focuses
- equipment
- locations
- exercise_goal_tags

body_areas의 MVP 허용 코드는 DOMAIN_RULES.md의 불편 부위 코드와 일치해야 한다.

각 lookup 행은 `code_set_version`을 저장한다. 최초 catalog importer의 `mvp-v1`은 실제
DRAFT 카탈로그 산출물이 사용하는 코드만 Pydantic `StrEnum`으로 검증한다. 기존 machine
code를 한국어 label로 바꾸거나 삭제하지 않으며 새 코드는 후속 version에 추가한다.
`display_name_ko`는 machine code와 분리하고 PM 승인값만 저장한다. PM 승인 표시명이 아직
없는 body area는 machine code를 임시 표시명으로 복제하지 않고 null로 유지한다.

### 5.4 exercise_body_parts

| 컬럼 | 설명 |
|---|---|
| exercise_id | exercises FK |
| body_area_code | body_areas FK |
| role_code | PRIMARY 또는 SECONDARY |

PK는 exercise_id, body_area_code, role_code 조합이다.

### 5.5 exercise_equipment

| 컬럼 | 설명 |
|---|---|
| exercise_id | exercises FK |
| equipment_code | equipment FK |
| requirement_code | REQUIRED 또는 OPTIONAL |

첫 importer slice의 산출물은 모든 장비를 필수 장비로 표현하므로 `mvp-v1`은 REQUIRED만
적재한다. OPTIONAL code는 이름을 변경하거나 삭제하지 않고 후속 입력 schema와 migration을
추가하는 방식으로 확장한다.

### 5.6 exercise_locations

| 컬럼 | 설명 |
|---|---|
| exercise_id | exercises FK |
| location_code | locations FK |

### 5.7 exercise_goal_tag_links

운동이 보존할 수 있는 운동 목적과 패턴을 연결한다. 이 값은 대체 운동과 CORE 보존 검증에 사용한다.

### 5.8 exercise_alternatives

| 컬럼 | 설명 |
|---|---|
| source_exercise_id | 원래 운동 FK |
| alternative_exercise_id | 대체 운동 FK |
| reason_code | EQUIPMENT, LOCATION, DIFFICULTY, DISCOMFORT 등 |
| goal_preservation_code | 보존 가능한 목표 |
| difficulty_delta | 난이도 변화 |
| review_status_code | 검수 상태 |
| rule_version | 대체 관계 버전 |
| created_at | 생성 시각 |

대체 관계는 방향성이 있다. A가 B를 대체한다고 해서 B가 A를 자동으로 대체하지 않는다.

DOMAIN_APPROVED 관계만 계획 생성에 사용한다.

### 5.9 exercise_safety_rules

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| catalog_version_id | 카탈로그 버전 |
| exercise_id | 특정 운동 대상, nullable |
| movement_pattern_code | 패턴 대상, nullable |
| body_area_code | 불편 부위 |
| minimum_severity_code | 규칙 적용 최소 심각도 |
| maximum_severity_code | 규칙 적용 최대 심각도 |
| effect_code | EXCLUDE 또는 CAUTION |
| reason_code | 구조화된 안전 이유 |
| review_status_code | 검수 상태 |
| rule_version | 규칙 버전 |
| created_at | 생성 시각 |
| updated_at | 수정 시각 |

exercise_id와 movement_pattern_code 중 정확히 하나를 지정해야 한다.

프로덕션 판단에는 DOMAIN_APPROVED 규칙만 사용한다. 이 테이블에 질환 진단이나 치료 정보를 저장하지 않는다.

### 5.10 catalog_sources

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| source_name | 출처명 |
| source_url | 원천 URL |
| license_code | 라이선스 |
| retrieved_at | 수집 시각 |
| raw_content_hash | 원본 해시 |

exercise_source_links로 운동과 출처를 연결한다.

최초 DRAFT importer 산출물에는 source URL과 license code가 포함되지 않으므로 이를
추정해 `catalog_sources`를 만들지 않는다. 대신 manifest의 source metadata와 exercise의
source track/identity를 보존한다. URL·license 근거가 포함된 후속 산출물 schema가 승인되면
`catalog_sources`와 link 적재를 추가한다.

### 5.10.1 DRAFT catalog importer transaction

- importer는 local/test 환경에서만 실행하며 staging/production에서는 DB 접근 전에 거부한다.
- manifest와 JSONL은 Pydantic schema, code set version, hash, byte count, record count를 모두
  검증한 뒤 하나의 DB transaction에서 catalog version, lookup, exercise와 관계를 적재한다.
- manifest의 파일 경로는 resolve한 결과가 artifact directory 내부일 때만 허용한다.
- 검증 또는 repository 처리 하나라도 실패하면 catalog와 exercise 부분 행을 남기지 않는다.
- JSONB는 `manifest_metadata`와 `form_cues_ko`에만 사용하고 자주 조회하는 source, status,
  version, code와 timing 값은 typed column으로 저장한다.
- 안전 rule reason code, alternatives와 미확정 임계값은 이 importer 계약에 포함하지 않는다.

### 5.11 catalog_review_records

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| target_type_code | EXERCISE, ALTERNATIVE, SAFETY_RULE, RECOVERY_CONTENT, SAFETY_COPY |
| target_id | 검수 대상 ID |
| review_status_code | 상태 |
| reviewer_role_code | DATA_OWNER, BACKEND_REVIEWER, PM_REVIEWER, DOMAIN_REVIEWER |
| reviewer_reference | 내부 비식별 참조 |
| evidence_reference | 검수 근거 |
| reviewed_at | 검수 시각 |

안전 관련 대상이 DOMAIN_APPROVED가 되려면 DOMAIN_REVIEWER의 승인 기록이 필요하다.

DOMAIN_REVIEWER는 건강운동관리사, 물리치료사 또는 동등한 수준의 운동·재활 전문가를 권장한다. 실제 자격 확인과 계약 방식은 운영 절차에서 관리하며 서비스가 검수 범위를 과장해 표현하지 않는다.

---

## 6. 루틴과 예정 운동

### 6.1 routines

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_id | users FK |
| version | 사용자별 루틴 버전 |
| goal_code | 루틴 목표 |
| status_code | DRAFT, ACTIVE, ARCHIVED |
| effective_from | 적용 시작일 |
| effective_to | 적용 종료일, nullable |
| catalog_version_id | 사용한 운동 카탈로그 버전 |
| created_at | 생성 시각 |

사용자별 version은 유일하다. 완료된 decision이 참조하는 루틴 버전은 수정하지 않고 새 버전을 만든다.
실제 루틴은 `ACTIVE`, `DOMAIN_APPROVED`, `production_eligible=true`, 도메인 검수 방식과
승격 시각을 모두 가진 단 하나의 catalog version만 참조한다. 사용자별 생성 transaction은
advisory lock을 사용하고 `(user_id, version)` UNIQUE로 동시 생성에서도 단조 증가를 보장한다.

### 6.2 routine_days

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| routine_id | routines FK |
| sequence | 루틴 내 순서 |
| schedule_rule | 요일 또는 순환 규칙 |
| title | 사용자 표시명 |
| training_type_code | STRENGTH, CARDIO, MOBILITY, MIXED 등 |
| body_focus_code | UPPER_BODY, LOWER_BODY 등, nullable |
| requested_duration_minutes | 사용자가 요청한 권장 운동 길이 |
| estimated_duration_seconds | requested_duration_minutes와 정확히 일치하는 계획 시간 합계 |
| setup_seconds | 0~60초 장비 준비 시간 |
| estimated_calories_burned | 체중 기반 예상 소모 칼로리 추정치, nullable |

### 6.3 routine_items

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| routine_day_id | routine_days FK |
| exercise_id | exercises FK |
| sequence | 수행 순서 |
| phase_code | WARMUP, MAIN, COOLDOWN |
| tier_code | CORE, SUPPORT, OPTIONAL |
| sets | 세트 수 |
| reps | 반복 수, nullable |
| work_seconds_per_set | 시간 기반 운동, nullable |
| rest_seconds_per_set | 세트 간 휴식 |
| intensity_code | 비의료적 운동 강도 코드 |

tier_code는 routine item의 문맥 속성이다.
각 routine day는 WARMUP, MAIN, COOLDOWN을 이 순서로 하나 이상 포함하고 MAIN에는 CORE가
하나 이상 있어야 한다. 단계 순서와 CORE 존재는 service 및 통합 테스트로 검증한다.
`estimated_duration_seconds = requested_duration_minutes * 60`은 DB CHECK와 duration service
양쪽에서 검증한다. `schedule_rule=ROTATION`이며 특정 요일을 저장하지 않는다.

### 6.3.1 user_available_locations

| 컬럼 | 설명 |
|---|---|
| user_id | users FK |
| location_code | locations FK, HOME, GYM, OUTDOOR 개별 코드 |
| created_at | 생성 시각 |

PK는 `(user_id, location_code)`다. 기존 `user_profiles.preferred_location_code`는 하위 호환을
위해 유지하고 migration에서 현재 값을 관계 테이블로 backfill한다. 복합 장소 enum은 만들지
않는다.

### 6.3.2 exercise_goal_tag_links와 exercise_prescription_profiles

`exercise_goal_tag_links`는 승인된 운동과 `goal_code`, `CORE/SUPPORT/OPTIONAL` 역할 가능성을
명시적으로 연결한다. `exercise_prescription_profiles`는 운동·목표·경험 수준·
`WARMUP/MAIN/COOLDOWN` 단계별 세트, 반복 또는 시간, 휴식, 강도와 prescription version을
저장한다. 두 테이블 모두 `DOMAIN_APPROVED` 행만 루틴 생성에 사용한다. 운동 이름이나
training type에서 목표·처방을 추론하지 않는다.

### 6.4 scheduled_workouts

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_id | users FK |
| routine_day_id | routine_days FK |
| scheduled_local_date | 예정 날짜 |
| status_code | SCHEDULED, STARTED, COMPLETED, PARTIAL, NOT_COMPLETED, REST_SELECTED |
| created_at | 생성 시각 |
| resolved_at | 상태 확정 시각 |

미수행 이력을 벌점 없는 학습 신호와 주간 집계로 재현하기 위해 필요하다. 미수행 횟수는
복귀 모드를 활성화하지 않는다. user_id와 scheduled_local_date, routine_day_id 조합은 유일하다.

### 6.5 calendar_connections

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_id | users FK |
| provider_code | 캘린더 제공자 코드 |
| provider_subject | 외부 계정의 불변 subject, nullable |
| status_code | ACTIVE, REVOKED |
| granted_at | 권한 부여 시각 |
| revoked_at | 연동 해제 시각, nullable |
| created_at | 생성 시각 |

외부 access/refresh token과 캘린더 본문 텍스트는 저장하지 않는다. `CALENDAR_INTEGRATION` 동의가 없거나 철회된 상태에서는 연결·조회·등록을 처리하지 않으며, 동의 철회 또는 연동 해제 시 동기화를 즉시 중단한다.

### 6.6 calendar_event_links

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| calendar_connection_id | calendar_connections FK |
| scheduled_workout_id | scheduled_workouts FK |
| external_event_id | 외부 이벤트 식별자 |
| start_at | 등록한 운동 시작 시각 |
| end_at | 등록한 운동 종료 시각 |
| performed | 등록된 운동 일정의 수행 여부 확인값, nullable |
| performance_checked_at | 수행 여부 확인 시각, nullable |
| created_at | 등록 시각 |

캘린더 이벤트는 시간 후보와 계획 등록을 위한 보조 기록이다. 등록된 운동 일정에 대해서는 `performed` 여부와 확인 시각만 확인·저장할 수 있고 세부 운동·수행 시간·강도 기록은 저장하지 않는다. provider가 수행 여부를 제공하지 않으면 `performed`는 `null`이다. 확인 결과는 운동 세션의 공식 상태를 생성하거나 변경하지 않는다. 웨어러블 운동 데이터로 캘린더 이벤트를 자동 생성하거나 갱신하지 않는다.

---

## 7. 일일 컨텍스트

### 7.1 daily_contexts

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_id | users FK |
| local_date | 사용자 로컬 날짜 |
| fatigue_level_code | LOW, MODERATE, HIGH |
| requested_duration_minutes | 0보다 큰 희망 운동 시간 |
| duration_adjustment_source_code | PROFILE 또는 USER_OVERRIDE |
| location_code | 당일 장소 |
| sleep_minutes | 선택적 수동 또는 요약값 |
| fasting_state_code | 선택 |
| hydration_state_code | 선택 |
| context_version | 낙관적 잠금 |
| created_at | 생성 시각 |
| updated_at | 수정 시각 |

user_id와 local_date 조합은 유일하다. 최초 버전은 1이며 기존 행을 전체 교체할 때마다 1씩
증가한다. 쓰기는 현재 버전을 비교하는 낙관적 잠금과 사용자·날짜 단위 트랜잭션 잠금을 함께
사용한다. 체크인 PUT의 멱등 응답은 `mutation_idempotency_records`에
`PUT_DAILY_CONTEXT` endpoint code로 저장한다.

피로 코드는 사용자의 주관적 제품 입력이며 의료 상태를 뜻하지 않는다. 수면 부족과 최근 부하의 파생 임계값은 별도 정책 버전으로 관리한다. 선택 입력이 null이면 unknown으로 유지하며 다른 값으로 채우거나 건강 상태를 추론하지 않는다. 생년월일과 만 나이는 이 테이블 및 이후 decision 입력에 복제하지 않는다.

### 7.2 daily_context_discomforts

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| daily_context_id | daily_contexts FK |
| body_area_code | body_areas FK |
| severity_code | MILD, MODERATE, SEVERE |

daily_context_id와 body_area_code 조합은 유일하다. NONE 항목은 저장하지 않고 빈 목록으로 표현할 수 있다.

### 7.3 daily_context_adverse_reactions

| 컬럼 | 설명 |
|---|---|
| daily_context_id | daily_contexts FK |
| reaction_code | DOMAIN_RULES.md의 이상 반응 코드 |

PK는 daily_context_id와 reaction_code 조합이다.

### 7.4 wearable_connections

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_id | users FK |
| provider_code | 웨어러블 제공자 코드 |
| device_code | 사용자가 선택한 기기 코드 |
| provider_subject | 외부 계정의 불변 subject, nullable |
| status_code | ACTIVE, REVOKED, FAILED |
| token_secret_ref | 외부 secret manager의 참조값, nullable; 토큰 원문은 저장하지 않음 |
| granted_at | 권한 부여 시각, nullable |
| revoked_at | 연동 해제 시각, nullable |
| created_at | 생성 시각 |
| updated_at | 수정 시각 |

연결 시작 전 `WEARABLE_INTEGRATION` 동의를 확인한다. 사용자와 provider_code, device_code의 활성 연결은 하나만 허용한다.

### 7.5 wearable_sync_runs

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| wearable_connection_id | wearable_connections FK |
| requested_local_date | 조회 기준 사용자 로컬 날짜 |
| status_code | SUCCEEDED, FAILED, PERMISSION_DENIED, NOT_CONNECTED, API_ERROR |
| failure_code | 구조화된 실패 이유, nullable |
| source_manifest | 제공자·API·필드 버전 메타데이터 JSONB |
| requested_at | 동기화 요청 시각 |
| completed_at | 처리 완료 시각, nullable |

기기 미연동·권한 거부·API 오류도 실패 상태로 기록하며, 실패 때문에 수동 체크인·앱 운동 블록 체크 경로를 차단하지 않는다.

### 7.6 wearable_raw_payloads

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| wearable_sync_run_id | wearable_sync_runs FK |
| user_id | users FK |
| payload_type_code | SLEEP, STEPS, ACTIVITY, WORKOUT |
| payload_encrypted | 암호화된 원본 payload, 임시 보관 |
| source_recorded_at | 제공자 기록 시각, nullable |
| expires_at | 저장 후 24시간 이내 |
| created_at | 저장 시각 |

원본은 정규화·품질 검증에만 사용하고 LLM 입력이나 장기 분석에 사용하지 않는다. GPS 경로·직접 식별자·초 단위 심박 샘플은 수집하지 않거나 정규화 전에 제거한다. `expires_at` 이후 원본을 삭제한다.

### 7.7 wearable_summaries

웨어러블 요약 연동은 MVP 입력 경로다. 다만 웨어러블 없이도 동일한 핵심 흐름을 사용할 수 있어야 하며, 검증된 사용자별 일별 요약만 결정 입력에 포함한다. 이 테이블은 공개 mutation 대상이 아니며, `POST /api/v1/wearables/sync`의 서버 수집·정규화·품질 검증이 성공한 경우에만 내부적으로 생성·교체한다. 클라이언트는 요약 수치, provider 원본, `source_sync_run_id`, `normalization_version`을 직접 지정할 수 없다.

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_id | users FK |
| local_date | 사용자 로컬 날짜 |
| provider_code | 웨어러블 제공자 코드 |
| sleep_minutes | 수면 일별 요약, nullable |
| steps | 걸음 수, nullable |
| active_minutes | 활동 시간, nullable |
| active_calories_burned | 활동 칼로리, nullable |
| last_workout_type_code | 최근 운동 유형, nullable |
| last_workout_started_at | 최근 운동 시작 시각, nullable |
| last_workout_ended_at | 최근 운동 종료 시각, nullable |
| last_workout_duration_minutes | 최근 운동 시간, nullable |
| average_heart_rate | 선택 평균 심박, nullable |
| resting_heart_rate_trend | 서버 정규화 코드 `UPWARD`, `STABLE`, `DOWNWARD`, nullable |
| normalization_version | 서버 웨어러블 정규화 규칙 버전, NOT NULL |
| source_sync_run_id | wearable_sync_runs FK |
| created_at | 생성 시각 |

사용자와 local_date, provider_code 조합은 유일하다. `source_sync_run_id`와 `wearable_sync_runs.source_manifest`는 제공자·API·원천 필드 버전을 추적하고, `normalization_version`은 서버 정규화 규칙 버전을 행마다 추적한다. 동일한 정규화 버전은 API의 `WearableDailySummary.normalization_version`으로 공개하며, 결정 입력에 사용한 경우 `input_snapshot`에도 함께 복사한다. `resting_heart_rate_trend`와 그 밖의 웨어러블 값만으로 안전 결정을 내리지 않는다.

---

## 8. 정책과 복귀 상태

### 8.1 policy_versions

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| version_code | 정책 버전 |
| return_mode_completion_gap_days | 기본 14, 마지막 공식 COMPLETED 세션 기준 |
| duration_rule_version | 시간 규칙 버전 |
| safety_rule_version | 안전 규칙 버전 |
| policy_data | 확장 JSONB |
| status_code | DRAFT, ACTIVE, RETIRED |
| activated_at | 활성화 시각 |

### 8.2 user_policy_versions

사용자별 선호와 학습 결과가 필요한 폐쇄 루프 단계에서 사용한다.

- id
- user_id
- version
- preferred_downshift_code
- training_weight
- recovery_weight
- safety_weight
- source_summary JSONB
- created_at

이 가중치는 비안전 조정·설명 선호에만 사용하고, SafetyAgent의 안전 veto나 안전 상태를 바꾸는 데 사용하지 않는다.

복귀 모드 자체는 별도 영구 플래그보다 workout_sessions의 마지막 공식 COMPLETED 시점으로부터
계산하고 decision input snapshot에 결과를 저장한다. workout_sessions의 NOT_COMPLETED 이력은
비벌점 학습 신호로만 사용하며 복귀 트리거가 아니다.

다음 decision 조립 전 복귀 이력 query는 대상 로컬 날짜보다 앞선 `decision_runs.local_date`와
연결된 `workout_sessions`만 조회한다. `COMPLETED`의 마지막 로컬 날짜와 `NOT_COMPLETED` 건수를
각각 반환하며, 미수행 건수는 학습 신호일 뿐 복귀 여부나 벌점을 직접 결정하지 않는다.

---

## 9. 결정과 에이전트 기록

### 9.1 decision_runs

Wave 6 물리 모델은 `daily_context_version`, 최소화된 `input_snapshot`/`input_hash`,
`catalog_version_id`, `policy_version_id`, `safety_rule_version`, `duration_rule_version`,
`graph_version`, `coordinator_version` 및 구조화된 `coordinator_result`를 함께 저장한다.
상태는 `RUNNING | COMPLETED | NEEDS_INPUT | FAILED`이며 성공 plan은 `COMPLETED` 중
`PASS | REVISE`에만 연결된다. `date_of_birth`, 만 나이, 이름, 성별, 키, 체중은 결정 입력
snapshot에 저장하지 않는다.

`decision_policy_versions`는 실행 시 사용한 결정 정책을 FK로 고정한다. Wave 6 기본 정책은
`decision-policy-v1`이고 migration에서 활성 버전을 설치한다.

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_id | users FK |
| local_date | 결정 대상 날짜 |
| daily_context_id | daily_contexts FK |
| daily_context_version | 사용한 체크인 버전 |
| base_routine_id | routines FK |
| scheduled_workout_id | scheduled_workouts FK, nullable |
| input_schema_version | 스냅샷 스키마 |
| input_snapshot | 최소화된 불변 JSONB |
| input_hash | 입력 해시 |
| catalog_version_id | 운동 카탈로그 버전 |
| policy_version_id | 정책 버전 |
| graph_version | 조정 흐름 버전 |
| coordinator_version | 조정기 버전 |
| prompt_version | LLM 미사용 시 null |
| status_code | RUNNING, COMPLETED, FAILED |
| recommended_action_code | 최종 추천 액션 |
| started_at | 시작 시각 |
| completed_at | 종료 시각 |
| failure_code | 실패 코드, nullable |

같은 사용자, local_date, input_hash, policy_version_id에 대한 중복 실행을 제한하는 unique 또는 idempotency 제약을 둔다.

`input_snapshot.profile`이 포함될 경우 허용 필드는 다음으로 제한한다.

- `primary_goal_code`
- `experience_level_code`
- `preferred_location_code`
- `equipment_codes`
- `attention_area_codes`
- `preferred_exercise_type_codes`
- `default_requested_duration_minutes`
- `desired_weekly_workout_count`
- `coaching_style_code`

`input_snapshot.profile`에는 `date_of_birth`, `age` 및 그 밖의 연령 관련 파생값을 포함하지 않는다. 닉네임·성별·키·체중도 포함하지 않으며, 체중 기반 칼로리 추정은 운동 계획·세션 경계에서만 처리한다. 수동 외부 기록은 MVP에 포함하지 않는다.

### 9.2 agent_proposals

Wave 6에서는 `proposal_payload` JSONB에 검증된 구조화 proposal을 저장하고
`(decision_run_id, agent_type_code)`를 unique로 강제한다. 네 agent proposal과 최종
Coordinator 결과는 서로 다른 레코드에 저장한다.

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| decision_run_id | decision_runs FK |
| agent_type_code | TRAINING, RECOVERY, SAFETY, FEASIBILITY |
| recommended_action_code | 제안 액션 |
| proposal_schema_version | JSON 구조 버전 |
| proposal | 구조화 JSONB |
| proposal_status_code | READY, NEEDS_INPUT, FAILED |
| policy_version | 에이전트 정책 버전 |
| created_at | 생성 시각 |

decision_run_id와 agent_type_code 조합은 유일하다.

### 9.3 plan_candidates

`selected=true`인 성공 후보는 반드시 `estimated_duration_seconds =
requested_duration_minutes * 60`을 만족한다. Coordinator가 거절한 재현용 후보는 실제 계산값을
보존하므로 이 등식이 성립하지 않을 수 있고 `decision_options`와 연결하지 않는다.

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| decision_run_id | decision_runs FK |
| candidate_code | ORIGINAL, FINAL, RECOVERY, FALLBACK |
| action_code | KEEP, DOWNSHIFT, CHANGE, RECOVERY |
| setup_seconds | 장비 준비 |
| warmup_seconds | 준비 운동 |
| cooldown_seconds | 마무리 |
| requested_duration_minutes | 사용자 요청 시간 |
| duration_adjustment_source_code | PROFILE 또는 USER_OVERRIDE |
| estimated_duration_seconds | requested_duration_minutes와 정확히 일치하는 계획 시간 합계 |
| estimated_calories_burned | 체중 기반 예상 소모 칼로리 추정치, nullable |
| goal_preservation_score | 비안전 목적 점수 |
| duration_rule_version | 시간 규칙 버전 |
| created_at | 생성 시각 |

requested_duration_minutes는 사용자 입력에서만 가져오며 시스템이 임의 변경하지 않는다. 계획이 있는 후보의 estimated_duration_seconds는 `requested_duration_minutes * 60`과 정확히 일치해야 한다. 이는 계획 단계의 hard target이지만 실제 수행의 hard execution limit이나 완료 조건은 아니다. estimated_calories_burned는 제공된 체중이 있을 때만 계산하며 진단·안전 판정의 단독 근거로 사용하지 않는다.

### 9.4 plan_items

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| plan_candidate_id | plan_candidates FK |
| exercise_id | exercises FK |
| source_routine_item_id | 원래 항목, nullable |
| replacement_of_exercise_id | 대체 전 운동, nullable |
| sequence | 수행 순서 |
| tier_code | CORE, SUPPORT, OPTIONAL |
| sets | 세트 수 |
| reps | 반복 수, nullable |
| work_seconds | 전체 동작 시간 |
| rest_seconds | 전체 휴식 시간 |
| transition_seconds | 이 동작 진입 전환 시간 |
| estimated_item_seconds | 항목 권장 예상 시간 |
| instruction_content_version | 표시한 자세·설명 콘텐츠 버전 |
| mascot_animation_asset_key | 실행 화면 중앙 애니메이션 참조, nullable |

처방값은 decision 시점 스냅샷이며 원본 운동 데이터 변경에 따라 바뀌지 않는다.

### 9.5 safety_reviews

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| decision_run_id | decision_runs FK |
| plan_candidate_id | plan_candidates FK |
| status_code | PASS, NEEDS_INPUT, REVISE, BLOCKED, FAILED |
| approved | 승인 여부 |
| veto | 안전 거부 여부 |
| prohibited_rule_codes | 적용된 규칙 코드 JSONB |
| excluded_exercise_ids | 제외 운동 JSONB |
| warning_codes | 경고 코드 JSONB |
| ruleset_version | 안전 규칙 버전 |
| created_at | 생성 시각 |

최종 운동 옵션은 approved=true이고 veto=false인 safety review가 있어야 한다.

### 9.6 decision_options

Wave 6는 option의 생성과 조회까지만 구현한다. option 선택과 workout session 연결은 Wave 7에서
구현한다. Safety veto된 후보는 `FINAL_ROUTINE` option으로 공개하지 않는다.

공개 가능한 최종 루틴과 사용자의 REST 선택을 같은 선택 모델에서 표현하기 위한 테이블이다. STOP_AND_SEEK_HELP는 사용자가 선택하는 option이 아니므로 decision run의 최종 action으로만 기록하고 이 테이블에 행을 만들지 않는다.

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| decision_run_id | decision_runs FK |
| option_code | FINAL_ROUTINE, REST |
| action_code | 최종 액션 |
| plan_candidate_id | 계획이 있을 때 FK, nullable |
| selectable | 사용자 선택 가능 여부 |
| blocked_reason_code | 선택 불가 이유, nullable |
| display_order | 표시 순서 |

규칙:

- REST option에는 plan_candidate_id가 없다. STOP_AND_SEEK_HELP는 decision_option 행을 만들지 않는다.
- KEEP, DOWNSHIFT, CHANGE, RECOVERY 결정의 공개 운동 option은 `FINAL_ROUTINE` 정확히 하나다.
- 위 결정에는 사용자의 자발적 휴식을 위한 별도 REST opt-out을 함께 둘 수 있다.
- 서버 권고가 REST인 결정은 plan candidate 없이 REST option 하나만 둘 수 있다.
- ORIGINAL과 안전 veto된 후보는 `plan_candidates`와 `safety_reviews`에만 남기며 `decision_options` 행을 만들거나 공개하지 않는다.

### 9.7 decision_selections

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| decision_run_id | decision_runs FK, UNIQUE |
| decision_option_id | decision_options FK |
| selected_action_code | 실제 사용자 선택 |
| idempotency_key | mutation 중복 방지 |
| selected_at | 선택 시각 |

### 9.8 decision_explanations

- decision_run_id
- source_code: TEMPLATE 또는 LLM
- summary
- reason_codes
- agent_summaries, Training·Recovery·Safety·Feasibility·Coordinator의 제한된 요약 JSONB, 잠정 구조
- safety_summary, SafetyAgent의 상태·veto·근거 요약 JSONB, 잠정 구조
- final_adjustment_reason, 최종 조정 이유 요약
- coaching_style_code
- prompt_version, nullable
- model_code, nullable
- created_at

안전 문구와 일반 설명을 분리하고 내부 추론을 저장하지 않는다. agent_summaries와 safety_summary는 공개 가능한 입력·판단 결과의 제한된 요약만 저장하며 증상 사용자 시나리오 검증 결과에 따라 상세 구조를 추후 보완할 수 있다. 독립적인 최종 Safety 재검사 결과는 저장하지 않는다.

---

## 10. 운동 세션과 피드백

### 10.1 workout_sessions

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_id | users FK |
| decision_selection_id | decision_selections FK |
| plan_candidate_id | plan_candidates FK |
| scheduled_workout_id | scheduled_workouts FK, nullable |
| status_code | PLANNED, IN_PROGRESS, COMPLETED, PARTIAL, NOT_COMPLETED, STOPPED_FOR_SAFETY |
| started_at | 시작 시각 |
| ended_at | 완료·부분·미수행·안전 중단 시각 |
| actual_elapsed_seconds | 일시정지를 제외하고 0초부터 기록한 화면 경과 시간, 정보값 |
| estimated_calories_burned | 체중 기반 추정치, nullable |
| idempotency_key | 세션 생성 중복 방지 |

REST selection 또는 STOP_AND_SEEK_HELP decision에는 workout_session을 만들지 않는다.

### 10.2 workout_session_items

- id
- workout_session_id
- plan_item_id
- status_code: PENDING, COMPLETED
- completed_at, nullable
- updated_at

한 plan item이 화면의 운동 블록 하나다. 사용자의 명시적 체크·제스처만 COMPLETED로 바꾸며 세트, 반복, 권장 시간 또는 actual_elapsed_seconds로 자동 완료하지 않는다.

COMPLETED로 바꾸면 completed_at을 기록하고, 세션 종료 전 PENDING으로 되돌리면 completed_at을 null로 되돌린다. 종료된 세션의 item 상태는 수정하지 않는다.

세션 종료 시 모든 item이 COMPLETED면 COMPLETED, 일부만 COMPLETED면 PARTIAL, 완료 item이 없으면 NOT_COMPLETED로 계산한다.

### 10.2.1 workout_timer_events

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| workout_session_id | workout_sessions FK |
| event_code | START, PAUSE, RESUME, END |
| occurred_at | 사용자가 기록한 이벤트 시각 |
| client_recorded_at | 클라이언트 기록 시각 |
| created_at | 서버 저장 시각 |

타이머 이벤트는 수행 시간과 이용 패턴 이력으로만 사용하며 운동 블록·세션 공식 상태를 변경하지 않는다.

### 10.2.2 workout_additional_activities

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| workout_session_id | workout_sessions FK |
| activity_type_code | 계획 외 운동 유형 |
| duration_seconds | 추가 운동 시간 |
| intensity_code | 비의료적 운동 강도, nullable |
| note | 선택 메모, nullable |
| created_at | 기록 시각 |

추가 운동은 계획 블록 체크나 공식 세션 상태를 변경하지 않으며 패턴 분석과 주간 리포트 입력으로 사용한다.

Wave 7A의 모든 mutation은 `mutation_idempotency_records`에 사용자·endpoint·요청 키·요청
hash·최초 응답을 저장한다. 같은 키와 다른 요청 hash는 거부한다. 종료 상태 또는 `ended_at`이
있는 세션에는 block, timer event, additional activity 행을 더 쓰지 않는다.

### 10.2.3 manual_activity_records (MVP 이후)

수동 외부 운동 기록은 MVP에서 제외하고 추후 기능으로 분류한다. 후속 기능에서 웨어러블을 사용하지 않는 사용자의 외부 운동 기록을 세션과 독립적으로 저장할 수 있다.

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_id | users FK |
| workout_session_id | workout_sessions FK, nullable |
| activity_type_code | 운동 종류 |
| duration_seconds | 수행 시간 |
| intensity_code | 비의료적 운동 강도 |
| weight_kg_snapshot | 입력 당시 체중, nullable |
| estimated_calories_burned | 예상 소모 칼로리, nullable |
| estimate_status_code | ESTIMATED, UNKNOWN, FAILED |
| calculation_version | 칼로리 산식 버전, nullable |
| created_at | 기록 시각 |

운동 종류·시간·강도는 후속 기능에서 필수로 검토하며 체중은 칼로리 추정 시 선택 입력이다. 입력값이 부족하거나 계산에 실패하면 `UNKNOWN` 또는 `FAILED`로 기록하고 추측값을 저장하지 않는다. 후속 수동 외부 기록은 공식 workout block 완료 상태를 생성하거나 변경하지 않는다.

### 10.3 workout_safety_events

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| workout_session_id | workout_sessions FK |
| occurred_at | 사용자에게 발생한 시각 |
| instruction_code | SHOW_CAUTION, STOP_SESSION, STOP_AND_SEEK_HELP |
| resulting_action_code | REST, STOP_AND_SEEK_HELP 또는 null |
| guidance_code | 검수된 안내 문구 코드 |
| reason_code | 결정론적 안전 분류 사유 코드 |
| rule_version | 적용한 workout safety event 규칙 버전 |
| created_at | 서버 저장 시각 |

workout_safety_event_discomforts와 workout_safety_event_adverse_reactions에 부위, 심각도, 이상 반응을 정규화해 저장한다.

REST 또는 STOP_AND_SEEK_HELP 결과가 나오면 세션 상태를 STOPPED_FOR_SAFETY로 바꾼다. MILD 또는 MODERATE 입력은 MVP에서 계획을 자동 재작성하지 않는다.

### 10.4 workout_feedback

| 컬럼 | 설명 |
|---|---|
| workout_session_id | PK, FK |
| difficulty_code | EASY, APPROPRIATE, HARD |
| fatigue_code | 선택형 피로도, 후보 코드 개발 전 확정 |
| satisfaction_code | 선택형 만족도, 후보 코드 개발 전 확정 |
| pain_occurred | 불편 발생 여부 |
| created_at | 생성 시각 |

workout_feedback_discomforts와 workout_feedback_adverse_reactions에 부위, 심각도, 이상 반응 코드를 정규화해 저장한다.

### 10.5 workout_skip_feedback

| 컬럼 | 설명 |
|---|---|
| workout_session_id | PK, FK |
| reason_code | 가장 큰 미수행 이유 하나 |
| created_at | 생성 시각 |

허용 이유 코드는 MVP_SCOPE.md와 API_CONTRACT.md에서 관리한다.

웨어러블 또는 외부 운동 기록은 별도 참고 테이블에 저장할 수 있으나 workout_sessions의 공식 status_code를 생성하거나 변경하지 않는다. 체크인 원자료는 28일, 웨어러블 원본은 24시간, 상세 수행·설문은 90일을 기본 보유한다.

---

## 11. 주간 리포트와 다음 계획

### 11.1 user_weeks

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_id | users FK |
| week_start_local_date | 사용자 timezone 기준 월요일 |
| week_end_local_date | 일요일 |
| timezone | 경계 계산에 사용한 IANA timezone |
| target_workout_count | 월요일~일요일 주간 목표 횟수 |
| plan_origin_code | COLD_START 또는 WEEKLY_REPORT |
| cold_start_applied | 이전 주 리포트 없는 최초 계획인지 |
| status_code | OPEN, CLOSED |
| closed_at | 논리적 마감 시각, nullable |

`(user_id, week_start_local_date)`는 유일하다. OPEN/CLOSED는 scheduler가 아니라 요청 시 현재 날짜와 경계를 비교해 계산·확정한다.
timezone과 target_workout_count는 해당 주를 처음 요청한 시점의 사용자 프로필 값으로 고정하며,
논리적 `closed_at`은 저장된 timezone의 다음 월요일 00:00 경계를 UTC로 변환한 시각이다.

### 11.2 weekly_reports

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_week_id | user_weeks FK, UNIQUE |
| status_code | GENERATED, ACKNOWLEDGED, FAILED |
| input_schema_version | 집계 snapshot 스키마 버전 |
| input_snapshot | 닫힌 주의 최소 집계 JSONB |
| input_hash | 집계 해시 |
| completed_count | 운동 블록 체크로 계산한 COMPLETED 수 |
| partial_count | PARTIAL 수 |
| not_completed_count | NOT_COMPLETED 수 |
| stopped_for_safety | STOPPED_FOR_SAFETY 수 |
| primary_miss_reason_code | 가장 많은 미수행 이유, nullable |
| completion_rate | 계획 대비 완료율 |
| persistence_rate | 연속 수행·재개 등 지속성 지표 |
| negotiation_success_rate | 조정 후 최종 루틴 수행 성공률 |
| weekday_failure_summary | 요일별 실패 집계 JSONB |
| high_completion_windows | 완료율이 높은 시간대 JSONB |
| pattern_summary | 수행 시간·운동 유형·강도·방해 조건의 최소 집계 JSONB |
| decision_summary | 이번 주 조정 결과와 의사결정 요약 |
| adjustment_direction_code | MAINTAIN, REDUCE, INCREASE, MIXED |
| next_action | 다음 주 행동 안내 |
| agent_summaries | 에이전트별 요약 JSONB, 잠정 구조 |
| summary | 템플릿 또는 승인된 설명 |
| report_policy_version | 생성 정책 버전 |
| generated_at | 생성 시각 |
| acknowledged_at | 사용자 확인 시각, nullable |

동일한 닫힌 주와 input_hash에 대해 멱등 생성한다. MVP 주간 리포트는 생성 후 불변이며 사용자용 세션 정정·리포트 재생성 API는 제공하지 않는다. 운영 정정이 필요하면 후속 ADR에서 version 모델과 감사 절차를 먼저 정의한다.

input_snapshot은 주 경계·목표 횟수, 블록 체크로 재검증한 공식 상태 수, 미수행 이유 수,
요일별 실패 수, 조정안 수행 수와 선택적 사후 설문 최소 집계만 저장한다. 사용자 ID, 세션 ID,
원시 건강 입력은 포함하지 않는다. completion_rate는 `COMPLETED / target_workout_count`,
persistence_rate는 `(COMPLETED + PARTIAL) / target_workout_count`이며 둘 다 1을 상한으로 한다.
negotiation_success_rate는 조정 액션 세션 중 `COMPLETED | PARTIAL` 비율이고 분모가 0이면 null이다.

### 11.3 weekly_plan_revisions

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| target_user_week_id | 다음 계획 대상 주 FK |
| source_weekly_report_id | 직전 주 리포트 FK, 최초 가입자 첫 주는 nullable |
| revision_sequence | 대상 주 안에서 증가하는 전체 수정 순서 |
| ai_revision_number | Coordinator 기반 AI 수정이면 1 또는 2, `INITIAL`·`USER`이면 null |
| revision_source_code | `INITIAL`은 `/weeks/{week_start}/plan`, `AI`·`USER`는 `/weeks/{week_start}/plan-revisions`에서만 생성 |
| routine_id | 생성·편집된 routine FK, nullable. `NEEDS_INPUT`, `BLOCKED`, `FAILED` revision은 반드시 NULL |
| safety_status_code | PASS, NEEDS_INPUT, REVISE, BLOCKED, FAILED |
| finalized_at | 최종 확정 시각, nullable |
| created_at | 생성 시각 |

콜드스타트·최초 계획·다음 주 초기 계획은 `/weeks/{week_start}/plan`이 `INITIAL` revision으로 생성한다. 기존 계획의 AI 또는 USER 수정은 `/weeks/{week_start}/plan-revisions`가 생성하며, 두 엔드포인트는 서로의 source code를 생성하지 않는다. AI 수정은 최대 2회다. USER 편집 횟수와 낙관적 잠금은 revision_sequence로 관리한다. 최초 가입자의 첫 주 계획은 `source_weekly_report_id`가 null일 수 있으며, 그 이후에는 source report가 `ACKNOWLEDGED`가 아니면 `finalized_at`을 설정할 수 없다. `NEEDS_INPUT`, `BLOCKED`, `FAILED` revision은 `routine_id=NULL`과 `finalized_at=NULL`로 저장한다. `PASS` 또는 `REVISE` revision은 routine이 생성·편집된 경우에만 `routine_id`를 채우며, `finalized_at`은 콜드스타트 예외 또는 직전 주 리포트 `ACKNOWLEDGED` 상태이고 `safety_status_code`가 `PASS` 또는 `REVISE`인 경우에만 설정할 수 있다. `finalized_at`이 있으면 `routine_id`는 반드시 non-null이어야 한다. USER 편집도 요청 시간·장소·장비 제약과 SafetyAgent 의견 반영 여부를 확인한다. 독립적인 최종 Safety 재검사는 수행하지 않으며 agent_summaries의 상세 구조는 증상 사용자 시나리오 검증 후 보완할 수 있다.

---

## 12. 주요 관계 요약

~~~text
users
  ├─ 1:N user_identities
  ├─ 1:1 user_profiles
  ├─ 1:N user_consent_events
  ├─ 1:N routines ─ 1:N routine_days ─ 1:N routine_items
  ├─ 1:N scheduled_workouts
  ├─ 1:N daily_contexts
  ├─ 1:N decision_runs
  ├─ 1:N workout_sessions
  └─ 1:N user_weeks ─ 1:0..1 weekly_reports

decision_runs
  ├─ 1:4 agent_proposals (Training, Recovery, Safety, Feasibility)
  ├─ 1:N plan_candidates ─ 1:N plan_items
  ├─ 1:N safety_reviews
  ├─ 1:N decision_options
  └─ 1:0..1 decision_selections
~~~

---

## 13. 인덱스와 무결성

필수 인덱스:

- user_identities(provider_code, provider_subject)
- user_identities(firebase_subject)
- daily_contexts(user_id, local_date)
- routines(user_id, status_code, effective_from)
- scheduled_workouts(user_id, scheduled_local_date, status_code)
- wearable_connections(user_id, status_code)
- wearable_sync_runs(wearable_connection_id, status_code, requested_at)
- wearable_summaries(user_id, local_date, provider_code)
- workout_sessions(user_id, ended_at, status_code)
- decision_runs(user_id, local_date, completed_at)
- exercises(catalog_version_id, review_status_code)
- exercise_safety_rules(body_area_code, minimum_severity_code, review_status_code)
- user_weeks(user_id, week_start_local_date)
- weekly_reports(user_week_id, status_code)
- manual_activity_records(user_id, created_at) — MVP 이후 인덱스

필수 CHECK:

- requested_duration_minutes > 0
- 모든 초 단위 값 >= 0
- discomfort severity는 허용 코드 중 하나
- setup_seconds는 0~60
- warmup_seconds는 60~180
- cooldown_seconds는 45~120
- exercise default_transition_seconds는 10~20
- plan이 있는 최종 option은 승인된 safety review를 가져야 함
- 사용자의 USER_OVERRIDE 없이 requested_duration_minutes 변경 금지
- plan이 있는 후보의 estimated_duration_seconds = requested_duration_minutes * 60
- weekly_plan_revisions의 ai_revision_number는 null, 1, 2 중 하나

마지막 조건처럼 여러 테이블을 참조하는 규칙은 서비스 계층과 통합 테스트로 보장한다.

---

## 14. 삭제와 보존

계정 삭제 절차:

1. users.status_code를 DELETION_PENDING으로 바꾸고 접근을 차단한다.
2. Firebase 계정과 외부 연동을 해제한다.
3. 생년월일을 포함한 운영 DB의 사용자 연결 데이터를 7일 이내 hard delete한다.
4. 사용자 캐시와 작업 데이터를 삭제한다.
5. 백업은 최대 30일 순환 주기 후 소멸시킨다.

사용자 소유 테이블은 users 삭제 시 안전하게 제거할 수 있도록 FK와 삭제 순서를 설계한다. 카탈로그와 집계 기준 데이터는 삭제하지 않는다.

보존 가능한 데이터:

- 개인을 다시 식별할 수 없는 집계 통계
- 법령상 별도 보존 의무가 확인된 최소 정보
- 체크인 원자료 28일, 웨어러블 원본 24시간, 일별 요약·상세 수행·설문 90일, 주간 리포트 12개월
- 관리자 접속기록 2년, 마스킹 오류 로그 7일

가명처리만 한 체크인, decision, agent proposal은 기본 보존하지 않는다. 삭제 작업의 운영 상태는 사용자 식별자를 포함하지 않는 opaque job ID로 감사할 수 있다.

실제 출시 전 개인정보 처리방침, 동의 철회·연동 해제, 운영 DB 삭제, 인증 제공자 삭제, 백업 만료 절차를 법률 또는 개인정보보호 담당자에게 검토받는다. 1년 미접속은 법정 휴면이 아닌 DORMANT 서비스 분류로 처리하고 30일 전 통지 후 삭제한다.

---

## 15. 운동 데이터 파이프라인

~~~text
data/raw/{source}
-> 출처, 라이선스, 원본 해시 기록
-> 필드 정규화
-> 중복과 한국어 명칭 정리
-> 부위, 패턴, 장비, 장소 태깅
-> 시간 메타데이터 작성
-> 대체 관계와 안전 규칙 초안
-> 기술 검증
-> 외부 도메인 검수
-> data/normalized/{catalog_version}
-> DB seed
~~~

검수 상태:

~~~text
DRAFT
TECH_REVIEWED
DOMAIN_APPROVED
REJECTED
DEPRECATED
~~~

안전 규칙, 대체 관계, 회복 콘텐츠, 안전 문구를 변경하면 재승인이 필요하다.

---

## 16. 선택한 대안과 제외한 대안

선택:

- 정규화 관계형 데이터와 제한적 JSONB
- 루틴 문맥의 CORE, SUPPORT, OPTIONAL
- proposal, candidate, safety review, final option의 분리 저장
- 사용자 삭제 시 연결 기록 삭제

선택하지 않음:

- 운동, 통증, 장비를 하나의 JSON 문서로 저장
- 운동마다 고정 tier 부여
- agent proposal과 final decision을 한 JSON에 덮어쓰기
- 가명 decision log를 계정 삭제 후 기본 보존
- 미검수 운동과 규칙을 production 후보로 사용

---

## 17. 아직 확정되지 않은 데이터 계약

- 운동 목표와 경험 수준의 전체 코드 목록
- training type과 body focus의 전체 코드 목록
- 자세·설명·미디어 콘텐츠의 승인자와 version 승격 규칙
- 수면 부족과 운동 부하 누적 정책값
- 복귀 모드의 정확한 볼륨 상한
- 외부 도메인 검수자의 운영상 식별·감사 방식
- 법률 검토 후 확정할 삭제 예외와 보존 의무

## 18. 팀 확인 질문

- 닉네임의 변경 횟수와 금칙어를 DB 제약과 서비스 정책 중 어디까지 둘 것인가?
- MVP 이후 주간 리포트 정정이 필요할 때 새 version과 관리자 감사 절차를 어떻게 설계할지?
- 1년 DORMANT 상태의 재활성화와 삭제 작업을 어떤 테이블로 감사할지?
- 실제 GitHub/운영 환경에서 계정 삭제 job의 owner와 실행 증적을 누가 관리할지?

이 항목을 구현하기 전에 API 계약과 도메인 규칙을 함께 갱신한다.
