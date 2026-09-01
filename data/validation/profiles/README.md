# Source profiles

`profile_kspo_fitness100.py`가 생성한 snapshot별 필드 profile과 검토 인벤토리를 둔다.

- `profile.json`: 결측·고유값·분포·중복 구조
- `candidate_inventory.jsonl`: 원천 메타데이터를 보존한 검토 후보
- `candidate_review.csv`: 사람 검토용 평면 목록
- `profile_manifest.json`: 원천 snapshot 연결과 산출물 SHA-256

모든 profile은 `DRAFT`이며 프로덕션 seed가 아니다. 생성된 파일을 직접 수정하지
않고, mapping 또는 screening 규칙이 바뀌면 profiler version을 올려 다시 생성한다.

Gym Visual 스트레칭·가동성 profile은 `gymvisual_mobility_profile.json`이다. 원천 후보
35건의 신체 부위·목표·family/variant 후보·장비·난이도 커버리지를 기록하지만, 안전
승인이나 대체 관계를 의미하지 않는다. profile에는 기존 카탈로그 56건, 안전 규칙
354건, 대체 관계 238건의 읽기 전용 기준 해시와 건수를 함께 기록한다.
