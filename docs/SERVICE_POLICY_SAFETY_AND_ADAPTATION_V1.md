# 운동 웰니스 서비스 정책·데이터 계약 기준안

> 상태: 최신 정책 기준안  
> 작성일: 2026-09-01 / 최종 변경: 2026-09-02  
> 적용 대상: 만 18–64세 일반 성인 중 운동 초보·입문자·복귀자  
> 범위: 온보딩, Daily Check-in, Safety, Recovery, Feasibility, Training, 운동 카탈로그, 운동 실행, 웨어러블, 주간 계획·리포트

## 1. 문서 목적

이 문서는 연구 근거와 제품정책을 구분하고, 현재 서비스에 적용할 목표 정책과 필요한 API·DB·머신 코드·검수 규칙을 하나의 기준으로 정리한다.

이 서비스는 의료 진단, 치료, 재활 또는 질환별 운동 처방을 제공하지 않는다. 사용자가 직접 입력한 최소 상태값을 바탕으로 검수된 일반 운동 후보를 제한하고 조정한다.

이 문서는 현재 개발의 정책 기준이다. 구현 변경 시에는 이 문서의 API·DB·프론트 영향과 안전 불변조건 테스트를 함께 갱신한다.

---

## 2. 근거 수준

### 2.1 직접 근거

가이드라인·메타분석 등이 해당 판단이나 입력값을 직접 지지하는 경우다.

- WHO의 성인 연령 구분에 따라 MVP 대상은 만 18–64세로 제한한다.
- 고령자, 임신·산후, 만성질환자는 운동 금지 집단이 아니라 현재 서비스가 집단별 처방을 검증하지 않았기 때문에 지원 범위에서 제외한다.
- 건강하고 무증상인 비활동자는 저강도에서 중강도로 시작하여 점진적으로 증가한다.
- 광범위한 병력 대신 의료적 운동 제한 여부와 당일 Red Flag를 확인한다.
- 흉부 불편감, 평소와 다른 심한 호흡곤란, 심한 어지럼·실신 느낌, 매우 빠르거나 불규칙한 심박 느낌은 운동 생성 또는 진행 중단 신호로 사용한다.
- 통증 강도는 0–10 NRS를 사용한다. 단, 제품의 NRS 구간별 동작은 임상 표준 cutoff가 아니다.
- 수면 7시간을 양호한 기준점으로 사용하고 수면 부족을 Recovery 참고값으로 사용한다.
- 주간 계획은 CARDIO와 STRENGTH를 함께 고려한다.
- 운동별 MET와 체중·시간을 사용해 예상 칼로리를 계산할 수 있다.
- 서비스 최소 운동시간 10분은 건강효과의 최소 기준이 아니라 제품 지원 범위다.
- 건강정보 동의는 일반 개인정보 동의와 분리한다.

### 2.2 간접 근거

관련 연구가 방향을 지지하지만 서비스의 정확한 알고리즘까지 검증한 것은 아닌 경우다.

- FITT 기본값은 성별보다 목표, 경험, Recovery와 실제 수행 반응을 중심으로 결정한다.
- BMI를 개인 운동 강도 조정값으로 사용하지 않는다.
- 다이어트는 STRENGTH와 CARDIO, 근육량 증가는 STRENGTH, 체력증진은 STRENGTH와 CARDIO의 균형을 우선한다.
- 수면과 피로를 Recovery 입력으로 사용한다.
- 운동 후 쉬움·적당·힘듦 피드백을 후속 progression 또는 regression 참고값으로 사용한다.
- 주간 계획은 실제 완료 이력에 따라 남은 운동 패턴을 재배치한다.
- 미수행 이유는 시간, 컨디션, 통증, 부담, 의욕과 기타로 구성한다.
- 웨어러블 수면은 장기 self-tracking 참고값으로만 사용하고 진단에 사용하지 않는다.

### 2.3 제품정책

다음 수치와 동작은 연구가 정답을 정해주지 않으므로 MVP 기본값으로 정의한다.

- NRS 1–3 / 4–6 / 7–10
- 수면·피로 조합별 Recovery level
- LIGHT / VERY_LIGHT FITT downshift
- 수행 상태는 당일 최종 완료 블록 개수로 판정
- 반복 피드백 2–3회
- 주간 목표 현실화의 80%, 2주, 3-of-4 trigger
- 서비스 지원시간 10–60분

모든 제품정책은 `policy_version`과 함께 결정 기록에 저장하고 향후 사용자 데이터로 검증·보정한다.

---

## 3. 서비스 범위 및 온보딩

### 3.1 지원 대상

- 만 18세 이상 64세 이하
- 일반 성인
- 운동 초보·입문자·복귀자
- 기본 저강도에서 중강도

### 3.2 지원 제외

- 만 18세 미만
- 만 65세 이상
- 질환·임신 등으로 별도의 의료적 운동 관리가 필요한 경우
- 의료진에게 운동 제한 또는 주의 안내를 받은 경우

지원 제외 사용자는 일반 자동 루틴을 생성하지 않는다. 상세 병력, 질환명, 임신 이력, 과거 부상 이력은 수집하지 않는다.

### 3.3 온보딩 질문

1. `생년월일을 입력해 주세요.`
2. `현재 질환·임신 등으로 개별적인 운동 관리가 필요하거나 의료진으로부터 운동 제한·주의 안내를 받은 상태인가요?`

### 3.4 최종 온보딩 입력

| 필드 | 타입 | 필수 | 소비처 | 저장 규칙 |
|---|---|---:|---|---|
| `date_of_birth` | date | 예 | Eligibility | 암호화 저장, 만 18–64세 판정에만 사용 |
| `medical_exercise_restriction` | boolean | 예 | Eligibility | `false`인 지원 사용자만 루틴 허용 |
| `weight_kg` | numeric(5,2) | 예 | 예상 kcal | 25–300, Safety에 사용 금지 |
| `primary_goal_code` | varchar(64) | 예 | Training | 목표 코드 사용 |
| `experience_level_code` | varchar(32) | 예 | Training | `BEGINNER`, `INTERMEDIATE` |
| `weekly_target_sessions` | smallint | 예 | Weekly Plan/Report | 1–7 |
| `coaching_style_code` | varchar(32) | 예 | UX | Safety·선택에 영향 금지 |
| `persistent_pains` | `PersistentPainInput[]` | 아니오 | Daily Check-in 기본값 | 원인·진단명 없이 부위와 NRS만 민감정보로 저장. 제출 전 Safety 입력으로 사용 금지 |
| `timezone` | varchar(64) | 예 | 날짜 경계 | IANA timezone |
| `terms_version` | varchar(64) | 예 | 이용약관 동의 이력 | 현재 게시된 서비스 이용약관 버전 |
| 일반 개인정보 동의 | boolean/event | 예 | Legal | 별도 동의 이벤트 저장 |
| 민감정보 처리 동의 | boolean/event | 예 | Legal | 일반 동의와 분리 |
| 웨어러블 동의 | boolean/event | 아니오 | Integration | 선택 |
| 마케팅 동의 | boolean/event | 아니오 | Marketing | 선택 |

삭제 대상 입력은 성별, 키, BMI, 온보딩 장소, 온보딩 1회 운동시간, 사용자 장비다.

`medical_exercise_restriction=true`와 같은 지원 제외 응답은 상세 의료정보로 확장하지 않는다. Eligibility 실패 이력을 장기 저장해야 할 법적·운영 목적이 확정되지 않았다면 최소한의 가입 차단 결과만 저장하고 질문 원문이나 자유서술을 저장하지 않는다.

`persistent_pains`는 허리디스크·부상명처럼 원인이나 진단을 묻지 않는다. 사용자가 평소 꾸준히 불편한 부위와 현재 통증 정도(NRS 1–10)만 선택하며, 부위별로 한 건만 허용한다. 값이 없으면 빈 목록으로 저장한다.

### 3.5 온보딩 필드·코드 상세 정의

표의 `*_code`는 사용자에게 그대로 보여주는 문구가 아니라 서버, DB, Agent 사이에서 의미가 변하지 않도록 사용하는 안정적인 영문 식별값이다. boolean 필드는 코드가 아니라 예·아니오 상태다. 화면에서는 반드시 별도의 한국어 질문과 label을 사용한다.

#### `date_of_birth`

- 종류: ISO 8601 calendar date (`YYYY-MM-DD`)
- 의미: 서버가 사용자 timezone의 local date를 기준으로 만 나이를 계산해 MVP 연령 범위를 판정하는 원본값이다.
- `18–64세`: `ELIGIBLE`
- 그 외: `OUT_OF_SCOPE_AGE`로 일반 루틴 생성 차단
- 사용처: 온보딩 Eligibility에서만 사용
- 사용 금지: 운동 강도, FITT, Safety 운동 제외, 칼로리 계산, LLM·결정 snapshot·분석·로그
- 저장 목적: 지원 연령 범위를 정확하게 판정하고 재검증하기 위함이다. 평문값은 저장하지 않으며 KMS/AES-GCM 암호화 envelope로만 보관한다.

예:

```json
{
  "date_of_birth": "1997-04-15"
}
```

#### `medical_exercise_restriction`

- 종류: boolean
- 의미: 질환·임신 등으로 개별 운동 관리가 필요하거나 의료진에게 운동 제한·주의 안내를 받은 상태인지 나타낸다.
- 질문: `현재 질환·임신 등으로 개별적인 운동 관리가 필요하거나 의료진으로부터 운동 제한·주의 안내를 받은 상태인가요?`
- `false`: 현재 MVP 범위 통과
- `true`: `OUT_OF_SCOPE_MEDICAL_MANAGEMENT`로 일반 루틴 생성 차단
- 사용처: 온보딩 Eligibility에서만 사용
- 사용 금지: 질환 추정, 진단명 생성, 제한 종류 추정, LLM 전달
- 저장 목적: 상세 병력을 수집하지 않고 서비스 지원 범위만 판정

#### Eligibility 결과 코드

| 코드 | 의미 | 시스템 동작 | 사용자 표시 예 |
|---|---|---|---|
| `ELIGIBLE` | 두 Eligibility 질문을 통과함 | 온보딩 계속 진행 | 별도 경고 없음 |
| `OUT_OF_SCOPE_AGE` | 18–64세 범위가 아님 | 일반 루틴 생성 차단 | `현재 서비스는 만 18–64세 성인을 대상으로 제공돼요.` |
| `OUT_OF_SCOPE_MEDICAL_MANAGEMENT` | 개별 의료적 운동 관리가 필요한 상태 | 일반 루틴 생성 차단 | `현재 상태에 맞는 개별 운동 관리는 의료진 또는 자격을 갖춘 전문가와 상의해주세요.` |

Eligibility 결과는 `eligibility_result_code`로 저장하거나 온보딩 차단 응답에 사용할 수 있다. 실패 사유를 운동 Agent가 다시 해석하지 않는다.

#### `weight_kg`

- 종류: `numeric(5,2)`
- 의미: 사용자가 제공한 현재 체중 kg
- 허용 범위: 25.00–300.00
- 사용처: 승인 MET와 실제 또는 예상 운동시간을 이용한 예상 kcal 계산
- 사용 금지: BMI 계산, 체형 판단, Safety 판단, 강도 자동 상향·하향, LLM 설명
- 결측 처리: 정책상 온보딩 필수지만 기존 사용자 migration 중 값이 없으면 kcal을 `null`로 반환

#### `primary_goal_code`

- 종류: 안정적인 목표 머신 코드
- 의미: Training이 어떤 운동 유형과 pattern을 우선할지 정하는 사용자 목표
- 사용처: Training 우선순위, 주간 coverage, 리포트 설명
- 사용 금지: Safety veto 완화, 장소·시간 hard constraint 해제

