# DOMAIN_RULES.md

## 1. 문서 목적과 적용 순서

이 문서는 오늘의 운동 계획을 유지, 축소, 변경, 회복, 휴식 또는 중단 안내로 조정하는 MVP 도메인 규칙을 정의한다.

이 규칙은 의료 진단, 치료 또는 재활 처방이 아니다. 사용자가 직접 보고한 상태를 이용해 검수된 운동 후보를 제한하는 제품 정책이다.

현재 멀티 에이전트 핵심 흐름은 Training·Recovery·Safety·Feasibility 네 proposal의 병렬 실행과 Coordinator 최종 결정으로 확정한다. 에이전트별 상세 입력·출력·proposal JSON 구조와 공개 요약 필드는 증상 사용자 시나리오 검증 결과에 따라 추후 보완할 수 있으며, 독립적인 최종 Safety 재검사는 현재 범위에 포함하지 않는다.

규칙의 적용 우선순위는 다음과 같다.

1. 중대한 이상 반응 처리
2. 심한 통증과 급성 부상 신호 처리
3. 통증 부위별 운동 제외
4. 요청 시간 선호, 장소, 장비 제약
5. 복귀 모드 상한
6. 목표와 CORE 운동 보존
7. 진척과 지속 가능성에 따른 후보 선택
8. 사용자용 설명 생성

낮은 우선순위의 규칙은 높은 우선순위의 거부나 제한을 완화할 수 없다.

---

## 2. 제품 불변조건

- 기본 경험은 최종 추천 루틴 하나를 제공한다.
- REST와 STOP_AND_SEEK_HELP에는 운동 계획을 제공하지 않는다.
- RECOVERY의 최종 추천 루틴은 검수된 저강도 회복 계획이다.
- 웨어러블 데이터가 없어도 모든 핵심 흐름이 동작한다.
- 웨어러블 데이터만으로 안전 결정을 내리지 않는다.
- 웨어러블은 MVP의 선택적 입력 경로이며 권한 거부·미연동 사용자는 수동 체크인으로 동일한 핵심 흐름을 사용한다.
- 캘린더는 빈 시간·계획 등록과 등록된 일정의 수행 여부만 확인하는 보조 경로다. 세부 운동 기록은 저장하지 않으며 공식 수행 상태를 변경하지 않는다.
- 웨어러블 운동 데이터는 캘린더에 자동 등록하지 않는다.
- 안전 거부는 조정 에이전트와 LLM이 무시할 수 없다.
- 내부 원래 후보의 안전 검증 결과는 최종 추천 루틴 반환 여부를 결정하며, 원래 후보를 사용자 선택지로 공개하지 않는다.
- 사용자가 요청한 운동 시간은 시스템이 임의로 축소하지 않는다.
- 다운시프트는 요청 시간을 유지하면서 부하·강도·세트·반복·운동 유형·휴식 구성을 조정한다.
- 예상 시간과 실제 경과 시간은 운동 완료 상태를 결정하지 않는다.
- 미수행은 벌점이 아니라 다음 결정의 입력이다.
- 사용자가 휴식을 선택하면 해당 사용자 로컬 날짜에는 추가 압박 알림을 보내지 않는다.
- 통증과 이상 반응 화면에는 장난스러운 마스코트 표현을 사용하지 않는다.
- 내부 프롬프트, 숨은 추론, 원시 건강 데이터는 클라이언트에 반환하지 않는다.
- 예상 소모 칼로리는 앱 운동 계획·세션에서 사용자가 제공한 체중과 운동 종류·시간·강도를 반영한 추정치이며, 체중이 없으면 추정값은 `null`로 둔다. 수동 외부 운동 기록 기반 추정은 MVP 이후 기능이다. 진단·안전 판정의 단독 근거로 사용하지 않는다.

---

## 3. 안정적인 머신 코드

DB와 API에는 아래 영문 코드를 사용하고 사용자 표시 문구는 별도로 관리한다.

### 3.1 최종 액션

~~~text
KEEP
DOWNSHIFT
CHANGE
RECOVERY
REST
STOP_AND_SEEK_HELP
~~~

### 3.2 불편 부위

~~~text
NECK
SHOULDER
ELBOW
WRIST_HAND
UPPER_BACK
LOWER_BACK
HIP
KNEE
ANKLE_FOOT
CHEST
ABDOMEN
GENERALIZED
OTHER
~~~

한 체크인 또는 피드백에서 여러 부위를 선택할 수 있다.

### 3.3 불편 심각도

| 값 | 코드 | 사용자 표시 | 제품 판단 |
|---:|---|---|---|
| 0 | NONE | 불편함 없음 | 일반 판단 |
| 1 | MILD | 조금 불편함 | 관련 동작 수정 또는 제외 검토 |
| 2 | MODERATE | 움직임에 영향을 줌 | 관련 동작 제외, 대체 또는 회복안 |
| 3 | SEVERE | 운동하기 어려움 | 운동 계획 제공 중단, 휴식·확인 안내 |

이 값은 의료적 통증 척도로 해석하지 않는다.

### 3.4 이상 반응 코드

