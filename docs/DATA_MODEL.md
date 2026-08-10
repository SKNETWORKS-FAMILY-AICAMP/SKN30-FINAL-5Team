# DATA_MODEL.md

## 1. 문서 목적

이 문서는 MVP의 PostgreSQL 논리 모델, 핵심 관계, 무결성 제약, 버전 및 삭제 정책을 정의한다.

실제 SQLAlchemy 모델과 Alembic 마이그레이션은 이 문서와 API 계약이 승인된 다음 작성한다.

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
| last_active_at | 인증된 서비스 활동 시각 |
| created_at | 생성 시각 |
| updated_at | 수정 시각 |
| deletion_requested_at | 삭제 요청 시각, nullable |

이메일, 전체 이름, 비밀번호, ID Token은 저장하지 않는다.

### 4.2 user_identities

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_id | users FK |
| provider_code | FIREBASE, GOOGLE, KAKAO, NAVER |
| provider_subject | provider가 발급한 불변 subject |
| firebase_subject | 최종 Firebase 사용자 연결 subject |
| created_at | 연결 시각 |
| revoked_at | 연결 해제 시각, nullable |

활성 identity의 `(provider_code, provider_subject)`와 `firebase_subject`는 유일해야 한다. provider access/refresh token, 이메일, 전체 이름은 저장하지 않는다.

### 4.3 user_profiles

| 컬럼 | 설명 |
|---|---|
| user_id | users FK, PK |
| nickname | 사용자 표시용 닉네임 |
| adult_confirmed | 성인 여부 확인, NOT NULL |
| primary_goal_code | 운동 목표 코드 |
| experience_level_code | 운동 경험 |
| timezone | IANA timezone |
| preferred_location_code | 기본 장소 |
| default_requested_duration_minutes | 사용자의 기본 희망 운동 시간 |
| desired_weekly_workout_count | 주간 희망 운동 횟수 |
| coaching_style_code | SUPPORTIVE, CONCISE, ENERGETIC |
| age_band_code | 선택적 연령대 |
| height_cm | 선택, 현재 핵심 판단에 사용하지 않음 |
| weight_kg | 선택, 현재 핵심 판단에 사용하지 않음 |
| sex_code | 선택, 현재 핵심 판단에 사용하지 않음 |
| profile_version | 낙관적 잠금 버전 |
| created_at | 생성 시각 |
| updated_at | 수정 시각 |

adult_confirmed는 true여야 온보딩을 완료할 수 있다. 정확한 생년월일은 수집하지 않는다.

nickname은 중복을 허용하는 표시값이며 인증·리소스 소유권에 사용하지 않는다. 키, 체중, 성별은 MVP 핵심 결정에 사용하지 않으므로 UI에서 수집하지 않는 구성이 더 적절할 수 있다. 수집 여부는 개인정보 최소화 검토 후 확정한다.

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
| status_code | DRAFT, ACTIVE, RETIRED |
| source_manifest_hash | 원천 목록 해시 |
| activated_at | 활성화 시각 |
| created_at | 생성 시각 |

한 시점에 하나의 ACTIVE 버전만 허용한다.

### 5.2 exercises

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| catalog_version_id | catalog_versions FK |
| stable_code | 카탈로그 내 안정적 코드 |
| name_ko | 한국어 표시명 |
| name_en | 선택적 영문명 |
| training_type_code | STRENGTH, CARDIO, MOBILITY 등 |
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
| estimated_duration_seconds | 구성에 따른 서버 예상 시간 |

### 6.3 routine_items

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| routine_day_id | routine_days FK |
| exercise_id | exercises FK |
| sequence | 수행 순서 |
| tier_code | CORE, SUPPORT, OPTIONAL |
| sets | 세트 수 |
| reps | 반복 수, nullable |
| work_seconds_per_set | 시간 기반 운동, nullable |
| rest_seconds_per_set | 세트 간 휴식 |
| intensity_code | 비의료적 운동 강도 코드 |

tier_code는 routine item의 문맥 속성이다.

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

복귀 모드의 예정 운동 3회 연속 미수행을 재현하기 위해 필요하다. user_id와 scheduled_local_date, routine_day_id 조합은 유일하다.

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

user_id와 local_date 조합은 유일하다.

피로 코드는 사용자의 주관적 제품 입력이며 의료 상태를 뜻하지 않는다. 수면 부족과 최근 부하의 파생 임계값은 별도 정책 버전으로 관리한다.

### 7.2 daily_context_discomforts

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| daily_context_id | daily_contexts FK |
| body_area_code | body_areas FK |
| severity_code | NONE, MILD, MODERATE, SEVERE |

daily_context_id와 body_area_code 조합은 유일하다. NONE 항목은 저장하지 않고 빈 목록으로 표현할 수 있다.

### 7.3 daily_context_adverse_reactions

| 컬럼 | 설명 |
|---|---|
| daily_context_id | daily_contexts FK |
| reaction_code | DOMAIN_RULES.md의 이상 반응 코드 |