| 코드 | 사용자 표시 | Training 의미 |
|---|---|---|
| `FAT_LOSS` | 다이어트 | STRENGTH와 CARDIO를 모두 높은 우선순위로 고려 |
| `MUSCLE_GAIN` | 근육량 증가 | STRENGTH를 가장 높은 우선순위로 고려 |
| `GENERAL_FITNESS` | 체력 증진 | STRENGTH와 CARDIO를 균형 있게 높은 우선순위로 고려 |

정확한 50:50 또는 60:40 비율을 의미하지 않는다.

#### `experience_level_code`

- 종류: 안정적인 운동 경험 머신 코드
- 의미: 사용할 수 있는 운동 난이도 후보와 기본 FITT 수준
- 사용처: Training 후보 필터와 FITT template 선택
- 사용 금지: 당일 Recovery가 나쁘다는 이유로 사용자 경험 수준 자체를 변경하는 것

| 코드 | 사용자 표시 | 후보와 기본 처방 |
|---|---|---|
| `BEGINNER` | 초급 | BEGINNER 운동과 Beginner 기본 FITT |
| `INTERMEDIATE` | 중급 | BEGINNER+INTERMEDIATE 운동과 Intermediate 기본 FITT |

Recovery 또는 Pain cap이 적용되면 경험 코드는 유지하고 세트·반복·강도 또는 낮은 variant rank를 조정한다.

#### `weekly_target_sessions`

- 종류: smallint 1–7
- 의미: 사용자가 한 주에 수행하려는 목표 운동 세션 수
- 사용처: 주간 계획 세션 수, pattern 분배, 목표 달성률, 주간 리포트, 목표 현실화 제안
- 사용 금지: 당일 강도나 NRS·Recovery 판정
- 예: `3`이면 Session A/B/C를 계획하지만 4번째 추가 운동 요청도 허용
- 기존 필드 전환: 현재 `desired_weekly_workout_count`를 목표 계약에서 `weekly_target_sessions`로 이름을 통일하되 API 호환 기간을 둔다.

#### `coaching_style_code`

- 종류: 안정적인 표현 성향 머신 코드
- 의미: 같은 결정 내용을 어떤 말투와 길이로 보여줄지 정한다.
- 사용처: 사용자 문구의 어조·길이
- 사용 금지: Safety, 운동 선택, 강도, 시간, progression

| 코드 | 사용자 표시 예 | 표현 원칙 |
|---|---|---|
| `SUPPORTIVE` | 든든하게 | 공감하고 부담을 주지 않는 문구 |
| `CONCISE` | 간결하게 | 핵심 행동과 이유를 짧게 표시 |
| `ENERGETIC` | 활기차게 | 활기 있는 표현, 단 Safety 화면은 진지한 어조 유지 |

#### `persistent_pains`

- 종류: `PersistentPainInput[]`; 각 항목은 `body_area_code`, `intensity_score`(NRS 1–10), `policy_version`으로 구성한다.
- 질문: `평소 꾸준히 불편한 부위가 있나요? 있다면 부위와 지금의 불편 정도를 선택해 주세요.`
- 수집 금지: 질환명, 부상 원인·시점, 치료·수술 이력, 자유서술.
- 사용처: Daily Check-in 초기값. `persistent_pains` 자체는 Safety 후보 필터 또는 당일 확정 통증이 아니다. 사용자가 당일 Check-in에서 수정·추가·삭제 후 제출한 `daily_context_pains`만 그날의 Safety 입력으로 사용한다.
- 저장: 민감정보로 취급하고 별도 row에 부위별 NRS·정책 버전·생성/수정 시각을 저장한다. 온보딩 원본을 Daily Check-in row에 복사해 덮어쓰지 않는다.

`user_persistent_pains`

| 컬럼 | 타입 | 규칙 |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | users FK |
| `body_area_code` | varchar(64) | 사용자 선택 부위 |
| `intensity_score` | smallint | NRS 1–10 |
| `policy_version` | varchar(64) | NRS 정책 버전 |
| `created_at`, `updated_at` | timestamptz | 저장 시각 |

`(user_id, body_area_code)`는 unique다. 사용자가 온보딩 완료 후 프로필에서 값을 수정하거나 삭제할 수 있으며, 변경은 이후 Daily Check-in의 기본값에만 반영한다.

#### `timezone`

- 종류: IANA timezone 문자열
- 예: `Asia/Seoul`
- 의미: 사용자의 하루와 주간 경계를 계산하는 기준
- 사용처: Daily Check-in의 `local_date`, 월–일 주간 범위, 휴식일 알림 차단, 리포트 마감
- 사용 금지: 운동 강도·Safety 판단
- UTC offset만 저장하지 않는다. 서머타임이 있는 지역의 날짜 경계를 정확히 처리하기 위해 IANA 이름을 사용한다.

#### 동의 유형 코드

동의 값은 `user_consents.consent_type_code`로 저장하고 현재 상태와 append-only 동의 이벤트를 분리한다.

| 코드 | 사용자 동의 의미 | 필수 | 허용되는 처리 |
|---|---|---:|---|
| `GENERAL_PERSONAL_DATA` | 서비스 이용을 위한 일반 개인정보 처리 | 예 | 계정·프로필·서비스 운영 |
| `SENSITIVE_DATA` | 지속 통증·당일 통증·수면·피로 등 건강 관련 민감정보 처리 | 예 | Safety·Recovery·리포트 |
| `WEARABLE_INTEGRATION` | 웨어러블 요약 연동 | 아니오 | 수면·HR·활동 kcal의 최소 normalized summary |
| `MARKETING` | 마케팅 수신·활용 | 아니오 | 별도 마케팅 정책 범위 |

각 row에는 `granted`, `policy_version`, `granted_at`, `revoked_at`을 저장한다. `WEARABLE_INTEGRATION=false`여도 수동 Check-in으로 핵심 기능이 모두 동작해야 한다. 마케팅 미동의는 운동 추천 품질에 영향을 주지 않는다.

서비스 이용약관 동의는 개인정보 처리 consent가 아니므로 위 네 코드에 추가하지 않는다. 가입 시
별도 `user_terms_agreements` append-only 이력에 `terms_version`, `terms_agreed_at`을 저장한다.
동일 약관 버전의 중복 동의는 만들지 않으며, 새 약관 버전이 게시되면 필요한 재동의를 별도 안내한다.

가입 화면은 다음을 한 화면에 함께 표시한다.

- `[필수] 서비스 이용약관 동의`
- `[필수] 일반 개인정보 처리 동의`
- `[필수] 건강정보 등 민감정보 처리 동의`
- `[선택] 웨어러블 연동 동의`
- `[선택] 마케팅 수신 동의`

개인정보처리방침은 동의 코드나 체크박스를 추가하지 않고, 가입 화면과 설정에서 언제나 열람할 수
있는 링크로 제공한다. 서비스 이용약관에는 만 18–64세 일반 성인만 지원하며 고령자, 임신·산후,
만성질환자 등은 운동 금지 집단이 아니라 현 서비스가 집단별 처방을 검증하지 않아 자동 루틴 지원
범위에서 제외된다는 사실을 고지한다.

#### 온보딩 정상 요청 예시

```json
{
  "date_of_birth": "1997-04-15",
  "medical_exercise_restriction": false,
  "weight_kg": 68.5,
  "primary_goal_code": "GENERAL_FITNESS",
  "experience_level_code": "BEGINNER",
  "weekly_target_sessions": 3,
  "coaching_style_code": "SUPPORTIVE",
  "persistent_pains": [
    {"body_area_code": "LOWER_BACK", "intensity_score": 3}
  ],
  "timezone": "Asia/Seoul",
  "consents": {
    "GENERAL_PERSONAL_DATA": true,
    "SENSITIVE_DATA": true,
    "WEARABLE_INTEGRATION": false,
    "MARKETING": false
  }
}
```

---

## 4. 전체 결정 구조

```text
통합 운동 카탈로그
        ↓
SafetyPolicyEngine
        ↓
Safety-approved Pool
        ↓
┌ TrainingAgent         → exercise plan proposal
├ RecoveryAgent         → adjustment codes
└ FeasibilityAgent      → adjustment codes
        ↓
Coordinator
        ↓
Plan Compiler
        ↓
Deterministic Integrity Validator
        ↓
Final Routine 또는 계획 없음
```

Safety는 Hard Constraint다. SafetyPolicyEngine이 BLOCK한 운동은 TrainingAgent, Coordinator 또는 LLM이 복구할 수 없다. TrainingAgent만 운동 계획을 만들고 RecoveryAgent와 FeasibilityAgent는 조정 코드만 제안한다. 최종 컴파일 계획은 Safety envelope, 장소, Recovery/Pain cap, 카탈로그 버전과 시간 범위를 결정적으로 검증한다.

---

## 5. Daily Check-in 계약

### 5.1 입력 필드

| 필드 | 타입 | 필수 | 제약 |
|---|---|---:|---|
| `sleep_minutes` | smallint nullable | 아니오 | 0–1440, `null`은 결측 |
| `sleep_source_code` | varchar(16) nullable | 조건부 | `MANUAL`, `WEARABLE` |
| `fatigue_level_code` | varchar(16) | 예 | `LOW`, `MODERATE`, `HIGH` |
| `available_time_minutes` | smallint | 예 | 10–60 |
| `location_code` | varchar(64) | 예 | `HOME`, `GYM` 등 승인 코드 |
| `pain_present` | boolean | 예 | pain row 존재 여부와 일치 |
| `red_flag_present` | boolean | 예 | `true`면 루틴 생성 STOP |

### 5.2 통증 입력과 온보딩 기본값

Daily Check-in을 열면 활성 `persistent_pains`를 부위·NRS 기본값으로 먼저 표시한다. 사용자는 당일 상태에 맞게 항목을 수정·추가·삭제한 뒤 제출하며, 제출된 `daily_context_pains`만 그날의 SafetyPolicyEngine 입력으로 사용한다. 온보딩 통증을 자동 확정하거나 당일 입력이 없을 때 이전 값을 안전 판단에 재사용하지 않는다.

### 5.3 통증 입력 테이블

`daily_context_pains`

| 컬럼 | 타입 | 규칙 |
|---|---|---|
| `id` | UUID | PK |
| `daily_context_id` | UUID | FK, cascade delete |
| `body_area_code` | varchar(64) | body area FK |
| `intensity_score` | smallint | 1–10 |
| `severity_code` | varchar(16) | 서버가 NRS에서 변환 |
| `policy_version` | varchar(64) | 변환 정책 버전 |
| `created_at` | timestamptz | 저장 시각 |

`(daily_context_id, body_area_code)`는 unique다. `pain_present=false`이면 pain row는 0개, `true`이면 1개 이상이어야 한다. 동일 부위를 중복 저장하지 않는다.

NRS 변환 코드는 다음과 같다.

```text
NRS 1–3  → MILD
NRS 4–6  → MODERATE
NRS 7–10 → SEVERE
```

---

## 6. Safety 정책

### 6.1 Red Flag

사용자 질문:

> 오늘 가슴 통증이나 압박감, 평소와 다른 심한 숨참, 심한 어지럼 또는 실신할 것 같은 느낌, 심장이 매우 빠르거나 불규칙하게 뛰는 느낌 같은 증상이 있나요?

`red_flag_present=true`이면 루틴 생성을 중단하고 Alternative를 제공하지 않는다. 원인을 추정하거나 진단하지 않는다.

### 6.2 NRS별 동작

| NRS | severity | 후보 필터 | 전역 상한 | 결과 |
|---:|---|---|---|---|
| 0 | NONE | 없음 | 없음 | 정상 |
| 1–3 | MILD | 해당 부위 contraindicated 운동 BLOCK | 없음 | 남은 후보로 목표 유지 |
| 4–6 | MODERATE | 해당 부위 contraindicated 운동 BLOCK | `LIGHT` | 남은 후보 전체에 통증 상한 적용 |
| 7–10 | SEVERE | 전체 생성 중단 | STOP | Alternative 없음 |

