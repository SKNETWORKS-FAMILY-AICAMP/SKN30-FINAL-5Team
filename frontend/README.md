# Frontend

React Native, TypeScript, Expo SDK 57 Development Build 기반 모바일 앱 영역입니다.

## 시작하기

Node 24.18.1과 npm 11을 사용합니다. 상세 결정과 근거는 `TECHNICAL_DECISIONS.md`에 있습니다.

```bash
npm ci
npm start
```

Development Build 네이티브 앱은 Android에서 `npm run android`, macOS/iOS에서 `npm run ios`로 생성합니다.

브라우저에서 Splash를 고정해 시각 수정하려면 웹 개발 서버를 연 뒤 아래 주소를 사용합니다.

```bash
npx expo start --web
```

`http://localhost:8081/?preview=splash`

품질 검증 명령:

```bash
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build:production
```

예정 구조:

- `src/app/`: navigation, providers, app bootstrap
- `src/features/`: onboarding, check-in, decision, workout, weekly report
- `src/components/`: 도메인 결정이 없는 공용 UI
- `src/api/`: 생성 또는 수기 typed API client와 DTO adapter
- `src/storage/`: 운동 진행 상태의 최소 로컬 임시 저장
- `src/assets/`: 마스코트와 정적 자산
- `tests/`: component와 E2E 테스트

현재 첫 이관 slice는 typed navigation, 재시도 가능한 앱 bootstrap 경계, 반응형 Splash 화면을 포함합니다.

운동 실행 화면의 기본 계약:

- 최상단: 0초부터 증가하며 일시정지·재개할 수 있는 전체 경과 타이머
- 중앙: 현재 운동에 맞는 마스코트 애니메이션
- 하단: 운동명·세트·반복/권장 목표가 있는 순서형 블록
- 블록 상단: 자세·설명 펼침 버튼
- 블록 완료: 체크 버튼, 격파 또는 좌측 밀기 제스처
- 완료 후: 다음 PENDING 블록으로 이동

경과 시간은 기록·확인용이며 공식 완료 상태는 블록 완료 mutation으로만 결정합니다.
