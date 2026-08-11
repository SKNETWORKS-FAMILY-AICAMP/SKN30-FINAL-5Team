"""Build DOMAIN_APPROVED exercise safety rules from approved catalog seeds.

`docs/DATA_MODEL.md` 5.9절의 `exercise_safety_rules` 행을 만든다. 규칙은 추측하지 않고
두 입력에서만 도출한다.

1. 승인된 카탈로그 seed의 부하 부위(`primary_body_area_codes`, `secondary_body_area_codes`)
2. `normalized/exercise_safety_rule_policy.json`의 심각도-효과 매핑과 패턴 공통 부하

`docs/DOMAIN_RULES.md` 4.2에 따라 SEVERE는 세션 단위 REST이므로 개별 운동 선택이
일어나지 않는다. 이 규칙표는 MILD와 MODERATE 판단에 사용한다.

패턴 규칙은 해당 패턴의 **모든** 운동에서 성립해야 한다. 하나라도 어긋나면 빌드가
실패한다. 패턴 규칙이 과일반화되면 부하가 없는 운동까지 제외되기 때문이다.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from kspo_fitness100_pipeline import PipelineError, sha256_bytes

RULES_GENERATOR_VERSION = "0.1.0"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "generated"
DEFAULT_POLICY = (
    Path(__file__).resolve().parents[1] / "normalized" / "exercise_safety_rule_policy.json"
)

# docs/DOMAIN_RULES.md 3.2절.
BODY_AREA_CODES = (
    "NECK",
    "SHOULDER",
    "ELBOW",
    "WRIST_HAND",
    "UPPER_BACK",
    "LOWER_BACK",
    "HIP",
    "KNEE",
    "ANKLE_FOOT",
    "CHEST",
    "ABDOMEN",
    "GENERALIZED",
    "OTHER",
)

# docs/DOMAIN_RULES.md 3.3절.
SEVERITY_ORDER = ("NONE", "MILD", "MODERATE", "SEVERE")

# docs/DATA_MODEL.md 5.9절.
EFFECT_CODES = ("EXCLUDE", "CAUTION")
BODY_PART_ROLES = ("PRIMARY", "SECONDARY")

# 개별 운동 선택이 일어나는 심각도. SEVERE는 세션 단위 REST다.
SELECTION_SEVERITIES = ("MILD", "MODERATE")


def severity_rank(code: str) -> int:
    try:
        return SEVERITY_ORDER.index(code)
    except ValueError as exc:
        raise PipelineError(f"unknown severity code: {code}") from exc


def load_json(path: Path, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"{label} is missing: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise PipelineError(f"{label} must be a JSON object")
    return payload


def load_policy(path: Path) -> dict[str, object]:
    policy = load_json(path, "safety rule policy")
    if policy.get("status") != "APPROVED":
        raise PipelineError("safety rule policy is not APPROVED")
    for key in ("severity_effects", "pattern_rules", "policy_version"):
        if key not in policy:
            raise PipelineError(f"safety rule policy is missing {key}")

    effects = policy["severity_effects"]
    if not isinstance(effects, dict):
        raise PipelineError("severity_effects must be an object")
    for role in BODY_PART_ROLES:
        entries = effects.get(role)
        if not isinstance(entries, list) or not entries:
            raise PipelineError(f"severity_effects is missing rules for {role}")
        for entry in entries:
            if not isinstance(entry, dict):
                raise PipelineError(f"severity_effects {role} entry must be an object")
            low = severity_rank(str(entry.get("minimum_severity_code", "")))
            high = severity_rank(str(entry.get("maximum_severity_code", "")))
            if low > high:
                raise PipelineError(f"severity_effects {role} range is inverted")
            if low == 0:
                raise PipelineError("severity_effects must not apply to NONE")
            if str(entry.get("effect_code", "")) not in EFFECT_CODES:
                raise PipelineError(f"severity_effects {role} effect_code is invalid")
            if not str(entry.get("reason_code", "")).strip():
                raise PipelineError(f"severity_effects {role} reason_code is missing")
    return policy


def load_seed_exercises(seed_dirs: list[Path]) -> list[dict[str, object]]:
    """승인된 seed에서 운동을 읽는다. DOMAIN_APPROVED가 아니면 실패한다."""

    exercises: list[dict[str, object]] = []
    seen: set[str] = set()
    for seed_dir in seed_dirs:
        manifest = load_json(seed_dir / "seed_manifest.json", "seed manifest")
        catalog = manifest.get("catalog_version")
        if not isinstance(catalog, dict):
            raise PipelineError(f"seed manifest has no catalog_version: {seed_dir.name}")
        version_code = str(catalog.get("version_code", ""))
        if not version_code:
            raise PipelineError(f"seed manifest has no version_code: {seed_dir.name}")

        raw = (seed_dir / "exercises.jsonl").read_bytes()
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise PipelineError(f"seed manifest lists no files: {seed_dir.name}")
        entry = files[0]
        if not isinstance(entry, dict) or sha256_bytes(raw) != entry.get("sha256"):
            raise PipelineError(f"seed hash mismatch: {seed_dir.name}")

        for line in raw.decode("utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("review_status_code") != "DOMAIN_APPROVED":
                raise PipelineError("seed contains an exercise without domain approval")
            stable_code = str(record.get("stable_code", ""))
            if stable_code in seen:
                raise PipelineError(f"stable_code appears in more than one seed: {stable_code}")
            seen.add(stable_code)
            record["catalog_version_code"] = version_code
            exercises.append(record)
    if not exercises:
        raise PipelineError("no approved exercises were found in the given seeds")
    return exercises


def body_areas(record: dict[str, object], field: str) -> list[str]:
    value = record.get(field, [])
    if not isinstance(value, list):
        raise PipelineError(f"{field} must be a list")
    codes = [str(code) for code in value]
    for code in codes:
        if code not in BODY_AREA_CODES:
            raise PipelineError(f"body area code is not in DOMAIN_RULES: {code}")
    return codes


def check_pattern_rules_hold(policy: dict[str, object], exercises: list[dict[str, object]]) -> None:
    """패턴 규칙이 그 패턴의 모든 운동에서 성립하는지 확인한다.

    패턴이 PRIMARY라고 선언한 부위는 모든 운동에서 PRIMARY여야 한다. SECONDARY라고
    선언한 부위는 PRIMARY 또는 SECONDARY여야 한다. 과일반화된 패턴 규칙은 부하가 없는
    운동까지 제외하므로 실패로 처리한다.
    """

    pattern_rules = policy["pattern_rules"]
    if not isinstance(pattern_rules, dict):
        raise PipelineError("pattern_rules must be an object")

    by_pattern: dict[str, list[dict[str, object]]] = {}
    for record in exercises:
        pattern = str(record.get("primary_movement_pattern_code", ""))
        by_pattern.setdefault(pattern, []).append(record)

    for pattern, spec in pattern_rules.items():
        if pattern.startswith("_") or not isinstance(spec, dict):
            continue
        members = by_pattern.get(pattern, [])
        for area in spec.get("primary", []) or []:
            for record in members:
                if str(area) not in body_areas(record, "primary_body_area_codes"):
                    raise PipelineError(
                        f"pattern rule {pattern}/{area} claims PRIMARY but "
                        f"{record.get('stable_code')} does not load it that way"
                    )
        for area in spec.get("secondary", []) or []:
            for record in members:
                loaded = body_areas(record, "primary_body_area_codes") + body_areas(
                    record, "secondary_body_area_codes"
                )
                if str(area) not in loaded:
                    raise PipelineError(
                        f"pattern rule {pattern}/{area} claims SECONDARY but "
                        f"{record.get('stable_code')} does not load it"
                    )


def pattern_coverage(policy: dict[str, object], pattern: str) -> dict[str, str]:
    """패턴 규칙이 이미 덮는 (부위 -> 역할) 목록."""

    pattern_rules = policy["pattern_rules"]
    assert isinstance(pattern_rules, dict)
    spec = pattern_rules.get(pattern)
    if not isinstance(spec, dict):
        return {}
    covered: dict[str, str] = {}
    for area in spec.get("secondary", []) or []:
        covered[str(area)] = "SECONDARY"
    for area in spec.get("primary", []) or []:
        covered[str(area)] = "PRIMARY"
    return covered


def effect_rows(policy: dict[str, object], role: str) -> list[dict[str, object]]:
    effects = policy["severity_effects"]
    assert isinstance(effects, dict)
    entries = effects[role]
    assert isinstance(entries, list)
    return [entry for entry in entries if isinstance(entry, dict)]


def build_rule_records(
    policy: dict[str, object], exercises: list[dict[str, object]]
) -> list[dict[str, object]]:
    check_pattern_rules_hold(policy, exercises)
    rule_version = str(policy["policy_version"])
    catalog_versions = sorted({str(record["catalog_version_code"]) for record in exercises})
    pattern_rules = policy["pattern_rules"]
    assert isinstance(pattern_rules, dict)

    rules: list[dict[str, object]] = []

    # 1. 패턴 단위 규칙. 카탈로그 버전마다 한 행씩 낸다.
    used_patterns = {str(record.get("primary_movement_pattern_code", "")) for record in exercises}
    for pattern in sorted(used_patterns):
        spec = pattern_rules.get(pattern)
        if not isinstance(spec, dict):
            raise PipelineError(f"pattern_rules has no entry for {pattern}")
        for role in BODY_PART_ROLES:
            for area in sorted(spec.get(role.lower(), []) or []):
                for entry in effect_rows(policy, role):
                    for catalog_version_code in catalog_versions:
                        rules.append(
                            {
                                "rule_scope": "MOVEMENT_PATTERN",
                                "catalog_version_code": catalog_version_code,
                                "movement_pattern_code": pattern,
                                "exercise_stable_code": None,
                                "body_area_code": str(area),
                                "body_part_role_code": role,
                                "minimum_severity_code": entry["minimum_severity_code"],
                                "maximum_severity_code": entry["maximum_severity_code"],
                                "effect_code": entry["effect_code"],
                                "reason_code": entry["reason_code"],
                                "review_status_code": "DOMAIN_APPROVED",
                                "rule_version": rule_version,
                            }
                        )

    # 2. 운동 단위 규칙. 패턴 규칙이 덮지 못하는 부하만 추가한다.
    for record in exercises:
        pattern = str(record.get("primary_movement_pattern_code", ""))
        covered = pattern_coverage(policy, pattern)
        for role, field in (
            ("PRIMARY", "primary_body_area_codes"),
            ("SECONDARY", "secondary_body_area_codes"),
        ):
            for area in body_areas(record, field):
                # 패턴이 같은 역할 이상으로 이미 덮으면 중복 행을 만들지 않는다.
                if covered.get(area) == role or (
                    role == "SECONDARY" and covered.get(area) == "PRIMARY"
                ):
                    continue
                for entry in effect_rows(policy, role):
                    rules.append(
                        {
                            "rule_scope": "EXERCISE",
                            "catalog_version_code": record["catalog_version_code"],
                            "movement_pattern_code": None,
                            "exercise_stable_code": record["stable_code"],
                            "body_area_code": area,
                            "body_part_role_code": role,
                            "minimum_severity_code": entry["minimum_severity_code"],
                            "maximum_severity_code": entry["maximum_severity_code"],
                            "effect_code": entry["effect_code"],
                            "reason_code": entry["reason_code"],
                            "review_status_code": "DOMAIN_APPROVED",
                            "rule_version": rule_version,
                        }
                    )
    return rules


def rule_problems(rule: dict[str, object]) -> list[str]:
    problems: list[str] = []
    scope = rule.get("rule_scope")
    has_exercise = bool(rule.get("exercise_stable_code"))
    has_pattern = bool(rule.get("movement_pattern_code"))
    # docs/DATA_MODEL.md 5.9: 정확히 하나만 지정해야 한다.
    if has_exercise == has_pattern:
        problems.append("exactly one of exercise or movement pattern must be set")
    if scope == "EXERCISE" and not has_exercise:
        problems.append("EXERCISE scope needs an exercise")
    if scope == "MOVEMENT_PATTERN" and not has_pattern:
        problems.append("MOVEMENT_PATTERN scope needs a movement pattern")
    if rule.get("body_area_code") not in BODY_AREA_CODES:
        problems.append("body area code is not in DOMAIN_RULES")
    if rule.get("effect_code") not in EFFECT_CODES:
        problems.append("effect_code must be EXCLUDE or CAUTION")
    if rule.get("review_status_code") != "DOMAIN_APPROVED":
        problems.append("rule is not domain approved")
    low = severity_rank(str(rule.get("minimum_severity_code", "")))
    high = severity_rank(str(rule.get("maximum_severity_code", "")))
    if low > high:
        problems.append("severity range is inverted")
    if low == 0:
        problems.append("severity range must not include NONE")
    if not str(rule.get("catalog_version_code", "")).strip():
        problems.append("catalog_version_code is missing")
    return problems


def applies(rule: dict[str, object], severity: str) -> bool:
    rank = severity_rank(severity)
    low = severity_rank(str(rule["minimum_severity_code"]))
    high = severity_rank(str(rule["maximum_severity_code"]))
    return low <= rank <= high


def resolve_effects(
    rules: list[dict[str, object]],
    exercises: list[dict[str, object]],
    body_area_code: str,
    severity: str,
) -> dict[str, str]:
    """운동별 최종 효과. EXCLUDE가 CAUTION을 이긴다."""

    by_pattern: dict[str, list[dict[str, object]]] = {}
    by_exercise: dict[str, list[dict[str, object]]] = {}
    for rule in rules:
        if rule["body_area_code"] != body_area_code or not applies(rule, severity):
            continue
        if rule["rule_scope"] == "MOVEMENT_PATTERN":
            by_pattern.setdefault(str(rule["movement_pattern_code"]), []).append(rule)
        else:
            by_exercise.setdefault(str(rule["exercise_stable_code"]), []).append(rule)

    resolved: dict[str, str] = {}
    for record in exercises:
        stable_code = str(record["stable_code"])
        matched = by_pattern.get(
            str(record.get("primary_movement_pattern_code", "")), []
        ) + by_exercise.get(stable_code, [])
        if not matched:
            continue
        resolved[stable_code] = (
            "EXCLUDE" if any(r["effect_code"] == "EXCLUDE" for r in matched) else "CAUTION"
        )
    return resolved


def build_coverage_report(
    rules: list[dict[str, object]], exercises: list[dict[str, object]]
) -> dict[str, object]:
    """부위·심각도별로 선택 가능한 운동이 남는지 보고한다.

    docs/DOMAIN_RULES.md 4.3은 목표를 보존하는 대체 계획을 요구한다. 어떤 부위에서
    남는 운동이 없으면 대체가 불가능하므로 미리 드러내야 한다.
    """

    total = len(exercises)
    report: dict[str, object] = {}
    for area in BODY_AREA_CODES:
        per_area: dict[str, object] = {}
        for severity in SELECTION_SEVERITIES:
            resolved = resolve_effects(rules, exercises, area, severity)
            excluded = sorted(code for code, effect in resolved.items() if effect == "EXCLUDE")
            caution = sorted(code for code, effect in resolved.items() if effect == "CAUTION")
            remaining = sorted(
                str(record["stable_code"])
                for record in exercises
                if resolved.get(str(record["stable_code"])) != "EXCLUDE"
            )
            per_area[severity] = {
                "excluded": len(excluded),
                "caution": len(caution),
                "selectable": len(remaining),
                "excluded_codes": excluded,
            }
        report[area] = per_area
    report["_total_exercises"] = total
    return report


def build_rules(
    seed_dirs: list[Path], policy_path: Path, output_root: Path, version_code: str
) -> Path:
    policy = load_policy(policy_path)
    exercises = load_seed_exercises([d.resolve() for d in seed_dirs])
    rules = build_rule_records(policy, exercises)

    for rule in rules:
        problems = rule_problems(rule)
        if problems:
            raise PipelineError(f"safety rule is not valid: {problems[0]}")

    natural_keys = {
        (
            rule["rule_scope"],
            rule["catalog_version_code"],
            rule["movement_pattern_code"],
            rule["exercise_stable_code"],
            rule["body_area_code"],
            rule["minimum_severity_code"],
            rule["effect_code"],
        )
        for rule in rules
    }
    if len(natural_keys) != len(rules):
        raise PipelineError("duplicate safety rule rows were produced")

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    directory_name = f"exercise-safety-rules-{version_code}"
    final_dir = output_root / directory_name
    partial_dir = output_root / f".{directory_name}.partial"
    if final_dir.exists():
        raise PipelineError(f"safety rule set already exists: {directory_name}")
    if partial_dir.exists():
        raise PipelineError(f"partial safety rule set already exists: {partial_dir.name}")

    partial_dir.mkdir()
    try:
        rules_path = partial_dir / "safety_rules.jsonl"
        with rules_path.open("w", encoding="utf-8", newline="\n") as handle:
            for rule in rules:
                handle.write(json.dumps(rule, ensure_ascii=False, sort_keys=True) + "\n")
        raw = rules_path.read_bytes()

        coverage = build_coverage_report(rules, exercises)
        coverage_path = partial_dir / "coverage_report.json"
        coverage_path.write_text(
            json.dumps(coverage, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        coverage_raw = coverage_path.read_bytes()

        manifest = {
            "schema_version": "1.0",
            "generator_version": RULES_GENERATOR_VERSION,
            "rule_set_version": {"version_code": version_code, "status_code": "DRAFT"},
            "source": {
                "catalog_seeds": [d.resolve().name for d in seed_dirs],
                "policy_sha256": sha256_bytes(policy_path.read_bytes()),
                "policy_version": str(policy["policy_version"]),
            },
            "review": {"status": "DOMAIN_APPROVED", "production_eligible": False},
            "summary": {
                "rule_records": len(rules),
                "exercise_records": len(exercises),
                "pattern_scope_rules": sum(
                    1 for r in rules if r["rule_scope"] == "MOVEMENT_PATTERN"
                ),
                "exercise_scope_rules": sum(1 for r in rules if r["rule_scope"] == "EXERCISE"),
            },
            "files": [
                {
                    "path": "safety_rules.jsonl",
                    "sha256": sha256_bytes(raw),
                    "bytes": len(raw),
                    "records": len(rules),
                },
                {
                    "path": "coverage_report.json",
                    "sha256": sha256_bytes(coverage_raw),
                    "bytes": len(coverage_raw),
                    "records": 1,
                },
            ],
        }
        (partial_dir / "rules_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        verify_rules(partial_dir)
        partial_dir.replace(final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise


def verify_rules(rules_dir: Path) -> dict[str, object]:
    rules_dir = rules_dir.resolve()
    manifest = load_json(rules_dir / "rules_manifest.json", "rules_manifest.json")
    if manifest.get("schema_version") != "1.0":
        raise PipelineError("unsupported rules manifest schema")
    review = manifest.get("review")
    if not isinstance(review, dict) or review.get("production_eligible") is not False:
        raise PipelineError("safety rule set must stay production-ineligible until promoted")

    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 2:
        raise PipelineError("rules manifest must list the rules and coverage files")
    for entry in files:
        if not isinstance(entry, dict):
            raise PipelineError("rules manifest file entry must be an object")
        path = rules_dir / str(entry.get("path", ""))
        try:
            raw = path.read_bytes()
        except FileNotFoundError as exc:
            raise PipelineError(f"safety rule file is missing: {entry.get('path')}") from exc
        if sha256_bytes(raw) != entry.get("sha256") or len(raw) != int(entry.get("bytes", -1)):
            raise PipelineError("safety rule hash or size mismatch")

    raw = (rules_dir / "safety_rules.jsonl").read_bytes()
    rules = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    for rule in rules:
        problems = rule_problems(rule)
        if problems:
            raise PipelineError(f"safety rule is not valid: {problems[0]}")
    return {
        "rule_set": rules_dir.name,
        "rules": len(rules),
        "status": "valid",
        "production_eligible": False,
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="build safety rules from approved catalog seeds")
    build.add_argument("seeds", type=Path, nargs="+")
    build.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    build.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    build.add_argument("--version-code", required=True)

    verify = subparsers.add_parser("verify", help="verify a generated safety rule set")
    verify.add_argument("rules", type=Path)

    coverage = subparsers.add_parser(
        "coverage", help="report selectable exercises per body area and severity"
    )
    coverage.add_argument("rules", type=Path)
    coverage.add_argument("seeds", type=Path, nargs="+")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "build":
            rules_dir = build_rules(args.seeds, args.policy, args.output_root, args.version_code)
            result: dict[str, object] = {"status": "built", "rules": str(rules_dir)}
        elif args.command == "coverage":
            raw = (args.rules.resolve() / "safety_rules.jsonl").read_bytes()
            rules = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
            exercises = load_seed_exercises([d.resolve() for d in args.seeds])
            result = build_coverage_report(rules, exercises)
        else:
            result = verify_rules(args.rules)
    except (PipelineError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