복수 통증은 모든 부위 BLOCK의 합집합을 적용한다. 하나라도 7 이상이면 전체 생성을 중단한다. 전역 `pain_load_cap`은 가장 높은 NRS를 기준으로 한다.

### 6.3 Safety 결과 코드

```text
PASS
REVISE
BLOCKED
NEEDS_INPUT
FAILED
```

사용자 행동 코드는 다음과 같이 유지한다.

```text
KEEP
DOWNSHIFT
CHANGE
RECOVERY
REST
STOP_AND_SEEK_HELP
```

### 6.4 Safety Pool 0개

- Safety 조건을 완화하지 않는다.
- Alternative를 뒤져 Safety-approved Pool 밖의 운동을 추가하지 않는다.
- 계획을 생성하지 않는다.
- 사용자에게 현재 입력으로 안전 기준을 만족하는 루틴을 구성하기 어렵다는 실패 이유를 표시한다.

---

## 7. 운동 카탈로그 목표 스키마

### 7.1 원칙

- PostgreSQL이 canonical SoT다.
- 반복 조회·필터·무결성 검사가 필요한 값은 JSONB가 아니라 typed column 또는 관계 테이블로 저장한다.
- 모든 운동과 안전 메타데이터는 `catalog_version`, 검수 상태, 근거와 reviewer를 보존한다.
- Raw source와 normalized production catalog를 분리한다.
- 검수되지 않은 값은 `NULL` 또는 `REVIEW_REQUIRED`이며 production 후보에 사용하지 않는다.

### 7.2 `variant_difficulty_rank`

`exercises` 테이블에 nullable 컬럼으로 추가한다.

| 속성 | 값 |
|---|---|
| 컬럼 | `variant_difficulty_rank` |
| 타입 | `smallint nullable` |
| CHECK | `NULL OR variant_difficulty_rank >= 1` |
| 적용 범위 | 같은 `family_code` 안의 상대 수행 난이도 |
| 정렬 | 숫자가 작을수록 쉬움 |
| 미확정 | 비교가 명확하지 않으면 `NULL` |

예:

| family | exercise | rank |
|---|---|---:|
| PUSH_UP | WALL_PUSH_UP | 1 |
| PUSH_UP | INCLINE_PUSH_UP | 2 |
| PUSH_UP | KNEE_PUSH_UP | 3 |
| PUSH_UP | FLOOR_PUSH_UP | 4 |

설정 규칙:

- family 내부에서만 비교한다. 서로 다른 family의 rank를 비교하지 않는다.
- rank를 절대 난이도 점수나 여러 항목의 합산 점수로 해석하지 않는다.
- 동일 family에서 사실상 같은 난이도의 장비·자세 변형은 같은 rank를 가질 수 있으므로 unique constraint를 두지 않는다.
- `difficulty_code`는 전체 추천 난이도, `variant_difficulty_rank`는 family 내부 상대 난이도다.
- 지지면 안정성, 체중부하, ROM, 균형, 자세 제어를 참고하되 도메인 검수자가 순서를 확정한다.
- Recovery regression은 현재 운동보다 낮은 non-null rank만 후보로 사용한다. rank가 `NULL`이면 자동 regression에 사용하지 않는다.

권장 보조 컬럼:

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `variant_rank_review_status_code` | varchar(32) nullable | `REVIEW_REQUIRED`, `DOMAIN_APPROVED` |
| `variant_rank_policy_version` | varchar(64) nullable | 순위 정책 버전 |
| `variant_rank_reviewed_at` | timestamptz nullable | 검수 시각 |
| `variant_rank_reviewer_code` | varchar(64) nullable | 검수자 코드 |

### 7.3 정식 `load_regions`

배열 컬럼보다 `exercise_load_regions` 관계 테이블을 사용한다.

| 컬럼 | 타입 | 규칙 |
|---|---|---|
| `exercise_id` | UUID | exercises FK |
| `body_area_code` | varchar(64) | body_areas FK |
| `load_role_code` | varchar(32) | 아래 코드 |
| `review_status_code` | varchar(32) | production은 `DOMAIN_APPROVED`만 |
| `policy_version` | varchar(64) | load-region 정책 버전 |
| `evidence_source_code` | varchar(120) | 검수 근거 |
| `reviewer_code` | varchar(64) | 검수자 코드 |
| `reviewed_at` | timestamptz | 검수 시각 |

PK 또는 unique key는 `(exercise_id, body_area_code, load_role_code)`다.

`load_role_code`:

```text
DIRECT_LOAD
JOINT_MOTION
STRETCH_REQUIRED
STABILIZATION_LOAD
```

포함 기준:

- 운동 중 직접 체중·외부저항을 받는 부위
- 해당 관절 움직임이 동작 수행에 필요한 부위
- 스트레칭에서 의도적으로 신장되는 부위
- 자세 유지에 실질적인 부하가 필요한 부위

`primary_body_area_codes`와 `secondary_body_area_codes`를 기계적으로 복사하지 않는다. 기존 부위 정보는 검수 후보를 만드는 참고값일 뿐이다.

### 7.4 `contraindicated_pain_regions`

`exercise_contraindicated_pain_regions` 관계 테이블을 사용한다.

운동 자체의 Safety 검수 완료 여부는 `exercises.safety_review_status_code`로 별도 관리한다.

| 값 | 의미 | production 추천 |
|---|---|---|
| `UNREVIEWED` | 금기 부위 검수 전 | 불가 |
| `REVIEW_REQUIRED` | 재검수 필요 | 불가 |
| `DOMAIN_APPROVED` | 현재 policy version의 검수 완료 | 가능 |

`DOMAIN_APPROVED`인데 관계 row가 0개인 경우만 **검수했으나 별도 금기 부위 없음**을 의미한다. `UNREVIEWED` 또는 `REVIEW_REQUIRED`의 row 0개는 정보가 없는 상태이며, 빈 목록으로 간주하지 않고 fail-closed로 제외한다.

| 컬럼 | 타입 | 규칙 |
|---|---|---|
| `exercise_id` | UUID | exercises FK |
| `body_area_code` | varchar(64) | body_areas FK |
| `effect_code` | varchar(16) | 현재 `EXCLUDE` 고정 |
| `review_status_code` | varchar(32) | production은 `DOMAIN_APPROVED`만 |
| `policy_version` | varchar(64) | contraindication 정책 버전 |
| `reason_code` | varchar(64) | 내부 구조화 이유 |
| `evidence_source_code` | varchar(120) | 직접·간접·제품 검수 근거 |
| `reviewer_code` | varchar(64) | 도메인 검수자 |
| `reviewed_at` | timestamptz | 검수 시각 |

PK 또는 unique key는 `(exercise_id, body_area_code, policy_version)`다.

설정 규칙:

- 현재 통증이 해당 부위에 1 이상 있으면 그 운동을 Safety-approved Pool에서 제외한다.
- NRS 구간은 이 테이블이 아니라 전역 Safety Policy가 해석한다.
- `load_regions`에 존재한다고 자동으로 contraindicated로 설정하지 않는다.
- `load_regions`에 없지만 자세, 압박, 균형 또는 신장 때문에 통증 시 부적절한 부위는 검수 후 추가할 수 있다.
- 스트레칭도 같은 모델을 사용한다.
- `caution_pain_regions`와 `impact_level`은 소비 규칙이 없으므로 신규 계약에 포함하지 않는다.
- Alternative 운동도 독립 exercise row이므로 동일 테이블로 다시 검사한다.

production 전에 최종 추천 가능 운동의 `DOMAIN_APPROVED` coverage를 100%로 만든다. coverage report는 최소 `pain_region × exercise_type`, `pain_region × movement_pattern`을 보여주고 Strength·Cardio·Stretching을 모두 포함한다.

권장 `reason_code`:

```text
DIRECT_LOAD_ON_PAIN_REGION
REQUIRED_JOINT_MOTION
REQUIRED_STRETCH_OF_PAIN_REGION
STABILIZATION_DEMAND
POSITIONAL_PRESSURE
DOMAIN_REVIEWED_OTHER
```

### 7.5 production용 `met_value`

`exercises`에 단일 float만 추가하지 않고 값과 provenance를 함께 저장한다.

| 컬럼 | 타입 | 규칙 |
|---|---|---|
| `met_value` | numeric(5,2) nullable | `> 0`, 검수 완료 전 `NULL` |
| `met_source_code` | varchar(64) nullable | 예: `ADULT_COMPENDIUM_2024` |
| `met_source_activity_code` | varchar(32) nullable | 원자료 activity code |
| `met_mapping_method_code` | varchar(32) nullable | 아래 코드 |
| `met_review_status_code` | varchar(32) nullable | `REVIEW_REQUIRED`, `DOMAIN_APPROVED` |
| `met_policy_version` | varchar(64) nullable | 매핑 정책 버전 |
| `met_reviewed_at` | timestamptz nullable | 검수 시각 |
| `met_reviewer_code` | varchar(64) nullable | 검수자 코드 |

`met_mapping_method_code`:

```text
EXACT_ACTIVITY_MATCH
CATEGORY_REPRESENTATIVE
INTENSITY_ADJUSTED_CATEGORY
DOMAIN_REVIEWED_ESTIMATE
```

production 사용 조건:

- `met_value IS NOT NULL`
- `met_review_status_code = DOMAIN_APPROVED`
- `met_source_code`, `met_mapping_method_code`, `met_policy_version` 모두 존재
- FITT intensity와 MET 강도 수준이 명백히 모순되지 않음

예상 kcal 공식:

```text
estimated_kcal = met_value × 3.5 × weight_kg ÷ 200 × actual_duration_minutes
```

실제 수행시간이 아직 없으면 계획의 expected duration으로 사전 추정하고, 세션 종료 후 actual duration으로 다시 계산한다. 체중 또는 승인 MET가 없으면 `null`을 반환한다. 반올림은 표시 계층에서 수행하고 canonical 계산값은 충분한 정밀도로 저장한다.

### 7.6 HOME 장비 및 설명 범위

HOME 후보는 현재 카탈로그의 장비값을 그대로 사용한다. HOME에서 허용하는 장비는 `DUMBBELL`, `FOAM_ROLLER`, `MAT`, `BAND`, `BODYWEIGHT`, `HOUSEHOLD_WEIGHT`다. 생활용품 또는 맨몸 수행에 관한 안내는 운동 상세의 부가 설명으로만 제공하며, 이 정책 문서에서 별도의 HOME 대체 관계·필터·추가 스키마를 정의하지 않는다.

운동 자세·준비물 설명은 사용자가 이해할 수 있는 문장으로 제공하고, 내부 머신 코드를 사용자에게 노출하지 않는다. 구체적인 카탈로그 필드와 설명 콘텐츠 검수는 현재 카탈로그 계약을 따른다.

### 7.8 현재 데모의 개발용어 노출 원인과 수정 기준

현재 데모에서 일부 자세 문구에 `SUPPORTED_SEATED_KNEES_NEUTRAL_UNWEIGHTED`, `BACKREST_AND_LOWER_LEG_SUPPORT`, `KNEE`, `REVIEWED_NO_LOAD_POSTURE` 같은 개발용어가 보일 수 있다.

확인된 원인은 다음과 같다.

1. 통증 안전 Variant 데이터의 `form_cues_ko` 자체에 구조화된 posture/support/body-area 코드가 한국어 문장 안에 포함되어 있다.
2. 일부 문구는 `safe-variant-cue-template-v1` 템플릿으로 생성되었으며 `form_cues_review_status=REVIEW_REQUIRED` 상태다.
3. Backend 운동 상세 API는 카탈로그의 `instruction_summary_ko`와 `form_cues_ko`를 별도 사용자 문구 변환 없이 그대로 반환한다.
4. Frontend 운동 상세 화면은 반환된 `form_cues`를 그대로 렌더링한다.
5. 일반 label mapping은 알 수 없는 코드를 `확인되지 않은 항목`으로 숨기지만, 문장 내부에 삽입된 코드는 label lookup 경계를 통과하지 않으므로 변환되지 않는다.

