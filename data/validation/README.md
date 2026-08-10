# Data validation

## Review batches

`review_batches/`에는 검증된 profile에서 재현 가능하게 생성한 1차 수동 검토 순서를 둡니다.
현재 방법은 MVP 범위 후보만 사용하고, 동일 원천 운동명별 대표 후보를 고른 뒤 원천의
장소·도구 조합을 순회합니다. 이 방법은 안전성, 초보자 적합성, 운동 품질 점수가 아니며
최종 30~50개 카탈로그 선정도 아닙니다.

각 배치는 원본 profile manifest SHA-256, 선택 방법 코드, 해석 금지 규칙, JSONL/CSV
파일 해시를 보존합니다. 모든 행은 명시적 리뷰 전까지 `DRAFT`이고 프로덕션에서 사용할 수
없습니다.

Schema 검사, 중복·누락·시간 계산 검증, 출처·라이선스 확인, TECH_REVIEWED/DOMAIN_APPROVED 증적을 둡니다.

현재 자동 검증 범위는 raw snapshot의 manifest 필수 필드, API 응답 성공 코드,
페이지·레코드 수, 파일 크기와 SHA-256 무결성이다. 정규화 schema와
TECH_REVIEWED/DOMAIN_APPROVED 승인 증적 형식은 실제 원천 profiling 후 별도 작업에서
추가한다.

`profiles/`에는 검증된 raw snapshot에서 생성한 필드 profile과 검토용 후보
인벤토리를 둔다. 산출물은 profiler가 생성하며 직접 수정하지 않는다. profile의
MVP 범위 표시는 제품 범위 필터일 뿐 안전 승인이나 추천 적합성을 의미하지 않는다.

wger profile은 전체 운동 수, 언어·장비·분류·항목별 라이선스 분포와 함께
`gym_candidate_inventory.jsonl`, `gym_candidate_review.csv`,
`target_movement_coverage.json`을 생성한다. 장비 및 영문 이름·별칭은 후보 검색 근거일
뿐 정규화 매핑이 아니다. 한국어 번역이 없는 행도 누락 상태를 보존하며 사람이 검토하기
전에는 임의 번역으로 채우지 않는다.

wger gym-core review batch는 60개 검토 행을 목표 운동군 할당량으로 먼저 채우고 남은
행을 원천 분류·장비 조합으로 보강한다. 동일 영문 원천명은 source metadata가 더 완전한
대표 1건만 사용한다. 요청된 랫풀다운·덤벨로우·시티드 케이블로우 이름은 존재할 때 먼저
배치하지만 이는 안전성 또는 포함 승인이 아니다. 모든 검토 입력 필드는 생성 시
`PENDING`이며, JSONL/CSV 해시와 행 identity가 다르면 검증에 실패한다.

v0.2 배치는 `catalog_review_records_template.jsonl/.csv`에 운동별 네 reviewer role의
증적 행을 생성한다. 이 구조는 `docs/DATA_MODEL.md`의 `catalog_review_records` 계약을
따른다. 운영상의 검수자 자격·계약 방식은 여기서 확정하지 않으며, reviewer reference에는
이메일이나 실명이 아닌 내부 비식별 코드를 사용한다. 상세 게이트는
`REVIEW_RESULTS_GATE.md`를 따른다.
