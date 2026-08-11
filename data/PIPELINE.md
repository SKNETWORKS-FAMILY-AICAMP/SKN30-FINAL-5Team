# External exercise data pipeline

## 1차 수동 검토 배치

profile의 `MVP_SCOPE_REVIEW` 후보는 곧바로 정규화하거나 승인하지 않습니다. 먼저
`build_kspo_fitness100_review_batch.py`로 재현 가능한 50개 검토 순서를 만들고 다음 항목을
담당자별로 채웁니다.

- 데이터/기술: 중복 경계, 원천 근거, 정규화 ID 후보
- PM/권리: 콘텐츠 및 미디어 이용 범위
- 도메인 검토자: taxonomy, 초보자 적합성, 실행 dosage, 자세 문구, 안전, 대체 관계
- 개발 리드: 리뷰 증적과 프로덕션 승격 게이트

검토 순서는 원천 장소·도구 조합의 다양성을 위한 운영 큐일 뿐입니다. 배치 포함 여부를
운동의 안전성, 품질 또는 최종 카탈로그 포함 결정으로 해석하지 않습니다.

KSPO 홈·맨몸 트랙과 wger 헬스장 트랙은 모두 review batch v0.2.0에서 검토 결과 입력 열과
역할별 증적 템플릿을 함께 제공하며, 같은 결과 게이트 규칙을 사용한다.
[validation/REVIEW_RESULTS_GATE.md](validation/REVIEW_RESULTS_GATE.md)를 따른다.

## 1. 목표

외부 운동 데이터를 출처와 라이선스가 추적 가능한 원문으로 수집하고, 기술 검증과
도메인 승인을 분리해 프로덕션 카탈로그로 승격한다. 외부 데이터는 운동 추천이나
안전 판단에 바로 사용하지 않는다.

## 2. 초기 범위

기본 원천은 공공데이터포털 데이터셋 `15108846`,
`서울올림픽기념국민체육진흥공단_국민체력100 동영상 정보`다. 헬스장 기구·프리웨이트
종목의 명칭과 장비 커버리지를 보강하기 위해 wger exercise catalog를 별도 원천으로
수집한다.

- 장점: 성인, 체력요인, 운동부위, 운동도구 등 MVP 카탈로그 후보를 찾는 데 필요한
  메타데이터를 제공한다.
- 이용 조건: 공공누리 제1유형(출처표시), 제3자 권리 포함.
- 제한: 영상과 썸네일 파일은 내려받지 않는다. API JSON 메타데이터만 수집한다.
- 상태: 수집 결과는 항상 `DRAFT`이며 자동으로 승인 데이터가 되지 않는다.

wger 보강 원천은 공개 API JSON만 수집한다. 운동·번역·미디어 항목의 개별 라이선스와
저작자 표시를 보존하고 이미지·동영상 바이너리는 수집하지 않는다. wger의 이름·장비·근육
필드는 KSPO 필드로 합쳐 표시하지 않으며 source-specific provenance를 유지한다.

체력측정 개인 결과 API, 사용자 데이터, 웨어러블 원시 데이터는 이 파이프라인의
수집 대상이 아니다.

## 3. 단계와 산출물

```text
official API
  -> immutable raw JSON pages + SHA-256 manifest (DRAFT)
  -> source field profiling and mapping proposal
  -> normalized catalog candidate (DRAFT)
  -> schema, duplicate, reference and duration validation
  -> TECH_REVIEWED
  -> PM license/content review
  -> external exercise/health professional review
  -> DOMAIN_APPROVED
  -> generated seed + DB import
```

승격 조건은 다음과 같다.

| 단계 | 자동화 가능 | 승인 책임 |
|---|---|---|
| 원문 수집·해시·페이지 수 검증 | 예 | 데이터 담당 |
| 필드 정규화·중복 후보 생성 | 예 | 백엔드/데이터 기술 검토 |
| 대체 운동 후보·통증 충돌 초안 | 후보 생성만 가능 | PM + 외부 전문가 |
| FITT/시간 메타데이터 | 범위·형식 검증만 가능 | 외부 전문가 |
| 프로덕션 seed 승격 | 승인 증적 검사만 가능 | 개발 리드 최종 게이트 |

## 4. 실패 폐쇄 원칙

