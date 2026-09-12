# PHASE 9 Performance / Failure Evaluation 결과

- 실행일: 2026-09-11
- 성능 원본: `results/paid/evaluation_summary.json` (실 provider 14건)
- 실패 평가: 실제 LangGraph + scripted fault injection 10개 시나리오
- 통합 산출물: `results/phase9/performance_failure.json`

## 결론

실 provider의 전체 그래프 지연은 P50 28.047초, P95 31.281초였고 workflow completion은
85.71%였다. 실패 주입 10개 시나리오는 모두 안전하게 종료됐으며 critical failure와 처리되지 않은
node exception은 0건이었다.

## 성능 지표

| 지표 | 결과 |
|---|---:|
| 표본 | 14 run |
| P50 latency | 28,047 ms |
| P95 latency | 31,281 ms |
| 최소 / 최대 | 4,344 / 39,000 ms |
| 평균 token usage | 26,096.2 / run |
| input / output token 합계 | 317,291 / 48,056 |
| 그래프 LLM 호출 | 54회, 평균 3.8571회/run |
| Workflow Completion Rate | 0.8571 |
| Fallback Rate | 0.2143 |
| Repair Rate | 0.0000 |

Judge 12회는 서비스 workflow가 아니라 평가 오버헤드이므로 LLM 호출 수에서 제외했다. percentile은
PHASE 6과 동일한 `nearest_rank_percentile`을 재사용했다.

## 실패 평가

| 시나리오 | 결과 | 안전 처리 |
|---|---|---:|
| Retriever vector 결과 없음 | PostgreSQL 승인 pool의 결정적 순위 사용, 계획 성공 | PASS |
| LLM timeout | failure code 기록 후 결정적 fallback | PASS |
| Structured output parsing 오류 | schema failure 기록 후 결정적 fallback | PASS |
| Agent exception | provider unavailable로 정규화 후 fallback | PASS |
| 외부 LLM API 전체 실패 | 결정적 fallback | PASS |
| 수행 불가능한 runtime 입력 | 계획 없이 `FAILED` | PASS |
| 필수 시간 누락 | graph 진입 전 거부 | PASS |
| 필수 목표 누락 | graph 진입 전 거부 | PASS |
| 필수 장소 누락 | graph 진입 전 거부 | PASS |
| Graph repair cycle | 첫 repair만 허용, 다음에는 fallback | PASS |

- Safe Termination Rate: **10/10 = 1.0000**
- Critical failure: **0**
- 처리되지 않은 node error: **0/6 graph runtime probe = 0.0000**
- Parsing Error Rate: **2/19 provider invocation = 0.1053**

Parsing Error Rate는 parsing/schema 오류를 의도적으로 포함한 controlled fault matrix 내부 비율이다.
운영 발생률 추정치가 아니다. 중요한 판정은 두 오류 모두 사용자에게 잘못된 계획을 노출하지 않고
failure code와 fallback 또는 fail-closed로 끝났다는 점이다.

## 해석

Workflow Completion 85.71%는 안전 실패가 아니라 기존 D-5의 가용성 문제다. advisory specialist가
non-READY면 coordinator가 실행되지 않고, 합성 pool에서 fallback이 요청 시간을 채우지 못한 2건이
계획 없이 종료됐다. 안전성은 유지됐지만 개인화된 계획 전달률이 낮아졌다.

P95가 31초를 넘으므로 동기 요청 UX에서는 loading·timeout 안내가 중요하다. 다만 이번 phase는 저장된
14건 표본의 재집계이며 더 큰 운영 표본의 tail latency를 추정하지 않는다.

## 범위와 한계

- 성능은 실제 provider 결과, 실패율은 재현 가능한 scripted fault 결과다. 둘을 같은 모집단으로 합치지 않았다.
- 외부 API 실패는 LLM provider adapter의 exception 경계를 검증했다. HTTP·DB·OAuth 통합 장애는 기존
  API/integration test의 책임이며 이번 그래프 평가에 포함하지 않았다.
- Retriever 실패는 vector 결과가 없을 때의 순위 fallback이다. PostgreSQL 승인 운동 pool 자체가 없는
  경우는 invalid/unsatisfiable input 경로에서 계획 없이 종료된다.
