# DOMAIN_RULES.md

## 1. 문서 목적과 적용 순서

이 문서는 오늘의 운동 계획을 유지, 축소, 변경, 회복, 휴식 또는 중단 안내로 조정하는 MVP 도메인 규칙을 정의한다.

이 규칙은 의료 진단, 치료 또는 재활 처방이 아니다. 사용자가 직접 보고한 상태를 이용해 검수된 운동 후보를 제한하는 제품 정책이다.

현재 멀티 에이전트 핵심 흐름은 Training·Recovery·Safety·Feasibility 네 proposal의 병렬 실행과 Coordinator 최종 결정으로 확정한다. 에이전트별 상세 입력·출력·proposal JSON 구조와 공개 요약 필드는 증상 사용자 시나리오 검증 결과에 따라 추후 보완할 수 있으며, 독립적인 최종 Safety 재검사는 현재 범위에 포함하지 않는다.

ADR-0012의 2라운드 구조화 상호검토는 승인된 V2 목표다. A2 기준 구현과 필수 검증이 병합되기
전에는 아래 현재 계약을 production 기준으로 유지하며, 8.1을 구현 완료나 새 안전 정책 승인으로
해석하지 않는다.

ADR-0013의 Safety-first LLM 멀티에이전트 V3 목표 계약은 `ACCEPTED`다. 8.2와 9.1은 구현·비교
검증과 production 전환 승인 전까지 현재 V1/V2의 네 proposal, 결정적 Coordinator와
narration-only LLM production 경계를 바꾸지 않는다. Qdrant 세부 목표 계약인 ADR-0014는
`ACCEPTED` 상태이지만 adapter·migration·shadow 검증 전에는 production 구현 완료로 간주하지 않는다.

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
- 다운시프트는 요청 시간을 유지하면서 부하·강도·세트·반복·운동 유형·휴식 구성을 조정한다. 승인된 운동 풀로 요청 시간을 정확히 채울 수 없을 때는 ±5분 이내에서 가장 가까운 계획을 선택한다.
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

Safety service actions:

```text
LOAD_REDUCED
ROM_REDUCED
ACTIVE_RECOVERY
SKIP_AFFECTED_AREA
STOP_EXERCISE
```
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

한 체크인 또는 안전 이벤트에서 여러 부위를 선택할 수 있다. `OTHER`는 온보딩 저장값이 아니다.
온보딩 UI에서 기본 노출되지 않은 실제 `body_area_code` 목록을 여는 control code로만 사용하고,
사용자가 고른 각 실제 code를 저장한다. Qdrant payload/vector/embedding query에는 어떤 통증 부위도
포함하지 않는다.

이 코드 집합은 안정적이며 화면 노출 범위와 분리한다. 클라이언트가 선택지를 줄이더라도 코드
자체를 줄이지 않는다. 다만 **사용자가 고를 수 없는 부위는 해당 규칙이 발동하지 않는다.** 노출
목록을 줄이는 변경은 안전 커버리지를 줄이는 변경이므로 4.3.1의 규칙 분포를 함께 확인한다.

### 3.3 불편 심각도

| 값 | 코드 | 사용자 표시 | 제품 판단 |
|---:|---|---|---|
| 0 | NONE | 불편함 없음 | 일반 판단 |
| 1 | MILD | 조금 불편함 | 관련 동작 수정 또는 제외 검토 |
| 2 | MODERATE | 움직임에 영향을 줌 | 관련 동작 제외, 대체 또는 회복안 |
| 3 | SEVERE | 운동하기 어려움 | 운동 계획 제공 중단, 휴식·확인 안내 |

이 값은 의료적 통증 척도로 해석하지 않는다.

### 3.3.1 온보딩 통증 입력과 점수 변환

신규 온보딩 계약은 `pain_present`와 `PainAreaInput[] pain_areas`를 사용한다.

```text
PainAreaInput
- body_area_code
- intensity_score: integer 1..10
```

검증은 결정적이다.

- `pain_present=false`이면 `pain_areas=[]`여야 한다.
- `pain_present=true`이면 `pain_areas`가 한 개 이상이어야 한다.
- `body_area_code`는 중복할 수 없고 `OTHER`를 직접 저장할 수 없다.
- 선택한 모든 부위에는 1..10의 정수 `intensity_score`가 필수다.
- UI는 `NECK`, `LOWER_BACK`, `SHOULDER`를 기본 노출한다. `OTHER` control을 누르면 `OTHER`를
  제외한 나머지 실제 body area code를 복수 선택할 수 있다.

결정 정책 `pain-intensity-action-v2`는 원점수 구간별 서비스 액션을 다음과 같이 결정한다.

| intensity_score | severity_code | service_action | alternative policy |
|---:|---|---|---|
| 1..3 | `MILD` | `LOAD_REDUCED` | 같은 목표 → 부하 감소 → ROM 감소 → 쉬운 변형 |
| 4..7 | `MODERATE` | `SKIP_AFFECTED_AREA` | 통증 부위 제외 → `ACTIVE_RECOVERY` |
| 8..10 | `SEVERE` | `STOP_EXERCISE` | 대체운동 없음 |

