# Frontend

React Native, TypeScript, Expo Development Build 기반 모바일 앱 영역입니다.

예정 구조:

- `src/app/`: navigation, providers, app bootstrap
- `src/features/`: onboarding, check-in, decision, workout, weekly report
- `src/components/`: 도메인 결정이 없는 공용 UI
- `src/api/`: 생성 또는 수기 typed API client와 DTO adapter
- `src/storage/`: 운동 진행 상태의 최소 로컬 임시 저장
- `src/assets/`: 마스코트와 정적 자산
- `tests/`: component와 E2E 테스트

프로젝트 초기화와 패키지 설치는 별도 구현 PR에서 수행합니다.

운동 실행 화면의 기본 계약:

- 최상단: 0초부터 증가하며 일시정지·재개할 수 있는 전체 경과 타이머
- 중앙: 현재 운동에 맞는 마스코트 애니메이션
- 하단: 운동명·세트·반복/권장 목표가 있는 순서형 블록
- 블록 상단: 자세·설명 펼침 버튼
- 블록 완료: 체크 버튼, 격파 또는 좌측 밀기 제스처
- 완료 후: 다음 PENDING 블록으로 이동

경과 시간은 기록·확인용이며 공식 완료 상태는 블록 완료 mutation으로만 결정합니다.