~~~text
CHEST_DISCOMFORT
UNEXPECTED_SEVERE_SHORTNESS_OF_BREATH
SEVERE_DIZZINESS
FAINTING
SUDDEN_WEAKNESS_OR_NUMBNESS
RAPID_OR_IRREGULAR_HEARTBEAT_WITH_SYMPTOMS
SUDDEN_SEVERE_PAIN
ACUTE_SWELLING_OR_DEFORMITY
CANNOT_BEAR_WEIGHT
OTHER_SERIOUS_REACTION
~~~

구현 시 하나의 목록으로 저장하되 처리 결과는 다음 두 그룹으로 구분한다.

긴급 중단 그룹:

- CHEST_DISCOMFORT
- UNEXPECTED_SEVERE_SHORTNESS_OF_BREATH
- SEVERE_DIZZINESS
- FAINTING
- SUDDEN_WEAKNESS_OR_NUMBNESS
- RAPID_OR_IRREGULAR_HEARTBEAT_WITH_SYMPTOMS
- OTHER_SERIOUS_REACTION

급성 근골격 신호 그룹:

- SUDDEN_SEVERE_PAIN
- ACUTE_SWELLING_OR_DEFORMITY
- CANNOT_BEAR_WEIGHT

이 구분은 P0 결정서에서 긴급 중단 흐름과 REST 흐름을 각각 정의한 내용을 구현 가능한 규칙으로 정규화한 것이다.

### 3.5 계획 역할

~~~text
CORE
SUPPORT
OPTIONAL
~~~

이 역할은 운동 자체의 절대 속성이 아니라 특정 루틴과 목표 안에서의 역할이다.

### 3.6 코치 문구 성향

~~~text
SUPPORTIVE
CONCISE
ENERGETIC
~~~

기본값은 SUPPORTIVE다. 코치 성향은 문구와 표현 길이에만 영향을 주며 안전, 강도, 시간, 운동 선택에는 영향을 주지 않는다.

### 3.7 안전 평가 상태

~~~text
PASS
NEEDS_INPUT
REVISE
BLOCKED
FAILED
~~~

- `PASS`: 현재 후보가 안전 규칙을 통과했다.
- `NEEDS_INPUT`: 결정에 필요한 안전 입력이 부족하며 계획을 반환하지 않는다.
- `REVISE`: 충돌 운동 제거 또는 대체 의견을 Coordinator 결정에 반영한다.
- `BLOCKED`: 현재 입력으로 운동 계획을 제공할 수 없다.
- `FAILED`: 필수 규칙, 에이전트 또는 저장 처리 실패로 결정할 수 없다.

안전 상태와 최종 액션은 다른 축이다. `BLOCKED`는 원인에 따라 REST 또는 STOP_AND_SEEK_HELP로 사용자에게 표시할 수 있고, `FAILED`는 제품 오류이며 운동 액션을 성공 결과로 만들지 않는다.

---

## 4. 결정 순서

### 4.1 중대한 이상 반응

긴급 중단 그룹의 코드가 하나라도 있으면 STOP_AND_SEEK_HELP를 반환한다.

- final_plan은 null이다.
- 운동을 추천하거나 증상의 원인을 추정하지 않는다.
- 긴급 안내 문구를 반환한다.
- 다른 에이전트 제안과 사용자 코치 성향은 이 결과를 변경할 수 없다.

### 4.2 심한 통증과 급성 근골격 신호

다음 중 하나면 REST를 반환한다.

- 한 부위라도 심각도가 SEVERE
- 급성 근골격 신호 그룹의 코드가 있음
- 안전 검증을 통과한 계획을 만들 수 없음
- 사용자가 명시적으로 휴식을 선택함

REST에는 final_plan을 제공하지 않는다.

### 4.3 특정 부위 불편

다음 조건을 모두 만족하면 충돌 운동을 제외하고 검수된 대체 후보를 만든다.

- 불편 부위가 명확함
- 심각도가 MILD 또는 MODERATE
- 긴급 중단 그룹과 급성 근골격 신호 그룹이 모두 비어 있음
- DOMAIN_APPROVED 상태의 통증 제외 규칙이 있음
- DOMAIN_APPROVED 상태의 대체 운동이 있음
- 대체 운동이 현재 장소와 장비를 충족함

원래 목표를 안전하게 보존하는 대체 계획이 만들어지면 CHANGE를 반환한다.

MODERATE 불편이 있고 목표 보존형 대체 계획을 만들 수 없지만 검수된 저강도 회복 계획이 가능하면 RECOVERY를 반환한다. 안전한 회복 계획도 없으면 REST를 반환한다.

### 4.4 피로와 회복 부족

피로 입력은 사용자의 주관적 제품 입력이며 의료 상태로 해석하지 않는다.

- 중간 수준 피로는 요청 시간을 유지하는 DOWNSHIFT 후보를 만든다.
- 높은 피로, 설정된 수면 부족 신호, 최근 운동 부하 누적, 여러 부위의 일반적 근육통은 RECOVERY 후보를 만든다.
- 수면 부족과 최근 부하의 수치 임계값은 버전화된 정책 설정으로 관리해야 하며 전문가 검수 전 임의로 정하지 않는다.

RECOVERY 콘텐츠는 DOMAIN_APPROVED 상태의 가벼운 걷기, 호흡, 가동성 운동으로 제한한다.

### 4.5 정상 상태