따라서 프론트에서 문자열 치환표를 계속 늘리는 방식으로 해결하지 않는다. 자세 콘텐츠 생성·검수 단계에서 내부 구조와 사용자 문구를 분리한다.

권장 원천 구조:

`exercise_instruction_steps`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | UUID | PK |
| `exercise_id` | UUID | exercises FK |
| `step_order` | smallint | 1부터 연속 순서 |
| `step_type_code` | varchar(32) | 아래 코드 |
| `instruction_ko` | text | 내부 코드가 없는 완성된 사용자 문장 |
| `posture_code` | varchar(120) nullable | 내부 검수·생성 참고값 |
| `support_code` | varchar(120) nullable | 내부 검수·생성 참고값 |
| `body_area_code` | varchar(64) nullable | 내부 검수용 부위 |
| `review_status_code` | varchar(32) | production은 `DOMAIN_APPROVED` |
| `content_version` | varchar(64) | 설명 콘텐츠 버전 |
| `reviewer_code` | varchar(64) | 검수자 |
| `reviewed_at` | timestamptz | 검수 시각 |

`step_type_code`:

```text
PREPARATION
START_POSITION
MOVEMENT
BREATHING
FORM_CAUTION
STOP_CONDITION
```

예시 변환:

```text
내부 posture_code:
SUPPORTED_SEATED_KNEES_NEUTRAL_UNWEIGHTED

사용자 instruction_ko:
등받이가 있는 안정적인 의자에 앉아 두 발을 바닥에 편하게 둡니다.

내부 support_code:
BACKREST_AND_LOWER_LEG_SUPPORT

사용자 instruction_ko:
운동이 끝날 때까지 등을 등받이에 기대고 두 발로 몸을 안정적으로 지지합니다.
```

production 콘텐츠 검증 규칙:

- `instruction_ko`, `setup_instructions`, `movement_steps`, `form_cues`에 대문자 snake case 토큰이 남아 있으면 import 또는 promotion을 실패시킨다.
- `REVIEW_REQUIRED` 자세 문구는 production 운동 상세 API에서 노출하지 않는다.
- 설명이 없거나 미검수인 운동은 HOME 추천 후보와 사용자 카탈로그에서 fail-closed로 제외한다.
- body-area와 장비 코드는 구조화 필드에서 label table로 변환하고 완성 문장에 직접 삽입하지 않는다.
- backend는 사용자 설명과 내부 검수 코드를 서로 다른 응답 필드로 제공하며 public API에는 내부 posture/support code를 기본 노출하지 않는다.
- frontend는 `instruction_summary`, `setup_instructions`, `movement_steps`, `form_cues`, `stop_conditions`만 표시한다.
- 접근성 label에도 머신 코드를 포함하지 않는다.

기존 데이터 전환 절차:

1. 전체 `form_cues_ko`에서 대문자 snake case 토큰을 탐지한다.
2. 토큰을 posture/support/body-area 구조 필드로 분리한다.
3. 검수 가능한 한국어 동작 단계로 다시 작성한다.
4. 도메인 검수 후 `DOMAIN_APPROVED`로 승격한다.
5. importer에 머신 코드 노출 방지 검증을 추가한다.
6. API fixture와 데모 preview의 임시 공통 문구를 실제 승인 카탈로그 설명으로 교체한다.
7. 텍스트만으로 운동을 수행할 수 있는지 수동 QA한다.

---

## 8. Recovery 정책과 저장 위치

### 8.1 수면·피로 조합

Recovery는 점수를 합산하지 않고 수면과 피로의 조합으로 결정한다. 피로는 선택형 코드이며, 근육통은 Recovery 입력으로 받거나 계산에 사용하지 않는다.

| 수면 \ 피로 | 가벼워요 (`LOW`) | 보통이에요 (`MODERATE`) | 피곤해요 (`HIGH`) |
|---|---|---|---|
| 7시간 이상 | `NORMAL` | `NORMAL` | `LIGHT` |
| 6시간 이상 7시간 미만 | `NORMAL` | `LIGHT` | `VERY_LIGHT` |
| 6시간 미만 | `LIGHT` | `VERY_LIGHT` | `VERY_LIGHT` |
| 미입력 | `NORMAL` | `LIGHT` | `VERY_LIGHT` |

`sleep_minutes=null`은 수면이 입력되지 않은 행을 뜻하며, 필수 `fatigue_level_code`와 위 표를 사용한다.

### 8.2 결정 기록 필드

Recovery 파생값은 `daily_contexts`의 사용자 원본 입력을 덮어쓰지 않고 결정 snapshot 또는 typed decision table에 저장한다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `recovery_level_code` | varchar(16) | `NORMAL`, `LIGHT`, `VERY_LIGHT`, `NEEDS_INPUT` |
| `recovery_policy_version` | varchar(64) | 수면·피로 조합 정책 버전 |
| `pain_load_cap_code` | varchar(16) nullable | `LIGHT` 등 통증 상한 |
| `effective_load_cap_code` | varchar(16) | Recovery와 Pain 중 더 보수적인 값 |

### 8.3 FITT downshift

Strength:

- NORMAL: 기본 FITT, 예 `3 × 8–12`
- LIGHT: 세트 한 단계 감소 후 rep range 하단, 예 `2 × 8–10`
- VERY_LIGHT: `1–2 × 8–10`, 필요 시 낮은 variant rank
- 적용 순서: 세트 감소 → rep 하단 → 쉬운 Variant

Stretching:

- NORMAL: 기본
- LIGHT: 대부분 유지
- VERY_LIGHT: 전체 시간 구성상 필요한 경우 개수 또는 시간을 소폭 감소
- 통증 부위 스트레칭은 이미 Safety에서 제거

Recovery와 Pain cap은 서로 값을 변경하지 않는다. Coordinator와 최종 validator는 더 보수적인 상한을 적용한다.

---

## 9. Training 및 Feasibility

### 9.1 목표별 우선순위 코드

```text
VERY_HIGH
HIGH
SUPPORT
```

| 목표 | STRENGTH | CARDIO | MOBILITY/STRETCHING |
|---|---|---|---|
| `FAT_LOSS` | HIGH | HIGH | SUPPORT |
| `MUSCLE_GAIN` | VERY_HIGH | SUPPORT | SUPPORT |
| `GENERAL_FITNESS` | HIGH | HIGH | SUPPORT |

정확한 50:50 또는 60:40 비율은 사용하지 않는다.

### 9.2 경험 수준

- BEGINNER: `difficulty_code=BEGINNER`, Beginner FITT
- INTERMEDIATE: BEGINNER와 INTERMEDIATE 후보, Intermediate FITT
- Recovery가 나쁘더라도 사용자 `experience_level_code`를 변경하지 않는다.
- 필요 시 volume downshift와 낮은 `variant_difficulty_rank`를 적용한다.

### 9.3 시간과 장소

- `available_time_minutes`: 10–60
- 장소: Hard Constraint
- FeasibilityAgent는 후보가 없으면 운동 수·세트 및 soft preference를 조정할 수 있다.
- 장소와 Safety는 완화할 수 없다.
- 그래도 후보가 없으면 계획을 생성하지 않고 구조화된 failure reason을 반환한다.

권장 실패 코드:

```text
SAFETY_POOL_EMPTY
LOCATION_POOL_EMPTY
DURATION_CONSTRAINT_UNSATISFIED
APPROVED_CANDIDATE_POOL_EMPTY
```

---

## 10. Variant와 Alternative

Variant는 같은 `family_code` 안의 상대 수행 방식이다. `variant_difficulty_rank`는 family 내부 순서만 표현한다.

Alternative는 서로 독립된 운동 간의 카탈로그 관계다. 통증을 근거로 한 운동 교체·추천은 폐지됐으며, SafetyPolicyEngine·Training·Feasibility·운동 실행은 `DISCOMFORT` 관계를 소비하지 않는다.

`exercise_alternatives`

| 컬럼 | 설명 |
|---|---|
| `source_exercise_id` | 원 운동 |
| `alternative_exercise_id` | 대체 운동 |
| `reason_code` | `DIFFICULTY`, `EQUIPMENT`, `LOCATION`, `DISCOMFORT`(레거시·비소비) |
| `priority` | 동일 조건 후보의 검수 우선순위 |
| `condition_code` | 적용 조건 |
| `pain_region_code` | 레거시 `DISCOMFORT` 관계의 부위. 신규 정책에서 소비 금지 |
| `review_status_code` | production은 `DOMAIN_APPROVED` |
| `policy_version` | 관계 정책 버전 |

`priority`는 `smallint >= 1`로 추가한다. `DISCOMFORT`가 아닌 소비 대상 관계에서만 같은 source·reason·condition 안의 낮은 숫자를 먼저 고려할 수 있다. 통증 Safety는 대체 관계를 조회하지 않고 `contraindicated` 규칙으로 Safety-approved Pool을 필터링한다.

Safety Pool이 0이라고 Alternative로 승인 범위 밖의 운동을 생성하지 않는다. Alternative 운동도 통합 카탈로그의 독립 row이며 현재 active pain 전체로 다시 Safety 검사한다.

---

## 11. 운동 중 Safety Event

운동 실행 화면의 별도 `불편·통증 보고` 또는 `통증이 있어요` 버튼은 제거하고, 통증·이상 반응도 상단 `중단` 흐름에서 처리한다. 사용자가 중단 사유로 `통증·이상 반응이 있어요`를 선택하면 증상 종류·통증 부위·NRS를 입력받지 않고 안내와 확인을 거쳐 현재 당일 루틴 전체를 종료한다.

### 11.1 `통증·이상 반응이 있어요`

- 통증 발생 시 현재 운동만이 아니라 해당 세션 전체를 중단한다.
- 남은 운동을 계속하거나 Skip 후 재개하지 않는다.
- 대체 운동과 Alternative를 추천하지 않는다.
- 통증 부위, NRS, 증상 유형은 수집하지 않는다.
- 구현상 문제가 없으면 사유를 선택한 시점의 `plan_item_id`를 시스템이 자동 기록해 주간 리포트에서 `어떤 운동 수행 중 안전 중단이 발생했는지`만 확인할 수 있게 한다. 사용자의 증상을 추정하거나 통증 부위를 유추하지 않는다.
- 원인을 진단하지 않고, 통증이 지속되거나 심해지면 전문가의 도움을 받으라는 중립적 안내를 제공한다.

권장 저장 구조:

`workout_safety_events`에는 `plan_item_id`, `result_code`, `occurred_at`, `rule_version`만 저장한다. `event_type_code`, 통증 부위, NRS, 자유서술 증상, `replacement_plan_item_id`는 운동 중 Safety Event 계약에서 사용하지 않는다.

결과 코드:

```text
SESSION_STOPPED
STOP_AND_SEEK_HELP
```

### 11.2 통합 중단 안내

`PARTIAL` 또는 `NOT_COMPLETED` 수행 상태와 별개로 Safety Event를 남긴다. 통증·이상 반응을 구분하지 않고 당일 루틴을 종료하며, 당일 이어하기·Alternative·대체 운동을 제공하지 않는다. 사유 항목에는 `이 사유로 중단하면 오늘 운동을 다시 이어 할 수 없습니다`를 명확히 노출한다. `?` 도움말에서는 어지러움, 메스꺼움, 평소와 다른 심한 호흡 곤란, 가슴 통증·압박감 등의 예시와 일반적인 운동 후 근육통은 이 안전 관련 이상 반응과 다르다는 점을 안내한다. 진단·치료를 암시하지 않으며, 증상이 지속되거나 심하면 의료기관의 도움을 받고 응급한 경우 119 등 응급의료 서비스를 이용하라는 중립적 문구를 사용한다.

---

## 12. 운동 진행·휴식·일시정지·중단·수행 상태

### 12.1 예상시간

