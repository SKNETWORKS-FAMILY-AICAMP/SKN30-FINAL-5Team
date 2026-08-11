# Physical activity guideline raw references

일반 성인의 신체활동 권고와 강도 분류에 필요한 공식 근거의 최소 원천 레이어다.
원문 HTML·PDF를 저장소에 재배포하지 않고, 공식 응답의 해시와 조회 메타데이터만
`snapshot_manifest.json`에 보존한다. 구조화한 사실은 원문의 위치를 함께 기록한다.
CDC 페이지처럼 일반 HTTP 클라이언트가 접근을 거부하는 경우에는 브라우저로 공식 페이지를
확인하고, 해당 출처에서 추출한 구조화 사실의 해시임을 명시한다. 이 값은 HTTP 응답 해시로
표현하지 않는다.

- `source_registry.json`: 공식 엔드포인트, 라이선스·사용 제한, 수집 가드
- `general_guideline_facts.json`: 일반 성인 FITT·강도 원천 사실
- `adult_compendium_mvp_reference_subset.jsonl`: 2024 Adult Compendium의 MVP 관련 참조 부분집합
- `snapshot_manifest.json`: 조회 시점의 HTTP 응답 해시와 로컬 파일 해시

Compendium 행은 공식 MET 값을 변경하지 않는다. 이 부분집합은 운동 카탈로그와 매핑한
결과가 아니며, 이름 유사성만으로 개별 운동의 MET를 결정하는 데 사용할 수 없다.
모든 파일은 DRAFT이고 운영 적재 대상이 아니다.