원점수와 변환된 code, `pain-intensity-action-v2`를 함께 보존해 재현한다. 이 구간은 안전·통증 정책
변경이므로 개발팀장, PM과 외부 도메인 검수 승인 전 production에서 활성화하지 않는다. 현재 데이터는
도메인 승인 입력으로 생성하지만 `production_eligible=false`다. 승인 전에는
기존 `attention_area_codes` 계약과 기존 severity 입력 경로를 유지하며 점수를 추정하거나 backfill하지
않는다.

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

다음 중 하나면 `STOP_EXERCISE`를 반환한다.

- 한 부위라도 NRS 7–10
- 급성 근골격 신호 그룹의 코드가 있음
- 운동 중 통증 증가·갑작스러운 통증·부종·감각 이상·체중부하 불가가 발생함

`STOP_EXERCISE`에는 대체 운동과 final_plan을 제공하지 않는다. 긴급 중단 그룹은
`STOP_AND_SEEK_HELP`로 별도 처리한다.

### 4.3 특정 부위 불편

NRS 구간별로 다음과 같이 처리한다.

- 불편 부위가 명확함
- NRS 1–3: 원래 목표를 유지하고 부하 감소, ROM 감소, 쉬운 변형 순으로 적용한다.
- NRS 4–6: 통증 부위를 primary·secondary 모두에서 제외하고 저강도 `ACTIVE_RECOVERY` 후보를 사용한다.
- NRS 7–10: 대체 후보를 만들지 않고 `STOP_EXERCISE`를 반환한다.
- 긴급 중단 그룹과 급성 근골격 신호 그룹이 모두 비어 있음
- 후보가 있는 경우 `DOMAIN_APPROVED` 상태의 대체 운동이어야 함
- 대체 운동이 현재 장소와 장비를 충족함

NRS 1–3의 서비스 액션은 `LOAD_REDUCED` 또는 `ROM_REDUCED`이며, 후보가 없으면 원 운동에
해당 다운시프트를 적용한다. NRS 4–6의 서비스 액션은 `SKIP_AFFECTED_AREA`이며
`ACTIVE_RECOVERY` 후보를 제공한다. NRS 7–10은 대체 운동을 제공하지 않는다.

### 4.3.1 안전 규칙 레코드 해석

4.3은 "DOMAIN_APPROVED 상태의 통증 제외 규칙이 있음"을 전제로 한다. 이 절은 그 규칙 레코드를
어떻게 읽는지 정한다. 규칙 자체를 새로 만들지 않으며, 4.3의 판단을 구현 가능한 수준으로 좁힌다.

각 규칙 레코드는 자신이 적용되는 심각도 범위와 효과를 스스로 선언한다.

| 필드 | 의미 |
|---|---|
| `body_area_code` | 규칙이 대응하는 불편 부위 |
| `minimum_severity_code` | 이 규칙이 적용되기 시작하는 심각도 |
| `maximum_severity_code` | 이 규칙이 적용되는 최대 심각도 |
| `effect_code` | `EXCLUDE` 또는 `CAUTION` |
| `rule_scope` | `EXERCISE` 또는 `MOVEMENT_PATTERN` |
| `reason_code` | 규칙 근거. 사용자에게 노출하지 않는다 |
| `review_status_code` | `DOMAIN_APPROVED`만 사용한다 |

#### 적용 규칙

1. 보고된 부위와 `body_area_code`가 일치하고, 보고된 심각도가
   `[minimum_severity_code, maximum_severity_code]` 범위에 포함되는 규칙만 적용한다.
2. 심각도별로 효과를 임의 매핑하지 않는다. **효과는 규칙 레코드가 결정한다.**
   경미한 불편이라도 `EXCLUDE` 규칙이 걸리면 해당 운동을 제외한다.
3. `EXCLUDE`는 해당 운동 또는 동작 패턴을 계획에서 제외한다.
4. `CAUTION`은 제외하지 않고 부하를 낮춘다. 강도, 세트, 반복, 난이도, 휴식 구조로만 낮춘다.
5. `rule_scope`가 `MOVEMENT_PATTERN`이면 해당 패턴에 속한 모든 운동에 적용한다.
6. 한 운동에 여러 규칙이 걸리면 `EXCLUDE`가 `CAUTION`보다 우선한다.
7. `review_status_code`가 `DOMAIN_APPROVED`가 아닌 규칙은 무시하지 않고 **적재 단계에서 배제한다.**
   미검수 규칙이 결정 경로에 들어오면 안 된다.

#### 적용 후 판단

제외와 부하 조정을 적용한 뒤에도 4.3의 나머지 조건이 그대로 적용된다. 목표 보존형 대체 계획이
만들어지면 CHANGE, 만들 수 없고 검수된 저강도 회복 계획이 가능하면 RECOVERY, 그것도 없으면 REST다.