계획에 다음 값을 저장한다.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `expected_duration_min_seconds` | integer | 보수적인 예상 최소시간 |
| `expected_duration_max_seconds` | integer | 예상 최대시간 |
| `duration_estimation_policy_version` | varchar(64) | 산출 규칙 버전 |

세트, 반복, rep당 시간, 휴식, 전환, timed cardio와 stretching을 합산한다. `min <= max`, 두 값 모두 양수여야 한다.

### 12.2 수행 상태 판정

공식 수행 상태는 중단 사유, 경과시간, 웨어러블이 아니라 **해당 지역 날짜의 최종 완료 블록 개수**로 판정한다.

```text
COMPLETED
PARTIAL
NOT_COMPLETED
```

| 상태 | 판정 기준 |
|---|---|
| `COMPLETED` | 모든 운동 블록 격파 완료 |
| `PARTIAL` | 1개 이상 블록을 완료했으나 당일 루틴 전체는 미완료 |
| `NOT_COMPLETED` | 완료한 블록 없이 당일 루틴 종료 |

- `STOPPED_FOR_SAFETY`를 공식 수행 상태로 사용하지 않고 Safety Event·중단 사유로 별도 저장한다.
- 통증·이상 반응 사유로 중단해도 완료 블록이 1개 이상이면 `PARTIAL`, 0개면 `NOT_COMPLETED`다.
- 일반 사유 중단 후 당일 이어하기로 모든 블록을 완료하면 `COMPLETED`로 갱신한다.
- 완료한 개별 블록은 `PARTIAL`이어도 actual exercise history에 반영한다.

화면 실행 상태는 위 공식 수행 상태와 별도로 다음과 같이 관리한다.

| 실행 상태 | 의미 |
|---|---|
| `RUNNING` | 정상 운동 진행 |
| `RESTING` | 휴식 중이며 전체 운동 타이머는 계속 진행 |
| `PAUSED` | 운동 진행을 잠시 멈추며 전체 운동 타이머와 휴식 타이머 모두 정지 |
| `STOPPED_RESUMABLE` | 일반 사유 중단으로 당일 이어하기 가능 |
| `STOPPED_SAFETY` | 통증·이상 반응 중단으로 당일 이어하기 불가 |
| `COMPLETED` | 모든 운동 블록을 정상 완료 |

실행 상태의 `COMPLETED`는 공식 수행 상태의 `COMPLETED`와 같은 완료 사건을 가리키지만, 나머지 실행 상태는 공식 수행 상태를 대체하지 않는다. 중단된 루틴의 공식 수행 상태는 최종 완료 블록 개수에 따라 `PARTIAL` 또는 `NOT_COMPLETED`로 판정한다.

### 12.3 중단·이어하기

- 운동 실행 화면 상단에 `중단` 버튼을 제공한다.
- `중단`을 누르면 별도 확인 팝업 없이 `오늘 운동을 마치지 못한 이유` 선택 화면으로 바로 이동한다. 잘못 진입한 사용자를 위해 `취소/돌아가기`를 제공하며, 돌아가면 직전 실행 상태와 타이머를 복원한다.
- 사유 선택 후 확인 단계에서 중단 사유와 현재 진행 상태를 먼저 저장한다. 이후 공통 피드백 입력을 별도 저장해, 피드백 화면을 이탈하더라도 중단 기록이 남게 한다.
- `시간 부족`, `피로`, `나중에 이어서`는 현재까지 완료한 블록·현재 블록·타이머 누적값을 저장하고 `STOPPED_RESUMABLE`로 전이한다.
- 공통 피드백 입력 후 홈으로 이동하며, `STOPPED_RESUMABLE`인 경우 홈에서 `이어하기`를 제공한다.
- 사용자의 IANA timezone 기준 동일 `local_date` 23:59 이전에 이어하기를 시작해야 한다.
- 23:59 이전에 이어하기를 시작하지 않았다면 최종 완료 블록 개수에 따라 `PARTIAL` 또는 `NOT_COMPLETED`로 마감한다. 23:59 이전에 이미 재개한 active session의 자정 이후 마감 처리는 주간 리포트 날짜 경계와 함께 구현 계약으로 확정한다.
- `통증·이상 반응`은 확인 전에 이어하기 불가 안내를 노출하고, 확인 시 Safety Event와 중단 사유를 저장한 뒤 `STOPPED_SAFETY`로 전이하여 당일 이어하기를 차단한다.

최종 흐름:

```text
운동 진행 → 중단 → 중단 사유 선택 → 확인 → 피드백 입력 → 홈
```

중단 사유 코드:

```text
HIGH_FATIGUE
TIME_SHORTAGE
RESUME_LATER
PAIN_OR_ABNORMAL_RESPONSE
```

`PAIN_OR_ABNORMAL_RESPONSE`는 Safety Event 흐름으로 전환하고 당일 이어하기를 차단한다. 사용자가 `잠시 중단` 또는 `완전히 중단`을 직접 선택하게 하지 않으며, 서버가 사유 코드로 이어하기 가능 여부를 결정한다.

사유와 관계없이 공통 피드백 입력 화면을 제공한다. `통증·이상 반응이 있어요`만 당일 이어하기 불가 항목이므로 다른 사유와 구분되는 색상·경고 스타일을 사용한다.

### 12.4 운동 실행 화면

- 상단에 `중단` 버튼을 제공한다.
- 하단 핵심 액션은 `블록 격파`, 보조 액션은 `휴식`과 `일시정지`로 명확히 구분한다.
- 세 액션은 하단 스크롤 영역에 묻히지 않도록 고정하거나 항상 접근 가능한 위치에 둔다.
- 별도 `통증이 있어요` 또는 `불편·통증 보고` 버튼은 노출하지 않는다.
- 타이머는 현재 누적 진행 시간과 사용자가 설정한 총 목표 운동 시간을 `12:30 / 30분`과 같은 형태로 함께 표시한다.
- 휴식 버튼을 누르면 휴식 타이머는 0초에서 시작해 올라간다.
- `RESTING`에서는 휴식 타이머와 전체 운동 타이머가 모두 계속 흐른다.
- `PAUSED`에서는 전체 운동 타이머와 휴식 타이머가 모두 정지하며, 재개하면 일시정지 직전 상태(`RUNNING` 또는 `RESTING`)에서 이어진다.

### 12.5 기본 저장 정보와 시간 정의

| 필드 | 의미 |
|---|---|
| `target_duration_seconds` | 사용자가 설정한 총 목표 운동 시간 |
| `accumulated_progress_seconds` | 일시정지 시간을 제외하고 운동 세션에서 흐른 누적 시간; 휴식 포함 |
| `accumulated_rest_seconds` | `RESTING` 상태의 누적 시간 |
| `accumulated_paused_seconds` | `PAUSED` 상태의 누적 시간 |
| `execution_state_code` | 현재 화면 실행 상태 |
| `stop_reason_code` | 중단 사유 코드; 중단 전에는 `null` |
| `is_resumable` | 당일 이어하기 허용 여부 |
| `last_state_changed_at` | 마지막 실행 상태 변경 시각; timezone 포함 ISO 8601 |

이어하기 가능 상태에는 완료 블록, 현재 `plan_item_id`와 블록 내 진행 위치도 함께 저장한다. 타이머 누적값은 상태 전이 시 서버 기준 시각으로 확정하고, 재시도 가능한 mutation에는 idempotency를 적용한다.

---

## 13. 운동 후 피드백과 미수행 이유

### 13.1 운동 강도

```text
EASY
APPROPRIATE
HARD
```

- EASY 1회: 기록
- 유사 운동에서 2–3회 반복: progression 검토
- APPROPRIATE: 유지
- HARD 1회: 기록
- 유사 운동에서 2–3회 반복: volume 감소 또는 낮은 variant rank 검토

반복 판단은 `family_code` 또는 명시된 유사운동 relation 단위로 수행한다. 단순 운동명 비교를 사용하지 않는다.

### 13.2 중단 이유 코드

```text
HIGH_FATIGUE
TIME_SHORTAGE
RESUME_LATER
PAIN_OR_ABNORMAL_RESPONSE
```

`HIGH_FATIGUE`, `TIME_SHORTAGE`, `RESUME_LATER`는 `STOPPED_RESUMABLE`로 저장하고 당일 이어하기를 허용한다. `PAIN_OR_ABNORMAL_RESPONSE`는 Safety Event와 함께 `STOPPED_SAFETY`로 저장하고 당일 이어하기를 허용하지 않는다. 증상 유형, 통증 부위, NRS, 자유서술은 받지 않는다.

### 13.3 미수행 이유별 후속 활용

| reason code | 사용자 표시 | 저장·후속 활용 |
|---|---|---|
| `HIGH_FATIGUE` | 피로가 컸어요 | 현재 진행 상태를 저장하고 당일 이어하기 제공; 다음 운동은 새 Recovery 입력으로 판단 |
| `TIME_SHORTAGE` | 시간이 부족해요 | 현재 진행 상태를 저장하고 당일 이어하기 제공; 반복되면 루틴 시간·주간 목표 현실화 제안에 활용 |
| `RESUME_LATER` | 나중에 이어서 할게요 | 완료 블록과 현재 위치를 저장하고 당일 이어하기 제공 |
| `PAIN_OR_ABNORMAL_RESPONSE` | 통증·이상 반응이 있어요 | Safety Event로 당일 루틴 종료, 당일 이어하기 차단 |

공통 규칙:

- 미수행은 벌점으로 사용하지 않는다.
- 한 번의 미수행만으로 주간 목표 또는 다음날 강도를 자동으로 낮추지 않는다.
- PARTIAL에서는 완료한 운동 블록을 actual exercise history에 반영한다.
- 중단 사유는 수행 상태를 결정하지 않으며 최종 완료 블록 개수가 상태의 SoT다.
- 이유 코드는 Safety 판단을 대신하지 않는다. 다음날 Safety와 Recovery는 새 Check-in으로 판정한다.
- 모든 중단 사유에서 공통 피드백 입력을 제공한다. 중단 사유·진행 상태 저장과 피드백 저장은 독립적으로 성공할 수 있어야 한다.

---

## 14. 웨어러블 및 칼로리

### 14.1 원칙

- 웨어러블은 선택 입력이다.
- 웨어러블 없이 수동 체크인으로 전체 핵심 흐름이 동작해야 한다.
- 원시 샘플, GPS route, 직접 식별자와 provider 원문을 저장하거나 LLM에 전달하지 않는다.
- 웨어러블을 단독 Safety 근거로 사용하지 않는다.
- 활동량·걸음수 기반 루틴 조정은 소비 정책이 없으므로 MVP에서 제외한다.
- 앱 밖에서 수행한 외부 운동 기록은 MVP에서 가져오거나 공식 수행 이력에 합치지 않는다.
- MVP 웨어러블 소비 범위는 수면시간, 앱 운동 중 평균·최대 심박수, wearable active kcal로 제한한다.

수면 입력 우선순위:

1. 웨어러블이 연결되어 있고 해당 날짜의 유효한 수면시간이 있으면 `sleep_source_code=WEARABLE`로 그 값을 사용한다.
2. 웨어러블이 연결되지 않았거나 유효한 수면값이 없으면 사용자가 입력한 수동 수면시간을 `sleep_source_code=MANUAL`로 사용한다.
3. 두 값을 평균내거나 동시에 Recovery 판단에 사용하지 않는다.
4. 웨어러블과 수동값이 모두 없으면 `sleep_minutes=null`로 결측 처리한다.

### 14.2 normalized wearable summary

`wearable_daily_summaries`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | UUID | PK |
| `user_id` | UUID | users FK |
| `local_date` | date | 사용자 timezone 날짜 |
| `provider_code` | varchar(32) | 공급자 코드 |
| `sleep_duration_minutes` | smallint nullable | Recovery 참고값 |
| `source_recorded_at` | timestamptz nullable | source 시각 |
| `summary_version` | integer | 낙관적 버전 |
| `created_at`, `updated_at` | timestamptz | 저장 시각 |