다음 조건을 모두 만족하면 KEEP을 반환한다.

- 통증과 이상 반응이 없음
- 회복 또는 복귀 제한이 없음
- 현재 장소와 장비로 원래 계획 수행 가능
- 원래 계획이 사용자가 요청한 시간 목표와 강도 선호에 부합함
- SafetyAgent의 안전 상태와 의견이 Coordinator 결정에 반영됨

---

## 5. 요청 시간과 예상 시간

`requested_duration_minutes`는 최종 루틴의 계획 시간 목표(분)다. 프로필 기본값을 사용하되 사용자가 당일 명시적으로 변경하면 그 값을 새 목표로 사용한다. 운동 계획을 반환하는 경우 계획의 `estimated_duration_seconds`는 반드시 `requested_duration_minutes * 60`과 일치해야 하며, 시스템은 사용자 변경 없이 이 값을 더 짧게 만들거나 임의로 초과할 수 없다.

~~~text
estimated_duration_seconds
= setup_seconds
+ warmup_seconds
+ sum(work_seconds)
+ sum(rest_seconds)
+ sum(transition_seconds)
+ cooldown_seconds
~~~

MVP 데이터 허용 범위:

| 항목 | 기본 허용 범위 |
|---|---:|
| 장비 준비 | 0~60초 |
| 준비 운동 | 60~180초 |
| 동작 전환 | 동작당 10~20초 |
| 세트 간 휴식 | 운동 데이터에 정의 |
| 마무리 | 45~120초 |

서버가 실제 동작 시간만 합산하고 준비, 휴식, 전환, 마무리를 누락하는 것은 금지한다. 시간 계산 규칙에는 version을 부여하고 decision run에 저장한다.

`estimated_duration_seconds`는 계획 단계의 hard target이다. 실제 수행을 강제하는 hard execution limit이나 완료 판정 조건은 아니지만, 계획기는 반드시 requested duration에 맞도록 준비·운동·휴식·전환·마무리 시간을 배분해야 한다. 검수된 후보와 안전 규칙만으로 요청 시간을 정확히 구성할 수 없으면 시간을 임의로 축소·초과하거나 불필요한 운동으로 채우지 않고 `NEEDS_INPUT` 또는 `BLOCKED`로 계획을 반환하지 않는다. 시간 구성과 반올림 규칙에는 version을 부여하고 decision run에 저장한다.

운동 시작 후 `actual_elapsed_seconds`는 0초부터 증가하는 클라이언트 경과 타이머 값이다. 이 값은 수행량 확인과 기록에만 사용하며 운동 블록, 세션 상태 또는 안전 결과를 자동 판정하지 않는다. 시작·일시정지·재개·종료 이벤트는 별도 이력으로 누적하되 공식 수행 상태를 변경하지 않는다.

예상 소모 칼로리 산식과 계수는 버전 관리하며 개발 전 확정한다. 표시 문구는 추정치임을 명시하고 의료적 해석을 제공하지 않는다.

---

## 6. 요청 시간 보존형 다운시프트

다운시프트는 사용자의 requested duration을 유지하면서 최종 추천 루틴의 수행 부담을 낮춘다. lighter 계획을 별도 생성하거나 공개하지 않는다.

1. 안전, 장소, 장비 충돌 운동을 제거한다.
2. requested duration과 CORE 목표·운동 순서를 유지하고 `estimated_duration_seconds`를 `requested_duration_minutes * 60`에 맞춘다.
3. 외부 부하와 강도를 낮춘다.
4. 필요하면 세트·반복, 운동 난이도 또는 운동 유형을 조정한다.
5. 준비·세트·반복·휴식·전환·마무리 구성을 조정해 요청 시간에 맞춘다.
6. 모든 대체 운동은 검수된 대체 관계를 사용한다.

시스템이 40분 요청을 15분 또는 5분으로 임의 축소하는 것은 금지한다. 사용자가 당일 시간을 직접 변경하면 변경된 값을 새 requested duration으로 사용한다. 남은 시간은 승인된 구성요소의 시간 배분으로 맞추되, 시간을 채우기 위한 불필요한 운동은 추가하지 않는다. 안전상 정확한 시간의 운동 제공이 불가능하면 시간 선호보다 REST 또는 STOP_AND_SEEK_HELP가 우선한다.

TIME_SHORTAGE 미수행 이력이 반복돼도 agent가 요청 시간을 자동 변경할 수 없다. 시스템은 사용자에게 희망 시간 변경 여부를 물을 수만 있고 명시적 USER_OVERRIDE가 있을 때만 반영한다.

---

## 7. 복귀 모드

복귀 모드는 마지막 공식 완료 운동 이후 14일 이상 경과했을 때만 활성화한다.

~~~text
마지막 공식 COMPLETED 세션 이후 14일 이상 경과
~~~

정책 설정:

~~~text
RETURN_MODE_COMPLETION_GAP_DAYS=14
~~~

14일은 의학적 기준이 아니라 MVP 운영 기준이다. 값은 버전화된 정책 설정으로 관리한다.
`NOT_COMPLETED` 이력과 연속 미수행 횟수는 다음 계획의 학습 신호로만 사용하며 복귀 모드를
활성화하거나 벌점을 부과하지 않는다. 마지막 공식 완료 이력이 없는 콜드스타트 사용자는
미수행 이력만으로 복귀 모드에 들어가지 않는다.