- API 성공 코드, 페이지 수, 전체 레코드 수가 일치하지 않으면 snapshot을 만들지 않는다.
- 원문 파일 해시가 달라지거나 manifest가 누락되면 검증에 실패한다.
- 출처, 라이선스, 수집 시각, pipeline version, review status가 없으면 실패한다.
- `DOMAIN_APPROVED` 증적이 없는 데이터는 generated seed로 승격하지 않는다.
- 원천의 질환명이나 운동 분류를 제품의 통증 제외 규칙으로 자동 변환하지 않는다.
- MET, RPE, 반복수, 휴식시간, 금기사항을 임의로 채우지 않는다.

## 5. 다음 구현 순서

1. KSPO와 wger snapshot 및 profile의 무결성을 재검증한다.
2. 헬스장 핵심 운동군별 source-to-normalized mapping 후보를 사람이 검토한다.
3. 한국어 표시명, 장비 taxonomy, 중복·변형 경계를 별도 필드로 확정한다.
4. MVP 30~50개 후보 선정 기준과 홈·헬스장 커버리지 목표를 문서화한다.
5. 공통 exercise schema와 source별 provenance 구조를 리뷰한다.
6. 실행 안내, FITT, 안전·대체 관계를 별도 검수 데이터로 작성한다.
7. 승인 증적을 요구하는 seed generator를 구현한다.

초기 후보는 성인 대상, 초보자 설명이 있는 운동, 홈·헬스장·걷기/가벼운 러닝·
스트레칭/코어 범위를 우선한다. 후보 선정은 다양성과 MVP 커버리지를 위한 것이며
안전 승인을 대신하지 않는다.

### 현재 상태

1번은 완료했다. KSPO·wger snapshot과 profile, 두 트랙의 v0.2.0 배치가 모두 해시
검증을 통과한다.

2번부터는 사람의 검토 입력이 필요하다. 두 트랙 모두 검토 결과 입력 열, 역할별 증적
템플릿, 실패 폐쇄 결과 validator가 준비되어 있으므로 홈 트랙과 헬스장 트랙 검토를
동시에 진행할 수 있다.

3번과 5번의 taxonomy 코드는 `docs/API_CONTRACT.md`의 미확정 계약이므로 파이프라인이 임의로
정하지 않는다. 원천 어휘 실측과 승인된 문서 문장에서 도출한 제안을
[normalized/EXERCISE_TAXONOMY_CODE_PROPOSAL.md](normalized/EXERCISE_TAXONOMY_CODE_PROPOSAL.md)와
`normalized/exercise_taxonomy_codes.json`에 두었다. 개발 리드가 2026-08-11에
승인했으므로 결과 validator가 `review_taxonomy_code`의 목록 소속을 검사한다. `body_area_code`는 `docs/DOMAIN_RULES.md`에서 이미
확정되어 있다.

FITT·MET 참고 원천은 [FITT_REFERENCE_ASSESSMENT.md](FITT_REFERENCE_ASSESSMENT.md)에서
평가했다. 결론은 snapshot 수집 대상이 아니라는 것이다. MVP 스키마에 MET 컬럼이 없고,
세션 시간 구조는 이미 `docs/DOMAIN_RULES.md`에 확정되어 있으며, 해당 문서들은 공개
API가 아니라 라이선스 제한이 있는 저작물이다.

7번 seed generator는 `scripts/build_exercise_catalog_seed.py`로 구현했다. 승인 증적이
없으면 아무것도 생성하지 않는다. 현재는 taxonomy registry가 `DRAFT`이고 검토 완료 행이
0건이므로 `build`가 항상 실패하며 이는 의도된 동작이다.

`readiness` 명령이 무엇이 비어 있는지 기계적으로 보고하므로, 남은 작업을 추정하지 않고
확인할 수 있다. 검토 배치에 없는 DATA_MODEL 필드는 `template` 명령이 만드는 catalog
attribute 시트에 도메인 검토자가 작성한다.

### 원천 단위 주의

`training-video` endpoint의 한 행은 운동 하나가 아니라 영상에서 추출한 이미지
프레임일 수 있다. `row_num`이나 `img_file_nm` 개수를 운동 개수로 사용하지 않는다.
현재 profiling 단계의 검토 후보 키는 `(file_nm, trng_nm)`이며, 서로 다른 영상의
동일 운동명이 같은 운동인지 여부는 정규화 리뷰에서 결정한다. `vdo_len`은 영상
길이이므로 운동 수행시간으로 사용하지 않는다.