부위 불편이 있으나 해당 부위에 적용 가능한 DOMAIN_APPROVED 규칙이 하나도 없으면 계획을
반환하지 않는다. 이는 fail-closed 동작이며 규칙 부재를 안전으로 간주하지 않겠다는 뜻이다.

#### 요청 시간

요청 시간을 ±5분을 넘겨 임의로 줄이지 않는다. 5절과 6절의 시간 보존 규칙이 그대로 적용된다.

#### 만성 주의 부위

온보딩에서 받은 주의 부위는 상시 입력으로 취급해 매일 다시 묻지 않는다. 당일 체크인에 해당
부위의 불편이 보고되지 않았더라도 만성 주의 부위에 대해 `CAUTION` 효과를 적용한다. `EXCLUDE`는
당일 보고된 불편에만 적용한다. 만성 입력만으로 운동을 제외하면 사용자가 영구적으로 특정 운동에
접근할 수 없게 되기 때문이다.

#### 사용자 문구

12.1과 12.2의 검수된 문구를 그대로 사용한다. 규칙의 `reason_code`와 내부 규칙 식별자는
사용자에게 노출하지 않는다.

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

`requested_duration_minutes`는 최종 루틴의 계획 시간 목표(분)다. 프로필 기본값을 사용하되 사용자가 당일 명시적으로 변경하면 그 값을 새 목표로 사용한다. 운동 계획을 반환하는 경우 계획의 `estimated_duration_seconds`는 `requested_duration_minutes * 60`을 목표로 하며, 승인된 운동 풀로 정확히 맞출 수 없을 때에 한해 ±300초 이내의 편차를 허용한다. 편차가 가장 작은 계획을 우선 선택하고, 허용 범위를 넘으면 계획을 반환하지 않고 실패한다. 시스템은 사용자 변경 없이 이 범위를 넘겨 시간을 줄이거나 초과할 수 없다.

이 허용 범위는 2026-08-27 프로젝트 오너 승인으로 도입됐다. 근거와 경위는 `docs/tasks/TASK-ROUTINE-EQUIPMENT-AND-DURATION.md`에 있다. 구현 상수는 `backend/app/modules/routines/service.py`의 `DURATION_TOLERANCE_SECONDS`다.

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

### 8.1 승인된 V2 구조화 상호검토 목표 계약

ADR-0012에 따라 A2는 현재 네 독립 proposal을 Round 1로 유지하고, 그 뒤 결정적 conflict detector와
최대 한 번의 Round 2 review를 추가한다.

#### 상태 전이

1. Round 1 네 proposal 누락·`FAILED`는 decision `FAILED`다.
2. `FAILED`가 없고 `NEEDS_INPUT`이 있으면 계획 없는 `NEEDS_INPUT`이다.
3. 네 proposal이 `READY`일 때만 conflict detector를 실행한다.
4. conflict가 없으면 Round 2를 `SKIPPED_NO_CONFLICT`로 기록하고, 네 Agent 모두 Agent 호출 없는
   `NOT_REQUIRED` event를 남긴 뒤 Coordinator로 진행한다.
5. conflict가 있으면 영향받는 Agent만 review 대상이며 나머지는 `NOT_REQUIRED` event를 남긴다.
6. 대상 review 누락·`FAILED`는 decision `FAILED`, `NEEDS_INPUT`은 계획 없는 `NEEDS_INPUT`이다.
7. Round 2 후 추가 토론은 하지 않고 constraint integrity 검증과 Coordinator로 종료한다.

#### `AgentReview` 최소 논리 필드

- `review_schema_version`, `round_number=2`, `agent_type_code`
- `review_status_code`: `READY | NOT_REQUIRED | NEEDS_INPUT | FAILED`
- `revision_status_code`: `UNCHANGED | REVISED | NOT_REQUIRED | null`. `NEEDS_INPUT`·`FAILED`에는 null
- `baseline_proposal_hash`, canonical `(agent_type_code, proposal_hash)` 구조의
  `reviewed_proposal_references`
- canonical `reviewed_agent_types`
- `accepted_constraint_codes`, `unresolved_conflict_codes`
- `revision_reason_codes`, `evidence_reference_codes`
- `revised_proposal`: `REVISED`일 때만 존재

review는 machine code와 승인 후보 ID만 포함하고 자유 텍스트 reasoning, prompt, 예외 문자열을
포함하지 않는다. revised proposal은 Round 1과 같은 Pydantic 불변식을 다시 통과해야 한다.

#### 권한과 단조성

- 요청 시간·시간 출처·승인 후보 집합·입력/정책/카탈로그/규칙 버전은 변경할 수 없다.
- Safety `BLOCKED`, `REST`, `STOP_AND_SEEK_HELP`, veto와 제외 운동은 완화할 수 없다.
- Safety Agent만 veto를 `false -> true`로 강화하거나 제외 운동을 추가할 수 있다.
- Feasibility의 장소·장비·가용 시간 불가능 조건은 다른 Agent 선호로 해제할 수 없다.
- 승인 정책이 만든 Recovery 최대 강도·부하·볼륨·복귀 상한을 Training이 초과할 수 없다.
- Training primary goal은 위 hard constraint 안에서 보존한다. 동시에 만족할 후보가 없으면 목표나
  시간을 임의로 바꾸지 않고 기존 계약의 `REST`, `NEEDS_INPUT` 또는 `FAILED`로 종료한다.
