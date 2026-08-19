# 국민체력100 source-to-normalized mapping proposal

- 상태: `DRAFT`
- 프로덕션 사용 가능: 아니요
- 근거 snapshot: `20260810T053458Z-training-video`
- profiler: `0.2.0`

## 1. 원천 grain

원천 1행은 운동 1개가 아니라 영상의 이미지 frame 메타데이터일 수 있다.

- raw frame 행: 1,668
- 고유 영상 파일: 243
- 운동명이 있는 `(file_nm, trng_nm)` 검토 후보: 391
- MVP 범위 검토 후보: 231
- MVP 범위 후보의 고유 운동명: 227

`(file_nm, trng_nm)`은 검토 후보 키일 뿐 애플리케이션 exercise ID가 아니다.
동일 운동명이 다른 영상에 있거나, 하나의 영상이 여러 준비·본동작을 포함할 수 있다.

## 2. 매핑 분류

| 원천 필드 | 제안 대상 | 처리 | 상태·주의 |
|---|---|---|---|
| `trng_nm` | `display_name_ko` 후보 | Unicode NFC·앞뒤 공백 정리 | 직접 확정 금지; 동일명·준비자세 분리 검토 |
| `file_nm` | source content reference | 원문 값 보존 | exercise code로 사용 금지 |
| `vdo_ttl_nm` | source content title | 원문 값 보존 | 운동명과 다를 수 있음 |
| `vdo_desc` | source description reference | 원문 값 보존 | 앱 자세 설명으로 자동 승격 금지 |
| `aggrp_nm` | source age group | 원문 값 보존 후 enum mapping | `공통`은 초보자 적합을 의미하지 않음 |
| `trng_plc_nm` | place 후보 | 승인된 machine code로 mapping | `실내`를 자동으로 `HOME`으로 해석하지 않음 |
| `tool_nm` | equipment 후보 | 승인된 machine code로 mapping | 빈 값은 맨몸이 아니라 미지정 |
| `trng_mscl_*` | anatomy reference | 용어집 mapping 후 저장 | 주동근·보조근 자동 구분 금지 |
| `set_cnt_nm` | source dosage | 원문 값 보존 | 83.9% 행 결측; 처방값 자동 채움 금지 |
| `rptt_tcnt_nm` | source dosage | 원문 값 보존 | 84.7% 행 결측 |
| `trng_hr_nm` | source dosage | 원문 값 보존 | 85.4% 행 결측 |
| `ecrg_cycl_nm` | source dosage | 원문 값 보존 | 86.4% 행 결측 |
| `vdo_len` | media duration | media metadata로만 보존 | 운동 예상·권장 시간으로 사용 금지 |
| `img_file_*`, `file_url` | media reference | 권리 검토용 참조 | 다운로드·재배포 자동화 금지 |
| `row_num` | source row metadata | raw에만 보존 | exercise ID로 사용 금지 |
| 해상도·FPS·frame 수·파일 크기 | media technical metadata | 필요 시 source metadata | 운동 결정 입력에서 제외 |

## 3. 원천만으로 채울 수 없는 필수 필드

다음 필드는 별도 작성과 승인이 필요하다.

- stable internal exercise code
- 운동 유형과 화면 focus
- movement pattern
- 난이도와 초보자 적합 여부
- 장비·장소 machine code
- 반복형·시간형 execution mode
- 세트, 반복, 동작시간, 휴식, 전환시간
- 목표 tag
- 대체 운동 관계
- 불편 부위 충돌과 안전 규칙
- recovery 사용 가능 여부
- 자세 설명, 핵심 cue, 콘텐츠 version
- media 사용 권리와 attribution 표현

빈 값을 일반적인 운동 지식이나 LLM으로 보충하지 않는다. 수치와 안전 관계는
검토 증적과 version을 가진 별도 데이터로 작성한다.

## 4. 초기 30~50개 shortlist 게이트

1. `MVP_SCOPE_REVIEW` 231개에서 시작한다.
2. 동일 운동명·준비자세·루틴 영상의 경계를 사람이 검토한다.
3. 승인된 exercise type, focus, pattern, place, equipment enum을 매핑한다.
4. 홈·헬스장·걷기/가벼운 러닝·스트레칭/코어 MVP 범위 커버리지를 확인한다.
5. 초보자 적합성, 실행 dosage, 자세 문구를 검토한다.
6. 대체 관계와 불편 부위 충돌을 별도 안전 review에서 승인한다.
7. 출처·라이선스·media 권리를 PM이 확인한다.
8. 위 항목을 모두 충족한 후보 중 30~50개를 `TECH_REVIEWED`로 올린다.
9. 외부 운동·보건 전문가 승인 후에만 `DOMAIN_APPROVED`로 승격한다.

초기 수량을 채우기 위해 미검수 후보를 포함하지 않는다. 범위 커버리지가 부족하면
다른 공식 원천을 추가하거나 수량을 줄여 승인된 최소 seed로 시작한다.

## 5. 정규화 산출물 분리안

```text
data/normalized/<catalog-version>/
  exercises.jsonl          # 운동 identity와 표시·실행 metadata
  source_references.jsonl  # 원천 행·영상·license 추적
  alternatives.jsonl       # 별도 검수된 대체 관계
  safety_rules.jsonl       # 별도 검수된 불편 부위 충돌
  review_evidence.jsonl    # reviewer, status, reviewed_at, evidence reference
```

운동 본문, 대체 관계, 안전 규칙을 한 JSON 문서에 섞지 않는다. `DOMAIN_APPROVED`가
아닌 관계나 규칙은 generated seed에 포함하지 않는다.
