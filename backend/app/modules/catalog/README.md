# Catalog module

검수된 운동, FITT 속성, 대체 관계, 안전 규칙, 출처·라이선스를 조회하는 모듈 경계입니다.

현재 구현된 첫 수직 슬라이스는 DRAFT exercise catalog importer뿐입니다.

- local/test에서만 `seed_manifest.json`과 exercise JSONL을 검증·적재합니다.
- Pydantic `StrEnum`의 `mvp-v1` code set과 승인 taxonomy hash를 사용합니다.
- version/hash 멱등성, artifact 경계, hash/byte/record count와 transaction 원자성을
  fail-closed로 검증합니다.
- `DOMAIN_APPROVED`는 파이프라인 호환 상태일 뿐 production 승격을 뜻하지 않습니다.
- 공개 exercise API, alternatives와 safety rule 적재는 아직 구현하지 않습니다.
