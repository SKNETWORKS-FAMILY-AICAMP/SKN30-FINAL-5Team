# ADR-0011: LLM narration provider 계약

- 상태: PROPOSED
- 날짜: 2026-08-18
- 소유자: 백엔드 개발팀장
- 승인자: 개발팀장 + PM(안전 문구 톤), 백엔드 owner(DB 스키마)
- 관련 요구사항/이슈: #61, `docs/ARCHITECTURE.md` 14절(LLM 공급자 미확정),
  `docs/DOMAIN_RULES.md` 9절(LLM 경계), `docs/DATA_MODEL.md` 9.8절

## 배경

`backend/app/integrations/`에는 Firebase, Calendar, 생년월일 암호화 adapter만 있고 LLM adapter가
없었다. `docs/ARCHITECTURE.md`는 LLM 공급자와 설명 기능의 MVP 포함 여부를 미확정으로 남겨 두었고,
`docs/DOMAIN_RULES.md` 9절은 LLM이 담당할 수 있는 범위를 "검수된 reason code를 사용자 친화적인
문장으로 변환"과 "안전 결과를 바꾸지 않는 마스코트 문구"로 이미 한정하고 있었다.

그동안 공개 응답의 `summary`, `public_agent_summaries[].summary`, `safety_summary.summary`는
repository 조회 시점에 하드코딩된 한 문장이었다. 결정 시점에 저장되지 않으므로 문구의 출처와
버전을 감사할 수 없었다.

## 결정

1. LLM 공급자는 OpenAI Responses API로 고정하고 `backend/app/integrations/llm_provider.py`
   adapter 뒤에 둔다. 기본값은 비활성(`LLM_ENABLED=false`)이며 이때 null object가 사용된다.
2. LLM은 **narration 전용**이다. 결정, 안전 상태, veto, 후보, 요청 시간은 결정적 규칙과
   Coordinator만 만든다. narration은 이미 확정된 code를 문장으로 바꾸는 단계이며 code를 추가·삭제·
   변경할 수 없다.
3. narration은 결정 생성 시점에 한 번 수행하고 `decision_explanations`에 저장한다. 조회는 저장된
   문구를 읽으며 LLM을 호출하지 않는다.
4. 다음 경우에는 LLM을 **호출하지 않고** 검수된 템플릿을 사용한다.
   - safety status가 `PASS`/`REVISE`가 아닌 경우
   - 최종 action이 `REST` 또는 `STOP_AND_SEEK_HELP`인 경우
   - SafetyAgent proposal이 없거나 `safety_vetoed`가 `false`가 아닌 경우. 승인된 대체 운동으로
     바꾼 `REVISE`/`CHANGE`처럼 veto를 동반하는 결정도 여기에 포함한다.
   - 공개 plan이 없는 `NEEDS_INPUT`/`FAILED`
   - 전송 payload에 machine code가 아닌 값이 하나라도 있는 경우
5. safety summary 문장은 LLM 경로에서도 항상 템플릿 문구를 유지한다.
6. LLM 응답은 요청한 slot 집합과 정확히 일치해야 하고, 문장별로 길이·문자 집합·금칙어(진단·처방·
   치료 어휘, 미수행을 벌점으로 읽히게 하는 어휘)를 검증한다. 하나라도 실패하면 전체를 버리고
   템플릿으로 되돌린다.
7. 전송 payload는 `^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$`를 만족하는 code, 정수, 불리언, null만
   허용한다. 직접 식별자, 날짜, 자유 문자열, 원시 건강·웨어러블 값은 이 검증을 통과할 수 없다.
8. 저장 레코드는 `source_code`(TEMPLATE|LLM), `template_version`, `prompt_version`, `model_code`,
   `fallback_reason_code`를 남긴다. graph·policy·catalog·safety rule version은 기존 `decision_runs`가
   계속 보유한다.

## 결정 이유