`wearable_workout_summaries`

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | UUID | PK |
| `workout_session_id` | UUID | 앱 세션 FK |
| `provider_code` | varchar(32) | 공급자 |
| `avg_hr_bpm` | smallint nullable | 결과·리포트용 |
| `max_hr_bpm` | smallint nullable | 결과·리포트용 |
| `active_kcal` | numeric(8,2) nullable | provider 제공 활동 kcal |
| `started_at`, `ended_at` | timestamptz nullable | normalized 시간 |
| `created_at` | timestamptz | 저장 시각 |

### 14.3 칼로리 출처

```text
WEARABLE
MET_ESTIMATE
UNAVAILABLE
```

세션 결과 저장 필드:

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `estimated_calories_burned` | numeric(8,2) nullable | 표시할 단일 값 |
| `calorie_source_code` | varchar(16) | 출처 코드 |
| `calorie_policy_version` | varchar(64) | 선택·계산 정책 |
| `calorie_input_snapshot` | JSONB nullable | MET, 체중, 시간 등 최소 재현값 |

선택 순서:

1. wearable active kcal가 있으면 `WEARABLE`
2. 없고 체중·승인 MET·실제시간이 있으면 `MET_ESTIMATE`
3. 계산 불가하면 `UNAVAILABLE`과 `null`

두 값을 동시에 사용자에게 보여주지 않는다. UI 표현은 출처와 무관하게 `예상 소모 칼로리`다.

---

## 15. Weekly Plan과 실제 수행 이력

### 15.1 주간 목표

`weekly_target_sessions`는 당일 강도를 결정하지 않는다. 다음에만 사용한다.

1. 주간 계획 생성
2. 세션 간 운동·pattern coverage 배치
3. 목표 달성률
4. 주간 리포트

### 15.2 계획 구조

요일 고정보다 세션 순서와 coverage를 중심으로 한다.

```text
Session A
Session B
Session C
```

### 15.3 미수행 및 추가 수행

- 미수행 세션을 다음 운동에 몰아서 합치지 않는다.
- 실제 완료 exercise와 pattern을 SoT로 사용한다.
- 아직 수행하지 않은 중요한 목표·pattern을 우선해 남은 세션을 재정렬한다.
- 주가 끝나면 미수행 운동량을 다음 주로 자동 이월하지 않는다.
- 주간 목표는 상한이 아니며 추가 세션을 허용한다.
- 추가 세션 전 최근 완료 운동, pattern coverage, Safety와 Recovery를 확인한다.
- 동일 운동의 불필요한 반복 추가를 피한다.

권장 주간 세션 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `session_sequence` | smallint | A/B/C의 정렬 기준 |
| `coverage_pattern_codes` | child rows | 계획한 pattern |
| `source_code` | varchar(16) | `PLANNED`, `REORDERED`, `EXTRA` |
| `reorder_reason_codes` | child rows/JSONB | 재정렬 근거 |
| `weekly_plan_policy_version` | varchar(64) | 정책 버전 |

### 15.4 목표 현실화 제안

다음 중 하나를 만족한다.

- 2주 연속 목표 달성률 80% 미만
- 최근 4주 중 3주가 80% 미만

그리고 주요 원인이 다음 중 하나다.

```text
TIME_SCHEDULE
LOW_MOTIVATION
ROUTINE_BURDEN
```

그때 다음 주 목표를 낮출지 사용자에게 제안할 수 있다. 자동으로 낮추지 않는다. 한 주 실패만으로 제안하지 않는다.

제안 기록 필드:

| 필드 | 설명 |
|---|---|
| `trigger_code` | `TWO_CONSECUTIVE_BELOW_80`, `THREE_OF_FOUR_BELOW_80` |
| `dominant_reason_code` | 주요 이유 |
| `current_target_sessions` | 현재 목표 |
| `suggested_target_sessions` | 제안 목표 |
| `user_response_code` | `ACCEPTED`, `DECLINED`, `PENDING` |
| `policy_version` | trigger 정책 버전 |

---

## 16. 핵심 머신 코드 모음

### Eligibility

```text
ELIGIBLE
OUT_OF_SCOPE_AGE
OUT_OF_SCOPE_MEDICAL_MANAGEMENT
```

### Goal

```text
FAT_LOSS
MUSCLE_GAIN
GENERAL_FITNESS
```

### Experience

```text
BEGINNER
INTERMEDIATE
```

### Recovery

```text
NORMAL
LIGHT
VERY_LIGHT
NEEDS_INPUT
```

### Calorie source

```text
WEARABLE
MET_ESTIMATE
UNAVAILABLE
```

### Completion

```text
COMPLETED
PARTIAL
NOT_COMPLETED
```

`STOPPED_FOR_SAFETY`는 신규 공식 수행 상태가 아니라 기존 데이터 호환 코드로만 읽는다. 신규 write는 `PARTIAL` 또는 `NOT_COMPLETED`와 별도 Safety Event를 사용한다.

### Workout execution state

```text
RUNNING
RESTING
PAUSED
STOPPED_RESUMABLE
STOPPED_SAFETY
COMPLETED
```

### Workout stop reason

```text
TIME_SHORTAGE
HIGH_FATIGUE
RESUME_LATER
PAIN_OR_ABNORMAL_RESPONSE
```

### Perceived difficulty

```text
EASY
APPROPRIATE
HARD
```

### Catalog review

```text
REVIEW_REQUIRED
DOMAIN_APPROVED
REJECTED
DEPRECATED
```

---

## 17. 현재 구현 대비 적용 판단

### 17.1 이미 활용 가능한 기반

- V3 Constraint Envelope와 최종 Integrity Validator
- Safety veto와 fail-closed 동작
- 복수 불편 부위 구조
- MILD/MODERATE/SEVERE severity 코드
- family_code와 difficulty_code
- Alternative relation
- 장소 constraint
- 운동 블록별 완료 기록과 PARTIAL 이력
- 주간 리포트 완료율·미수행 이유 집계
- 운동 후 EASY/APPROPRIATE/HARD 피드백
- 건강정보 별도 동의 구조

### 17.2 신규 API·DB·프론트가 필요한 영역

- 온보딩 Eligibility와 지속 통증 입력, 기존 키·성별·기본 장소·시간 입력 제거; 생년월일은 암호화 저장·18–64세 Eligibility 전용으로 유지
- 피로 선택 코드(`LOW`/`MODERATE`/`HIGH`)와 온보딩 지속 통증 기본값
- 숫자 NRS 활성화
- 수면·피로 조합 Recovery와 FITT downshift
- `variant_difficulty_rank`
- `exercise_load_regions`
- `exercise_contraindicated_pain_regions`
- production MET와 calorie provenance
- 자세 문장에 포함된 개발용 posture/support/body-area 코드 제거 및 콘텐츠 재검수
- 웨어러블 normalized summary
- 상단 중단·사유 기반 당일 이어하기·Safety Event 이어하기 차단
- `RUNNING/RESTING/PAUSED/STOPPED_RESUMABLE/STOPPED_SAFETY/COMPLETED` 실행 상태와 상태별 타이머
- 목표·진행·휴식·일시정지 시간, 중단 사유, 이어하기 가능 여부와 마지막 상태 변경 시각 저장
- 완료 블록 기반 `COMPLETED/PARTIAL/NOT_COMPLETED` 판정과 휴식 포함 전체 진행시간
- actual pattern coverage 기반 주간 재정렬
- 반복 피드백 progression/regression
- 주간 목표 현실화 제안

### 17.3 호환 전략

- 기존 공개 필드는 한 번에 삭제하지 않고 additive 필드 도입 → 신규 write 전환 → 구버전 read 지원 → 후속 제거 순으로 진행한다.
- DB 컬럼 삭제는 write 중단과 배포 호환 기간 이후 별도 migration으로 수행한다.
- 기존 `PARTIAL`은 유지한다. `STOPPED_FOR_SAFETY`는 구버전 read 호환용으로만 유지하고 신규 write는 완료 블록 기반 상태 + Safety Event로 분리한다.
- 기존 severity 경로는 숫자 NRS가 완전히 활성화될 때까지 호환 입력으로 유지할 수 있으나 서버가 원점수를 추정하거나 backfill하면 안 된다.
- V3 production 전환 전에는 shadow 비교와 Safety invariant 100% 통과를 확인한다.

---

## 18. 권장 구현 순서

1. 정책·코드 집합·API 계약 확정
2. 카탈로그 핵심 Safety 필드와 개발용어 없는 자세 콘텐츠 검수
3. additive migration과 importer 검증
4. 온보딩 및 Daily Check-in API·DB 전환
5. SafetyPolicyEngine을 contraindicated relation 기반으로 전환
6. 수면·피로 조합 Recovery·Pain cap·FITT downshift 구현
7. Training/Feasibility 시간·장소 정책 구현
8. Coordinator compiler와 integrity validator 확장
9. 상단 중단·사유 기반 당일 이어하기·`통증·이상 반응` Safety 중단 흐름과 실행 상태·타이머 구현
10. MET·웨어러블·칼로리 출처 구현
11. 주간 재정렬·반복 피드백·목표 현실화 구현
12. 프론트 전체 상태 및 실패 사유 UI 반영
13. golden scenario, Safety invariant, fallback, migration, API 호환 테스트
14. V3 shadow 검증 후 production 전환 승인

---

## 19. 필수 테스트 시나리오