- conflict detector와 integrity validator는 결정적 Python 규칙이며 LLM을 호출하지 않는다.
- integrity validator는 Safety proposal 보존을 검사하며 안전 규칙을 재실행하는 FinalSafetyGate가 아니다.

#### Agent Tool 경계

Agent는 DB, repository, FastAPI, ORM, LLM SDK와 외부 API를 직접 호출하지 않는다. application
service는 검수 catalog, 목표·루틴 policy, Recovery ceiling, Safety rule·대체, 정확한 시간 계산,
장소·장비 호환성의 정규화·버전화된 결과를 immutable request로 조립한다. Tool 장애가 필수 판단을
막으면 고정 failure code로 fail-closed하며 예외 원문이나 사용자 원문을 복사하지 않는다.

### 8.2 승인된 V3 Safety-first LLM Agent 목표 계약

V3는 Safety를 LLM Agent로 실행하지 않는다. 결정적 `SafetyPolicyEngine`이 Agent 호출 전에 다음을
포함한 immutable `ConstraintEnvelope`를 만든다.

- `plan_generation_allowed`, `required_action_code`, safety status와 veto
- excluded exercise ID와 승인 대체 범위
- 요청 시간과 시간 출처
- primary goal과 required goal tag
- intensity·load·volume·return ceiling
- 장소·장비와 실행 가능 hard constraint
- input, policy, safety, duration, catalog schema/version/hash

application loader는 같은 catalog version의 PostgreSQL에서 production-approved 운동을 결정적으로
필터링해 eligible/mandatory ID를 먼저 만든다. ADR-0014에 따라 `ExerciseRetriever`가 별도 Qdrant
derived index에서 eligible 범위 안의 순위·다양성만 계산하고, application loader가 결과를
PostgreSQL에서 다시 조회·검증해 canonical `ExercisePoolSnapshot`을 만든다. 필수 목표 운동과 승인된
안전 대체는 Vector 결과와 무관하게 보존한다. 각 항목은 exercise ID, goal/location/equipment tag,
검수 처방 범위와 content version만 포함한다. Agent와 Coordinator는 DB·repository·ORM·raw SQL·
Qdrant를 직접 호출하지 않는다.

Qdrant unavailable/not-ready/timeout, stale result와 catalog/index/embedding version mismatch에서는
결과를 폐기하고 같은 envelope를 만족하는 결정적 후보 생성으로 fallback한다. fallback도 PostgreSQL
재검증과 mandatory 보존을 통과해야 한다. Vector 장애는 Safety veto를 완화하거나 새 안전 실패를
만들지 않는다.

Round 1 LLM Agent는 `TRAINING`, `RECOVERY`, `FEASIBILITY` 세 개다. 동일 envelope와 pool을 받아
LangGraph에서 병렬 실행하고 LangChain/Pydantic structured output만 반환한다. Training은 pool 안에서
PlanSpec 초안을 만들고, Recovery는 승인 ceiling 안의 조정, Feasibility는 장소·장비·시간 안의 실행
가능성 proposal을 만든다.

결정적 conflict detector는 Agent 상호 간뿐 아니라 envelope 위반도 검사한다. conflict가 있을 때만
영향 Agent를 최대 한 번 review하고 비대상 Agent는 `NOT_REQUIRED`를 저장한다. Safety veto, 생성 금지,
요청 시간, pool, version, Recovery/return ceiling과 Feasibility 불가능 조건은 review나 Coordinator가
완화할 수 없다.

LLM Coordinator는 proposal·review를 종합·선택해 하나의 `PlanSpec`을 반환한다. Plan Compiler는
exercise reference, sequence, set/rep/work/rest/transition과 정확한 시간을 결정적으로 계산한다. 최종
integrity validator는 원시 통증·이상 반응을 재분류하지 않고 compiled plan이 envelope의 safety,
duration, goal, equipment/location, catalog와 schema constraint를 지켰는지만 검사한다.

repairable violation은 machine code로 Coordinator에 한 번만 반환한다. 요청 시간, 세트·반복,
Recovery ceiling, 순서·schema, 필수 목표, 장비, 승인 대체가 있는 제외 운동 위반만 repair 대상이다.
`STOP_AND_SEEK_HELP`, 생성 금지 veto, 안전 운동 없음, 필수 입력 누락, 정책 데이터 불완전, provider
전체 장애와 repair 재실패는 Coordinator로 돌아가지 않는다. deterministic fallback도 같은 compiler와
validator를 통과해야 하며 `STOP_AND_SEEK_HELP`를 REST나 plan으로 바꿀 수 없다.

#### V3 수동 재생성

추가 입력 없는 재생성은 유효한 기존 snapshot·envelope·pool을 재사용하고 `RegenerationContext`를
추가해 세 전문 Agent부터 다시 실행한다. Coordinator만 재실행하지 않는다. context에는 attempt,
이전 plan hash·exercise 순서·구조, exact duplicate 금지와 variation code를 포함한다.

