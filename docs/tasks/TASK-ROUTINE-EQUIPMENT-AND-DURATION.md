# 루틴 생성 정책 변경: 장비 비의존 추천, 시간 오차 허용, 변형운동 확인

## 1. 배경

루틴 생성이 `ROUTINE_CONTENT_UNAVAILABLE` 또는 `ROUTINE_DURATION_UNAVAILABLE`로 계속
실패했다. 조사 결과 카탈로그 데이터가 아니라 선정 정책이 의도보다 좁게 구현돼 있었다.

확인된 원인은 세 가지다.

1. `beginner_suitable=true`인 운동이 22개뿐이었고 전부 MAIN 단계였다. WARMUP·COOLDOWN
   후보가 0이어서 3단계 구성이 불가능했다. → 카탈로그 v2.0.1로 해소 (MOBILITY 17건 승격)
2. 장비 필터가 `issubset` 이라 운동이 요구하는 장비를 사용자가 **전부** 보유해야 후보로
   남았다. 맨몸 사용자에게 `BODYWEIGHT|MAT` 운동조차 걸러졌다.
3. 요청 시간을 **정확히** 채우는 조합만 허용했다. 후보 39개로 만들 수 있는 총합은 30가지뿐,
   1800초(30분) 근처 값이 하나도 없었다.

## 2. 확정 사항

회의 결정. 이 문서가 구현의 기준이다.

### 2.1 장비

- 온보딩·마이페이지에서 **운동 장비 선택 항목을 제거**한다.
- 루틴 생성은 장비 보유 여부와 무관하게 **사용자 적합성만으로** 판단한다.
- `user_equipment` 테이블은 쓰기를 멈추되 **이번 릴리스에서 삭제하지 않는다**
  (`AGENTS.md` 10절: 쓰기를 멈춘 릴리스에서 컬럼/테이블을 제거하지 않는다).

### 2.2 시간

- 요청 시간에 대해 **±5분 오차를 허용**한다.
- `AGENTS.md` 7절의 "must not shorten duration without explicit user input" 불변식과
  충돌하므로 **문서를 함께 갱신**해야 한다. 회의 결정을 근거로 남긴다.

### 2.3 용어 통일

| 한국어 | 영문 | 트리거 | 데이터 소스 |
|---|---|---|---|
| 대체운동 | alternative | 통증 시 교체에는 사용하지 않음(폐지) | `exercise_alternatives.reason_code = 'DISCOMFORT'` (레거시·비소비 감사 데이터) |
| 변형운동 | variant | 장비가 없을 때 | `exercise_alternatives.reason_code = 'EQUIPMENT'` (20건 / 15개 운동) |

- `DIFFICULTY`(10건)는 표본이 적어 **사용하지 않는다**.
- `LOCATION`(35건)의 처리는 **미결**. 3절 참고.

### 2.4 변형운동 기능 범위

- 루틴 화면과 운동 수행 중에 **버튼으로 확인만** 한다.
- 필요한 장비가 무엇인지, 장비 없이 어떻게 변형할지를 보여준다.
- **운동을 교체하지 않는다.** 세션 기록에도 반영하지 않는다.
- 변형운동이 없는 운동은 버튼을 노출하지 않는다(맨몸 운동은 변형이 불필요).

### 2.5 숙련도

- 온보딩은 **초급/중급** 두 단계로 나눈다.
- 운동 후보는 누적 방식이다. 초급 사용자는 초급 운동만, 중급 사용자는 초급·중급 운동을
  선정할 수 있다.
- 정상 상태에서는 사용자 숙련도와 같은 FITT 처방을 적용한다. 기존 downshift 조건이 발동한
  경우에만 초급 운동과 초급 FITT로 재구성한다.
- 중급 처방 데이터는 **데이터 파트에서 별도 작업**한다. 그 전까지 중급은 후보가 0이므로
  온보딩 노출 시점을 데이터 완료와 맞춘다.

### 2.6 복귀자