1. 정상 상태에서 목표·경험에 맞는 원 루틴이 생성된다.
2. NRS 1–3 통증 부위 contraindicated 운동은 모두 제외된다.
3. NRS 4–6은 해당 운동 제외와 LIGHT cap을 동시에 적용한다.
4. 복수 통증은 제외 합집합을 적용한다.
5. NRS 7 이상 또는 Red Flag는 계획을 생성하지 않는다.
6. Coordinator가 Safety 제외 운동을 복구하면 최종 validator가 거부한다.
7. Safety Pool이 0이면 Alternative로 안전조건을 우회하지 않는다.
8. 온보딩 지속 통증이 Daily Check-in 부위·NRS 기본값으로 표시되고, 당일 수정값만 Safety 입력으로 사용된다.
9. 운동 자세·접근성 문구에 대문자 snake case 또는 stable code가 노출되지 않는다.
10. GIF·이미지가 없어도 준비·시작 자세·동작·호흡·중단 조건을 이해할 수 있다.
11. `REVIEW_REQUIRED` 자세 콘텐츠는 production API에 노출되지 않는다.
12. 수면 결측은 피로와 조합표로 처리한다.
13. Recovery와 Pain cap 중 더 보수적인 상한이 적용된다.
14. wearable이 없어도 수동 입력으로 전체 흐름이 동작한다.
18. wearable kcal가 있으면 단일 WEARABLE 값만 표시한다.
19. wearable kcal가 없으면 승인 MET와 실제시간으로 계산한다.
20. 체중 또는 승인 MET가 없으면 kcal은 null이다.
21. 부분 수행의 완료 운동은 actual exercise history에 남는다.
22. 수행 상태는 시간·중단 사유가 아니라 최종 완료 블록 개수로만 판정된다.
23. 미수행 세션을 다음 운동에 몰아넣지 않는다.
24. 추가 세션은 최근 수행 pattern과 Safety·Recovery를 반영한다.
25. 한 주 미달만으로 주간 목표 하향을 제안하지 않는다.
26. LLM 실패 시 결정적 fallback 또는 계획 없음으로 종료한다.
27. `DOMAIN_APPROVED` 전의 운동과 Safety 필수 필드가 결측된 운동은 추천에서 제외된다.
28. `DOMAIN_APPROVED`이면서 금기 관계 row가 0개인 운동은 검수 완료·금기 없음으로 해석된다.
29. 운동 중 상단 `중단`을 누르면 확인 팝업 없이 사유 선택 화면으로 이동하고 `취소/돌아가기`로 기존 실행 상태를 복원할 수 있다.
30. Safety Event로 중단된 세션은 당일 이어하기, Skip 후 재개, Alternative 및 대체 운동을 제공하지 않는다.
31. 수면이 미입력이더라도 필수 `fatigue_level_code`와 Recovery 조합표로 level을 결정한다.
32. 최근 48시간 동일 pattern은 priority가 낮아지지만 Safety BLOCK으로 처리되지 않는다.
33. Progression은 정책 조건을 만족한 2회 연속 수행 후 주간 재계획에서 한 요소·한 단계만 올라간다.
34. 일반 중단 사유 확인 후 완료 블록, 현재 위치와 타이머 누적값이 저장되고, 23:59 이전 당일 이어하기가 가능하다.
35. 일반 중단 후 이어서 모든 블록을 완료하면 `COMPLETED`로 갱신된다.
36. 완료 블록이 1개 이상인 미완료 루틴은 `PARTIAL`, 0개인 미완료 루틴은 `NOT_COMPLETED`다.
37. 휴식 타이머는 0초에서 시작하고, 휴식 중에도 전체 운동 수행시간은 계속 증가한다.
38. 모든 중단 사유에서 공통 피드백 화면을 제공하고, 피드백을 완료하지 않아도 먼저 확정한 중단 사유와 진행 상태는 남는다.
39. `PAIN_OR_ABNORMAL_RESPONSE` 항목은 다른 사유와 색상으로 구분되고 `?`에서 예시·이어하기 불가를 안내한다.
40. Safety Event는 증상 유형·통증 부위·NRS를 수집하지 않고 현재 `plan_item_id`만 선택적으로 자동 기록한다.
41. 상단에는 `중단`, 하단에는 핵심 액션 `블록 격파`와 보조 액션 `휴식`, `일시정지`가 노출되고 별도 통증 버튼은 노출되지 않는다.
42. `RUNNING`에서 전체 타이머가 흐르고, `RESTING`에서 전체·휴식 타이머가 함께 흐르며, `PAUSED`에서는 두 타이머가 모두 멈춘다.
43. `PAUSED`를 재개하면 직전 `RUNNING` 또는 `RESTING` 상태와 타이머 누적값에서 이어진다.
44. 타이머에 현재 누적 진행 시간과 사용자의 총 목표 운동 시간이 함께 표시된다.
45. 사유 선택 후 시스템이 `STOPPED_RESUMABLE` 또는 `STOPPED_SAFETY`와 `is_resumable`을 결정하며 사용자가 중단 유형을 직접 고르지 않는다.

---

## 20. 출시 전 필수 보강 체크리스트

### 20.1 P0 — Safety 출시 차단 조건

1. **Safety 검수 coverage 100%**: 최종 추천 가능 운동은 모두 `safety_review_status_code=DOMAIN_APPROVED`여야 한다. 검수 완료 후 금기 부위가 없는 빈 관계 집합과 미검수 상태를 구분한다. `caution_pain_regions`는 소비 규칙이 없으므로 추가하지 않는다.
2. **Safety 결측 fail-closed**: 필수 Safety 필드가 `NULL`이거나 검수 상태가 승인 전이면 추천 후보에서 제외한다. 설명·썸네일 같은 비안전 metadata 결측은 별도 fallback을 허용한다.
3. **운동 중 통증·이상 반응 사유 선택 시 전체 중단**: 상단 `중단` 흐름에서 해당 사유를 선택하면 증상 세부정보를 받지 않고 안전 안내 후 현재 당일 루틴 전체를 종료한다. 당일 이어하기·Alternative·대체 운동을 제공하지 않는다.
4. **최종 deterministic validator**: compiled plan의 `exercise_ids` 전체가 Safety-approved Pool의 부분집합인지, 통증 금기·검수 상태·장소를 다시 검사한다. 위반 시 plan을 거부하고 승인된 bounded repair 또는 deterministic fallback을 실행한 후 재검사한다. LLM은 Safety veto를 복구할 수 없다.
5. **fallback 테스트**: 아래 20.4의 장애·결측 경로를 출시 전 자동화한다.
6. **Red Flag UI·문구 검수**: 진단성 표현을 쓰지 않고 운동 중단·지속 또는 심한 증상의 의료기관 이용·응급상황의 119 안내만 제공한다. 운동 도메인과 UX 검수를 모두 받는다.

Red Flag 권장 문구:

> 오늘은 운동 루틴 생성을 중단할게요. 가슴 통증, 심한 어지럼이나 실신 느낌, 평소와 다른 심한 호흡곤란, 갑작스런 마비나 심한 힘 빠짐이 있다면 운동을 중단해 주세요. 증상이 지속되거나 심하면 의료기관의 도움을 받아 주세요. 응급한 증상이면 119 등 응급의료 서비스를 이용해 주세요.

### 20.2 P1 — 추천 품질 출시 권장 조건

1. **최근 이력 과부하 방지**: 최근 48시간 내 같은 major muscle 또는 `movement_pattern` 수행은 Safety BLOCK이 아니라 Training priority penalty로 처리한다. 최근 고볼륨 + Recovery `LIGHT/VERY_LIGHT` + 같은 부위이면 다른 pattern을 적극 우선한다. 가벼운 Cardio와 Stretching에는 동일 penalty를 기계적으로 적용하지 않는다.
2. **Progression 상한·주기**: 유사 루틴 2회 연속 정상 완료, `APPROPRIATE` 또는 `EASY`, 새 통증 없음을 모두 만족할 때만 progression eligible로 한다. 주간 재계획 1회에 한 요소·한 단계만 바꾸며 순서는 반복수 → 세트 → 높은 `variant_difficulty_rank`다. 반복·세트·variant를 동시에 올리지 않는다.

### 20.3 Safety invariant

> 검수된 안전 데이터가 없는 운동은 후보가 될 수 없고, Safety가 한 번 제외한 운동은 어떤 Agent나 LLM도 복구할 수 없으며, 운동 중 `통증·이상 반응이 있어요`가 중단 사유로 선택되면 세부 증상을 수집하지 않고 해당 당일 루틴을 종료하며 당일 이어하기·대체 운동을 제공하지 않는다.

### 20.4 필수 fallback 표

| 상황 | 결과 |
|---|---|
| Safety Pool 0 | 조건 완화 없이 루틴 생성 중단 |
| Safety metadata 결측·미검수 | 해당 운동 제외 |
| LLM timeout | deterministic/template fallback |
| LLM schema 오류 | validator 거부 후 fallback |
| wearable 미연동 | 수동 체크인 |
| wearable sleep 결측 | 수동 수면값 |
| 수면 미입력 | 피로와 Recovery 조합표의 `미입력` 행 사용 |
| 운동 중 통증·이상 반응 사유 선택 | 세부 증상 입력 없이 안전 안내 후 당일 루틴 종료; 당일 이어하기·Alternative·대체 운동 없음 |
| Feasibility 후보 0 | soft 선호·운동 수·세트를 조정하되 hard constraint를 유지; 그래도 0이면 생성 중단 |
| Coordinator가 BLOCK 운동 반환 | 최종 validator 거부 후 승인 fallback·재검증 |

---

## 21. 개인정보·보안 영향

- 상세 병력·질환명·임신 이력·과거 부상 이력을 수집하지 않는다.
- 지속 통증·당일 통증·수면·피로·웨어러블 요약은 민감정보로 취급한다.
- 원시 웨어러블 샘플, GPS, 이메일, 이름, 인증 토큰을 LLM 또는 결정 snapshot에 전달하지 않는다.
- LLM에는 최소 normalized 값과 승인 후보만 전달한다.
- 로그에는 raw check-in, active pain snapshot, 웨어러블 원문을 기록하지 않는다.
- 정책·카탈로그·Safety rule·Recovery·완료 판정 버전을 저장해 결정을 재현한다.
- `OTHER` 자유서술은 불필요한 건강정보 수집 위험이 있으므로 기본적으로 저장하지 않는다.

---

## 22. 팀 검토 시 확인할 정책

아래 항목도 본 초안에서 제외하지 않고 해당 절의 정책대로 우선 기재했다. 팀 검토에서는 구현 전에 수치·충돌 처리만 최종 확인한다.

1. 수면 결측은 0점으로 간주하지 않고 `null`과 `recovery_missing_input_codes=["SLEEP"]`로 보존한다. 결측일의 최종 Recovery level 계산 방식만 확정한다.
2. 온보딩 지속 통증은 Daily Check-in 기본값으로만 사용하고 당일 사용자의 수정값이 Safety 입력이 되는지 확인한다.
3. 수행 상태는 시간이 아니라 당일 최종 완료 블록 개수로 `COMPLETED/PARTIAL/NOT_COMPLETED`를 판정한다.
4. 쉬움·힘듦은 1회 기록, 같은·유사 family에서 2–3회 반복되면 progression 또는 regression을 고려한다.
5. 운동 실행 화면은 상단 `중단`, 하단 `블록 격파/휴식/일시정지`로 구성하고, 중단 사유가 당일 이어하기 가능 여부를 결정한다.

---

## 23. 출처 및 내부 근거

### 연구근거·제품정책 구분표