새 plan은 핵심 운동, 운동 순서, 승인된 세트·반복 구조 또는 루틴 구성 방식 중 하나 이상이 의미 있게
달라야 한다. 설명·UUID·미미한 시간 변경만으로는 통과하지 않는다. 안전하고 목표를 보존하는 대안이
없으면 constraint를 약화하지 않고 `NO_ALTERNATIVE_AVAILABLE`로 종료한다. 성공 재생성은 root
decision당 최대 두 번이고 idempotent하다. snapshot/envelope/pool이 stale하거나 safety·catalog·policy
version이 바뀌면 새 decision/check-in 경로가 필요하다.

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
- 최종 결정 이후 공개 가능한 deliberation event code의 사용자용 문장 변환

LLM에는 직접 식별자, 원시 건강 기록, 원시 웨어러블 샘플을 보내지 않는다. LLM 실패 시 검수된 템플릿 문구를 사용하며 계획 결과는 바뀌지 않는다.

V2 narration은 Agent별 provider 호출이나 자유 토론이 아니라 한 번의 bounded batch다.
application log, 날짜, 자유 체크인, hidden reasoning, graph checkpoint를 입력으로 사용하지 않는다.
safety status가 `PASS/REVISE`가 아니거나 최종 action이 `REST/STOP_AND_SEEK_HELP`이거나 Safety
veto가 있는 결과는 LLM을 호출하지 않고 검수 템플릿을 사용한다.

### 9.1 승인된 V3 목표 LLM 경계

V3가 구현·검증되어 production 전환되면 LLM은 세 전문 proposal, conflict에 영향받은 Agent의 한 번 review, Coordinator
initial/repair와 일반 narration에 참여할 수 있다. SafetyPolicyEngine, constraint builder, conflict
detector, Plan Compiler, integrity validator와 fallback policy는 LLM을 호출하지 않는다.

Agent input은 직접 식별자를 제거한 input snapshot, ConstraintEnvelope, ExercisePoolSnapshot,
machine code와 최소 normalized summary로 제한한다. 날짜, 자유 체크인, raw 건강·웨어러블·캘린더 값,
application log, prompt 원문, hidden reasoning, provider 예외 원문을 전달·저장하지 않는다.
통증 부위와 `intensity_score`/severity는 Qdrant vector, payload, embedding input/query에도 포함하지
않는다.

structured output validation 또는 required Agent가 최종 실패하면 부분 proposal로 계속하지 않는다.
결정적 fallback을 사용하고 같은 envelope를 검증하거나 계획 없는 상태로 종료한다. LLM fresh inference의
동일성은 보장하지 않으며 저장된 structured output과 version으로 provider 재호출 없이 replay한다.

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
| NRS 1–3 | `SHOW_CAUTION` | `LOAD_REDUCED` 또는 `ROM_REDUCED` | `IN_PROGRESS` | `MILD_DISCOMFORT` | `MILD_DISCOMFORT_CAUTION` |
| NRS 4–6 | `SHOW_CAUTION` | `SKIP_AFFECTED_AREA` 또는 `ACTIVE_RECOVERY` | `IN_PROGRESS` | `MODERATE_DISCOMFORT` | `MODERATE_DISCOMFORT_CAUTION` |
| NRS 7–10 | `STOP_SESSION` | `STOP_EXERCISE` | `STOPPED_FOR_SAFETY` | `SEVERE_DISCOMFORT` | `SEVERE_OR_ACUTE_STOP` |
| 급성 근골격 신호 | `STOP_SESSION` | `STOP_EXERCISE` | `STOPPED_FOR_SAFETY` | `ACUTE_MUSCULOSKELETAL_REACTION` | `SEVERE_OR_ACUTE_STOP` |
| 긴급 중단 그룹 | `STOP_AND_SEEK_HELP` | `STOP_AND_SEEK_HELP` | `STOPPED_FOR_SAFETY` | `EMERGENCY_ADVERSE_REACTION` | `SERIOUS_ADVERSE_REACTION_STOP` |

긴급 중단 그룹은 다른 안전 이벤트보다 우선하며 veto를 유지한다. NRS 1–7 이벤트는 위의
검수된 동적 재구성 정책에 따라 처리한다. COMPLETED, PARTIAL,
NOT_COMPLETED, STOPPED_FOR_SAFETY로 종료된 세션의 블록과 상태는 변경할 수 없다.

