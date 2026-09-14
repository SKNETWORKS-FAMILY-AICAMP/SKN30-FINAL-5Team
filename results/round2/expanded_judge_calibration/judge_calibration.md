# Judge calibration

Discrimination: model plan 3.7986 vs deterministic fallback 2.9062 (difference 0.8924, n=96/64)
Groundedness: pearson(duration error, FEASIBILITY) = -0.12 over 96 authored plans

| comparison | authored only | wins A | wins B | ties | p |
|---|---|---:|---:|---:|---:|
| C. Multi-Agent vs B. Single Agent + RAG | no | 19 | 29 | 5 | 0.1934 |
| C. Multi-Agent vs B. Single Agent + RAG | yes | 18 | 19 | 3 | 1.0 |
| B. Single Agent + RAG vs A. Single LLM | no | 48 | 3 | 2 | 0.0 |
| C. Multi-Agent vs A. Single LLM | no | 44 | 4 | 5 | 0.0 |
