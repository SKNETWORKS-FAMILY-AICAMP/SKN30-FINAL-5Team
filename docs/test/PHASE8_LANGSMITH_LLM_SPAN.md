# PHASE 8 LangSmith LLM Span 결과

- 실행일: 2026-09-11
- 승인: 개발팀장·PM 사용자 명시 승인(ADR-0020)
- LangSmith project / experiment: `helkki` / `multi-agent-v1`
- 모델: `OPENAI:gpt-5.6-terra`
- case: `SQ-SIMPLE-001`
- 실행 제한: Judge 제외, provider 호출 최대 4회
- 로컬 산출물: `results/phase8_llm_span/`

## 결과

| 항목 | 결과 |
|---|---:|
| 실행 상태 | `SUCCEEDED` |
| 계획 생성 | 성공 |
| provider 호출 | 4 |
| input tokens | 24,140 |
| output tokens | 3,332 |
| total tokens | 27,472 |
| wall clock | 27,328 ms |
| repair | 0 |
| fallback | 사용 안 함 |
| critical failure | 0 |

LangSmith UI에서 최신 root trace의 total token은 27.47K, latency는 27.32초로 표시돼
로컬 `InvocationAudit` 집계와 일치했다.

## LLM span 확인

root `LangGraph` 아래에서 다음 네 provider span을 직접 확인했다.

- `agent_feasibility` → `ChatOpenAI gpt-5.6-terra`
- `agent_recovery` → `ChatOpenAI gpt-5.6-terra`
- `agent_training` → `ChatOpenAI gpt-5.6-terra`
- `coordinator_agent` → `ChatOpenAI gpt-5.6-terra`

따라서 기존의 워크플로 노드 trace뿐 아니라 PHASE 8에서 누락됐던 prompt·모델 응답·provider token
span도 승인된 옵트인 경로에서 확인 가능하다.

## 안전 경계

- Secrets Manager 값은 실행 프로세스 환경에만 주입했으며 파일·로그·결과물에 기록하지 않았다.
- `LLM_AGENTS_TRACING_ENABLED` 기본값은 계속 `false`다.
- production compose에는 tracing ON 설정을 추가하지 않았다.
- 실제 전송은 승인된 평가 실행에서만 명시적으로 활성화했다.

## 결론

ADR-0020의 두 요구를 모두 실측했다. 기본 경로는 provider tracing을 차단하고, 승인된 옵트인 경로는
네 LLM 호출을 LangSmith child span으로 전송한다. PHASE 8 LLM span 승인·구현·최소 실측은 완료됐다.
