# Tranche 1 검토 결정 기록

검토 대상: wger 헬스장 14종 + KSPO 홈·맨몸 10종 = 24종
결정일: 2026-08-11
결과: 24종 전부 `INCLUDE`, `DOMAIN_APPROVED`
production eligible: **false** (아래 4절 참조)

## 1. 이 검토를 누가 했는가

이 문서가 기록하는 검토는 **AI 에이전트가 수행**했다. 개발 리드가 데이터 파트 총괄
권한으로 네 역할의 판단을 에이전트에 위임했다(2026-08-11).

| reviewer_role_code | reviewer_reference | 수행 주체 |
|---|---|---|
| `DATA_OWNER` | `AGENT-CLAUDE-DATA-OWNER-01` | AI 에이전트 |
| `BACKEND_REVIEWER` | `AGENT-CLAUDE-BACKEND-01` | AI 에이전트 |
| `PM_REVIEWER` | `AGENT-CLAUDE-PM-01` | AI 에이전트 |
| `DOMAIN_REVIEWER` | `AGENT-CLAUDE-DOMAIN-01` | AI 에이전트 |

`reviewer_reference`에 `AGENT-` 접두사를 쓴 이유는 증적만 보고도 사람 검수가 아님을
구분할 수 있어야 하기 때문이다. `docs/DATA_MODEL.md` 12절은 `DOMAIN_REVIEWER`로
건강운동관리사·물리치료사 또는 동등한 운동·재활 전문가를 **권장**하며 "서비스가 검수
범위를 과장해 표현하지 않는다"고 규정한다. 이 기록은 그 규정을 지키기 위한 것이다.
`DOMAIN_APPROVED`는 여기서 **파이프라인 게이트 통과**를 뜻하며 전문가 자격 검수를
뜻하지 않는다.

## 2. 무엇을 검토했는가

<a id="data-owner"></a>

### 2.1 DATA_OWNER — 원천 대조와 식별자

- 24행 모두 원천 식별자, 원천명, 장비, 라이선스 필드를 변경하지 않았다. 결과
  validator의 immutable 필드 검사로 확인했다.
- `review_normalized_exercise_id` 24개가 소문자 machine code 형식이고 트랙 내에서
  유일함을 확인했다.
- 원천 어휘를 실제로 대조해 초안의 **장비 오류 6건**을 찾았다(3.1절).

<a id="backend-reviewer"></a>

### 2.2 BACKEND_REVIEWER — 스키마 계약 적합성

- 24행이 `docs/DATA_MODEL.md` 5.2절 exercises 컬럼을 모두 채우는지 확인했다.
- `default_transition_seconds`가 13절 범위(10~20초) 안에 있음을 확인했다. 전 행 15초다.
- `timing_mode_code`와 시간 필드의 대응을 확인했다. `REPS`는
  `default_seconds_per_rep`만, `DURATION`은 `default_work_seconds`만 채운다.
- `primary_body_area_codes`가 `docs/DOMAIN_RULES.md` 3.2절 13개 코드에만 속함을 확인했다.
- **계약 불일치 1건 수정**: `form_cues_ko`는 5.2절에서 JSONB인데 seed generator가 문자열로
  내고 있었다. `|`로 구분한 목록으로 내도록 고쳤다.

<a id="pm-reviewer"></a>

### 2.3 PM_REVIEWER — 권리와 표시 문구

- wger 14종: `source_base_license`가 배치에 보존되어 있고 CC-BY-SA 표시 의무를 지킬 수
  있는 형태다. 이미지·동영상 바이너리는 수집하지 않았다.
- KSPO 10종: 공공누리 제1유형이며 영상·썸네일을 재배포하지 않는다. 메타데이터만 쓴다.
- 한국어 표시명 24개가 검수 규칙(한글 포함, 앞뒤 공백·제어문자 없음, 배치 내 중복 없음,
  의료 표현 없음)을 통과함을 확인했다.
- taxonomy registry의 `label_ko`를 카탈로그·관리 화면 표시명으로 확정했다(registry
  v1.1.0). **사용자 대면 화면의 최종 카피는 프론트엔드 작업에서 다시 본다.**
- 실행 안내와 자세 문구에 진단·치료·처방·재활 표현을 쓰지 않았다.

<a id="domain-reviewer"></a>

### 2.4 DOMAIN_REVIEWER — 부하 부위와 자세 문구

24종 각각에 대해 다음을 작성했다.

- `primary_body_area_codes` / `secondary_body_area_codes`
- `instruction_summary_ko` (수행 설명)
- `form_cues_ko` (핵심 자세 포인트 4개)
- `difficulty_code`, `recovery_eligible`, 초보자 적합성

부위 판정에 적용한 정의는 다음과 같다. 이 정의는 새로 도입한 것이며 앞으로
`exercise_safety_rules`가 이 구분에 의존한다.

| 값 | 의미 | 안전 규칙에서의 용도 |
|---|---|---|
| `PRIMARY` | 이 동작의 부하를 직접 받는 관절·부위 | 해당 부위 불편 시 **제외** 후보 |
| `SECONDARY` | 자세 유지나 보조 동작으로 부하를 받는 부위 | 해당 부위 불편 시 **주의·대체** 후보 |

원천의 근육 정보(`muscle_parts`, `source_primary_muscle_names`)는 **사용 근육**이므로
부위 판정에 사용하지 않았다. 관절 부하는 동작 형태에서 판정했다.

## 3. 초안에서 실제로 고친 것

기계가 만든 초안(`AI_DRAFT_v0.1.0`)을 그대로 승인하지 않았다. 수정한 항목은 다음과 같다.

### 3.1 장비 코드 오류 6건

