# Normalized data

출처별 표현을 공통 exercise/FITT/safety schema로 정규화한 중간 결과를 둡니다. 프로덕션 승인 상태와는 구분합니다.

국민체력100 원천의 초기 필드 매핑과 금지 규칙은
[KSPO_FITNESS100_MAPPING_PROPOSAL.md](KSPO_FITNESS100_MAPPING_PROPOSAL.md)를 따른다. 이 문서는 DRAFT
제안이며 공통 enum과 외부 도메인 검토 전 normalized seed를 만들지 않는다.

헬스장 운동 보강 범위와 wger 원천의 매핑 경계는
[GYM_EXERCISE_SOURCE_COVERAGE.md](GYM_EXERCISE_SOURCE_COVERAGE.md)를 따른다. 원천의 이름
일치는 정규화 운동의 동일성, 초보자 적합성 또는 안전 승인을 의미하지 않는다.

`physical_activity_reference_v0.1.0/`은 WHO·CDC·질병관리청의 일반 성인 주간 권고,
CDC 강도 경계, 2024 Adult Compendium의 MVP 관련 부분집합을 분리해 보존한 DRAFT다.
애플리케이션 스키마와 개별 운동 MET 매핑은 미확정이며 운영 적재 대상이 아니다.
