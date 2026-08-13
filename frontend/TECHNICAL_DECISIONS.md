# React Native 기반 기술 결정

기준일: 2026-08-12

## 결정

| 항목                       | 결정                                                             | 근거와 운영 규칙                                                                                                                                                                                                                                                          |
| -------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Node.js                    | 24.18.1 LTS, `.nvmrc` 고정                                       | Expo SDK 57의 최소 Node는 22.13.x다. 신규 기반은 유지보수 단계의 22 대신 현재 LTS 24를 사용한다. `engines`는 Expo가 지원하는 22.13 이상과 차기 26까지 허용하고, 개발·CI 기준은 `.nvmrc`의 정확한 버전이다.                                                                |
| 패키지 관리자              | npm 11.13.0, lockfile v3                                         | Node 공식 배포에 포함되고 별도 Corepack 준비가 필요 없다. `packageManager`로 버전을 기록하고 CI는 `npm ci`를 사용한다. lockfile은 의존성 변경 PR에서만 갱신한다.                                                                                                          |
| Expo                       | 안정판 SDK 57 + Continuous Native Generation + `expo-dev-client` | SDK 57은 React Native 0.86과 React 19.2.3 조합이며 Android 7+, iOS 16.4+를 지원한다. `expo-dev-client`와 EAS development profile로 Expo Go가 아닌 Development Build를 표준화한다. `android/`, `ios/` 생성물은 커밋하지 않고 앱 설정에서 재생성한다.                       |
| Navigation                 | React Navigation 7 native stack                                  | boot/auth/onboarding/main/workout/safety modal을 명시적 typed route로 관리하기 쉽고, 부트 완료 시 `resetRoot` 한 번으로 history에서 Splash를 제거할 수 있다. 이번 slice는 `Splash`, `Auth`, `Main` 경계만 만든다. 인증 복원 adapter가 준비되기 전 기본 목적지는 `Auth`다. |
| 컴포넌트 테스트            | Jest 29 + `jest-expo` + React Native Testing Library 13.3        | Expo SDK 57이 검증한 Jest 29, React 19/RN 0.86을 지원하는 RNTL 조합과 사용자 관점의 접근성 query를 함께 사용한다. Splash는 로컬 자산, 접근성 텍스트, 390×844/320×568 레이아웃, reduced motion, animation cleanup, 부트 실패 재시도, 단일 navigation을 검증한다.           |
| E2E                        | Maestro 예정, 이번 slice에는 미설치                              | YAML 기반으로 Development Build의 인증·온보딩·수동 체크인·REST/STOP·주간 리포트 acknowledgement 흐름을 검증할 예정이다. 화면 한 개뿐인 현재 단계에서는 네이티브 E2E 기반을 추가하지 않는다.                                                                               |
| Formatter/linter/typecheck | Prettier 3, ESLint 9 + `eslint-config-expo`, TypeScript strict   | Expo config plugin의 검증된 peer 범위 안에서 사용한다. `npm run format:check`, `npm run lint`, `npm run typecheck`를 CI 명령으로 사용한다.                                                                                                                                |
| Production bundle check    | Android와 iOS 각각 `expo export`                                 | 이 명령은 production mode JS bundle과 로컬 자산 해석을 검증한다. 스토어 서명 네이티브 바이너리는 EAS project/signing 설정 후 `eas build --profile production`으로 별도 검증한다.                                                                                          |

## Splash 구현 경계

- 원본 HTML, WebView, Claude Design runtime을 사용하지 않는다.
- `question-mark`는 56px/112px, `splash-island`는 460px/920px 폭의 1x/2x PNG로 앱 자산화한다. 원본 비율과 alpha를 유지하면서 최대 decode 크기를 줄인다.
- Baloo 2 variable TTF와 Jua Regular TTF를 `src/assets/fonts`에 로컬 번들하고 각 OFL 원문을 `src/assets/fonts/licenses`에 보존한다. `expo-font` config plugin으로 Android/iOS 빌드에 포함하고, 웹에는 `FontDisplay.SWAP`으로 로드한다. 로드 완료 전이나 실패 시 고정된 텍스트 영역 안에서 시스템 sans-serif fallback을 사용한다.
- 화면 좌표는 390×844 절대값을 복사하지 않고 가용 safe-area 크기의 비율과 최대 폭으로 계산한다. portrait만 지원한다.
- 플랫폼 reduced-motion 설정을 보수적으로 먼저 적용하고 설정 확인 후에만 2.4초 상하 loop를 시작한다. unmount 시 loop를 중단한다.
- 현재 bootstrap adapter는 토큰·사용자·건강 데이터를 읽지 않는다. 이후 Firebase adapter가 `Auth` 또는 `Main`만 반환하며, 실패는 재시도 가능한 Splash 오류 상태로 전환한다.

## 계약 충돌 유지

정확한 생년월일과 성별·키·체중 필수 UI는 PM 검증된 이관 대상이다. 기존 API·DB 계약에는 해당 필수 request/persistence가 없거나 nullable이므로 이번 기반 작업은 이를 변경하지 않는다. 향후 Profile UI는 로컬 폼 경계까지만 구현하고 계약에 없는 필드를 전송하거나 저장 성공으로 처리하지 않는다.

## 알려진 도구 체인 보안 항목

2026-08-12 `npm audit --omit=dev --audit-level=moderate`는 18건(중간 7, 높음 11)을 보고한다. 경로는 Expo/RN build tooling의 `metro@0.84.4 → image-size@1.2.1`과 `@expo/config-plugins@57.0.7 → xcode@3.0.1 → uuid@7.0.3`이다. 현재 Splash는 신뢰된 저장소 PNG만 빌드 입력으로 사용하며 외부 이미지를 이 parser에 전달하지 않는다. npm이 제안하는 `--force` 수정은 Expo 53 또는 React Native 0.72로 호환성을 깨뜨리는 downgrade이므로 적용하지 않는다. Expo SDK의 upstream dependency 갱신을 추적하고 SDK 57 호환 patch가 제공되면 lockfile을 갱신한다.

## 참고 자료

- Expo SDK 57 버전·Node·OS 표: <https://docs.expo.dev/versions/latest/>
- Expo Development Build: <https://docs.expo.dev/develop/development-builds/introduction/>
- React Navigation 설치와 요구사항: <https://reactnavigation.org/docs/getting-started/>
- Node.js release policy: <https://nodejs.org/en/about/previous-releases>
