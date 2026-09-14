| 지표 | A. Single LLM | B. Single Agent + RAG | C. Multi-Agent + RAG |
|---|---|---|---|
| 실행 수 | 54 | 54 | 54 |
| Constraint Satisfaction | 0.9815 | 1.0 | 0.9815 |
| LLM Plan Rate (fallback 제외) | 0.0741 | 0.963 | 0.7407 |
| Plan Delivery Rate (fallback 포함) | 1.0 | 1.0 | 1.0 |
| Safety Compliance | 1.0 | 1.0 | 1.0 |
| Workflow Success | 1.0 | 1.0 | 1.0 |
| Structured Output Success | 0.1667 | 1.0 | 0.8333 |
| Critical 실패 | 0 | 0 | 0 |
| Judge 평균 | 2.9874 | 3.7377 | 3.5943 |
| Judge PERSONALIZATION | 3.6981 | 4.2778 | 3.8491 |
| Judge FEASIBILITY | 3.3019 | 3.7593 | 3.7547 |
| Judge OVERALL_QUALITY | 3.1698 | 3.8333 | 3.6415 |
| P50 Latency (ms) | 15391 | 25641 | 31813 |
| P95 Latency (ms) | 20546 | 48953 | 51047 |
| LLM 호출 (합계) | 54 | 54 | 208 |
| 1회 실행당 호출 | 1.0 | 1.0 | 3.8519 |
| 1회 실행당 토큰 | 4581.1 | 9171.7 | 22043.6 |
