# ADR-0020: LangSmith 트레이싱을 shadow·demo 표면에 한정 허용

- 상태: ACCEPTED
- 날짜: 2026-09-07
- 소유자: 백엔드 개발팀장
- 승인 근거: 사용자 명시 요청(2026-09-07). `TECHNICAL_PLAN.md`가 요구한 "별도 승인"에 해당한다
- 관련: ADR-0013(V3 LangGraph runtime 도입), ADR-0015(단일 라운드 agent 구성), `AGENTS.md` 8절
- 관련 코드: `backend/app/integrations/langsmith_tracing.py`

## 배경

`TECHNICAL_PLAN.md`는 V3 runtime을 도입하되 **"persistent checkpointer, 장기 memory, LangSmith
SaaS 전송은 별도 승인 없이는 포함하지 않는다"**고 정했고, 같은 문서 V3-C1 절은 "LangSmith tracing과
callbacks는 명시적으로 비활성화"를 요구했다. 구현도 그대로 따라가
`StructuredChatInvoker`가 모든 호출을 `tracing_context(enabled=False)`로 감싸고 있다.

그 결과 멀티에이전트 실행을 관찰할 수 있는 수단이 저장된 사후 기록뿐이다.

- `InvocationAudit`: role·phase·status·attempt·latency·token count
- `V3GraphResult`: round-one proposals, coordinator 초안과 repair 결과, fallback spec,
  integrity validation, compiled plan
- shadow 실행의 JSONL 산출물과 `decision_*` 테이블

이 기록은 재현에는 충분하지만 **"세 specialist 중 어느 branch가 느렸고 coordinator가 무엇을 보고
repair로 갔는지"**를 실행 중에 보여주지 못한다. 프롬프트 조정과 지연 분석이 로그 대조 작업이 된다.

## 결정

**LangSmith를 staging의 shadow·demo 런타임에서만 허용한다. 프로덕션 decision 경로에는 tracer를
주입하지 않는다.**

### 활성화 방식: 환경변수가 아니라 주입

두 호출 지점의 `tracing_context(enabled=False)`는 **설정으로 바뀌지 않고 그대로 남는다.**
대신 composition이 만든 `LangChainTracer`를 callback으로 넘길 때만 트레이싱이 일어난다.

`langchain_core`가 이 비대칭을 보장한다. `_configure`는 명시적으로 전달된 handler를 무조건
callback manager에 넣고, tracing context flag는 **암묵적** tracer를 추가할지 결정할 때만 본다.
따라서

- `LANGSMITH_TRACING=true`를 환경에 심어도 어떤 경로에서도 전송이 시작되지 않는다.
- tracer를 건네받은 composition만 전송한다.

환경변수 하나로 전 경로가 켜지는 구조를 피한 것이 이 ADR의 핵심이다. LangSmith SDK 자체의
`LANGSMITH_TRACING` 변수는 **읽지 않으며**, 저장소 게이트는 별도 이름인
`LANGSMITH_TRACING_ENABLED`를 쓴다.

### 허용 표면

| 표면 | tracer 주입 | 근거 |
|---|---|---|
| `build_v3_shadow_runtime` | 예 | 합성 입력 기반 오프라인 평가. 사용자 트래픽이 아니다 |
| `build_v3_demo_runtime` | 예 | `APP_ENV=staging` + `V3_EXECUTION_PROFILE=DEMO`에서만 구성된다 |
| `build_structured_chat_invoker` (프로덕션) | **아니오** | 사용자 decision 경로 |
| `build_v3_langgraph_runtime` | **아니오** | 같은 이유 |

### fail-closed 게이트

- `LANGSMITH_TRACING_ENABLED=true`인데 `LANGSMITH_API_KEY`가 없으면 기동을 막는다.
  트레이스가 조용히 사라지는 것보다 낫다.
- `LANGSMITH_ENDPOINT`는 https만 허용한다.
- `APP_ENV=production`에서 켜면 기동을 막는다.

## 무엇이 LangSmith로 나가는가

이 결정이 새로 노출하는 데이터는 없다. **이미 OpenAI로 나가고 있는 payload와 동일한 내용**이
LangSmith에도 기록될 뿐이다.

`llm_agents/payload.py`가 전송 전에 강제하는 경계는 그대로다.

- 금지 필드 목록: `user_id`, `email`, `name`, `birthdate`, `pain*`, `severity`,
  `intensity_score`, `health*`, `wearable*`, `calendar*`, `retrieval_metadata`,
  `similarity_score*` 등
- 허용되는 것: 승인된 머신 코드, 카탈로그 정수(초·세트·반복), envelope/pool hash, 버전 코드

즉 통증 부위·NRS·수면·식별자는 애초에 payload에 들어가지 않는다. LangSmith가 받는 것은
운동 카탈로그 코드와 계획 제약이다.

그럼에도 **제3자 처리자가 하나 늘어나는 것은 사실**이므로 staging 합성·데모 데이터로 범위를 묶고,
프로덕션 사용자 트래픽은 제외한다.

## 이유

- 관찰 수단이 사후 기록뿐이면 멀티에이전트 조정 문제를 재현 없이 진단할 수 없다.
- 반대로 전 경로를 열면 실사용자 트래픽이 제3자로 나가고, 그건 개인정보 처리방침(BL-6) 범위를
  다시 정의해야 하는 결정이다. 관측 편의를 위해 감수할 만한 교환이 아니다.
- staging 합성 데이터는 그 교환 없이 필요한 정보 대부분을 준다.

## 대안과 선택하지 않은 이유

- **설정으로 `tracing_context(enabled=...)`를 뒤집는다**: 가장 짧지만 환경변수 하나로 프로덕션
  경로까지 켜진다. 사고 한 번의 대가가 너무 크다.
- **self-hosted LangSmith**: SaaS 전송 문제는 사라지지만 운영 부담이 새로 생기고, 4명 팀에서
  관측 도구 하나를 위해 감당할 규모가 아니다. 필요가 확인되면 다시 검토한다.
- **OpenTelemetry로 자체 수집**: 벤더 종속이 없지만 collector·백엔드·대시보드를 전부 세워야 하고,
  LangGraph node 구조를 그대로 보여주는 기성 뷰가 없다.
- **현행 유지(저장 기록만)**: 재현에는 충분하나 조정·지연 문제 진단이 여전히 로그 대조다.

## 결과

- `Settings`에 `langsmith_tracing_enabled`, `langsmith_endpoint`, `langsmith_api_key`,
  `langsmith_project` 추가. 기본값은 꺼짐.
- `backend/app/integrations/langsmith_tracing.py` adapter가 tracer 생성을 소유한다.
- `StructuredChatInvoker`와 `V3LangGraphRuntime`이 `tracing_callbacks`를 받는다. 기본값은 빈 튜플.
- `V3LangGraphRuntime.ainvoke`도 `tracing_context(enabled=False)`로 감싼다. 그래프 층에서도
  암묵적 tracer가 붙지 못하게 한다.
- `TECHNICAL_PLAN.md`의 두 문장을 이 ADR의 범위로 갱신한다.
- API key는 `.env` 또는 Secrets Manager에 둔다. `.env.example`에는 빈 값만 둔다.

## 미확정 사항

- 트레이스 보관 기간과 LangSmith workspace 접근 권한자 목록. 운영 계약으로 별도 확정한다.
- 프로덕션 경로 관측이 실제로 필요해질 경우의 대안(self-hosted 또는 OTel). 필요가 측정으로
  확인되면 새 ADR로 다룬다.