- 명칭을 **서비스 복귀자**로 확정한다.
- **서비스 14일 미접속** 시 서비스 복귀자로 간주한다.
- 기존 `backend/app/domain/rules/return_mode.py`의 `RETURN_MODE` 개념을 그대로 쓴다.
  온보딩 입력 항목으로 만들지 않는다.
- 기존 판정 기준은 `COMPLETION_GAP_14_DAYS`(운동 완료 공백)이므로, **접속 기준으로
  바꿀지 확인이 필요하다**. 3절 참고.

## 3. 승인 및 확정

2026-08-27 프로젝트 오너 승인. 아래 항목은 더 이상 미결이 아니다.

| 항목 | 확정 내용 |
|---|---|
| 시간 ±5분 허용 | **승인.** `AGENTS.md` 7절, `docs/DOMAIN_RULES.md` 4·5절 갱신 완료 |
| `LOCATION` 관계(35건) | **변형운동에서 제외.** 운동 장소에 따라 달라지는 축이라 "장비가 없을 때의 변형"과 다른 개념이다 |
| 복귀 판정 기준 | **현행 유지.** `COMPLETION_GAP_14_DAYS`(운동 완료 공백) 그대로 쓴다. 접속 기준으로 바꾸지 않는다 |
| 레벨별 적합성 마이그레이션 | **백엔드 정책 반영.** `difficulty_code`는 운동 난이도, `experience_level_code`는 사용자·FITT 숙련도로 구분하고 방향성 호환성을 적용한다. 실제 중급 처방 데이터 생성은 데이터 담당 작업으로 유지한다 |

변형운동의 데이터 소스는 `reason_code = 'EQUIPMENT'` **하나뿐**이다. `LOCATION`·`DIFFICULTY`는
쓰지 않는다.

## 4. 작업 순서

### 1단계 — 루틴 생성 정상화 (선행)

- `backend/app/db/repositories/routine.py`: 장비 필터 제거
- `backend/app/modules/routines/service.py`: 시간 ±5분 오차 허용
- `AGENTS.md` 7절, `docs/DOMAIN_RULES.md` 갱신
- 골든 시나리오 테스트 갱신

**이 단계만으로 루틴이 생성된다.** 데모 가능 시점.

### 2단계 — 온보딩 장비 항목 제거

- 백엔드: 온보딩·프로필 요청/응답 스키마에서 장비 필드 제거
- 프론트엔드: 온보딩·마이페이지 장비 선택 UI 제거
- `docs/API_CONTRACT.md` 갱신, 프론트·백엔드 오너 리뷰
- `user_equipment` 테이블은 유지(쓰기만 중단)

### 3단계 — 변형운동 확인 기능

- 백엔드: 변형운동 조회 엔드포인트 (`reason_code='EQUIPMENT'` 기준)
- 프론트엔드: 루틴 화면·운동 수행 화면에 버튼과 표시
- 교체 기능 없음

## 5. 참고 — 현재 데이터 현황

2026-08-27 기준, RDS `exercise-catalog-v2.0.1-final` (ACTIVE).

```
카탈로그 난이도    BEGINNER 73 · INTERMEDIATE 29 · ADVANCED 0
처방              BEGINNER 137건 · INTERMEDIATE 0건
beginner_suitable  true 39 · false 63
대체관계           DISCOMFORT 220 · LOCATION 35 · EQUIPMENT 20 · DIFFICULTY 10
```

후속 정책 변경으로 `difficulty_code`는 운동 자체 난이도, `experience_level_code`는 사용자·FITT
숙련도로 구분했다. 초급 사용자는 초급 운동만, 중급 사용자는 초급·중급 운동을 사용할 수 있고,
처방은 운동 난이도 이상의 숙련도만 허용한다.
`beginner_suitable`는 신규 카탈로그 입력과 추천 로직에서 제거하고 DB 컬럼만 호환 기간 동안
유지한다. 중급 오픈 전 데이터 담당자는 `BEGINNER` 운동용 `INTERMEDIATE` 처방과
`INTERMEDIATE` 운동용 `INTERMEDIATE` 처방을 포함한 새 bundle을 생성해야 한다.
