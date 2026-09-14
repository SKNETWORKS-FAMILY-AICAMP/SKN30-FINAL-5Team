# MET v2.0.7 Backend handoff

Status: verified DRAFT; not promoted.

- Source: `data/normalized/v2_0_6_exercise_catalog.csv`
- Source SHA-256: `c9143eb25bf88ba60fc7440ef0b4a55c0fd6dddf62ee56925cd526785c5cca27`
- Bundle root: `data/generated/exercise-catalog-v2.0.7-draft/backend_bundle`
- Bundle root SHA-256 (bundle_manifest.json): `f842b6e274d917868ebad636e0110c0aac5cddde0c1253c7cb3f9fb784a00ef4`
- MET approval manifest SHA-256: `2568be6b2b8197abadcf511638f1ed42bdc5f36793313673ce2a1b3168310162`
- MET non-null / NULL: 237 / 0
- DOMAIN_APPROVED: 237

v2.0.6 대비 운동 데이터 변경은 MET 6개 projection뿐입니다. 버전 참조와 출처 해시는 새 bundle에 맞게 생성했으며 safety/처방/media/대체운동 의미는 동일합니다.
기존 규칙·처방·media set version은 의미가 같으므로 유지합니다.

승인: 2026-09-06 사용자 승인. Adult Compendium 2024의 기존 DIRECT / SIMILAR_ACTIVITY 값과 PDF/HOME 출처 코드를 그대로 유지했습니다.

| Artifact | Records | Bytes | SHA-256 |
|---|---:|---:|---|
| alternatives/alternatives.jsonl | 1 | 1036 | f5014f867a36f947602e0ac9765fc984fbbdcbeb531f275e306cb5bc8b1001b3 |
| alternatives/alternatives_manifest.json | — | 1183 | 6dbbefbf1ce68f59edc2f52747ee5272873a716564f845ad948c53f20794ebad |
| alternatives/input/alternative_projection_conflicts.json | — | 190 | bc80f6e5b5b41d1b13a7037b5980b2d23753ce77c543fbdf88777c42c559dc0c |
| audit/projection_audit.jsonl | 237 | 51695 | b36f0a6d6a1c518c75e06abe3a25758da04c60d2a34c2ca985731f5f097a7c56 |
| catalog/exercises.jsonl | 237 | 408080 | 8690b4586b5b86695c20873f9439cb000921e774abc0a8549670e48da8cb26c1 |
| catalog/input/met_review_approval_manifest.json | — | 1107 | 2568be6b2b8197abadcf511638f1ed42bdc5f36793313673ce2a1b3168310162 |
| catalog/input/representative_exercises.csv | — | 9785 | fd7099554043cfbfa9ea0e5658bc8078c620272c728aa9c1c8ac2bc6a2178627 |
| catalog/seed_manifest.json | — | 1539 | b4f4ea1f6f7462e5414ddd63cb628257ec66ac831c461a008fc1f73259fb6c37 |
| media/media_assets.jsonl | 237 | 170906 | f4bb0e7141e6ed38ae2cd05eda9e071f8ed76887dcf7e70503d3926e88b037e3 |
| media/media_manifest.json | — | 1231 | b94124693e8192c2556ecf5bfbbb45d1622b8b0cc072260541da030d62514c79 |
| prescriptions/goal_tag_links.jsonl | 711 | 155760 | 16edf7103184972edfd65d1d211e3e6e2cdd1602a34a813ce54652dbeb132990 |
| prescriptions/prescription_manifest.json | — | 1254 | 50cc64677fa2bdaa9e1d21ba6261c9f28bc7dd17b8b507c967be5c364d6dbcb7 |
| prescriptions/prescription_profiles.jsonl | 1449 | 617100 | d6725499038cf7b2900fb23066579cfe881d669dfed84f225794da14fca09086 |
| safety/rules_manifest.json | — | 1054 | 11ac8eaaafbb48f6b7ed6ff40aa8a99a1d2dac06233239f4335d4edd1c25b0dc |
| safety/safety_rules.jsonl | 2131 | 1831639 | 7d59b211e059602ebc9e2ce5827773fae412612526f8bb08054236c13ff0dcda |

## Backend 후속 작업

- [ ] exercises 테이블 MET 6개 nullable 컬럼 migration
- [ ] ExerciseRecord/importer의 6개 필드 검증·저장 지원
- [ ] 새 bundle hash approval/promotion 등록 및 최종 승인 후 별도 final 생성
- [ ] import·activate 및 237개 MET 저장 확인
- [ ] kcal 계산 연결

## 검증·재현

`python data/scripts/build_v2_0_7_backend_bundle.py` (출력 경로가 없어야 함)
`python -m pytest data/scripts/tests/test_build_v2_0_7_backend_bundle.py data/scripts/tests/test_build_v2_0_6_backend_bundle.py`

수동 검수: validation report의 root hash를 bundle_manifest.json의 SHA-256과 대조하고, child artifact의 hash/bytes/records를 확인합니다.

## 제한

met_reviewed_at/met_reviewer_code는 이번 bundle의 운동 레코드에 포함하지 않았습니다. 승인 manifest의 기존 감사 메타데이터는 증적으로 보존합니다.
backend kcal 계산/DB 적재, API·schema 변경은 수행하지 않았습니다. 현재 ExerciseRecord는 MET를 지원하지 않으므로 그대로 적재하면 안 됩니다.
개인정보·건강 기록을 추가하거나 외부로 전송하지 않았습니다.
