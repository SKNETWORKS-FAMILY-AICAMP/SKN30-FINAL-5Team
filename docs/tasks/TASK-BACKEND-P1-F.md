# TASK-BACKEND-P1-F: 안전 규칙 캘리브레이션 리포트

> 상태: IMPLEMENTED
> 기준: 2026-09-03 헬끼 코어 루프 로드맵 P1-F, `SERVICE_POLICY_SAFETY_AND_ADAPTATION_V1.md`, `DOMAIN_RULES.md`

- Primary owner: 백엔드
- Reviewers: 개발 리드, PM, 필요 시 도메인 검수자
- 목표 브랜치: `feat/p1-f-safety-calibration`

## 목표

검수된 운동 카탈로그와 안전 규칙에 대표 사용자 상황을 반복 적용해, 규칙이 과도하거나 느슨한지를
코드 예외가 아니라 수치 변화로 검토할 수 있게 한다.

## 포함 범위

- 고정된 합성 사용자 상황과 NRS 1–3, 4–6, 7–10 경계
- Red Flag, 복수 통증, 수면·피로, 13일/14일 복귀 모드 상황
- 상황별 전체 후보 수, 승인 Pool 크기, 제외 운동 수, 계획 생성 실패 여부, 적용 상한
- 전체 상황의 계획 생성 실패율
- 입력 bundle의 manifest/hash/record count 검증
- Markdown 및 JSON 리포트 출력

## 제외 범위

- 안전 규칙 데이터의 심각도 범위 변경
- P1-B의 Daily Check-in API/DB 및 NRS 런타임 배선
- 미승인 복귀 모드 부하·볼륨 상한의 임의 결정
- 공개 API 또는 데이터베이스 스키마 변경

## 인수 조건

1. 동일 bundle과 동일 시나리오는 정렬 순서와 관계없이 동일한 리포트를 만든다.
2. NRS 1–3은 해당 부위 제외만, NRS 4–6은 제외와 `LIGHT`, NRS 7–10은 계획 중단으로 집계한다.
3. Red Flag는 승인 Pool을 만들지 않고 `STOP_AND_SEEK_HELP`로 집계한다.
4. 복수 통증은 부위별 제외 운동의 합집합을 사용한다.
5. 14일 복귀 모드는 검수된 상한이 없으면 `APPROVED_CAPS_REQUIRED`로 실패 안전 처리하며 숫자를 만들지 않는다.
6. v2.0.5 고정 bundle의 단일·복수 부위 기준값은 골든 테스트로 고정한다.
7. 리포트에는 사용자 식별자, 자유서술 건강정보, 원시 wearable 데이터가 포함되지 않는다.

## 예상 변경 파일

- `backend/scripts/safety_calibration_report.py`
- `backend/tests/unit/test_safety_calibration_report.py`
- `backend/tests/scenarios/test_safety_calibration_golden.py`
- `docs/tasks/TASK-BACKEND-P1-F.md`

## API·DB·보안 영향

- API 변경 없음
- DB 및 migration 변경 없음
- 합성 입력과 공개된 검수 bundle만 읽으며 사용자 데이터는 읽거나 저장하지 않음

## 수동 확인

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.safety_calibration_report
.\.venv\Scripts\python.exe -m backend.scripts.safety_calibration_report --format json
```