POL-012의 14일 미접속 서비스 분류는 계정 참여 상태를 위한 별도 운영 정책이며, 운동 복귀
모드를 활성화하는 근거가 아니다. 운동 복귀 모드의 유일한 날짜 근거는 마지막 공식
`COMPLETED` 세션이다.

복귀 모드에서는 다음을 적용한다.

- 요청한 첫 세션 시간 유지
- 부하·강도·세트·반복 또는 볼륨 조정
- 이전에 완료한 익숙한 운동 우선
- 실패했던 강도를 그대로 복원하지 않음
- 첫 복귀 세션 결과 확인 후 단계적으로 복원

정확한 복귀 볼륨 비율은 외부 도메인 검수 전 임의로 정하지 않는다.

운동 공백은 다음과 같이 분류한다.

- 14일 미만: 일반 공백이며 복귀 모드를 적용하지 않음
- 14일 이상: `RETURN_MODE`로 분류하고 체크인과 복귀 상한을 반드시 재평가
- 1년 이상 서비스 활동 없음: 법정 휴면이 아닌 `DORMANT` 서비스 분류와 30일 전 통지 후 삭제 정책을 적용한다.

14일과 1년은 의료 기준이 아니라 MVP 운영·데이터 정책 기준이다.

---

## 8. 에이전트 계약

전문 에이전트는 독립된 구조화 proposal을 반환한다. 아래 세부 계약은 멀티 에이전트 로직 설계 후 확정하기 전까지 잠정이다.

~~~text
TRAINING
RECOVERY
SAFETY
FEASIBILITY
~~~

공통 입력에는 다음 스냅샷이 포함된다.

- 사용자 프로필의 최소 정규화 필드
- `date_of_birth`와 서버가 계산한 만 나이는 에이전트 입력에 포함하지 않는다. 만 나이는 가입 자격 확인과 프로필 표시 외에 사용하지 않는다.
- 활성 기본 루틴 버전
- 당일 체크인과 이상 반응
- 최근 완료·미수행 기록
- 복귀 모드 상태
- 사용자 정책 버전
- 운동 카탈로그와 안전 규칙 버전
- 선택적 웨어러블 요약
- 가능 시간·장소·장비·일정·선호·기피 조건

공통 출력에는 다음을 포함한다.

- agent_type
- recommended_action
- requested_duration_minutes
- estimated_duration_seconds
- duration_adjustment_source_code: PROFILE | USER_OVERRIDE
- intensity_delta
- required_goal_tags
- preferred_exercise_ids
- excluded_exercise_ids
- hard_constraint_codes
- reason_codes
- evidence references
- policy_version

proposal_status는 `READY`, `NEEDS_INPUT`, `FAILED` 중 하나다. opaque confidence 점수는 MVP 계약에 포함하지 않는다. Training·Recovery·Safety·Feasibility 네 proposal 중 하나라도 `FAILED`이거나 누락되면 decision run은 `FAILED`이며 계획을 성공 응답하지 않는다.

evidence는 저장된 입력 필드와 규칙 코드를 가리키는 구조화 참조다. 내부 추론 전문을 저장하거나 클라이언트에 노출하지 않는다.

Coordinator(의장 에이전트)는 공통 입력·기본 후보와 Training·Recovery·Safety·Feasibility proposal을 입력받아 최종 루틴 한 개를 선택한다. `BLOCKED`와 같은 SafetyAgent의 중단 의견을 우선 반영하고, 요청 운동 시간을 보존한다.

독립적인 Safety 최종 재검사는 수행하지 않는다.

---

## 9. LLM 경계

결정적 Python 규칙이 담당하는 영역:

- 불편 부위와 이상 반응 분류
- 안전 제외와 veto
- 장소와 장비 검증
- 시간 계산
- 복귀 모드
- 다운시프트와 후보 생성
- 후보 점수화와 최종 선택
- 공개 선택지 및 안전 veto 후보 선택 가능 여부

선택적 LLM이 담당할 수 있는 영역:

- 검수된 reason code를 사용자 친화적인 문장으로 변환
- 안전 결과를 바꾸지 않는 마스코트 문구

LLM에는 직접 식별자, 원시 건강 기록, 원시 웨어러블 샘플을 보내지 않는다. LLM 실패 시 검수된 템플릿 문구를 사용하며 계획 결과는 바뀌지 않는다.

---

## 10. 사용자 선택과 상태 전이

- 최종 추천 루틴 또는 REST 중 서버가 selectable로 표시한 선택지만 처리한다.
- 내부 원래 후보와 안전 veto된 후보는 사용자 선택지로 노출하지 않는다.
- KEEP, DOWNSHIFT, CHANGE, RECOVERY 결정에서는 사용자가 운동 대신 쉴 수 있도록 별도의 REST 선택을 제공할 수 있다.
- REST 권고에는 운동 옵션이 없다.
- STOP_AND_SEEK_HELP에는 선택 가능한 운동 옵션이 없다.
- 사용자의 휴식 선택은 원래 decision result와 별도로 selection에 저장한다.
- 휴식 선택 이후 해당 로컬 날짜의 압박 알림은 차단한다.