운동 후 신규 공개 feedback은 `difficulty_code=EASY|APPROPRIATE|HARD` 하나만 받는다. 표시 문구는
각각 `쉬웠어요`, `적당했어요`, `어려워요`다. 운동 후 통증·이상 반응 수집을 feedback에 중복하지
않고 운동 중 Safety Event API를 유지한다. 기존 fatigue/satisfaction/pain/discomfort/adverse 필드는
호환 기간 동안만 읽기·legacy write를 지원하고 새 client는 보내지 않는다. 기존 값을 삭제하거나
통증 없음으로 재해석하지 않는다.

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
- 신규 `pain_report_count`의 canonical 원천은 해당 주의 `workout_safety_event_discomforts`가 존재하는
  distinct workout session 수다. 동일 세션의 여러 event/부위는 한 번만 센다. 호환 기간의 legacy
  `workout_feedback.pain_occurred=true`는 safety event가 없는 historical session에 한해 한 번 포함하고
  중복 집계하지 않는다. onboarding pain과 daily check-in은 주간 운동 중 통증 보고 수에 포함하지
  않는다. 집계 전환은 새 aggregate schema/report policy version으로 구분한다.

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
| 캘린더 미연결·권한 거부 | 수동 체크인과 앱 운동 블록 체크를 유지하고 계획을 변경하지 않음 |
| 캘린더 provider 장애 | `PROVIDER_UNAVAILABLE`, 계획을 삭제·변경하지 않고 수동 경로 유지 |
| 선택 데이터 누락 | 칼로리 값은 `null`로 유지하고 의료 상태를 추론하지 않음 |
| LLM 장애 | 템플릿 설명 사용 |
| 필수 전문 에이전트 하나라도 장애 | FAILED, 운동 계획을 성공 응답으로 반환하지 않음 |
| 필수 안전 규칙 장애 | FAILED, 운동 계획을 성공 응답으로 반환하지 않음 |
| 검수된 안전 후보 없음 | REST |
| DB 저장 실패 | 재현할 수 없는 계획을 클라이언트에 반환하지 않음 |
| 중복 mutation | Idempotency-Key의 기존 결과 반환 |
| 오래된 체크인 버전 | STALE_CONTEXT 오류 |
| Qdrant unavailable/not-ready/version mismatch/timeout/stale 결과 | 결과 폐기, PostgreSQL 결정적 pool fallback |

V3에서는 `LLM 장애`를 narration과 decision Agent로 구분한다. narration 장애는 템플릿을 사용한다.
필수 decision Agent·Coordinator provider 장애는 부분 LLM 결과를 버리고 검증된 결정적 fallback을
사용하며, fallback이 없으면 `FAILED`다. SafetyPolicyEngine이 이미 `REST` 또는
`STOP_AND_SEEK_HELP`를 확정한 경우 provider를 호출하지 않고 그 결과를 유지한다.

Vector retrieval 원인 code는 `VECTOR_INDEX_UNAVAILABLE`, `VECTOR_INDEX_NOT_READY`,
`VECTOR_INDEX_VERSION_MISMATCH`, `VECTOR_SEARCH_TIMEOUT`, `VECTOR_RESULT_STALE`,
`VECTOR_RESULT_NOT_CANONICAL`, `VECTOR_RESULT_INSUFFICIENT`다. 결정적 pool을 실제 사용하면 원인과
별도로 `DETERMINISTIC_POOL_FALLBACK_USED`를 저장한다.

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

### 13.2 인증 provider와 identity 연결

인증 provider의 상세 계약은 `PROPOSED` ADR-0009와 `auth-provider-policy-v1`을 따른다. ADR이
`ACCEPTED`가 되기 전에는 실제 route·adapter·migration을 구현하지 않는다.

- 첫 구현 provider는 KAKAO backend authorization-code/OIDC다. FastAPI의 최종 권한은 항상
  Firebase ID Token이며 Google은 Firebase 기본 provider 경로만 사용한다.
- 신뢰 경로는 `verified provider subject -> Firebase principal -> internal user UUID`다. Firebase
  subject와 provider subject를 같은 값으로 추정하지 않는다.
- 같은 `(provider_code, provider_subject)` 반복 로그인은 같은 내부 user를 반환한다. 다른 user에
  연결된 subject는 `IDENTITY_ALREADY_LINKED`이며 email·이름·닉네임으로 자동 병합하지 않는다.
- 연결되지 않은 KAKAO subject는 별도 user로 만들고 로그인 결과를 현재 user에 암묵 연결하지 않는다.
  명시적 계정 연결 API는 MVP에서 제외한다. 향후 단독 해제는 마지막 활성 로그인 수단 제거를
  거부하며 이미 해제된 identity 재요청은 성공 no-op이어야 한다.
- 저장 가능한 identity 값은 내부 UUID/FK, provider code, 불변 provider subject, 상태·정책 버전,
  연결·해제·재시도 시각과 allowlist failure code다.
- email, email_verified, name, nickname, picture, phone, birthday, birthyear, age, gender, locale,
  provider 원본 응답과 모든 token은 identity 판단·저장·로그·snapshot·metric label에서 금지한다.
- Google은 추가 OAuth scope를 요청하지 않는다. Kakao/Naver 직접 adapter는 `openid`만 허용한다.
- 직접 adapter의 OAuth flow는 UUIDv4 flow ID, server-bound state, server allowlist redirect URI와
  PKCE S256을 사용한다. Kakao는 nonce도 필수다. Naver nonce는 확인한 공식 문서에 없으므로
  지원을 추정하지 않고 도입 전 재검토한다.
