# 루틴 생성 완료·운동 화면 추가 정리

- Primary owner: frontend
- Branch/worktree: `feat/routine-workout-polish-0908`, `.worktrees/routine-workout-polish-0908`
- 요청: 프로젝트 소유자, 2026-09-08 첨부 수정사항 및 `monkey_run_02.gif` 교체.
- 선행 변경: 휴식 통합·주간 리포트의 완료 및 검증 기록을 확인한 뒤 현재 미커밋 변경을 복사한 독립 worktree에서 작업한다. 원본 적용 전 파일별 기준 스냅샷과 비교하여 다른 작업을 덮어쓰지 않는다.

## 구현 계획과 인수 조건

1. 루틴 준비 문구를 정리하고 KEEP의 중복 상태 pill·요약을 제거한다. 추천 이유는 루틴명과 시간 바로 아래 배치하고 운동 목표·컨디션·운동 환경으로 설명한다. 서버의 reason code에 대응하는 기존 사용자 문구와 안전 guidance를 보존한다.
2. 운동 타이머 여백과 버튼 크기를 줄이고 카드 높이를 내용에 맞춘다. 서버가 검수 대체안을 반환할 때만 장비 버튼을 표시하는 기존 조건을 유지한다. 장비 안내를 준비물·대체 동작·검수 자세 설명 중심으로 정리한다.
3. 일반 중단과 안전 중단을 구분하고 선택 시 당일 재개 불가 및 확인 문구를 간결하게 표시한다. 세부 도움말과 기존 안전 API는 유지한다.
4. 완료 블록 정보는 한 번만 표시한다. 안전 중단 결과는 서버 guidance를 보존한 단일 영역과 `진행한 운동까지 기록했어요.`로 정리한다. 난이도는 질문 하나로 표시하며 피드백 저장 성공·실패 및 홈 이동을 보존한다.
5. 운동 진행 GIF를 요청 에셋으로 교체하고 포맷·린트·타입 검사, 관련/전체 테스트, Android/iOS production export 및 360/390px 브라우저 미리보기를 검증한다.

## 계약·영향·제한

- `NOT_COMPLETED`의 사용자 표시는 선행 변경의 `휴식`을 유지한다. 상태 코드, API, DB, 공식 블록 완료 판정과 안전 판정은 변경하지 않는다.
- 휴식 타이머는 현행 계약상 count-up이다. 남은 시간으로 오인하지 않도록 `경과 휴식 mm:ss`로 표시하며 임의의 제한 시간이나 자동 종료를 추가하지 않는다.
- 어려움 사유의 기존 두 항목을 유지한다. 현재 UI의 세부 선택은 기존 동작대로 전송하지 않으며 새 저장 코드를 추가하지 않는다. 사유 확장·저장 연결은 백엔드와 별도 계약 확인이 필요하다.
- 새 의존성, 개인정보 수집, 로깅 및 외부 전송은 없다.
- 병합·배포와 실기기/실제 서버 검증은 이 작업에 포함하지 않는다.

## 수동 확인

- Home(API) 루틴 생성 완료에서 준비 pill, 제목, 루틴명·시간, 추천 이유, 운동 목록·시작 버튼 순서를 확인한다. 추천 이유에 내부 에이전트/서버 표현이 없고 조정·안전 이유가 유지되는지 확인한다.
- Workout(API)에서 360×800·390×844 크기, 새 GIF, 장비 버튼 유무별 카드 높이, 휴식 경과 시간을 확인한다.
- 중단 사유의 일반/안전 구분, 선택 전후 확인 체크와 CTA, 안전 결과의 단일 안내, 0블록 종료 시 홈 이동을 확인한다.
- 전체/부분 수행 결과에서 블록 수가 한 번만 나오고 피드백 선택 전 저장 불가, 저장 후 홈 이동 및 실패 재시도를 확인한다.

## 변경 파일

- `frontend/src/assets/index.ts`: 요청 GIF 연결.
- `frontend/src/features/home/HomeRoutineCard.tsx`, `HomeChrome.tsx`, `HomeScreenContent.tsx`, `homeContentModel.ts`, `homeStyles.tsx`: 준비 상태·추천 설명·장비 제목·카드 밀도.
- `frontend/src/features/workout/WorkoutScreen.tsx`, `ExerciseVariants.tsx`, `SessionResultScreen.tsx`: 운동 진행·휴식·중단·결과 UI.
- `frontend/tests/HomeScreen.test.tsx`, `WorkoutScreen.test.tsx`, `SessionResultScreen.test.tsx`, `PreviewGallery.test.tsx`, `mainFlowRestore.test.tsx`: 변경한 화면 동작과 기존 복구 흐름 검증.

## 검증 결과 (2026-09-08)

- 전체 테스트: **37 suites, 642 tests 통과**. 블록 완료·재개·0블록 휴식·피드백 저장 실패/재시도, 대체안 없는 카드의 빈 영역 제거, 완료/안전 결과의 중복 제거를 포함한다.
- `npm.cmd run format:check`, `npm.cmd run typecheck`: 통과.
- `npm.cmd run lint`: 오류 0개, 기존 `BirthDateField.tsx:266`의 `scrollToIndex` 의존성 경고 1개.
- `npm.cmd run build:production`: Android/iOS Hermes export 모두 통과. sandbox의 Hermes `spawn EPERM` 이후 동일 명령을 실행 권한을 확보하여 검증했다.
- `git diff --check`: 통과.
- 브라우저: 390×844·360×800 운동 화면의 카드·CTA, 실제 `monkey_run_02.gif` 이미지 경로, 루틴 준비 정보 순서와 추천 이유 3개 영역, 안전 중단 단일 안내·난이도 질문을 확인했다. 실기기와 실제 서버 검증은 별도로 필요하다.
- 변경한 소스·테스트 14개 파일을 원본 스냅샷과 비교하여 다른 작업의 추가 변경이 없는 경우에만 적용한다. 공유 API/DB/정책 문서와 기존 다른 작업의 수정은 보존한다.