공식 운동 수행 상태는 앱의 운동 블록 완료 체크로만 확정한다. 전체 경과 타이머, 웨어러블 또는 캘린더의 수행 여부 확인 결과는 참고 신호이며 공식 상태를 변경할 수 없다. 수동 외부 운동 기록은 MVP에 포함하지 않는다.

운동 세션 상태 전이:

~~~text
PLANNED -> IN_PROGRESS -> COMPLETED
                       -> PARTIAL
                       -> NOT_COMPLETED
                       -> STOPPED_FOR_SAFETY
~~~

각 운동 블록은 `PENDING` 또는 `COMPLETED`다. 사용자가 체크 버튼, 블록 격파 또는 좌측 밀기 등 클라이언트 제스처로 완료를 명시하면 해당 plan item을 COMPLETED로 저장한다. 세트·반복·유산소 권장 시간은 처방 정보이며 센서나 경과 시간으로 완료를 추정하지 않는다.

최종 수행 상태는 서로 배타적이다. 모든 계획 블록이 COMPLETED면 세션은 COMPLETED, 하나 이상 완료됐지만 PENDING 블록이 남으면 PARTIAL, 완료 블록이 없으면 NOT_COMPLETED다. NOT_COMPLETED에는 가장 큰 이유 하나만 저장한다.

운동 중 안전 이벤트는 다음 결정적 코드를 사용한다.

| 조건 | instruction | resulting action | session status | reason code | guidance code |
|---|---|---|---|---|---|
| MILD 불편 | `SHOW_CAUTION` | null | `IN_PROGRESS` | `MILD_DISCOMFORT` | `MILD_DISCOMFORT_CAUTION` |
| MODERATE 불편 | `SHOW_CAUTION` | null | `IN_PROGRESS` | `MODERATE_DISCOMFORT` | `MODERATE_DISCOMFORT_CAUTION` |
| SEVERE 불편 | `STOP_SESSION` | `REST` | `STOPPED_FOR_SAFETY` | `SEVERE_DISCOMFORT` | `SEVERE_OR_ACUTE_STOP` |
| 급성 근골격 신호 | `STOP_SESSION` | `REST` | `STOPPED_FOR_SAFETY` | `ACUTE_MUSCULOSKELETAL_REACTION` | `SEVERE_OR_ACUTE_STOP` |
| 긴급 중단 그룹 | `STOP_AND_SEEK_HELP` | `STOP_AND_SEEK_HELP` | `STOPPED_FOR_SAFETY` | `EMERGENCY_ADVERSE_REACTION` | `SERIOUS_ADVERSE_REACTION_STOP` |

긴급 중단 그룹은 다른 안전 이벤트보다 우선하며 veto를 유지한다. MILD 또는 MODERATE 이벤트는
검수된 동적 재구성 정책이 없으므로 진행 중 계획을 자동 변경하지 않는다. COMPLETED, PARTIAL,
NOT_COMPLETED, STOPPED_FOR_SAFETY로 종료된 세션의 블록과 상태는 변경할 수 없다.

## 11. 주간 주기와 리포트 게이트

- 주간 범위는 사용자 timezone의 월요일 00:00부터 일요일 23:59:59까지다.
- 로그인 여부와 관계없이 날짜가 경계를 지나면 주는 논리적으로 닫힌다.
- 경계는 저장된 IANA timezone으로 계산하며 다음 로컬 월요일 00:00부터 직전 주를 `CLOSED`로 판정한다. scheduler 상태나 마지막 로그인 시각은 이 판정의 입력이 아니다.
- 열린 주는 최종 주간 리포트를 생성할 수 없다.
- 닫힌 주 리포트는 사용자가 요청할 때 생성한다.
- 공식 집계는 앱 운동 블록 체크로 계산한 COMPLETED, PARTIAL, NOT_COMPLETED, STOPPED_FOR_SAFETY를 사용한다.
- 웨어러블 요약과 캘린더 수행 여부 확인 결과는 별도 참고 항목으로만 표시한다.
- 다음 주 계획은 직전 주 리포트가 생성되고 사용자가 확인한 뒤에만 최종 확정할 수 있다.
- 최초 가입자의 첫 주 목표·루틴은 이전 주 리포트 없이 생성할 수 있다. 이 콜드스타트 예외 이후의 다음 주 계획부터 직전 주 리포트 생성·확인 게이트를 적용한다.
- AI 기반 다음 주 계획 수정은 최대 2회다.
- 2회를 모두 사용하면 사용자가 직접 편집할 수 있으나 모든 수정은 시간·장소·장비·안전 규칙을 다시 통과해야 한다.
- 주간 리포트 생성과 계획 수정에서 필수 규칙 또는 에이전트가 실패하면 `FAILED`이며 추정값으로 계속하지 않는다.

주간 리포트 확인은 최초 열람으로 추정하지 않고 사용자의 명시적 acknowledgement mutation으로 기록한다.

### 11.1 닫힌 주 집계 입력 계약