| 정책 | 근거 수준 | 근거와 해석 |
|---|---|---|
| 초보·복귀자는 저강도에서 중강도부터 시작 | 직접 근거 | ACSM은 불필요한 사전 의료 스크리닝을 줄이고 저·중강도 운동의 진입장벽을 낮추면서 운동량과 강도를 점진적으로 늘리는 방향을 제시한다. [ACSM 사전 스크리닝 권고](https://journals.lww.com/acsm-msse/fulltext/2015/11000/updating_acsm_s_recommendations_for_exercise.28.aspx) |
| 흉통·심한 어지럼·실신·비정상적 호흡곤란 등을 STOP 신호로 사용 | 직접 근거 | ACSM이 흉통·압박감, lightheadedness, 비정상적 숨참 등을 운동 관련 주요 warning sign으로 제시한다. [ACSM 사전 스크리닝 권고](https://journals.lww.com/acsm-msse/fulltext/2015/11000/updating_acsm_s_recommendations_for_exercise.28.aspx) |
| 상세 병력을 전부 받지 않음 | 간접 근거 + 제품정책 | ACSM은 광범위한 위험요인 스크리닝이 과도한 의료 의뢰와 운동 참여 장벽을 만들 수 있어 사전 스크리닝을 단순화했다. 병력을 수집하지 않는 범위는 서비스 대상과 개인정보 최소수집을 고려한 제품 결정이다. [ACSM 사전 스크리닝 권고](https://journals.lww.com/acsm-msse/fulltext/2015/11000/updating_acsm_s_recommendations_for_exercise.28.aspx) |
| NRS 0–10으로 통증 강도 수집 | 직접·일반적 근거 | NRS는 통증 강도를 정량화하는 대표적 척도다. 다만 mild/moderate/severe cutoff는 연구마다 차이가 있다. [PubMed 26541396](https://pubmed.ncbi.nlm.nih.gov/26541396/) |
| NRS 1–3 / 4–6 / 7–10 | 제품정책 | 절대적인 표준 cutoff가 없으므로 서비스의 보수적인 운영 기준으로 정의한다. [PubMed 26541396](https://pubmed.ncbi.nlm.nih.gov/26541396/) |
| 통증 부위에 직접 부하·움직임·신장이 필요한 운동 제거 | 간접 근거 + 도메인 정책 | 논문이 `contraindicated_pain_regions` 구조를 직접 제시하지는 않는다. 통증을 악화시킬 직접 자극을 피하기 위한 Safety filtering 정책이며 운동별 도메인 검수가 필요하다. |
| 수면·피로를 Recovery 변수로 사용 | 간접 근거 | 체계적 문헌고찰에서 subjective well-being 지표가 training load 변화에 민감했고 fatigue와 sleep이 대표적으로 사용됐다. 연구 대상이 주로 선수이므로 일반 초보자 적용은 간접 근거다. [PubMed 26423706](https://pubmed.ncbi.nlm.nih.gov/26423706/) |
| 성인 수면 7시간 이상을 정상 기준점으로 사용 | 직접 근거 | AASM/SRS 공동 합의문은 건강한 성인에게 정기적으로 7시간 이상 수면을 권고한다. [AASM/SRS 합의문](https://www.aasm.org/resources/pdf/adultsleepdurationconsensus.pdf) |
| 6시간 미만 수면을 더 보수적인 Recovery 행으로 사용 | 간접 근거 | 메타분석에서 급성 수면 손실이 운동 수행을 저하시킬 수 있음을 보고했지만 `<6시간이면 반드시 LIGHT` 같은 처방 cutoff를 제시한 것은 아니다. [PubMed 35708888](https://pubmed.ncbi.nlm.nih.gov/35708888/) |
| 수면·피로 조합 Recovery 표 | 제품정책 | 수면과 피로가 수행 준비도에 영향을 줄 수 있다는 근거를 단순한 조합표로 구현한 정책이다. 각 행·열의 `NORMAL/LIGHT/VERY_LIGHT` 결과는 임상 표준이 아니다. |
| LIGHT / VERY_LIGHT에서 운동량 조절 | 간접 근거 | 당일 수행능력과 주관적 readiness에 따라 훈련을 조정하는 autoregulation 접근 자체는 연구되고 있다. [PubMed 32813181](https://pubmed.ncbi.nlm.nih.gov/32813181/) |
| `NORMAL 3세트 / LIGHT 2세트 / VERY_LIGHT 1–2세트` | 제품정책 | downshift 원리는 설명 가능하지만 구체적인 세트 대응은 서비스 초기 정책이다. |
| 세트 → 반복 하단 → 쉬운 Variant 순으로 조절 | 제품정책 + 간접 근거 | 운동을 계속 교체하기보다 volume을 먼저 조절하는 방식은 autoregulation 개념과 부합하지만 정확한 적용 순서는 제품 설계다. [PubMed 32813181](https://pubmed.ncbi.nlm.nih.gov/32813181/) |
| 운동 후 힘들었다는 피드백을 다음 루틴에 반영 | 간접 근거 | RPE 등 perceived capability를 이용해 다음 training load를 조정하는 autoregulation 방식에 연구 근거가 있다. [PubMed 40791980](https://pubmed.ncbi.nlm.nih.gov/40791980/) |
| 힘듦 1회 기록, 2–3회 반복 시 감량 고려 | 제품정책 | 정확히 2–3회를 기준으로 하라는 연구는 없다. 하루 컨디션 변동으로 인한 과잉조정을 막기 위한 정책이다. |
| Safety BLOCK을 다른 Agent가 복구하지 못함 | 시스템 안전설계 | 운동처방 연구의 임계값이 아니라 SafetyPolicyEngine을 hard constraint로 유지하기 위한 시스템 설계다. |
| Variant를 독립 row로 저장하고 개별 Safety 검사 | 데이터·도메인 정책 | 같은 family라도 자세와 부하가 달라질 수 있으므로 각각 독립 검수한다. |
| Alternative를 별도 relation으로 관리 | 데이터·추천 정책 | 연구 기준이 아니라 기존 운동을 승인된 다른 운동으로 교체하기 위한 추천 시스템 설계다. |
| `variant_difficulty_rank` | 제품·도메인 정책 | 지지면 안정성, 체중부하, ROM, 균형, 자세 제어를 참고해 family 내부 상대 순서를 정한다. 기존 5항목×1–3 절대 합산점수 방식은 사용하지 않는다. |
| 18–64세와 65세 이상 구분 | 직접 근거 | WHO 2020은 두 집단을 별도로 구분하고 65세 이상에 균형·기능·낙상예방 다요소 활동을 추가한다. 현 MVP가 이 규칙을 제공하지 않으므로 18–64세로 한정한다. [WHO 2020 Guidelines](https://www.who.int/publications/i/item/9789240015128) |
| 60세 이상 MET 예외 | 직접 근거 + 향후 정책 | WHO의 고령자 경계는 65세지만 Adult Compendium은 19–59세, Older Adult Compendium은 60세 이상을 대상으로 하며 MET60+에 2.7 mL/kg/min을 사용한다. 60세 이상 지원 시 연령·MET 정책을 따로 두어야 한다. [Adult Compendium](https://pmc.ncbi.nlm.nih.gov/articles/PMC10818145/), [Older Adult Compendium](https://pmc.ncbi.nlm.nih.gov/articles/PMC10818108/) |
| 임신·산후·만성질환자 별도 처방 제외 | 직접 근거 + 제품정책 | WHO는 이들을 별도 하위집단으로 다루며 능력·기능 제한·합병증·치료계획 등의 추가 고려가 필요하다. 운동 금지 집단이라는 뜻이 아니라 현 서비스가 개별 처방을 지원하지 않는다는 범위 제한이다. [WHO 2020 Guidelines](https://www.who.int/publications/i/item/9789240015128) |
| 주 150–300분 유산소 + 주 2일 근력 | 직접 근거 | 성인의 장기 주간 목표·리포트 기준점으로 쓴다. 초보·복귀자에게 첫 주부터 강제하지 않고 소량에서 점진적으로 접근한다. [WHO 2020 Guidelines](https://www.who.int/publications/i/item/9789240015128) |
| MET 정의·kcal 공식·2024 Compendium | 직접 근거 | `kcal = MET × 3.5 × weight_kg ÷ 200 × minutes`를 사용하되 표준 MET가 개인의 실제 안정시 대사량은 아니므로 UI는 `예상 소모 칼로리`와 약간의 반올림 표시를 사용한다. 2024 Adult Compendium은 19–59세 대상 1,114개 활동을 제공한다. [2024 Adult Compendium](https://pmc.ncbi.nlm.nih.gov/articles/PMC10818145/) |
| 웨어러블 HR과 kcal 정확도 차이 | 직접 근거 + 제품정책 | umbrella review에서 HR은 비교적 양호했지만 활동강도·에너지소비는 오차가 크고 기기·활동별 편차가 크다. HR은 리포트 보조값, wearable kcal와 MET kcal은 서로 다른 추정 source로 보고 동시 표시하지 않는다. [Wearable umbrella review](https://link.springer.com/article/10.1007/s40279-024-02077-2), [Systematic review](https://pmc.ncbi.nlm.nih.gov/articles/PMC7509623/) |
| 10분 bout 제한 폐지 | 직접 근거 | 길이와 관계없이 누적된 신체활동이 이점에 기여한다. `available_time` 10분은 하나의 루틴을 구성하는 서비스 최소 단위일 뿐, 10분 미만 활동을 무효로 판정하는 기준이 아니다. [Physical Activity Guidelines, 2nd ed.](https://www.cdc.gov/physical-activity/media/pdfs/Physical_Activity_Guidelines_2nd_edition.pdf), [WHO guideline update paper](https://doi.org/10.1136/bjsports-2020-102955) |
| 건강정보 별도 동의·최소수집 | 법적 직접 근거 | 지속 통증·당일 NRS·피로·수면·웨어러블 건강 정보의 처리 범위와 목적을 출시 전 검토하고, 일반 개인정보 동의와 민감정보 동의를 분리한다. 실제 수집 항목 기준의 법률 검토가 필요하다. [국가법령정보센터 개인정보 보호법](https://www.law.go.kr/법령/개인정보보호법) |
| 성별·BMI 입력 제외 | 간접 근거 + 제품정책 | 일반 성인 활동 권고는 성별·BMI별 서로 다른 기본 처방량을 제시하지 않는다. 현 개인화의 소비처가 없으므로 최소수집 원칙에 따라 제외하되, 칼로리 정확도 손실이 0이라고 설명하지 않고 추정치로 표시한다. MET 공식에는 체중은 필요하지만 BMI는 필요하지 않다. [WHO 2020 Guidelines](https://www.who.int/publications/i/item/9789240015128) |
| 목표별 Training 차등 | 직접 + 간접 근거 | 체력은 유산소+전신 근력, 근성장은 저항운동·주간 volume, 다이어트는 유산소·총활동량을 높이면서 근력을 유지, 습관·지속은 성공 가능성·점진 증가를 우선한다. 식이를 관리하지 않는 서비스는 체중감량 결과를 보장하지 않는다. [Resistance-training network meta-analysis](https://doi.org/10.1136/BJSPORTS-2023-106807), [Planning meta-analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC9223740/) |
| 주간 재계획·미수행 이유 활용 | 간접 근거 + cadence 제품정책 | action/coping planning, goal review, feedback, self-monitoring, problem solving은 신체활동 행동변화에 활용된다. barrier를 받아 다음 계획에 쓰는 방향은 설명 가능하지만 정확한 7일 주기와 이유별 trigger는 제품정책이다. [Planning meta-analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC9223740/) |
| 웨어러블 수면을 Recovery 보조신호로 사용 | 직접 근거 + 제품정책 | PSG와 비교한 메타분석에서 총수면시간·수면효율 등에 차이가 있었다. 임상 진단에 쓰지 않고, 유효한 wearable 값이 있으면 우선 사용하며 없거나 미연동이면 수동 수면값으로 fallback한다. [Consumer sleep tracker meta-analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC11874098/) |
| 최근 48시간 동일 부위·pattern penalty | 간접 근거 + 제품정책 | 근육군 회복 간격을 고려하는 일반 근력 권고를 초보·복귀자 추천 순위에 반영한다. 48시간을 절대 BLOCK으로 사용하지 않고 Training penalty로만 사용한다. [ACSM progression model](https://doi.org/10.1097/00005768-200202000-00027) |
| Progression 상한·적용 빈도 | 간접 근거 + 제품정책 | ACSM의 1–2회 초과 수행 시 2–10% 저항 증가 모델은 근거가 되지만, 실제 kg을 관리하지 않는 서비스에 비율을 직접 적용하지 않는다. 2회 연속 적합성 확인 후 주간 재계획에서 한 요소·한 단계만 올리는 것은 보수적 제품정책이다. [ACSM progression model](https://doi.org/10.1097/00005768-200202000-00027) |

발표에서는 연구가 방향을 지지하는 부분과 서비스가 정한 수치를 분리해 설명한다. 예를 들어 `논문에서 LIGHT는 2세트라고 했다`고 표현하지 않고 다음과 같이 설명한다.

> 연구에서 수면과 피로가 회복상태와 운동 수행에 영향을 줄 수 있다는 근거를 확인했고, 이를 서비스에서 사용할 수 있는 단순한 조합표로 변환했습니다. 표의 `NORMAL/LIGHT/VERY_LIGHT` 구간은 표준화된 임상 기준이 아니라 초보·복귀자 대상 서비스의 초기 제품정책이며, 추후 사용자 수행·피드백 데이터로 보정하도록 설계했습니다.

### 현재 저장소 구현 근거

- `backend/app/domain/agents/v3_contracts.py`: Constraint Envelope와 Recovery Ceiling
- `backend/app/domain/agents/v3_validation.py`: Safety·장소·Recovery·시간 최종 무결성 검사
- `backend/app/domain/rules/safety.py`: 현재 severity, Red Flag, Safety rule 평가
- `backend/app/domain/rules/workout_execution.py`: 운동 블록 기반 공식 완료 상태
- `backend/app/modules/profiles/schemas.py`: 현재 온보딩 계약
- `backend/app/modules/checkins/schemas.py`: 현재 Daily Check-in 계약
- `backend/app/db/models/catalog.py`: 현재 운동·Safety rule·Alternative 모델
- `backend/app/modules/weekly_reports/service.py`: 주간 완료율과 미수행 이유 집계
- `docs/ARCHITECTURE.md`, `docs/DOMAIN_RULES.md`, `docs/API_CONTRACT.md`, `docs/DATA_MODEL.md`: 기존 시스템 경계와 계약
