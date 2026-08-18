# Integrations

Firebase, Google/Kakao/Naver OAuth, 선택적 LLM을 adapter로 격리합니다. 외부 SDK 타입을 domain에 노출하지 않습니다.

`firebase_auth.py`는 Firebase Admin SDK와 Application Default Credentials를 사용해 ID Token을
검증합니다. `FIREBASE_PROJECT_ID`가 없으면 애플리케이션은 기동하되 보호 API 인증을
`AUTH_PROVIDER_UNAVAILABLE`로 닫습니다. token과 decoded subject는 로그에 남기지 않습니다.

`calendar_provider.py`는 local/CI와 production-disabled 구성에서 사용하는 unavailable null object와
synthetic contract adapter입니다. Google Calendar 원시 payload나 token을 domain에 전달하지 않으며
실제 HTTP adapter는 `ACCEPTED` ADR-0010의 9C-2C 범위입니다.

`llm_provider.py`는 선택적 narration adapter입니다. 기본값은 `LLM_ENABLED=false`이며 이때
`UnavailableNarrationProvider` null object가 사용됩니다. `OpenAiNarrationProvider`는 OpenAI Responses
API에 code만 담긴 payload를 보내고 slot별 문장을 돌려받습니다. HTTP 호출은 주입 가능한
`JsonHttpTransport`(기본 표준 라이브러리 구현) 뒤에 있어 새 production dependency가 없습니다.

adapter는 결정을 만들지 않습니다. 안전 상태·veto·후보·요청 시간은 결정적 규칙과 Coordinator만
결정하며, provider 실패·비활성·검증 실패는 모두 `backend/app/modules/decisions/explanations.py`의
검수 템플릿 문구로 되돌아갑니다. API key와 요청·응답 본문, provider 원시 오류 메시지는 로그에
남기지 않습니다. 경계와 근거는 ADR-0011입니다.
