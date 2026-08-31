# S3 운동 모션 URL 백엔드 연결

## 결정

- 기존 `exercise_media_assets.s3_key`는 canonical `catalog-media/...` key 의미를 유지한다.
- 실제 `videos/` source key는 schema migration 없이 승인 media 행의 versioned provenance 영역인
  `source_metadata.source_object_key`에 보존한다. 이 값은 조회 필터가 아니라 상세 응답을 만들기
  위한 검증 증적이며, object content type과 검증 시각을 함께 기록한다.
- `media_url`은 상세 조회 application service가 승인 registry exact-match를 재검증하고 S3 adapter가
  HEAD와 presign에 성공한 경우에만 생성한다. route는 S3 SDK를 호출하지 않는다.

## 운영 검증

필수 설정:

```text
EXERCISE_MEDIA_S3_BUCKET=exercise-app-media-343953861875-ap-northeast-2-an
EXERCISE_MEDIA_S3_REGION=ap-northeast-2
EXERCISE_MEDIA_S3_PREFIX=videos/
EXERCISE_MEDIA_URL_EXPIRY_SECONDS=300
```

DB 접근과 S3 `ListBucket`, `HeadObject`, `GetObject` 권한이 있는 배포 환경에서 먼저 dry-run하고,
중복 수가 0임을 확인한 뒤 적용한다.

```powershell
uv run python -m backend.scripts.sync_exercise_media_sources
uv run python -m backend.scripts.sync_exercise_media_sources --apply
```

두 명령은 `target_object_count`, `mapped_count`, `unmatched_count`, `duplicate_count`,
`invalid_filename_count`, GIF 검증 수와 저장 수를 JSON 한 줄로 출력한다. 한 prefix에 여러 객체가
있거나 여러 승인 운동이 같은 `source_identity`를 가지면 전체 저장을 중단하고 exit code 2를
반환한다. 이 job은 S3 upload, copy, delete를 수행하지 않는다.

2026-08-31 실제 `videos/` 검증 결과:

- raw prefix 항목 107개: prefix marker `videos/` 1개 + mapping 대상 GIF 106개
- filename parser 통과 106개, 4자리 prefix 중복 0개
- 106개 HEAD 모두 `ContentType=image/gif`
- 최신 develop의 승인 v2.0.2 catalog artifact 155개와 source_identity 대조: 성공 72개,
  미매칭 34개, 중복 0개
- 승인 registry media 68개는 실제 source GIF와 68개 전부 exact match, 미존재 0개

현재 로컬 PostgreSQL이 실행 중이지 않아 실제 운영 DB UUID를 사용하는 dry-run과 `--apply`는
실행하지 않았다. 배포 DB에서 위 명령을 다시 실행한 결과가 최종 운영 증적이다.

## Rollback

API 설정을 해제하면 즉시 `media_url=null`로 fail closed한다. 저장 metadata를 제거할 필요는 없지만,
후속 forward-fix가 필요하면 `source_object_*` 세 key만 승인 media 행에서 제거한다. canonical key와
rights/approval 증적은 건드리지 않는다.