- 리포트 입력은 timezone, 월요일·일요일 로컬 날짜, 네 공식 세션 상태의 횟수, 선택적인 대표 미수행 reason code와 버전만 가진 불변 최소 집계다.
- `NOT_COMPLETED`는 `NOT_COMPLETED` 학습 신호로만 전달하고 penalty 또는 감점 필드를 허용하지 않는다.
- 원시 체크인, 원시 건강 기록, 원시 웨어러블 샘플, 캘린더 본문과 직접 식별자는 집계 스냅샷에 복제하지 않는다.
- 집계 schema version과 report policy version을 함께 고정한다. 같은 불변 집계와 같은 policy version은 같은 domain 판정을 만든다.

### 11.2 다음 계획 revision과 finalize 정책

- 초기 계획 endpoint는 `INITIAL`만, 수정 endpoint는 `AI` 또는 `USER`만 생성한다.
- `AI` revision의 루틴 결정 주체는 결정적 Coordinator이며 Safety 상태·의견은 SafetyAgent 결과를 보존한다. LLM은 설명 문구에만 사용할 수 있고 루틴, 요청 시간, 안전 상태, veto 또는 후보를 변경할 수 없다.
- 성공한 Coordinator 기반 `AI` revision만 횟수에 포함하며 1회와 2회는 허용하고 세 번째 요청은 `AI_REVISION_LIMIT_REACHED`로 차단한다. `NEEDS_INPUT`, `BLOCKED`, `FAILED` 결과는 성공 횟수를 늘리지 않는다.
- `USER` revision은 AI 수정 횟수와 무관하게 허용할 수 있지만 요청 시간 일치, 허용 장소, 사용 가능한 장비, SafetyAgent 의견 반영을 모두 검증한다. 하나라도 불일치하면 해당 routine을 허용하지 않는다.
- `NEEDS_INPUT`, `BLOCKED`, `FAILED` revision에는 routine이 없으며 finalized는 항상 false다. `PASS` 또는 `REVISE`도 routine이 없으면 finalize할 수 없다.
- `finalized=true`는 직전 리포트가 명시적으로 `ACKNOWLEDGED`된 경우에만 허용한다. `is_first_user_week=true`, `cold_start_applied=true`, 직전 리포트 없음이 동시에 성립하는 최초 한 주만 acknowledgement를 생략할 수 있다.
- weekly report aggregate schema와 weekly report/plan policy는 각각 version을 가지며, 입력과 version이 같으면 revision 및 finalize 판정도 같아야 한다.

---

## 12. 검수된 안전 문구

### 12.1 경미한 불편

> 불편한 부위에 부담이 가는 동작은 제외하고 진행할게요. 움직이는 동안 불편함이 커지면 운동을 중단해주세요.

### 12.2 중간 수준 불편

> 오늘은 해당 부위를 사용하는 운동을 제외하고 회복 중심으로 조정했어요. 불편함이 반복되거나 일상적인 움직임에도 영향을 준다면 의료 또는 운동 전문가에게 확인해주세요.

### 12.3 심한 통증 또는 급성 부상 신호

> 오늘 운동은 진행하지 않는 것이 좋습니다. 갑작스럽거나 심한 통증, 붓기, 변형 또는 체중을 싣기 어려운 상태라면 의료 전문가의 확인을 받아주세요.

### 12.4 중대한 이상 반응

> 운동을 즉시 중단해주세요. 가슴의 압박감이나 통증, 예상하지 못한 심한 숨참, 실신 또는 심한 어지럼 등의 증상이 있다면 즉시 지역 응급의료 도움을 요청하세요.

문구 변경은 외부 운동·보건 전문가의 재승인이 필요하다.

---

## 13. 폴백과 장애 처리

| 상황 | 필수 처리 |
|---|---|
| 웨어러블 없음 또는 권한 거부 | 수동 체크인과 앱 운동 블록 체크로 정상 처리 |
| 선택 데이터 누락 | 칼로리 값은 `null`로 유지하고 의료 상태를 추론하지 않음 |
| LLM 장애 | 템플릿 설명 사용 |
| 필수 전문 에이전트 하나라도 장애 | FAILED, 운동 계획을 성공 응답으로 반환하지 않음 |
| 필수 안전 규칙 장애 | FAILED, 운동 계획을 성공 응답으로 반환하지 않음 |
| 검수된 안전 후보 없음 | REST |
| DB 저장 실패 | 재현할 수 없는 계획을 클라이언트에 반환하지 않음 |
| 중복 mutation | Idempotency-Key의 기존 결과 반환 |
| 오래된 체크인 버전 | STALE_CONTEXT 오류 |

---

## 13.1 동의·보유·삭제 정책

아래 정확한 기간은 `ACCEPTED` ADR-0004의 승인된 기본 정책이다. 법률상 예외가 확인되거나 기간을 변경할 때는 새 ADR과 production 보유·삭제 작업을 함께 갱신한다.

- 일반 개인정보, 민감정보, 웨어러블 연동, 캘린더 연동, 마케팅 동의를 별도로 기록한다.
- 동의 철회 시 해당 수집·동기화와 외부 토큰을 즉시 중단하며, 연동 해제와 데이터 삭제는 별도 조작으로 제공한다.
- 체크인 원자료는 28일, 웨어러블 원본은 24시간, 일별 요약·상세 수행·설문은 90일, 주간 리포트는 12개월을 기본 보유기간으로 한다.
- 탈퇴·삭제 요청 즉시 접근과 동기화를 차단하고 운영 DB 연결 데이터는 7일 이내 삭제, 백업은 30일 이내 순환 삭제한다. 관리자 접속기록은 2년 보관한다.
- 마스킹 오류 로그는 7일 이내 보유하며, 삭제 후 재식별 가능한 decision·proposal·feedback은 기본 보존하지 않는다.

