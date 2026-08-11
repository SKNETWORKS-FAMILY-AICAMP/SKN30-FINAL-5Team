# 운동 taxonomy 코드 제안

상태: `APPROVED` (개발 리드, 2026-08-11)
registry 버전: `1.0.0`
확정본: `exercise_taxonomy_codes.json`
남은 승인: PM(한국어 표시명), 도메인 검토자(운동 패턴의 안전 규칙 적용)

## 1. 목적

`docs/API_CONTRACT.md` 19절의 미확정 계약 중 다음 코드 목록을 확정하기 위한 제안이다.

- `training_type_code`
- `body_focus_code`
- `movement_pattern_code`
- `equipment_code`
- `location_code`

개발 리드가 2026-08-11에 5개 집합을 모두 승인했다. 결과 validator는 이제
`review_taxonomy_code`의 형식이 아니라 승인된 목록 소속을 검사한다.

`body_area_code`는 `docs/DOMAIN_RULES.md` 3.2절에서 이미 확정된 13개 코드를 사용하며 이
문서에서 다시 제안하지 않는다.

## 2. 근거

제안값은 두 가지에서만 도출했다. 새로운 운동학적 분류를 창작하지 않았다.

1. 승인된 문서의 문장
   - `docs/MVP_SCOPE.md` 5.3: "운동 유형: 근력, 유산소, 가동성 등", "운동 초점: 상체,
     하체 등 루틴 화면 분류", "운동 패턴", 카탈로그 규모 50~80개
   - `docs/MVP_SCOPE.md` 5.4 지원 범위: 홈트, 헬스장, 걷기와 가벼운 러닝, 스트레칭과 코어
   - `docs/DATA_MODEL.md` 5.2: "STRENGTH, CARDIO, MOBILITY 등"
   - `GYM_EXERCISE_SOURCE_COVERAGE.md`의 1차 헬스장 검토 우선순위 8개 운동군
2. 실제 수집 원천의 어휘 분포(아래 표)

## 3. 원천 어휘 실측

wger snapshot `20260810T063833Z`, KSPO profile `20260810T053458Z` 기준이다.

| 원천 필드 | 고유값 | 비고 |
|---|---:|---|
| wger category | 8 | Legs 202, Back 159, Arms 138, Abs 114, Shoulders 107, Chest 82, Cardio 48, Calves 12 |
| wger equipment | 12 | bodyweight 271, Dumbbell 144, Cable machine 101, Barbell 73 … |
| wger primary muscle | 15 | 라틴 해부학 명칭, 정제된 상태 |
| KSPO places | 7 | 실내 230, 헬스장 43, 수영장 26 … |
| KSPO tools | 43 | 미지정 130, 밴드 33, 공 30, 매트 30 … |
| KSPO 운동부위 | 208 | 자유 문자열, 중복·공백 포함 |

wger `category`는 운동 유형과 신체 초점이 한 필드에 섞여 있다. `Cardio`만 운동 유형이고
나머지 7개는 신체 부위다. 그래서 이 필드를 그대로 `training_type_code`로 쓸 수 없다.

## 4. 제안 코드

### 4.1 training_type_code

| 코드 | 표시명 | 근거 |
|---|---|---|
| `STRENGTH` | 근력 | MVP_SCOPE 5.3, DATA_MODEL 5.2 |
| `CARDIO` | 유산소 | MVP_SCOPE 5.3, wger Cardio 48건 |
| `MOBILITY` | 가동성 | MVP_SCOPE 5.3, 지원 범위의 스트레칭 |

회복 콘텐츠(`docs/DOMAIN_RULES.md` "가벼운 걷기, 호흡, 가동성 운동")는 별도 유형을 만들지
않고 `CARDIO`/`MOBILITY` + `recovery_eligible` 플래그로 표현한다.

`BALANCE`는 KSPO에 보슈·균형 운동이 있으나 MVP 지원 범위 문장에 없어 이번 제안에서 제외한다.
필요하면 별도 승인으로 추가한다.

### 4.2 body_focus_code

MVP_SCOPE의 "상체, 하체 등 루틴 화면 분류" 수준이다. wger category보다 거칠다.

| 코드 | 표시명 | wger category 매핑 |
|---|---|---|
| `UPPER_BODY` | 상체 | Back, Arms, Shoulders, Chest |
| `LOWER_BODY` | 하체 | Legs, Calves |
| `CORE` | 코어 | Abs |
| `FULL_BODY` | 전신 | (원천 매핑 없음, 검토자 판단) |

`Cardio`는 초점이 아니라 유형이므로 여기에 매핑하지 않는다.

### 4.3 movement_pattern_code

`exercise_safety_rules`가 이 코드로 제외 규칙을 건다. 개발 리드가 코드 목록을 승인했으므로
카탈로그 taxonomy로는 사용할 수 있다. 다만 `docs/DOMAIN_RULES.md` 16절의 "각 신체 부위와
운동 패턴의 제외 규칙"은 여전히 미승인이므로 **안전 규칙 작성에는 도메인 검토자 승인이
별도로 필요하다.**

앞의 8개는 `GYM_EXERCISE_SOURCE_COVERAGE.md` 검토 우선순위를 그대로 코드화했다.

