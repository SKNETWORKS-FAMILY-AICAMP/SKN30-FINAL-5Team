# FE-11 소셜 로그인 UI 구현 계획

## 범위

- 기존 이메일·비밀번호 로그인과 회원가입 경로를 유지한다.
- Google과 Kakao 모두 앱에서 PKCE S256을 생성하고 백엔드 authorization-code/OIDC 교환 뒤 받은
  Firebase custom token을 Firebase SDK에서 즉시 소비한다.
- Naver, 계정 연결·해제, 계정 병합은 구현하지 않는다.

## 예상 변경 파일

- 인증: `frontend/src/auth/firebase.ts`, `frontend/src/auth/socialOAuth.ts`
- 화면·연결: `frontend/src/features/auth/LoginScreen.tsx`, `SignInScreen.tsx`,
  `frontend/src/app/SessionProvider.tsx`
- 공개 설정: `frontend/src/config/env.ts`, `frontend/.env.example`
- 프리뷰·테스트: `frontend/src/features/preview/authPreview.ts`, `frontend/tests/AuthScreens.test.tsx`,
  `SignInScreen.test.tsx`, `SessionRejectedToken.test.tsx`, `SocialOAuth.test.ts`,
  `FirebaseSocialAuth.test.ts`, `demoFlow.test.tsx`, `setup.ts`
- 앱 의존성: `frontend/package.json`, `frontend/package-lock.json`

## API·보안·호환 위험

- 공개 API 스키마는 변경하지 않고 `POST /api/v1/auth/social/{provider_code}/authorize-init`과
  `POST /api/v1/auth/social/{provider_code}/exchange`를 `GOOGLE | KAKAO` provider-neutral client에서
  그대로 소비한다.
- `EXPO_PUBLIC_GOOGLE_OAUTH_REDIRECT_URI`, `EXPO_PUBLIC_KAKAO_REDIRECT_URI`는 provider console과
  백엔드 allowlist에 등록한 provider별 exact HTTPS callback이어야 한다. custom scheme fallback은
  사용하지 않으며 누락·비HTTPS 값은 로그인 전에 명확한 설정 오류로 거부한다.
- PKCE verifier, state, nonce, authorization code, Firebase custom token은 메모리의 한 로그인 호출
  범위에서만 보관하고 로그·스토리지·오류 문구에 남기지 않는다.
- Expo의 `EXPO_PUBLIC_*` 값은 번들 공개값이므로 provider secret을 추가하지 않는다.
- `expo-crypto`는 네이티브 CSPRNG와 PKCE SHA-256을, `expo-web-browser`는 OS 인증 세션과 앱 callback을
  제공하기 위해 필요하다. 두 모듈 모두 Expo SDK 57 호환 버전으로 고정하며 provider credential을
  포함하지 않는다.
- Google·Kakao의 provider별 redirect URI allowlist는 실제 Android/iOS 기기에서 출시 전 확인한다.
  이메일 로그인 인터페이스는 유지해 이전 사용자의 접근을 보존한다.

## 검증

- formatter, ESLint, TypeScript
- 인증 화면 및 Kakao OAuth component/unit tests와 전체 frontend test suite
- Android·iOS production export
- `git diff --check`, 변경 파일·민감정보·의도하지 않은 backend 변경 검토

### 실행 결과와 통합 단계 이관

- Prettier check, ESLint, TypeScript는 통과했다.
- FE-11 변경 영역 테스트(OAuth client, Firebase custom-token 소비, 로그인 화면, 환경 설정)는
  통과했다.
- 전체 테스트는 556개 중 545개가 통과했고, FE-11과 무관한 `WorkoutScreen.test.tsx` 및
  `PreviewGallery.test.tsx`의 기존 비동기 `waitFor` 11개가 저공간·고부하 환경에서 시간 초과했다.
- 공간 확보 후 Android와 iOS production export를 하나씩 실행해 모두 통과했다. 플랫폼별 검증 직후
  재생성 가능한 `dist`를 삭제해 다음 검증 공간을 확보했다.
