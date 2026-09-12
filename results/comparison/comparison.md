| 지표 | A. Single LLM | B. Single Agent + RAG | C. Multi-Agent + RAG |
|---|---|---|---|
| 실행 수 | 28 | 28 | 28 |
| Constraint Satisfaction | 0.8929 | 1.0 | 0.8571 |
| LLM Plan Rate (fallback 제외) | 0.6071 | 1.0 | 0.8571 |
| Plan Delivery Rate (fallback 포함) | 0.8929 | 1.0 | 0.8571 |
| Safety Compliance | 1.0 | 1.0 | 1.0 |
| Workflow Success | 0.8929 | 1.0 | 0.8571 |
| Structured Output Success | 1.0 | 1.0 | 0.8929 |
| Critical 실패 | 0 | 0 | 0 |
| Judge 평균 | 3.6389 | 4.0833 | 4.4028 |
| Judge PERSONALIZATION | 4.0 | 4.5 | 4.8333 |
| Judge FEASIBILITY | 3.9167 | 4.3571 | 4.5833 |
| Judge OVERALL_QUALITY | 3.6667 | 4.4286 | 4.5833 |
| P50 Latency (ms) | 18218 | 14031 | 25219 |
| P95 Latency (ms) | 30313 | 20359 | 36141 |
| LLM 호출 (합계) | 28 | 28 | 109 |
| 1회 실행당 호출 | 1.0 | 1.0 | 3.8929 |
| 1회 실행당 토큰 | 4360.5 | 7474.5 | 26645.5 |
