# Gym Visual exercise raw data

Gym Visual 운동 데이터셋의 원천 JSON 스냅샷이다. 운동명·신체 부위·장비·주요 근육,
다국어 실행 설명과 이미지·GIF 미디어 참조를 보존한다.

## 파일

- `exercises.json`: 운동 원천 레코드 1,324건
- `exercises.schema.json`: JSON Schema Draft 2020-12 기반 레코드 구조
- `source.json`: 수집 시각, 레코드 수, 파일별 SHA-256, 라이선스와 검토 상태

각 레코드는 영어·스페인어·이탈리아어·튀르키예어·러시아어·중국어·힌디어·폴란드어·
한국어·프랑스어 설명과 단계별 지침을 포함할 수 있다. `image`와 `gif_url`은 원천 미디어
참조 경로이며, 이 디렉터리에는 이미지·GIF 바이너리를 포함하지 않는다.

## 출처와 검토 상태

- 데이터셋 식별자: `exercises-dataset`
- 원천 스키마 참조: <https://github.com/hasaneyldrm/exercises-dataset>
- 수집 시각: `2026-08-20T00:00:00+09:00`
- 라이선스: `MIT`
- GIF 사용 허가: 프로젝트 기간 동안 제한된 학생 프로젝트에서 무료로 임시 사용 가능
- GIF 필수 저작자 표시: `© Aliaksandr Makatserchyk - Gym visual - https://gymvisual.com/`
- 미디어 라이선스 승인 플래그: `true` (출처 manifest 기록)
- 검토 상태: `DRAFT`

파일 무결성, 원천 메타데이터와 라이선스 정보는 `source.json`을 기준으로 확인한다.
위 GIF 허가는 제공받은 별도 사용 허가이며, 프로젝트 기간과 제한된 학생 프로젝트 범위를
벗어난 상업적 이용·재배포·운영 서비스 사용을 허가하는 의미로 해석하지 않는다.
이 데이터는 아직 도메인 검토와 운영 적합성 승인을 완료하지 않은 원천 레이어이므로,
안전 규칙·통증 대응·개인별 운동 처방의 근거로 직접 사용하거나 운영 데이터로 승격하지
않는다. 정규화와 안전 검토가 필요한 경우 `data/normalized/` 및 `data/validation/`의
승인된 산출물 경계를 따른다.
