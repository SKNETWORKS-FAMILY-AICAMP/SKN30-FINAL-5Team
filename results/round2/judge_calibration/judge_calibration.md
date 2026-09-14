# Judge calibration

Discrimination: model plan 3.7449 vs deterministic fallback 2.8991 (difference 0.8458, n=49/38)
Groundedness: pearson(duration error, FEASIBILITY) = -0.0297 over 49 authored plans

| comparison | authored only | wins A | wins B | ties | p |
|---|---|---:|---:|---:|---:|
| C. Multi-Agent vs B. Single Agent + RAG | no | 12 | 15 | 2 | 0.7011 |
| C. Multi-Agent vs B. Single Agent + RAG | yes | 9 | 9 | 1 | 1.0 |
| B. Single Agent + RAG vs A. Single LLM | no | 23 | 5 | 1 | 0.0009 |
| C. Multi-Agent vs A. Single LLM | no | 23 | 4 | 2 | 0.0003 |
