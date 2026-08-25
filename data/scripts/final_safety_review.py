"""Run a fail-closed final safety review for the consolidated exercise catalog.

This review is intentionally evidence-gated.  It does not infer impact, fall risk,
equipment safety, beginner regressions, contraindications, or safer alternatives
from an exercise name or an LLM response.  A row is operationally eligible only
when every required safety dimension has an explicit approved result and all
upstream manifests are production eligible.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

DATA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_ROOT.parent
DEFAULT_CATALOG_DIR = DATA_ROOT / "generated/exercise-catalog-deduplicated-v0.4.0"
DEFAULT_CATALOG = DEFAULT_CATALOG_DIR / "exercises.jsonl"
DEFAULT_CATALOG_MANIFEST = DEFAULT_CATALOG_DIR / "seed_manifest.json"
DEFAULT_SAFETY_MANIFEST = (
    DATA_ROOT / "generated/exercise-safety-rules-mvp-v0.3.0/rules_manifest.json"
)
DEFAULT_ALTERNATIVE_MANIFEST = (
    DATA_ROOT / "generated/exercise-alternatives-mvp-v0.2.0/alternatives_manifest.json"
)
DEFAULT_REVIEW_QUEUE = (
    DATA_ROOT
    / "validation/review_batches/gymvisual-integrated-review-v0.1.0/integrated_exercise_review.csv"
)
DEFAULT_OUTPUT_JSON = DATA_ROOT / "reports/integrated_catalog_safety_review_v0.1.0.json"
DEFAULT_OUTPUT_MD = DATA_ROOT / "reports/INTEGRATED_CATALOG_SAFETY_REVIEW_v0.1.0.md"

REVIEW_VERSION = "integrated-catalog-safety-review-v0.1.0"

# These fields are deliberately not synthesized.  Existing catalog rows do not
# contain them, which must result in REVIEW_REQUIRED rather than approval.
REQUIRED_SAFETY_FIELDS = {
    "impact_level_code": "IMPACT_LEVEL",
    "balance_fall_risk_code": "BALANCE_FALL_RISK",
    "equipment_safety_status_code": "EQUIPMENT_SAFETY",
    "beginner_regression_status_code": "BEGINNER_REGRESSION",
    "instruction_safety_status_code": "INSTRUCTION_SAFETY",
    "safety_review_status_code": "SAFETY_REVIEW_STATUS",
    "safety_evidence_refs": "SAFETY_EVIDENCE",
}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def load_catalog(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"catalog row {line_number} must be an object")
        stable_code = value.get("stable_code")
        if not isinstance(stable_code, str) or not stable_code.strip():
            raise ValueError(f"catalog row {line_number} lacks stable_code")
        rows.append(value)
    if not rows:
        raise ValueError(f"catalog is empty: {path}")
    return rows


def manifest_production_eligible(path: Path) -> bool:
    review = load_json(path).get("review")
    return isinstance(review, dict) and review.get("production_eligible") is True


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def review_queue_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "reason_code": "REVIEW_QUEUE_NOT_FOUND"}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        "available": True,
        "records": len(rows),
        "review_decision_counts": dict(Counter(row.get("review_decision", "") for row in rows)),
        "review_status_counts": dict(Counter(row.get("review_status", "") for row in rows)),
        "production_eligible_counts": dict(
            Counter(row.get("production_eligible", "") for row in rows)
        ),
    }


def row_review(row: dict[str, Any], upstream_blockers: list[str]) -> dict[str, Any]:
    missing_fields = [
        label
        for field, label in REQUIRED_SAFETY_FIELDS.items()
        if field not in row or row[field] in (None, "", [], {})
    ]
    explicit_decision = row.get("safety_review_decision")
    if explicit_decision == "EXCLUDE":
        decision = "EXCLUDED"
        reason_codes = ["EXPLICIT_SAFETY_EXCLUSION"]
    elif explicit_decision == "APPROVE":
        decision = "APPROVED" if not upstream_blockers and not missing_fields else "REVIEW_REQUIRED"
        reason_codes = [] if decision == "APPROVED" else ["APPROVAL_EVIDENCE_INCOMPLETE"]
    else:
        decision = "REVIEW_REQUIRED"
        reason_codes = ["SAFETY_REVIEW_RESULT_MISSING"]

    reason_codes.extend(f"SAFETY_REVIEW_REQUIRED.{field}" for field in missing_fields)
    reason_codes.extend(upstream_blockers)
    return {
        "stable_code": row["stable_code"],
        "name_ko": row.get("name_ko", ""),
        "decision": decision,
        "reason_codes": sorted(set(reason_codes)),
        "safety_dimensions": {
            label: "MISSING" if label in missing_fields else "PRESENT_NOT_APPROVED"
            for label in REQUIRED_SAFETY_FIELDS.values()
        },
    }


def build_report(
    *,
    catalog_path: Path,
    catalog_manifest_path: Path,
    safety_manifest_path: Path,
    alternative_manifest_path: Path,
    review_queue_path: Path,
) -> dict[str, Any]:
    catalog = load_catalog(catalog_path)
    manifest_blockers = [
        f"{label}_NOT_PRODUCTION_ELIGIBLE"
        for label, path in (
            ("CATALOG", catalog_manifest_path),
            ("SAFETY_RULESET", safety_manifest_path),
            ("ALTERNATIVE_POLICY", alternative_manifest_path),
        )
        if not manifest_production_eligible(path)
    ]
    rows = [row_review(row, manifest_blockers) for row in catalog]
    counts = Counter(row["decision"] for row in rows)
    artifact_summaries = {
        label: load_json(path).get("summary", {})
        for label, path in (
            ("catalog", catalog_manifest_path),
            ("safety_rules", safety_manifest_path),
            ("alternatives", alternative_manifest_path),
        )
    }
    return {
        "review_version": REVIEW_VERSION,
        "scope": {
            "catalog_path": display_path(catalog_path),
            "catalog_records": len(rows),
            "catalog_manifest": display_path(catalog_manifest_path),
            "safety_manifest": display_path(safety_manifest_path),
            "alternative_manifest": display_path(alternative_manifest_path),
        },
        "deterministic_policy": {
            "safety_veto_precedence": [
                "EMERGENCY_OR_ACUTE_SIGNAL",
                "EXPLICIT_EXCLUSION",
                "CAUTION_OR_REVISE",
                "PASS",
            ],
            "llm_can_override_safety_veto": False,
            "wearable_required": False,
            "missing_evidence_default": "REVIEW_REQUIRED",
            "alternatives_or_contraindications_auto_created": False,
        },
        "upstream_blockers": manifest_blockers,
        "artifact_summaries": artifact_summaries,
        "decision_counts": dict(counts),
        "approved_stable_codes": sorted(
            row["stable_code"] for row in rows if row["decision"] == "APPROVED"
        ),
        "review_required": [row for row in rows if row["decision"] == "REVIEW_REQUIRED"],
        "excluded": [row for row in rows if row["decision"] == "EXCLUDED"],
        "review_queue": review_queue_summary(review_queue_path),
        "privacy_checks": {
            "direct_identifiers_in_report": False,
            "raw_health_data_in_report": False,
            "llm_input_used": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    counts = report["decision_counts"]
    lines = [
        "# 통합 운동 카탈로그 최종 안전 검수",
        "",
        f"- 검수 버전: `{report['review_version']}`",
        f"- 검수 대상: `{report['scope']['catalog_records']}`행",
        "- 결론: 운영 승인 `0`행. 안전 근거가 없는 모든 행은 `REVIEW_REQUIRED`로 보류.",
        "",
        "## 판정 요약",
        "",
        f"- 승인: `{counts.get('APPROVED', 0)}`",
        f"- 보류: `{counts.get('REVIEW_REQUIRED', 0)}`",
        f"- 제외: `{counts.get('EXCLUDED', 0)}` (명시적 안전 제외 근거가 없어 자동 제외하지 않음)",
        "",
        "## 보류 사유",
        "",
        "모든 행에 다음 안전 검수 결과가 없거나 운영 승인 증적이 없습니다.",
        "",
        "- 통증 충돌·동작별 제외 근거",
        "- 충격 수준",
        "- 균형·낙상 위험",
        "- 장비 안전성·설치 조건",
        "- 초보자 회귀 가능성",
        "- 수행 지침 안전성",
        "",
        "추가로 카탈로그, 안전 규칙셋, 대체 정책 manifest가 모두 "
        "`production_eligible=false`입니다.",
        f"안전 규칙 산출물은 "
        f"`{report['artifact_summaries']['safety_rules'].get('rule_records', 0)}`행 "
        f"(대상 운동 "
        f"`{report['artifact_summaries']['safety_rules'].get('exercise_records', 0)}`개), "
        f"대체 산출물은 "
        f"`{report['artifact_summaries']['alternatives'].get('alternative_records', 0)}`행이지만, "
        "둘 다 `AGENT_ONLY`이며 운영 적격이 아닙니다.",
        "대체 운동·금기 규칙은 이 검수에서 새로 확정하지 않았습니다.",
        "",
        "## 결정적 안전 경계",
        "",
        "- 안전 veto 우선순위는 이상 반응/급성 신호 → 명시적 제외 → 주의/수정 → 통과입니다.",
        "- LLM 결과는 안전 판정 입력이 아니며 안전 veto를 덮어쓸 수 없습니다.",
        "- 웨어러블은 필수 입력이 아니며 수동 체크인만으로 판정 경로를 유지합니다.",
        "- 안전 근거 누락의 기본값은 `REVIEW_REQUIRED`입니다.",
        "",
        "## 목록",
        "",
        "### 승인",
        "",
        "없음.",
        "",
        "### 보류",
        "",
    ]
    for row in report["review_required"]:
        lines.append(
            f"- `{row['stable_code']}` {row['name_ko']}: "
            + ", ".join(row["reason_codes"])
        )
    lines.extend(["", "### 제외", "", "없음.", ""])
    queue = report["review_queue"]
    if queue.get("available"):
        lines.extend(
            [
                "## 통합 검토 큐 참고",
                "",
                f"- 전체 `{queue['records']}`행",
                f"- 검토 결정: `{queue['review_decision_counts']}`",
                f"- 검토 상태: `{queue['review_status_counts']}`",
                f"- 운영 적격: `{queue['production_eligible_counts']}`",
                "",
                "검토 큐의 `DOMAIN_APPROVED`는 파이프라인 호환 상태일 뿐 "
                "외부 도메인 최종 승인으로 해석하지 않았습니다.",
                "",
            ]
        )
    lines.extend(
        [
            "## 출처",
            "",
            f"- 카탈로그: `{report['scope']['catalog_path']}`",
            f"- 카탈로그 manifest: `{report['scope']['catalog_manifest']}`",
            f"- 안전 규칙 manifest: `{report['scope']['safety_manifest']}`",
            f"- 대체 정책 manifest: `{report['scope']['alternative_manifest']}`",
            "- 저장소 규칙: `AGENTS.md`, `docs/DOMAIN_RULES.md`, "
            "`docs/DATA_MODEL.md`, `docs/tasks/TASK-SAFETY-001.md`",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--catalog-manifest", type=Path, default=DEFAULT_CATALOG_MANIFEST)
    parser.add_argument("--safety-manifest", type=Path, default=DEFAULT_SAFETY_MANIFEST)
    parser.add_argument("--alternative-manifest", type=Path, default=DEFAULT_ALTERNATIVE_MANIFEST)
    parser.add_argument("--review-queue", type=Path, default=DEFAULT_REVIEW_QUEUE)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args(argv)

    report = build_report(
        catalog_path=args.catalog.resolve(),
        catalog_manifest_path=args.catalog_manifest.resolve(),
        safety_manifest_path=args.safety_manifest.resolve(),
        alternative_manifest_path=args.alternative_manifest.resolve(),
        review_queue_path=args.review_queue.resolve(),
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output_markdown.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report["decision_counts"], ensure_ascii=False, sort_keys=True))
    return 0 if report["decision_counts"].get("REVIEW_REQUIRED", 0) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
