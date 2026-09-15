# Round 3 Multi-Agent 표적 반복 평가 결과

- 실행일: 2026-09-15
- 브랜치: `test/multi-agent-round3`
- 대상: `expanded_heldout_cases`의 conflict/complex planning case 28건
- 반복: architecture별 3회, 총 168 run
- 비교: B. Single-Agent+RAG / C. Multi-Agent+RAG
- 모델: `OPENAI:gpt-5.6-terra:reasoning-low`
- Judge: 미실행
- 호출 하드 스톱: 480회
- 실제 호출: 417회
- 산출물: `results/round3/conflict_complex_r3_paid_20260915/`

Round 2 공식 판정을 소급 변경하지 않는 후속 표적 평가다. 같은 dataset, 모델, 카탈로그, 정책,
compiler, integrity validator와 fallback을 사용했다. AWS Secrets Manager의 API key는 실행 프로세스
환경에만 주입했으며 파일·로그·산출물에 저장하지 않았다.

## 결과 요약

| 지표 | Single-Agent+RAG | Multi-Agent+RAG |
|---|---:|---:|
| run | 84 | 84 |
| 모델 직접 계획 | 81 (0.9643) | 73 (0.8690) |
| 모델 직접 계획 Wilson 95% CI | 0.9002~0.9878 | 0.7805~0.9253 |
| fallback 계획 | 3 | 11 |
| 계획 전달 | 84/84 (1.000) | 84/84 (1.000) |
| Safety Compliance | 1.000 | 1.000 |
| Workflow Success | 1.000 | 1.000 |
| Constraint Satisfaction (현행 정책 정정) | 1.000 | 1.000 |
| Critical failure | 0 | 0 |
| P50 latency | 19.532초 | 24.421초 |
| P95 latency | 38.563초 | 40.734초 |
| 호출 수 | 84 | 333 |
| 평균 token/run | 9,822.0 | 24,737.3 |

두 architecture의 모델 직접 계획을 같은 case·repeat 순서로 짝지으면 B 승 11, C 승 3, 동률
70이었다. decisive pair에서 B 승률은 0.7857이고 Wilson 95% CI는 0.5241~0.9243이다. 표본상 B가
앞섰지만 decisive pair가 14개뿐이므로 효과 크기를 확정값으로 일반화하지 않는다.

category별 모델 직접 계획률은 다음과 같다.

| Category | Single-Agent+RAG | Multi-Agent+RAG |
|---|---:|---:|
| complex (48 run) | 0.9792 | 0.8333 |
| conflict (36 run) | 0.9444 | 0.9167 |

## 반복 변동

| Architecture | 1회차 | 2회차 | 3회차 |
|---|---:|---:|---:|
| Single-Agent+RAG 직접 계획 | 27/28 | 28/28 | 26/28 |
| Multi-Agent+RAG 직접 계획 | 24/28 | 22/28 | 27/28 |

Multi-Agent의 직접 계획률은 0.7857~0.9643 범위로 흔들렸다. `SQ-HELD-022`는 처음 두 반복에서
specialist 단계 fallback이었지만 세 번째 반복에서는 직접 통과했다. 단일 실행만으로 architecture를
판정하면 안 된다는 Round 2 결론을 재확인한다.

## 실패 단계와 지연

Single-Agent의 모델 직접 계획 실패는 contract 1건, deterministic gate 2건이었다. Multi-Agent의
11건은 모두 contract 계열로 분류됐으며 invocation audit와 downstream consequence를 함께 세면
Training 5, Coordinator initial 5, Coordinator repair 1, compiler/PlanSpec absence 6, integrity 2가
관측됐다. 단계 수는 하나의 run에 중복될 수 있으므로 합계가 fallback 11건과 같지 않다.

Multi-Agent 역할별 provider 지연은 다음과 같다.

| 역할/phase | 호출 | 실패 | P50 | P95 |
|---|---:|---:|---:|---:|
| Training/Propose | 84 | 5 | 16.984초 | 30.437초 |
| Recovery/Propose | 84 | 0 | 2.703초 | 3.672초 |
| Feasibility/Propose | 84 | 0 | 2.672초 | 3.953초 |
| Coordinator/Initial | 79 | 5 | 6.922초 | 16.406초 |
| Coordinator/Repair | 2 | 1 | 11.296초 | 20.641초 |

전체 Multi P95 40.734초는 사전 기준 30초를 넘었다. Training P95만 30.437초이고 Recovery와
Feasibility는 병렬이므로, 후속 지연 개선은 Training 출력 안정화·payload와 Coordinator 호출 경로를
우선 검토해야 한다. 조건부 advisory 호출은 ADR-0015 구조 변경이므로 별도 승인 없이 구현하지 않는다.

## 평가 데이터 정정

`SQ-HELD-044`의 `prohibited_equipment_codes=[DUMBBELL]` 조건은 2026-08-27 승인된 장비 비게이트
정책과 충돌하는 오래된 평가 조건이었다. 덤벨 운동 포함은 서비스 결함이 아니며
`PROHIBITED_EQUIPMENT_REQUIRED` finding은 판정에서 제외한다. 같은 원천에서 생성된 장비 금지
시나리오는 후속 `heldout_cases_v2`·`expanded_heldout_cases_v2`에서 장비 보유 정보 없는
장소·시간 시나리오로 교체했다. 과거 실행의 원본 dataset과 manifest는 재현성을 위해 보존한다.

정책에 맞게 해석하면 B와 C의 Constraint Satisfaction은 모두 1.000이다. 이 정정은 이미 저장된
모델 출력, 직접 계획/fallback 분류, 지연, 호출 수와 토큰을 바꾸지 않으므로 아키텍처 우월성 판정에는
영향이 없다.

## 비용

실측 token은 입력 2,530,257, 출력 372,732였다. 2026-07-30 이후 공식 GPT-5.6 Terra 표준 가격
입력 $2/1M, 출력 $12/1M을 적용한 계산 비용은 **$9.5333**이다. cached-input 할인은 반영하지 않아
보수적인 계산이며 승인 한도 $40의 23.8%다. 가격 근거는 같은 산출물 디렉터리의
`pricing_reference.json`에 고정했다.

## 판정

- 안전·전달: 두 architecture 모두 Safety 1.000, Plan Delivery 1.000, critical 0으로 유지했다.
- 지연: 두 architecture 모두 30초 P95 기준 미달이며 Multi가 2.171초 느렸다.
- 직접 계획: B가 전체·complex·conflict 모두 C 이상이었다.
- 비용: Multi는 B 대비 호출 3.96배, 평균 token/run 2.52배였다.
- 평가 정정: 금지 장비 finding은 현행 정책과 충돌해 제외했으며 정책 기준 Constraint는 양쪽 1.000이다.

따라서 Round 3도 Multi-Agent의 Single-Agent+RAG 대비 우월성을 지지하지 않는다. 현 증거에서는
Single-Agent+RAG가 비용·지연·직접 계획 안정성에서 우세하고, Multi-Agent는 안전 또는 전달률의 추가
이점을 보이지 않았다. 현 구조 승격은 보류하고 ADR-0025의 후보 생성·교차 검토·제한 조정 실험으로
별도 재평가한다.