| 코드 | 표시명 | 출처 |
|---|---|---|
| `VERTICAL_PULL` | 수직 당기기 | 커버리지 문서 1번 |
| `HORIZONTAL_PULL` | 수평 당기기 | 커버리지 문서 2번 |
| `HORIZONTAL_PUSH` | 수평 밀기 | 커버리지 문서 3번 |
| `VERTICAL_PUSH` | 수직 밀기 | 커버리지 문서 4번 |
| `KNEE_DOMINANT` | 무릎 중심 하체 | 커버리지 문서 5번 |
| `HIP_DOMINANT` | 엉덩관절 중심 하체 | 커버리지 문서 6번 |
| `KNEE_FLEXION` | 무릎 굽힘 | 커버리지 문서 7번 |
| `ISOLATION` | 단순 보조 | 커버리지 문서 8번 |
| `GAIT` | 걷기·가벼운 러닝 | MVP_SCOPE 5.4 지원 범위 |
| `CORE_BRACE` | 코어 | MVP_SCOPE 5.4 지원 범위 |
| `MOBILITY_STRETCH` | 스트레칭·가동성 | MVP_SCOPE 5.4 지원 범위 |

### 4.4 equipment_code

MVP 지원 범위(홈트·헬스장)에 필요한 것만 제안한다.

| 코드 | 표시명 | wger 원천값 | KSPO 원천값 |
|---|---|---|---|
| `BODYWEIGHT` | 맨몸 | none (bodyweight exercise) | — |
| `DUMBBELL` | 덤벨 | Dumbbell | 덤벨 |
| `BARBELL` | 바벨 | Barbell | 바벨 |
| `EZ_BAR` | 이지바 | SZ-Bar | — |
| `KETTLEBELL` | 케틀벨 | Kettlebell | — |
| `CABLE_MACHINE` | 케이블 머신 | Cable machine | 헬스기구(일부) |
| `BENCH` | 벤치 | Bench, Incline bench | — |
| `PULL_UP_BAR` | 풀업바 | Pull-up bar | — |
| `RESISTANCE_BAND` | 밴드 | Resistance band | 밴드 |
| `MAT` | 매트 | Gym mat | 매트 |
| `STABILITY_BALL` | 짐볼 | Swiss Ball | 짐볼, 공 |
| `CHAIR` | 의자 | — | 의자 |

**중요:** KSPO의 빈 도구 값 130건은 `BODYWEIGHT`로 변환하지 않는다. 원천 배치의
`BLANK_SOURCE_TOOL_IS_UNSPECIFIED_NOT_BODYWEIGHT` 규칙에 따라 미지정 상태로 남긴다.

KSPO의 풍선·라바콘·색테이프·사다리·테니스공 등은 유아기 체력측정용이므로 MVP 카탈로그
장비에서 제외한다. `Incline bench`를 `BENCH`로 합칠지 분리할지는 검토자 확인이 필요하다.

### 4.5 location_code

| 코드 | 표시명 | KSPO 원천값 |
|---|---|---|
| `HOME` | 홈 | 실내 |
| `GYM` | 헬스장 | 헬스장 |
| `OUTDOOR` | 실외 | 실외 |

수영장 26건은 MVP 지원 범위 밖이며 profiler가 이미 `PLACE_POOL_ONLY`로 제외하고 있다.

## 5. 정규화 시 주의할 원천 품질 문제

실측에서 확인한 사항이다. 코드 확정과 별개로 정규화 단계에서 처리해야 한다.

1. KSPO `places`의 구분자가 일관되지 않다. `실내, 실외`와 `실내/실외`가 같은 의미로
   따로 존재한다. 고유값 7개는 실제 개념 4개의 조합 표기 차이다.
2. KSPO 운동부위 208개는 자유 문자열이며 `복부,복부`처럼 중복이 들어 있고 후행 공백이
   있는 값(`바깥쪽 어깨 `)이 있다.
3. wger 근육 정보는 **사용 근육**이고 `body_area_code`는 **불편 부위**다. 두 체계가 다르므로
   근육에서 관절 부하를 추론하지 않는다. 이 원칙은
   `GYM_EXERCISE_SOURCE_COVERAGE.md` 매핑 규칙 6번에 이미 있다.

## 6. 이 문서가 정하지 않는 것

- 개별 운동이 어떤 코드에 속하는지: 검토 배치에서 사람이 작성한다.
- 안전 제외 규칙과 대체 관계: 어떤 원천도 제공하지 않으며 도메인 검토자가 작성한다.
- FITT, MET, 세트·반복·휴식 값: 근거 원천이 아직 수집되지 않았다.
- 난이도와 초보자 적합성 판정 기준.

## 7. 승인 체크리스트

- [x] 개발 리드: 5개 코드 목록과 코드 문자열 확정 (2026-08-11)
- [x] `exercise_taxonomy_codes.json`을 확정본으로 승격하고 결과 validator를 목록 소속
      검사로 변경
- [ ] PM: 한국어 표시명 확정. 현재 값은 사용자 노출 전 참고값이다.
- [ ] 도메인 검토자: `movement_pattern_code` 11개를 안전 제외 규칙의 단위로 쓰는 것이
      적절한지 확인. 카탈로그 taxonomy 사용은 이미 가능하다.