- authorization flow는 10분 후 만료하며 state·nonce·등록 redirect URI digest와 PKCE challenge만
  보관한다. exchange는 이를 검증하고 provider 호출 전에 row를 삭제·commit한다. 소비 row가 없으면
  `INVALID_OAUTH_STATE`이며 외부 실패에도 되살리지 않는다. authorization code, verifier,
  access/refresh/ID/custom token은 저장하지 않고 처리 후 폐기한다.
- authorize-init과 exchange는 PostgreSQL fixed window로 canonical IP 10회/분 및 provider·등록
  redirect URI 60회/시간을 제한한다. raw IP/URI 대신 secret-key HMAC digest만 window 동안 보관한다.
- timeout·5xx·provider rate limit은 retryable `PROVIDER_UNAVAILABLE`이다. signature·issuer·audience·
  expiry·nonce·subject 검증 실패를 provider 장애나 성공으로 매핑하지 않는다.
- 독립 연결 해제 실패는 1분, 5분, 30분, 2시간, 12시간 backoff로 총 5회·24시간 내 재시도한다.
  이후 `REVOCATION_FAILED_REQUIRES_REVIEW`이며 해당 identity 로그인 차단을 유지한다.
- 계정 삭제의 provider 해제는 위 독립 해제 예산이 아니라 ADR-0008의 7일·로컬 hard-delete 우선
  계약을 사용한다.

### 13.3 운동 가능 시간과 캘린더 외부 컨텍스트 정책

#### 13.3.1 현행 정책 — 사용자 수동 가능 시간

외부 캘린더(Google) 연동은 보류 상태다(ADR-0010 "구현 보류"). 따라서 운동 가능 시간의 유일한
입력원은 사용자가 일일 체크인에서 직접 입력한 값이다.

- 가능 시간 입력은 선택이다. 입력하지 않아도 체크인, 결정, 운동 실행, 주간 리포트의 핵심 흐름이
  모두 정상 동작한다.
- 미입력(`ROUTINE_DEFAULT`)과 명시적 빈 선택(`MANUAL`, 구간 0개)은 서로 다른 상태이며 서버가
  둘을 같게 취급하거나 누락값을 보완하지 않는다.
- 구간은 사용자 프로필 IANA timezone 기준으로 해당 `local_date`에 속해야 하고, 서로 겹치거나
  맞닿을 수 없으며 최대 8개다. 서버는 시작 시각 오름차순으로 정규화한다.
- 가능 시간은 참고 입력이다. 사용자의 희망 운동시간을 단축·연장하지 않고, 운동 계획·안전 판단·
  안전 veto·공식 운동 수행 상태를 바꾸지 않으며, 특정 요일을 필수 운동일로 강제하지 않는다.
- 일정 제목, 설명, 참석자, 장소, 링크 같은 캘린더 본문 성격의 값은 받지도 저장하지도 않는다.
- 후보 계산은 `select_availability`와 `AvailabilitySlot`을 그대로 사용한다. 캘린더 연동이 재개되면
  `CALENDAR` 입력원이 수동 입력보다 낮은 우선순위로 추가될 뿐 이 규칙은 바뀌지 않는다.

#### 13.3.2 보류된 캘린더 provider 정책

아래는 캘린더 연동이 재개될 때 적용할 승인된 계약이다. 현재는 구현하지 않는다.

Google Calendar의 provider별 상세 계약은 `ACCEPTED` ADR-0010과
`external-context-policy-v2`를 따른다. 실제 route·HTTP adapter·repository·migration은
TASK-BACKEND-007의 단계별 게이트를 따른다.

- 캘린더는 선택적 보조 컨텍스트다. 미연결·권한 거부·provider 장애에서도 수동 체크인과 앱 운동
  블록 체크를 포함한 핵심 흐름이 동작한다.
- `CALENDAR_INTEGRATION` 동의가 없거나 철회되면 provider 호출을 수행하지 않는다.
- availability는 저장된 사용자 IANA timezone의 로컬 하루와 literal `primary` calendar 하나를 Google
  freebusy 전용 scope로 조회한다. CalendarList, secondary/shared calendar, event list, 제목, 설명,
  참석자, 위치와 calendar 본문은 조회하지 않는다.
- freebusy는 종일 여부를 제공하지 않으므로 종일 여부를 시간 경계로 추정하지 않는다. provider가
  반환한 종일 포함 모든 busy 구간을 점유 시간으로 처리한다.
- 겹치거나 맞닿은 busy 구간을 병합한 뒤 각 빈 구간의 앞뒤 15분을 buffer로 제외한다. 남은 구간이
  사용자의 희망 운동시간보다 짧으면 후보를 만들지 않는다.