- veto 우회 가능성을 코드 구조에서 제거한다. narration은 문장 필드만 교체하므로 LLM 출력이 code를
  바꿀 경로 자체가 없다.
- 통증·이상 반응 화면은 LLM을 아예 호출하지 않으므로 톤 규칙이 모델 품질에 의존하지 않는다.
- 문구 출처와 버전을 저장하면 동일 입력의 결정 재현성과 문구 감사를 분리해서 검증할 수 있다.
- 기본 비활성이므로 MVP 흐름은 외부 의존성 없이 그대로 동작한다.

## 검토한 대안

- **Anthropic Claude 사용**: 이슈 #61이 OpenAI adapter를 지정했고, 어느 쪽이든 adapter 뒤에서
  교체 가능하다. `NarrationProviderPort`를 구현하는 adapter를 추가하면 되므로 공급자 교체 비용은 낮다.
- **공식 OpenAI Python SDK 사용**: 재시도·타임아웃 처리를 제공하지만 선택 기능 하나 때문에 상시
  production dependency가 늘어난다. 요청이 단일 JSON POST이므로 표준 라이브러리 transport와
  주입 가능한 `JsonHttpTransport`로 충분하고, 테스트에서 실제 네트워크 없이 계약을 검증할 수 있다.
- **조회 시점 narration**: 응답마다 지연과 비용이 발생하고 같은 결정이 매번 다른 문구를 갖게 되어
  감사와 재현성이 나빠진다.

## 선택하지 않은 대안과 이유

- LLM이 후보·루틴·안전 판단을 생성: 검수 카탈로그와 안전 veto를 우회한다.
- LLM 출력의 부분 채택: 일부 문장만 교체하면 문구 톤이 섞이고 실패 원인 추적이 어렵다.
- 실패 시 재시도 루프: 동기 결정 흐름의 응답 시간을 늘린다. 첫 실패에서 템플릿으로 되돌린다.

## 결과와 영향

- 공개 API 응답 필드와 타입은 변하지 않는다. `summary` 계열 문자열의 출처만 바뀐다.
- `decision_explanations` 테이블과 migration `0019_decision_explanations`가 추가된다.
- narration 레코드가 없는 이전 decision은 기존 기본 문구로 계속 응답한다.
- `DecisionService`는 선택적 `narration_provider`를 받는다. 라우트는 provider를 주입만 하고 직접
  호출하지 않는다.

## 보안·개인정보·호환성 영향

- API key는 `OPENAI_API_KEY` 설정으로만 읽고 로그·본문·fixture에 남기지 않는다.
- provider 예외 메시지는 요청 내용을 되비출 수 있으므로 저장·로그에 복사하지 않는다.
- 전송 payload는 code allowlist 검증을 통과한 값만 포함한다.
- 내부 instruction과 slot 구조는 클라이언트 응답에 포함하지 않는다.

`docs/DOMAIN_RULES.md` 9절의 LLM 경계는 그대로 유지하며, 이 ADR은 그 안에서 더 보수적인 실행 규칙을
정의한다. 9절 본문에 veto 조건을 명시하려면 안전 규칙 변경 절차(개발팀장 + PM + 외부 도메인 검수)를
따른다.

## 아직 확정되지 않은 사항

- production에서 사용할 정확한 OpenAI model id. `LLM_MODEL_CODE` 기본값은 운영 배포 전에 공급자의
  현재 모델 목록으로 확인해야 한다.
- narration 기능의 MVP 실제 활성화 여부와 비용 상한.
- 코칭 스타일(`SUPPORTIVE`/`CONCISE`/`ENERGETIC`)별 템플릿 분화 여부.

## 후속 작업

- 운영 활성화 전 model id 확인과 비용·지연 측정.
- 결정 생성 트랜잭션 안에서 narration을 수행하므로, 활성화 시 타임아웃(`LLM_TIMEOUT_SECONDS`)과
  실패율을 관측한 뒤 비동기 후처리 전환 필요 여부를 판단한다.
