# Integrations

Firebase, Google/Kakao/Naver OAuth, 선택적 LLM을 adapter로 격리합니다. 외부 SDK 타입을 domain에 노출하지 않습니다.

`firebase_auth.py`는 Firebase Admin SDK와 Application Default Credentials를 사용해 ID Token을
검증합니다. `FIREBASE_PROJECT_ID`가 없으면 애플리케이션은 기동하되 보호 API 인증을
`AUTH_PROVIDER_UNAVAILABLE`로 닫습니다. token과 decoded subject는 로그에 남기지 않습니다.

`calendar_provider.py`는 local/CI와 production-disabled 구성에서 사용하는 unavailable null object와
synthetic contract adapter입니다. Google Calendar 원시 payload나 token을 domain에 전달하지 않으며
실제 HTTP adapter는 `ACCEPTED` ADR-0010의 9C-2C 범위입니다.
