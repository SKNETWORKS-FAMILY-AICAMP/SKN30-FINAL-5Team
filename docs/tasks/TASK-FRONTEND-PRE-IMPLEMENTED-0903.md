# TASK-FRONTEND-PRE-IMPLEMENTED-0903: 프론트엔드 선제 구현 기록

- Primary owner: 프론트엔드
- 관련 ADR: ADR-0018 (D4 세트·반복 편집, D5 phase 안 순서 변경)
- 성격: **참고용 기록.** 계약을 정의하지 않는다.

## 목적

2026-09-03 프론트엔드가 서버 경로보다 먼저 구현한 항목과 그 방식을 남긴다. 나중에 서버 쪽 작업을 할 때
"프론트가 이미 무엇을 어떤 모양으로 준비해 뒀는지" 확인하는 용도다.

`docs/API_CONTRACT.md`를 포함한 공개 API 계약은 이 문서의 범위가 아니다. 아래 내용은 계약이 아니라
현재 클라이언트 구현 상태의 서술이다.

---

## 1. 당일 최종 계획의 사용자 편집 (세트·반복, 순서)

### 화면 동작

- 홈 루틴 카드의 **[세트·횟수 수정] → [저장하기]**, 그리고 항목 앞 핸들 **드래그 순서 변경**.
- 편집 결과를 오늘의 결정 plan 자체에 적용한다. 이전에는 세트·반복 편집이 홈 카드 표시에만 남아
  운동 진행 화면은 원래 처방으로 진행됐다. 이제 두 화면이 같은 plan을 읽는다.
- 순서 변경은 `WARMUP`·`MAIN`·`COOLDOWN` **각 phase 안에서만** 적용하고, 경계를 넘는 이동은 화면에서
  되돌린다(ADR-0018 D5). 이미 완료된 블록은 이동 대상에서 제외한다.

### 저장 방식

- 편집을 적용한 뒤 서버 저장을 요청하는 호출 지점을 optional API capability로 준비해 뒀다.
  `frontend/src/api/endpoints.ts`의 `DecisionPlanEditCapability`이며, 기존
  `WeeklyPlanRevisionReadCapability`와 같은 패턴이다.
- **route가 없는 동안에는 호출하지 않는다.** 실행 중인 앱 안에서만 편집이 유지되고, 앱을 재시작하거나
  홈을 다시 읽으면 서버에 저장된 계획으로 돌아간다.
- 서버 API client에 해당 메서드가 생기면 화면 코드 변경 없이 저장 경로가 켜진다.
- 드래그는 한 칸마다 이벤트가 발생하므로 마지막 상태 하나만 지연 전송한다(`PLAN_EDIT_SAVE_DELAY_MS`).
- 저장 실패 시 사용자에게 안내를 표시하고, 저장된 결정을 다시 읽어 화면을 되돌린다.

### 프론트엔드가 준비한 호출 형태 (참고)

확정 계약이 아니다. 서버 쪽 형태가 정해지면 클라이언트가 맞춘다.

~~~text
updateDecisionPlan(decision_id, {
  expected_plan_id: string,
  item_order: string[],            // 편집 후 수행 순서의 plan_item_id 전체
  item_prescriptions: [{ plan_item_id, sets, reps }]   // 편집 후 전체 처방
}) -> DecisionResponse
~~~

부분 patch가 아니라 편집 후 전체 plan을 보내는 형태로 만들었다. 운동 정체성·phase·안전 상태·veto·
reason code·소요 시간은 보내지 않는다.

### 관련 코드

- `frontend/src/api/workoutPlan.ts`: phase 경계 검사, 처방 적용, 요청 본문 구성
- `frontend/src/features/home/HomeContainer.tsx`: 편집 적용과 저장 시도, 실패 시 복구
- `frontend/src/features/home/HomeScreen.tsx`: 편집 UI와 낙관적 표시
- `frontend/tests/workoutPlan.test.ts`, `frontend/tests/demoFlow.test.tsx`

---

## 2. 당일 체크인 통증 초기값을 서버에서 조회

- 홈 진입 시 `GET /api/v1/daily-contexts/{local_date}/defaults`(P1-B에서 구현된 경로)를 함께 읽어
  체크인 화면의 통증 부위·강도 초기값으로 사용한다.
- 이전에는 프로필 `persistent_pains`를 클라이언트가 그대로 복사했다. 같은 값을 두 곳에서 계산하지
  않도록 서버 값을 우선한다.
- 이 조회가 실패하거나 값이 없으면 기존처럼 프로필 값으로 저하 동작한다. **체크인 작성 자체는 어떤
  경우에도 막히지 않는다.**
- 이미 저장된 당일 체크인이 있으면 초기값 대신 저장된 체크인을 표시한다.

### 관련 코드

- `frontend/src/api/endpoints.ts`: `getDailyContextDefaults`
- `frontend/src/features/home/HomeContainer.tsx`: 조회와 저하 동작

---

## 3. 검증

- `npm run typecheck`, `npm run lint`, `npm run format:check` 통과
- `npm test` 516건 통과 (신규 9건: phase 경계, 처방 적용, 요청 본문, 체크인 초기값 2건, 편집 저장 2건)
- `npm run build:production` (Android/iOS) 성공

## 4. 현재 한계

- 세트·반복과 순서 편집은 서버 저장 경로가 생기기 전까지 실행 중인 앱 안에서만 유지된다.
- 결과 화면에서 수집하는 "어떤 점이 어려웠나요"(`VOLUME_HIGH`, `MOVEMENT_DIFFICULT`)는 현재 요청에
  포함하지 않는다.
