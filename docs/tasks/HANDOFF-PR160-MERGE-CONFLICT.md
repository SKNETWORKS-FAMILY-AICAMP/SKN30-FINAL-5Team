# 인계: PR #160과 develop(#158)의 카탈로그 파이프라인 충돌 해소

새 세션에서 이 문서를 읽고 그대로 진행하면 된다. 브랜치는 깨끗한 상태로 두었다.

## 상황

- 작업 브랜치: `feat/staging-catalog-release-import` (PR #160, base `develop`)
- `develop`에 #158 `feat: db 적재 준비`가 병합되면서 충돌 발생
- 두 PR이 **같은 번들을 각자 재생성**했다. 텍스트 병합으로는 풀 수 없다

### 충돌 파일 5개

```
backend/app/modules/catalog/approvals.py
backend/scripts/catalog_promote_v2.py
backend/tests/unit/test_catalog_approvals.py
backend/tests/unit/test_catalog_data_bundle_importer.py
data/scripts/build_v2_prescriptions.py
```

자동 병합된 파일(내용 검토 필요): `build_final_exercise_catalog_v2.py`(#158이 +227줄),
`build_v2_backend_bundle.py`, `.gitignore`

### 핵심 대립

| | PR #160 (이 브랜치) | develop (#158) |
|---|---|---|
| 처방 세트 | `prescription-set-v2.0.1` | `prescription-set-v2.0.0` |
| 처방 매니페스트 해시 | `9d5a8fc0…` | `6c1ccbae…` |

#158은 gymvisual 미디어 동기화(`sync_gymvisual_media.py` +631줄, 검수 CSV +88줄)를
추가하면서 카탈로그를 재생성했다.

## 확정된 방침

**2026-08-27 프로젝트 오너 결정: v2.0.1을 기준으로 삼고 #158을 그 위에 얹는다.**

근거: v2.0.1이 이미 Aurora에 `ACTIVE`로 적재돼 있어 되돌리는 비용이 더 크다.
처방 세트도 v2.0.1로 통일한다.

## 해소 절차

### 1. 스크립트 변경 병합

```bash
git checkout feat/staging-catalog-release-import
git merge origin/develop
```

충돌 해결 원칙:

- **버전 코드**는 전부 `v2.0.1` 쪽(HEAD)을 채택
- **해시 값**은 어느 쪽도 채택하지 않는다. 2단계 재빌드 결과로 덮어쓴다
- `build_final_exercise_catalog_v2.py`의 #158 추가분(+227줄, 미디어 관련)은 **유지**한다.
  이 브랜치가 같은 파일에 넣은 재현성 수정(`_write_text_lf`, `lineterminator="\n"`,
  `.as_posix()` 3곳)도 **함께 유지**해야 한다. 둘은 서로 다른 부분이라 양립한다
- `build_v2_prescriptions.py`는 `CATALOG_VERSION`과 출력 디렉터리를 v2.0.1로

### 2. 전체 재생성

순서를 지켜야 한다. 앞 단계 산출물을 뒤 단계가 읽는다.

```bash
./.venv/Scripts/python.exe -m data.scripts.build_final_exercise_catalog_v2
./.venv/Scripts/python.exe -m data.scripts.build_v2_runtime_artifacts
PYTHONPATH="data/scripts" ./.venv/Scripts/python.exe data/scripts/build_v2_prescriptions.py --force
rm -rf data/generated/exercise-catalog-v2.0.1-final/backend_bundle
PYTHONPATH="data/scripts" ./.venv/Scripts/python.exe data/scripts/build_v2_backend_bundle.py
```

`build_v2_backend_bundle.py`와 `build_v2_prescriptions.py`는 형제 모듈을 import하므로
`-m`이 아니라 `PYTHONPATH="data/scripts"`로 직접 실행해야 한다.

### 3. 새 해시 수집과 반영

```python
import json, hashlib
from pathlib import Path
root = Path('data/generated/exercise-catalog-v2.0.1-final/backend_bundle')
bm = json.loads((root/'bundle_manifest.json').read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
print('BUNDLE', sha(root/'bundle_manifest.json'))
for k, rel in bm['importer_paths'].items():
    print(k, sha(root/rel))
```

반영할 곳:

- `backend/app/modules/catalog/approvals.py` — CATALOG / SAFETY_RULES / ALTERNATIVES /
  PRESCRIPTIONS 4개 항목의 `manifest_sha256`
- `backend/scripts/catalog_promote_v2.py` — `APPROVED_BUNDLE_MANIFEST_SHA256`
- `backend/tests/unit/test_catalog_approvals.py` — 동일 해시 4개
- `backend/tests/unit/test_catalog_data_bundle_importer.py` — `V2_BUNDLE_HASH`

`approvals.py`의 `approval_metadata.beginner_suitability_review` 블록은 **지우지 말 것.**
25건 분류의 출처 기록이다.

### 4. 검증

```bash
uv run --no-sync pytest backend/tests/unit backend/tests/scenarios -q   # 1112 passed 기준
uv run --no-sync ruff check backend data/scripts
uv run --no-sync mypy
```

재현성 확인(중요): 입력 변경 없이 한 번 더 재빌드해 산출물 SHA256이 동일한지 본다.
다르면 #158이 추가한 코드에 플랫폼 의존 출력이 있다는 뜻이므로 그것부터 고친다.

### 5. RDS 재적재

현재 Aurora 상태: `exercise-catalog-v2.0.1-final`이 ACTIVE. 해시가 바뀌므로 다시 넣어야 한다.

```bash
env -u APP_ENV -u DATABASE_URL ./.venv/Scripts/python.exe -m backend.scripts.catalog_promote_v2
env -u APP_ENV -u DATABASE_URL ./.venv/Scripts/python.exe -m backend.scripts.catalog_activate activate exercise-catalog-v2.0.1-final
```

`DERIVED_SET_CONFLICT`가 나면 파생 세트 버전이 기존 적재분과 같은데 해시만 달라진 경우다.
그때는 파생 세트 버전을 v2.0.2로 함께 올려야 한다. 버전 코드는
`data/normalized/v2_representative_decisions.json`의 `alternative_set_version_code`,
`rule_set_version_code`에 있다(스크립트가 아니다 — 처음에 이걸 못 찾아 헤맸다).

`--demo-unreviewed`는 쓰지 않는다. 승인 레지스트리가 `DOMAIN_REVIEWER`를 이미 담고 있어
정식 경로로 통과한다.

### 6. 루틴 생성 재확인

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.app.core.config import get_settings
from backend.app.db.repositories.routine import RoutineRepository
from backend.app.modules.routines import service as svc
e = create_engine(get_settings().database_url.get_secret_value())
with Session(e) as s:
    ctx = RoutineRepository().get_creation_context(s, '<user_id>', "GENERAL_FITNESS")
    setup, items, req = svc._select_exact_plan(ctx)
```

기준값: 후보 56개(워밍업 17·본운동 22·쿨다운 17), 10분 요청 → 600초, 오차 0초.

## 주의

- `backend/.env`는 gitignore 대상이고 현재 `APP_ENV=local` + Aurora URL로 맞춰져 있다.
  `demo-local.ps1`은 셸 환경변수로 이걸 덮어쓰므로 RDS 작업에는 쓰지 말 것
- `uv run`은 실행 중인 uvicorn과 `Scripts/*.exe` 잠금 충돌을 일으킨다. `--no-sync`를 붙이거나
  `./.venv/Scripts/python.exe`를 직접 쓴다
- `ml/models/MODEL_CARD.md`는 ML 담당자의 미커밋 변경이다. 건드리지 않는다

## 배경 문서

- `docs/tasks/TASK-ROUTINE-EQUIPMENT-AND-DURATION.md` — 결정사항·승인·데이터 현황·후속 단계
- PR #160 본문 — 변경 요약과 위험 요소