- 시간대 필터와 필수 운동 요일을 적용하지 않는다. 후보는 시작 시각 오름차순으로 최대 8개다.
- 후보가 없으면 빈 배열을 반환하고 사용자 희망 운동시간을 임의 단축하지 않는다.
- 사용자가 수동 가능 시간을 명시하면 명시적 빈 목록을 포함해 calendar 후보보다 항상 우선한다.
- 사용자별 availability 30회/시간과 전체 calendar endpoint 60회/시간을 provider 호출 전에 적용한다.
- availability는 cache하지 않아 stale 판정이 없고 성공값은 `freshness_code=LIVE`다. performance는
  공식 workout session 종료 상태 이후,
  같은 link의 직전 `performance_checked_at`부터 10분 뒤에만 재확인한다.
- Google Calendar는 운동 수행 필드가 없으므로 `performed=null`과 검수 fallback 안내를 반환한다.
  Google event를 다시 조회하지 않고 confirmed, tentative, cancelled, 삭제와 참석 응답을 운동 수행
  여부로 해석하지 않는다.
- Calendar event link는 `scheduled_workout_id`가 아니라 공식 block completion을 가진
  `workout_session_id`를 참조한다. 사용자 소유 `PLANNED` session에만 한 번 등록하고 server가 계획의
  요청 시간으로 `end_at`을 계산한다.
- 캘린더 관찰 결과는 workout session의 공식 `COMPLETED`, `PARTIAL`, `NOT_COMPLETED`,
  `STOPPED_FOR_SAFETY`를 생성·
  변경할 수 없다. 안전 veto와 수동 체크인보다 우선할 수 없다.
- raw freebusy/event payload 보유기간은 0시간이다. token 원문, calendar 본문과 provider 원시 오류를
  DB, cache, log, metric, trace, snapshot, fixture와 LLM 입력에 포함하지 않는다.
- 보조 캘린더와 이벤트 summary는 각각 고정 `헬끼 운동 일정`, `헬끼 운동`이며 설명·위치·참석자·
  회의 링크·메모를 보내지 않는다.
- 연동 해제는 로컬 `REVOKE_PENDING`으로 접근을 차단하고 token secret 폐기 뒤 `REVOKED`로 완료한다.
  반복 해제는 성공 no-op이다. Firebase 로그인과 동일한 Google Cloud project에서는 Calendar 단독
  provider revoke를 호출하지 않는다. 원격 보조 캘린더는 남고 사용자가 직접 삭제한다.
- 동의 철회는 즉시 provider 접근을 막고 같은 secret cleanup을 시작한다. 계정 삭제는 DB hard delete
  전에 Calendar secret 파기를 완료하도록 ADR-0008 checkpoint를 확장한다.

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
- V2 구현 사용 시 conflict detector·precedence version, canonical conflict code, review 대상과
  `NOT_REQUIRED` event, revised proposal과 각 hash
- 후보와 안전 검증 결과
- 최종 옵션
- LLM 사용 시 모델과 프롬프트 버전

동일한 입력 스냅샷과 동일한 결정 규칙 버전은 동일한 운동 후보와 최종 액션을 만들어야 한다. LLM 문구는 결정 재현성의 일부로 사용하지 않는다.

V3에서는 fresh LLM 재호출의 byte-identical 결과를 요구하지 않는다. 대신 envelope·pool·proposal·
review·Coordinator output·compiler/validator 결과와 모든 model/prompt/graph version을 저장하고,
저장된 structured output을 입력으로 provider 재호출 없이 동일 final result를 replay해야 한다.

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
33. invalid state 또는 nonce: identity 조회 전에 거부
34. issuer 또는 audience 불일치: provider token 거부
35. 만료·변조 token과 subject 누락: user 생성 없음
36. provider timeout·5xx: `PROVIDER_UNAVAILABLE`, 원시 오류 비노출
37. 이미 다른 user에 연결된 subject: 자동 병합 없이 충돌
38. 같은 subject 반복 로그인: 같은 내부 user와 identity 재사용
39. provider 연결 해제 반복 호출: 이미 REVOKED면 성공 no-op
40. identity DB commit 실패: 전체 rollback, custom token·성공 응답 없음
41. token·email·name·nickname·subject·원시 provider 응답이 로그·snapshot에 없음
42. 마지막 활성 identity 일반 해제 차단, 계정 삭제 전체 해제는 허용
43. 캘린더 미연동: 수동 체크인과 앱 운동 블록 체크로 정상 핵심 흐름
44. 캘린더 권한 거부: 수동 경로 유지, 기존 운동 계획 불변
45. 캘린더 `performed=true`: 공식 세션 상태 불변
46. Google `performed=null`: fallback 안내 반환, 오류 아님
47. 캘린더 provider 장애: `PROVIDER_UNAVAILABLE`, 계획 삭제·변경 없음
48. 하루 전체 busy: 빈 후보 배열, 희망 운동시간 단축 없음
49. freebusy 종일 구간: busy로 처리하며 일정 본문 조회 없음

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
- 첫 출시 국가와 대상 사용자가 대한민국인지
- Kakao 앱·REST key·client secret·production redirect URI owner와 등록 완료일
- Google/Firebase 프로젝트 및 Naver 앱 등록·심사 담당자와 완료일
- Naver user token 영구 저장 없이 계정 삭제 시 revocation을 완료하는 방식

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