계정 삭제의 상세 상태·실패 복구·backup restore 계약은 `ACCEPTED` ADR-0008과
`account-deletion-policy-v1`을 따른다.

### 13.1.1 계정 삭제 상태와 접근

- 사용자 상태는 `ACTIVE -> DELETION_PENDING -> users row hard delete`다. 완료 상태를 위해
  사용자 row를 유지하지 않는다.
- 삭제 요청은 철회할 수 없다.
- `DELETION_PENDING` 전환 즉시 모든 인증 사용자 제품 API와 외부 동기화를 차단한다. 비인증
  health와 기존 삭제 요청을 멱등 재처리하는 deletion lifecycle 경계만 허용한다.
- 이미 `DELETION_PENDING`인 사용자가 새 `Idempotency-Key`로 요청해도 최초 request ID와
  deadline을 반환하고 새 request/job을 만들지 않는다.
- 7일은 `requested_at`부터 기다리는 기간이 아니라 즉시 실행 가능한 운영 DB hard delete의
  완료 상한이다. backup과 restore-block tombstone은 `requested_at + 30일` 이내 만료한다.

삭제 job 상태는 다음 machine code를 사용한다.

```text
PENDING
RUNNING
RETRY_PENDING
BACKUP_EXPIRY_PENDING
COMPLETED
COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE
FAILED_REQUIRES_REVIEW
```

고정 단계는 `ACCESS_BLOCK -> EXTERNAL_REVOCATION -> OPERATIONAL_DATA_DELETE ->
CACHE_AND_WORK_DELETE -> AUDIT_DEIDENTIFICATION -> BACKUP_EXPIRY_VERIFICATION`이다. 완료 단계는
재실행 시 건너뛰고 실패 단계부터 재개한다. 존재하지 않는 대상 삭제는 성공으로 처리하며 외부
호출을 운영 DB hard-delete transaction 안에 포함하지 않는다.

### 13.1.2 provider 실패와 최종 상태

- provider 해제 실패는 `RETRY_PENDING`으로 두고 운영 DB 삭제 기한 전까지 재시도한다.
- 기한까지 실패하면 provider 상태를 `FAILED_FINAL`로 확정하고 provider 식별자를 더 보존하지 않는다.
- provider 실패와 무관하게 로컬 사용자 연결 데이터는 7일 이내 hard delete한다.
- backup 만료 증적 확인 후 최종 job 상태는
  `COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE`다.
- 운영 DB 삭제 자체가 기한 내 완료되지 않으면 `FAILED_REQUIRES_REVIEW`이며 접근 차단을 유지하고
  개인정보 사고 대응 대상으로 에스컬레이션한다.

### 13.1.3 삭제 대상·비식별 집계·감사

- identity, profile, 암호화 생년월일, consent, routine/context, integration, decision/proposal,
  workout/feedback, weekly report/plan, idempotency, cache/work payload 등 모든 user-linked 또는
  재식별 가능한 데이터는 7일 기한을 적용한다.
- 일반 데이터별 28일·90일·12개월 보유기간보다 명시적 계정 삭제 기한이 우선한다.
- 개인과 다시 연결할 수 없고 다른 데이터와 결합해도 singling-out할 수 없는 집계만 보존할 수
  있다. 가명·해시·user ID 제거만으로는 비식별 집계가 아니다.
- hard delete 후 감사에는 UUIDv4 request/job ID, 상태·단계·policy version, attempt count,
  구조화 failure code와 기한·완료 시각만 허용한다. user/provider ID, 생년월일, token,
  idempotency key, 요청·응답, 원시 오류·건강 snapshot을 금지한다.
- restore-block tombstone은 `requested_at + 30일`을 넘겨 보존하지 않는다. identifier-free opaque
  감사의 정확한 보존기간은 별도 PM·법률/개인정보 승인 전까지 하드코딩하지 않는다.
- restore-block tombstone은 내부 user UUID의 HMAC-SHA256 keyed digest, opaque request ID,
  policy version, 생성·만료 시각만 가진다. key는 secret manager 경계에 두고 분석·추적에 재사용하지 않는다.
- backup expiry는 단순 경과 시간이 아니라 해당 사용자를 포함할 수 있는 마지막 recovery point의
  만료 증적이 확인된 경우에만 완료된다.

---

## 14. 재현성과 감사

모든 decision run은 다음을 저장한다.

- 정규화된 입력 스냅샷과 해시
- 기본 루틴 버전
- 운동 카탈로그 버전
- 정책 버전
- 안전 규칙 버전
- 시간 계산 규칙 버전
- 조정기 버전
- 전문 에이전트 proposal
- 후보와 안전 검증 결과
- 최종 옵션
- LLM 사용 시 모델과 프롬프트 버전

동일한 입력 스냅샷과 동일한 결정 규칙 버전은 동일한 운동 후보와 최종 액션을 만들어야 한다. LLM 문구는 결정 재현성의 일부로 사용하지 않는다.

---

## 15. 필수 골든 시나리오

