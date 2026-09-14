# TASK-TEMP-FE3-RED-FLAG-QUESTION: 체크인 위험 신호 질문 중복 제거

- 상태: DONE
- Primary owner: 프론트엔드 담당자
- Reviewers: 프론트엔드 또는 개발팀장 1명
- 관련 요구사항: `docs/tasks/2026-09-improvements/FRONTEND.md` FE-3
- 목표 브랜치: `fix/temp-fe3-red-flag-after-fe14`
- 선행 브랜치: `refactor/temp-fe14-home-screen-split`

## 배경과 사용자 가치

체크인 위험 신호 영역에서 제목과 설명 뒤에 같은 의미의 `위 증상이 있나요?` 라벨이 다시
표시된다. 중복 라벨을 없애되, 사용자가 안전 질문의 맥락과 필수 응답 여부를 놓치지 않게 한다.

## 포함 범위

- `위 증상이 있나요?` ChoiceBlock 라벨 제거
- `없어요`와 `있어요` 버튼을 위험 신호 박스 안으로 이동
- 위험 신호 박스를 접근성 그룹으로 표시
- 기존 버튼 접근성 라벨과 미선택 경고 유지

## 제외 범위

- 위험 신호 문구, 판정 규칙 또는 API payload 변경
- 통증·이상반응 화면의 시각적 톤 변경
- FE-14의 구조 변경

## 인수 조건

1. `위 증상이 있나요?` 라벨이 표시되지 않는다.
2. `없어요`와 `있어요` 버튼이 위험 신호 박스 안에 있다.
3. 박스는 `오늘 위험 신호가 있나요?`라는 이름의 접근성 그룹이다.
4. `위험 신호 없어요`와 `위험 신호 있어요` 접근성 라벨이 유지된다.
5. 미선택 상태에서 저장이 비활성화되고 `위험 신호 여부를 선택해주세요.` 경고가 유지된다.
6. 기존 체크인 payload와 안전 동작이 바뀌지 않는다.

## 변경 예상 파일

- `frontend/src/features/home/HomeCheckinSheet.tsx`
- `frontend/tests/HomeScreen.test.tsx`
- `docs/tasks/TASK-TEMP-FE3-RED-FLAG-QUESTION.md`

## API·DB 영향

없음. 요청·응답 계약과 저장 구조를 변경하지 않는다.

## 안전·개인정보·보안 영향

안전 필수 질문의 제목, 설명, 명시적 선택, 미선택 차단을 모두 유지한다. 새로운 개인정보를
수집하거나 로그에 남기지 않는다.

## 테스트 계획

- 중복 라벨 부재와 위험 신호 그룹 내부의 두 버튼 확인
- 버튼 접근성 라벨과 미선택 경고 확인
- 기존 체크인 제출 테스트로 `redFlagPresent` payload 회귀 확인
- 포맷, 린트, 타입 체크, 전체 테스트, Android/iOS 프로덕션 export

## 수동 확인

1. 홈에서 오늘 컨디션 체크를 연다.
2. 위험 신호 박스 안에 `없어요`와 `있어요`가 있고 중복 질문이 없는지 확인한다.
3. 아무것도 선택하지 않았을 때 저장할 수 없는지 확인한다.
4. 각 선택지가 스크린 리더에서 위험 신호 맥락으로 읽히는지 확인한다.

## 알려진 제한과 후속 작업

FE-14 분할 구조 위로 이동을 완료했다. FE-14가 먼저 병합된 뒤 이 브랜치를 병합한다.

## 검증 결과

- `npm.cmd run format:check`: 통과
- `npm.cmd run lint`: 통과
- `npm.cmd run typecheck`: 통과
- `npm.cmd test -- --runInBand tests/HomeScreen.test.tsx --silent`: 56 tests 통과
- `npm.cmd test -- --runInBand --silent`: 32 suites, 547 tests 통과
- `npm.cmd run build:production`: Android와 iOS export 통과

첫 빌드는 샌드박스의 Hermes 프로세스 실행 권한(`spawn EPERM`) 때문에 중단됐고,
동일 명령을 승인된 환경에서 다시 실행해 두 플랫폼 export를 확인했다.
