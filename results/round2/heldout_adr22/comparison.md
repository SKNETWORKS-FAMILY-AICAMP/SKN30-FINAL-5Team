| 지표 | A. Single LLM | B. Single Agent + RAG | C. Multi-Agent + RAG |
|---|---|---|---|
| 실행 수 | 29 | 29 | 29 |
| Constraint Satisfaction | 1.0 | 1.0 | 1.0 |
| LLM Plan Rate (fallback 제외) | 0.1034 | 0.8621 | 0.7241 |
| Plan Delivery Rate (fallback 포함) | 1.0 | 1.0 | 1.0 |
| Safety Compliance | 1.0 | 1.0 | 1.0 |
| Workflow Success | 1.0 | 1.0 | 1.0 |
| Structured Output Success | 0.1724 | 1.0 | 0.7586 |
| Critical 실패 | 0 | 0 | 0 |
| Judge 평균 | 2.977 | 3.6322 | 3.5172 |
| Judge PERSONALIZATION | 3.8276 | 4.1379 | 3.931 |
| Judge FEASIBILITY | 3.2414 | 3.6207 | 3.5517 |
| Judge OVERALL_QUALITY | 3.1724 | 3.6552 | 3.6207 |
| P50 Latency (ms) | 13953 | 23922 | 27094 |
| P95 Latency (ms) | 17485 | 40390 | 43093 |
| LLM 호출 (합계) | 29 | 29 | 110 |
| 1회 실행당 호출 | 1.0 | 1.0 | 3.7931 |
| 1회 실행당 토큰 | 4403.2 | 8721.0 | 19247.7 |
