# Catalog module

검수된 운동, FITT 속성, 대체 관계, 안전 규칙, 출처·라이선스를 조회하는 모듈 경계입니다.

현재 구현은 DRAFT catalog와 파생 안전 규칙·대체 관계 bundle importer를 포함합니다.

- local/test에서만 `seed_manifest.json`과 exercise JSONL을 검증·적재합니다.
- Pydantic `StrEnum`의 `mvp-v1` code set과 승인 taxonomy hash를 사용합니다.
- version/hash 멱등성, artifact 경계, hash/byte/record count와 transaction 원자성을
  fail-closed로 검증합니다.
- 원본 DRAFT 매니페스트의 `DOMAIN_APPROVED`는 파이프라인 호환 상태이며 그 자체로 production
  승격을 뜻하지 않습니다.
- `python -m backend.scripts.catalog_data_load load`는 네 카탈로그와 안전 규칙 354개,
  대체 관계 238개를 한 transaction으로 적재하며 재실행은 멱등합니다.
- Issue 53에서 별도 승인된 안전 규칙 `mvp-v0.3.0` 354건과 대체 관계 `mvp-v0.2.0`
  238건은 승인 registry의 version/hash/count가 모두 일치할 때 `production_eligible=true`로
  적재됩니다. 그 밖의 파생 데이터는 계속 false로 fail-closed 처리합니다.
- 현재 매니페스트에 없는 URL·license code는 추정하지 않습니다. source 매니페스트 전체를
  보존하므로 후속 schema가 해당 필드를 제공하면 손실 없이 저장할 수 있습니다.