1. 통증 없음, 프로필 희망 시간 확인: KEEP
2. 상체 근력 40분 요청과 피로 MODERATE: 요청 시간과 CORE를 보존한 강도 DOWNSHIFT, `estimated_duration_seconds=2400`
3. 프로필 40분에서 사용자가 당일 30분으로 변경: 30분 요청과 `estimated_duration_seconds=1800`을 사용하고 임의 추가 축소 없음
4. 무릎 MILD 또는 MODERATE: 검수된 충돌 운동 제외와 대체 후보
5. 무릎 SEVERE: REST, 운동 계획 없음
6. 긴급 중단 그룹 입력: STOP_AND_SEEK_HELP, 운동 계획 없음
7. 마지막 공식 완료 후 13일: 복귀 모드 비활성
8. 마지막 공식 완료 후 14일: 복귀 모드 활성화
9. 예정 운동 연속 미수행: 복귀 모드 비활성, 비벌점 학습 신호만 생성
10. 웨어러블 없음: 수동 체크인으로 정상 결정
11. LLM 실패: 동일 계획과 템플릿 설명
12. 안전 veto된 후보: 최종 루틴으로 반환하지 않음
13. REST 선택: 당일 압박 알림 차단
14. 필수 agent 하나 실패: FAILED, 운동 계획 없음
15. 운동 블록 일부 완료 체크: 경과 시간과 무관하게 PARTIAL
16. 모든 운동 블록 완료 체크: 경과 시간과 무관하게 COMPLETED
17. 완료 블록 없음: 경과 시간이 길어도 NOT_COMPLETED
18. 운동 중 안전 중단: STOPPED_FOR_SAFETY와 승인 reason/guidance code
19. 닫히지 않은 주 리포트 요청: 거부
20. 직전 주 리포트 미확인 상태의 다음 계획 확정: 거부
21. AI 수정 2회 이후 추가 AI 수정: 거부, 직접 편집 경로 제공
22. ACTIVE 사용자 삭제 요청: 즉시 `DELETION_PENDING`, 동일 요청과 새 키 재요청은 최초 request 반환
23. 삭제 요청 직후 인증 사용자 제품 API와 외부 동기화 차단
24. 삭제 job은 요청 즉시 실행 가능하고 7일 경계까지 운영 DB hard delete 완료
25. provider 해제 실패: 기한 전 재시도, 기한 후 로컬 삭제와 최종 실패 상태 보존
26. 일부 repository 삭제 transaction 실패: 부분 commit 없이 같은 단계 재실행
27. 재실행: 완료 checkpoint를 건너뛰고 실패 단계부터 결정적으로 재개
28. 사용자 연결 decision·proposal·feedback·생년월일·idempotency 삭제
29. 재식별 가능 집계는 삭제하고 불가역 비식별 집계만 보존
30. opaque 감사·로그·snapshot에 사용자/provider 식별정보와 원시 건강 데이터 없음
31. backup restore tombstone은 일치 계정을 차단하고 요청 후 30일에 만료
32. backup expiry 운영 증적 전에는 삭제 job `COMPLETED` 금지

---

## 16. 아직 필요한 후속 승인

- 수면 부족과 최근 운동 부하 누적의 수치 정책
- 복귀 모드 첫 세션의 정확한 볼륨 상한
- requested duration의 지원 범위와 정확히 구성할 수 없을 때의 `NEEDS_INPUT`/`BLOCKED` 처리 정책
- 각 신체 부위와 운동 패턴의 제외 규칙
- 회복 콘텐츠 목록
- 안전 문구의 외부 도메인 최종 검수
- PAR-Q+ 문항 사용 여부와 번역·라이선스
- 주간 리포트 acknowledgement UX

이 항목은 별도의 승인 없이 임의의 의료 또는 안전 기준으로 구현하지 않는다.

## 17. 결정 이유와 대안

선택한 방식은 결정적 규칙이 후보를 만들고 제한한 뒤 구조화된 전문 에이전트와 조정기가 승인 후보를 선택하는 구조다. 안전 veto, 요청 시간 보존, 주간 게이트와 블록 기반 수행 상태를 재현하고 테스트할 수 있기 때문이다.

선택하지 않은 대안:

- LLM이 자유 형식 계획 생성: 검수 카탈로그와 안전 veto를 우회할 수 있어 제외
- 하나의 종합 점수로 모든 목적 결정: 어떤 제약이 결과를 바꿨는지 설명·감사하기 어려워 제외
- 필수 agent 장애 시 일부 proposal로 계속 진행: 요구사항의 fail-closed 원칙과 맞지 않아 제외
- 경과 시간이나 웨어러블로 공식 완료 판정: 사용자가 어떤 운동 블록을 실제 수행했는지 보장할 수 없어 제외

## 18. 팀 확인 질문

- 수면 부족, 최근 부하, 복귀 첫 세션의 전문가 승인 상한은 무엇인가?
- 계획 시간이 요청 시간과 정확히 일치하더라도 실제 경과 시간은 달라질 수 있음을 UI에서 어떤 문구로 표시할 것인가?
- 주간 리포트 명시적 확인 버튼의 최종 문구와 배치는 무엇인가?
- 안전 문구와 부위별 제외표의 최종 외부 승인자는 누구인가?