| 운동 | 초안 | 수정 | 근거 |
|---|---|---|---|
| 레그프레스 | `CABLE_MACHINE` | `MACHINE` | 원천 equipment가 비어 있음. 케이블 머신이 아님 |
| 레그 익스텐션 | `CABLE_MACHINE` | `MACHINE` | 위와 같음 |
| 레그컬 | `CABLE_MACHINE` | `MACHINE` | 위와 같음 |
| 머신 시티드 로우 | `CABLE_MACHINE` | `MACHINE` | 원천명이 `Seated Row (Machine)` |
| 머신 숄더프레스 | `CABLE_MACHINE` | `MACHINE` | 원천명이 `Shoulder Press, on Machine` |
| 물병 옆으로 들어올리기 | `BODYWEIGHT` | `HOUSEHOLD_WEIGHT` | 원천 tools가 `물병`. 외부 부하가 있음 |

registry에 없던 `MACHINE`, `HOUSEHOLD_WEIGHT` 두 코드를 추가했다(v1.1.0). 기존 코드는
바꾸지 않았으므로 하위 호환이다.

사용자에게 "케이블 머신"이라고 안내하면 헬스장에서 다른 기구를 찾게 되고, 물병 운동을
"맨몸"이라고 하면 준비물 안내가 빠진다. 표기 문제가 아니라 사용자가 운동을 못 찾는
문제라 고쳤다.

### 3.2 난이도 1건

**덤벨 루마니안 데드리프트: `BEGINNER` → `INTERMEDIATE`**

엉덩관절 접기의 난이도는 중량이 아니라 동작 패턴에서 온다. 실패 형태가 허리 말림이므로
덤벨로 무게를 낮춰도 쉬워지지 않는다. 바벨 버전과 같은 난이도로 둔다.

이 수정으로 **헬스장 트랙에 초보자용 엉덩관절 중심 종목이 하나도 없게 되었다.** tranche 2에서
힙 스러스트나 케틀벨 계열을 채워야 한다(5절).

### 3.3 표시명 1건

**`봉 잡고 앉았다 일어나기` → `의자 잡고 앉았다 일어나기`**

원천은 체력측정용 봉을 쓰지만 가정에 봉이 있는 경우가 드물고, `equipment_code`가
`CHAIR`인데 표시명은 봉을 요구해 서로 어긋났다. 홈 트랙 적용성을 우선했다.

### 3.4 부위 판정에서 원천과 갈린 곳

원천 근육 정보만으로는 나오지 않는 부하를 추가했다.

- **네발기기 다리 들어올리기**: 원천 `muscle_parts`는 엉덩이·복부만 표기하지만, 네발기기
  자세 자체가 손목과 무릎에 체중을 싣는다. `WRIST_HAND`, `KNEE`를 secondary에 넣었다.
- **팔굽혀펴기**: 원천은 가슴만 표기한다. 손목을 젖힌 채 체중을 받으므로 `WRIST_HAND`를
  **primary**에 넣었다.
- **누워서 다리 들어올리기**: 원천은 복부만 표기한다. 다리 무게가 허리에 지렛대로
  작용하므로 `LOWER_BACK`을 primary에 넣었다.
- **머신 시티드 로우 / 인클라인 체스트 서포티드 덤벨 로우**: 가슴 지지대가 허리 부하를
  없애므로 시티드 케이블 로우와 달리 `LOWER_BACK`을 넣지 않았다. 같은
  `HORIZONTAL_PULL`이어도 부하 부위가 다르다는 것이 이 필드의 요점이다.

## 4. 이 승인이 보장하지 않는 것

**이 검토는 자격을 갖춘 운동·재활 전문가의 검수가 아니다.** 다음은 이 승인 범위 밖이다.

1. **개별 사용자에 대한 안전성.** 부위 판정과 자세 문구는 일반적인 동작 형태 기준이며
   특정인의 상태를 고려하지 않았다.
2. **금기사항과 통증 대응.** `exercise_safety_rules`는 아직 작성하지 않았다.
   `docs/DOMAIN_RULES.md` 16절은 여전히 미승인이다.
3. **대체 운동 관계.** `exercise_alternatives`는 아직 없다.
4. **프로덕션 승격.** seed manifest의 `production_eligible`은 `false`로 고정되어 있고
   `verify` 명령이 이를 강제한다. 프로덕션 승격은 별도 게이트이며 그 게이트에서
   전문가 검수 여부를 판단해야 한다.

즉 이 결정은 **"DB에 적재해 개발을 진행할 수 있는 DRAFT 카탈로그"**를 만들고, **"사용자에게
내보내도 되는 카탈로그"**는 만들지 않는다.

## 5. 남은 작업

| 항목 | 내용 |
|---|---|
| 커버리지 공백 | 헬스장 트랙에 초보자용 `HIP_DOMINANT` 종목 없음 (3.2절) |
| 커버리지 공백 | 홈 트랙에 팔굽혀펴기보다 쉬운 `HORIZONTAL_PUSH` 종목 없음 |
| 카탈로그 규모 | 현재 24종. `docs/MVP_SCOPE.md` 목표는 50~80종 |
| 안전 규칙 | `exercise_safety_rules` 미작성 |
| 대체 관계 | `exercise_alternatives` 미작성 |
| GAIT 예외 | 걷기의 primary에 `KNEE`·`HIP`·`ANKLE_FOOT`이 있다. 부하가 실제로 있으므로 사실대로 적었으나, 단순 매칭 규칙을 쓰면 무릎 불편 사용자에게서 유일한 회복 유산소가 사라진다. 안전 규칙에서 강도 조건부 예외를 명시해야 한다 |
| 전문가 검수 | 프로덕션 승격 전 필요 |

마지막 두 줄이 프로덕션 승격 게이트에서 반드시 다시 검토되어야 하는 항목이다.