PK는 daily_context_id와 reaction_code 조합이다.

### 7.4 wearable_summaries

웨어러블은 핵심 MVP 이후 기능이다. 도입 시 다음 최소 요약값만 저장한다.

- user_id
- local_date
- provider_code
- sleep_minutes
- steps
- active_minutes
- last_workout_at
- resting_heart_rate_trend
- created_at

초 단위 심박, GPS 경로, 직접 식별자는 저장하지 않는다. 사용자와 local_date, provider_code 조합은 유일하다.

---

## 8. 정책과 복귀 상태

### 8.1 policy_versions

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| version_code | 정책 버전 |
| return_mode_inactivity_days | 기본 7 |
| return_mode_consecutive_misses | 기본 3 |
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
- progress_weight
- recovery_weight
- feasibility_weight
- adherence_weight
- source_summary JSONB
- created_at

안전 결정에는 이 가중치를 사용하지 않는다.

복귀 모드 자체는 별도 영구 플래그보다 scheduled_workouts와 workout_sessions로부터 계산하고 decision input snapshot에 결과를 저장한다.

---

## 9. 결정과 에이전트 기록

### 9.1 decision_runs

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

### 9.2 agent_proposals

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| decision_run_id | decision_runs FK |
| agent_type_code | PROGRESS, RECOVERY_SAFETY, FEASIBILITY, ADHERENCE |
| recommended_action_code | 제안 액션 |
| proposal_schema_version | JSON 구조 버전 |
| proposal | 구조화 JSONB |
| proposal_status_code | READY, NEEDS_INPUT, FAILED |
| policy_version | 에이전트 정책 버전 |
| created_at | 생성 시각 |

decision_run_id와 agent_type_code 조합은 유일하다.

### 9.3 plan_candidates

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| decision_run_id | decision_runs FK |
| candidate_code | ORIGINAL, PRIMARY, LIGHTER, RECOVERY, FALLBACK |
| action_code | KEEP, DOWNSHIFT, CHANGE, RECOVERY |
| setup_seconds | 장비 준비 |
| warmup_seconds | 준비 운동 |
| cooldown_seconds | 마무리 |
| requested_duration_minutes | 사용자 요청 시간 |
| duration_adjustment_source_code | PROFILE 또는 USER_OVERRIDE |
| estimated_duration_seconds | 권장 전체 예상 시간 |
| goal_preservation_score | 비안전 목적 점수 |
| duration_rule_version | 시간 규칙 버전 |
| created_at | 생성 시각 |

requested_duration_minutes는 사용자 입력에서만 가져오며 시스템이 임의 축소하지 않는다. estimated_duration_seconds는 권장 정보이고 hard limit 또는 완료 조건이 아니다.

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

운동 계획이 없는 REST와 STOP_AND_SEEK_HELP도 동일한 선택 모델에서 표현하기 위한 테이블이다.

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| decision_run_id | decision_runs FK |
| option_code | PRIMARY, LIGHTER, ORIGINAL, REST |
| action_code | 최종 액션 |
| plan_candidate_id | 계획이 있을 때 FK, nullable |
| selectable | 사용자 선택 가능 여부 |
| blocked_reason_code | 선택 불가 이유, nullable |
| display_order | 표시 순서 |

규칙:

- REST와 STOP_AND_SEEK_HELP에는 plan_candidate_id가 없다.
- REST 권고에는 LIGHTER 옵션을 만들지 않는다.
- RECOVERY의 LIGHTER 옵션은 action_code=REST, plan_candidate_id=null일 수 있다.
- KEEP, DOWNSHIFT, CHANGE, RECOVERY 결정에는 사용자의 자발적 휴식을 위한 별도 REST option을 둘 수 있다.
- 안전 veto된 ORIGINAL은 selectable=false다.

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
- coaching_style_code
- prompt_version, nullable
- model_code, nullable
- created_at

안전 문구와 일반 설명을 분리하고 내부 추론을 저장하지 않는다.

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
| idempotency_key | 세션 생성 중복 방지 |

REST 또는 STOP_AND_SEEK_HELP 선택에는 workout_session을 만들지 않는다.

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

### 10.3 workout_safety_events

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| workout_session_id | workout_sessions FK |
| occurred_at | 사용자에게 발생한 시각 |
| instruction_code | SHOW_CAUTION, STOP_SESSION, STOP_AND_SEEK_HELP |
| resulting_action_code | REST, STOP_AND_SEEK_HELP 또는 null |
| guidance_code | 검수된 안내 문구 코드 |
| created_at | 서버 저장 시각 |

workout_safety_event_discomforts와 workout_safety_event_adverse_reactions에 부위, 심각도, 이상 반응을 정규화해 저장한다.

REST 또는 STOP_AND_SEEK_HELP 결과가 나오면 세션 상태를 STOPPED_FOR_SAFETY로 바꾼다. MILD 또는 MODERATE 입력은 MVP에서 계획을 자동 재작성하지 않는다.

### 10.4 workout_feedback

