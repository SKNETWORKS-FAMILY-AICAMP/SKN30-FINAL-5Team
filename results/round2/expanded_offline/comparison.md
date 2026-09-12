| 지표 | A. Single LLM | B. Single Agent + RAG | C. Multi-Agent + RAG |
|---|---|---|---|
| 실행 수 | 54 | 54 | 54 |
| Constraint Satisfaction | 0.9815 | 0.9815 | 0.9815 |
| LLM Plan Rate (fallback 제외) | 0.6296 | 0.6296 | 0.6296 |
| Plan Delivery Rate (fallback 포함) | 1.0 | 1.0 | 1.0 |
| Safety Compliance | 1.0 | 1.0 | 1.0 |
| Workflow Success | 1.0 | 1.0 | 1.0 |
| Structured Output Success | 0.6296 | 0.6296 | 0.6296 |
| Critical 실패 | 0 | 0 | 0 |
| Judge 평균 | 4.7327 | 4.7327 | 4.7327 |
| Judge PERSONALIZATION | 4.6226 | 4.6226 | 4.6226 |
| Judge FEASIBILITY | 4.6981 | 4.6981 | 4.6981 |
| Judge OVERALL_QUALITY | 4.8302 | 4.8302 | 4.8302 |
| P50 Latency (ms) | 15 | 16 | 47 |
| P95 Latency (ms) | 31 | 32 | 63 |
| LLM 호출 (합계) | 54 | 54 | 216 |
| 1회 실행당 호출 | 1.0 | 1.0 | 4.0 |
| 1회 실행당 토큰 | 1500.0 | 1500.0 | 5444.4 |
