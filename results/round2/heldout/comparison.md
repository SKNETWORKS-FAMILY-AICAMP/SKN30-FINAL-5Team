| 지표 | A. Single LLM | B. Single Agent + RAG | C. Multi-Agent + RAG |
|---|---|---|---|
| 실행 수 | 29 | 29 | 29 |
| Constraint Satisfaction | 1.0 | 1.0 | 1.0 |
| LLM Plan Rate (fallback 제외) | 0.0345 | 0.8966 | 0.7586 |
| Plan Delivery Rate (fallback 포함) | 1.0 | 1.0 | 1.0 |
| Safety Compliance | 1.0 | 1.0 | 1.0 |
| Workflow Success | 1.0 | 1.0 | 1.0 |
| Structured Output Success | 0.1724 | 1.0 | 0.8276 |
| Critical 실패 | 0 | 0 | 0 |
| Judge 평균 | 2.9138 | 3.7011 | 3.6552 |
| Judge PERSONALIZATION | 3.6897 | 4.3103 | 3.9655 |
| Judge FEASIBILITY | 3.2414 | 3.6552 | 3.8276 |
| Judge OVERALL_QUALITY | 3.1034 | 3.7241 | 3.7241 |
| P50 Latency (ms) | 13796 | 22047 | 32390 |
| P95 Latency (ms) | 15703 | 48563 | 48813 |
| LLM 호출 (합계) | 29 | 29 | 111 |
| 1회 실행당 호출 | 1.0 | 1.0 | 3.8276 |
| 1회 실행당 토큰 | 4154.3 | 8808.2 | 20386.4 |