| 컬럼 | 설명 |
|---|---|
| workout_session_id | PK, FK |
| difficulty_code | EASY, APPROPRIATE, HARD |
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

웨어러블 또는 외부 운동 기록은 별도 참고 테이블에 저장할 수 있으나 workout_sessions의 공식 status_code를 생성하거나 변경하지 않는다.

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
| status_code | OPEN, CLOSED |
| closed_at | 논리적 마감 시각, nullable |

`(user_id, week_start_local_date)`는 유일하다. OPEN/CLOSED는 scheduler가 아니라 요청 시 현재 날짜와 경계를 비교해 계산·확정한다.

### 11.2 weekly_reports

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| user_week_id | user_weeks FK, UNIQUE |
| status_code | GENERATED, ACKNOWLEDGED, FAILED |
| input_snapshot | 닫힌 주의 최소 집계 JSONB |
| input_hash | 집계 해시 |
| completed_count | 운동 블록 체크로 계산한 COMPLETED 수 |
| partial_count | PARTIAL 수 |
| not_completed_count | NOT_COMPLETED 수 |
| safety_stopped_count | STOPPED_FOR_SAFETY 수 |
| primary_miss_reason_code | 가장 많은 미수행 이유, nullable |
| summary | 템플릿 또는 승인된 설명 |
| report_policy_version | 생성 정책 버전 |
| generated_at | 생성 시각 |
| acknowledged_at | 사용자 확인 시각, nullable |

동일한 닫힌 주와 input_hash에 대해 멱등 생성한다. MVP 주간 리포트는 생성 후 불변이며 사용자용 세션 정정·리포트 재생성 API는 제공하지 않는다. 운영 정정이 필요하면 후속 ADR에서 version 모델과 감사 절차를 먼저 정의한다.

### 11.3 weekly_plan_revisions

| 컬럼 | 설명 |
|---|---|
| id | UUID, PK |
| target_user_week_id | 다음 계획 대상 주 FK |
| source_weekly_report_id | 직전 주 리포트 FK |
| revision_sequence | 대상 주 안에서 증가하는 전체 수정 순서 |
| ai_revision_number | AI 수정이면 1 또는 2, 그 외 null |
| revision_source_code | INITIAL, AI, USER |
| routine_id | 생성·편집된 routine FK |
| safety_status_code | PASS, REVISE, BLOCKED, FAILED |
| finalized_at | 최종 확정 시각, nullable |
| created_at | 생성 시각 |

AI 수정은 최대 2회다. USER 편집 횟수와 낙관적 잠금은 revision_sequence로 관리한다. `source_weekly_report_id`가 ACKNOWLEDGED가 아니면 `finalized_at`을 설정할 수 없다. USER 편집도 최종 안전 검증을 통과해야 한다.

---

## 12. 주요 관계 요약

~~~text
users
  ├─ 1:N user_identities
  ├─ 1:1 user_profiles
  ├─ 1:N routines ─ 1:N routine_days ─ 1:N routine_items
  ├─ 1:N scheduled_workouts
  ├─ 1:N daily_contexts
  ├─ 1:N decision_runs
  ├─ 1:N workout_sessions
  └─ 1:N user_weeks ─ 1:0..1 weekly_reports

decision_runs
  ├─ 1:4 agent_proposals
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
- workout_sessions(user_id, ended_at, status_code)
- decision_runs(user_id, local_date, completed_at)
- exercises(catalog_version_id, review_status_code)
- exercise_safety_rules(body_area_code, minimum_severity_code, review_status_code)
- user_weeks(user_id, week_start_local_date)
- weekly_reports(user_week_id, status_code)

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
- weekly_plan_revisions의 ai_revision_number는 null, 1, 2 중 하나

마지막 조건처럼 여러 테이블을 참조하는 규칙은 서비스 계층과 통합 테스트로 보장한다.

---

## 14. 삭제와 보존

계정 삭제 절차:

1. users.status_code를 DELETION_PENDING으로 바꾸고 접근을 차단한다.
2. Firebase 계정과 외부 연동을 해제한다.
3. 운영 DB의 사용자 연결 데이터를 7일 이내 hard delete한다.
4. 사용자 캐시와 작업 데이터를 삭제한다.
5. 백업은 최대 30일 순환 주기 후 소멸시킨다.

사용자 소유 테이블은 users 삭제 시 안전하게 제거할 수 있도록 FK와 삭제 순서를 설계한다. 카탈로그와 집계 기준 데이터는 삭제하지 않는다.

보존 가능한 데이터:

- 개인을 다시 식별할 수 없는 집계 통계
- 법령상 별도 보존 의무가 확인된 최소 정보

가명처리만 한 체크인, decision, agent proposal은 기본 보존하지 않는다. 삭제 작업의 운영 상태는 사용자 식별자를 포함하지 않는 opaque job ID로 감사할 수 있다.

실제 출시 전 개인정보 처리방침, 운영 DB 삭제, 인증 제공자 삭제, 백업 만료 절차를 법률 또는 개인정보보호 담당자에게 검토받는다.

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
