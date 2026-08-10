# TASK-DATA-001: 국민체력100 원문 수집 파이프라인 bootstrap

- Primary owner: 개발 리드·백엔드/데이터
- Reviewers: 백엔드, PM(라이선스), 외부 운동·보건 전문가(후속 정규화 데이터)
- 관련 요구사항: MVP_SCOPE 5.3, DATA_MODEL 15, AGENTS 6·8
- 관련 ADR: 없음
- 목표 브랜치: `feat/data-001-pipeline-bootstrap`

## 배경과 사용자 가치

검수 가능한 운동 카탈로그를 만들기 위해 출처와 라이선스가 보존되고 재현 가능한
첫 외부 데이터 수집 경로가 필요하다.

## 포함 범위

- 국민체력100 OpenAPI JSON 페이지 수집
- API 성공·페이지·레코드 수 검증
- 원문 바이트, SHA-256, 출처, 라이선스, 수집 시각, pipeline version manifest
- 별도 재검증 명령
- 인증키 비노출과 로컬 snapshot Git 제외
- 표준 라이브러리 기반 단위 테스트
- 검증된 snapshot의 필드·결측·고유값·중복 profiling
- `(원천 영상 파일명, 운동명)` 단위의 DRAFT 검토 인벤토리
- profile과 후보 CSV/JSONL의 SHA-256 재검증

## 제외 범위

- 공통 exercise schema로의 필드 정규화와 최종 30~50개 선정
- 대체 운동, 통증 충돌, FITT, 시간값 추론
- 미디어 파일 다운로드
- `TECH_REVIEWED`/`DOMAIN_APPROVED` 승격
- DB schema, migration, seed import

## 인수 조건

1. 환경변수의 서비스키로 allowlist endpoint를 페이지네이션 수집한다.
2. 원문 JSON을 수정하지 않고 페이지별 파일로 보존한다.
3. manifest에 출처·라이선스·수집시각·버전·해시·레코드 수·`DRAFT` 상태가 있다.
4. 실패 응답, 잘못된 JSON, 전체 개수 불일치에는 snapshot을 완성하지 않는다.
5. 파일 변조 후 재검증은 실패한다.
6. 키는 manifest, 파일명, 콘솔 출력에 포함되지 않는다.
7. 실제 외부 호출 없이 단위 테스트할 수 있다.
8. frame 행과 고유 영상·운동 후보 수를 분리해 보고한다.
9. 모든 검토 후보는 `DRAFT/production_eligible=false`이며 필수 리뷰 코드를 가진다.
10. profile 산출물 변조 후 재검증은 실패한다.

## 변경 예상 파일

- `data/scripts/kspo_fitness100_pipeline.py`
- `data/scripts/tests/test_kspo_fitness100_pipeline.py`
- `data/scripts/profile_kspo_fitness100.py`
- `data/scripts/tests/test_profile_kspo_fitness100.py`
- `data/raw/kspo_fitness100_video/**`
- `data/validation/profiles/**`
- `data/PIPELINE.md`와 관련 README
- `.gitignore`

## API 영향

애플리케이션 공개 API 영향 없음.

## DB·마이그레이션 영향

없음.

## 안전·개인정보·보안 영향

사용자 데이터와 개인 체력측정 결과를 수집하지 않는다. 서비스키는 환경변수로만
읽는다. 외부 원천을 안전 규칙으로 자동 변환하지 않으며 모든 결과는 `DRAFT`다.

## 선행 관계와 차단 요소

- 실제 수집 실행에는 공공데이터포털 데이터셋 `15108846` 개발계정 활용신청과
  Decoding 일반 인증키가 필요하다.
- 정규화 전 실제 응답 필드 profiling이 필요하다.

## 테스트 계획

- 2페이지 정상 응답 수집과 manifest 검증
- API 실패 코드와 레코드 수 불일치 실패
- 원문 파일 변조 감지
- manifest에 인증키가 없는지 확인
- frame 중복, 빈 운동명, 유아·수영장 전용 범위 표시
- profile 산출물 해시 변조 감지

## 수동 확인

실제 키로 `training-video`를 1회 수집하고 `validate`를 실행한 뒤 레코드 수와
manifest를 확인한다.

## 알려진 제한과 후속 작업

원천의 `vdo_len`은 영상 길이로 취급하며 운동 수행시간으로 매핑하지 않는다.
영상·이미지의 제3자 권리와 자세 문구 재사용 범위는 PM 검토가 필요하다. profile의
검토 인벤토리는 최종 30~50개 선정이나 normalized seed가 아니다.
