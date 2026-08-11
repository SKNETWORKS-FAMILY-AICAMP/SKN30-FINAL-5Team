"""Build a DB-loadable exercise catalog seed, refusing without approval evidence.

이 도구는 검토 결과만으로 seed를 만들지 않는다. `docs/DATA_MODEL.md` 5.2절의 exercises
행을 채우려면 검토 배치에 없는 값(운동 유형, 운동 패턴, 난이도, 수행 시간, 휴식, 실행
안내)이 추가로 필요하다. 그 값은 `template` 명령이 만드는 catalog attribute 시트에
도메인 검토자가 작성한다.

`build`는 다음이 모두 충족될 때만 산출물을 만든다. 하나라도 어긋나면 아무것도 만들지
않고 실패한다.

1. review batch manifest 해시 검증 통과
2. mapping·evidence 결과가 기존 결과 validator를 통과
3. taxonomy 코드 registry가 `APPROVED` 상태
4. 각 운동에 DOMAIN_REVIEWER의 `DOMAIN_APPROVED` 증적 존재
5. attribute 행의 모든 필수 필드가 채워지고 승인된 코드 목록에 속함

`readiness`는 실패시키지 않고 무엇이 비어 있는지만 보고한다.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from korean_display_name_rules import display_name_problems, duplicate_display_names
from kspo_fitness100_pipeline import PipelineError, sha256_bytes

SEED_GENERATOR_VERSION = "0.1.0"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "generated"

# docs/DOMAIN_RULES.md 3.2절에서 확정된 불편 부위 코드.
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

TIMING_MODE_CODES = ("REPS", "DURATION")
DIFFICULTY_CODES = ("BEGINNER", "INTERMEDIATE", "ADVANCED")
BODY_PART_ROLE_CODES = ("PRIMARY", "SECONDARY")

# docs/DATA_MODEL.md 13절의 값 범위.
TRANSITION_SECONDS_RANGE = (10, 20)

ATTRIBUTE_FIELDS = [
    "source_identity",
    "review_normalized_exercise_id",
    "review_display_name_ko",
    "training_type_code",
    "body_focus_code",
    "primary_movement_pattern_code",
    "difficulty_code",
    "timing_mode_code",
    "default_seconds_per_rep",
    "default_work_seconds",
    "default_rest_seconds",
    "default_transition_seconds",
    "recovery_eligible",
    "primary_body_area_codes",
    "secondary_body_area_codes",
    "equipment_codes",
    "location_codes",
    "instruction_summary_ko",
    "form_cues_ko",
    "instruction_content_version",
    "attribute_status",
]

PENDING_ATTRIBUTE_VALUES = {
    "training_type_code": "",
    "body_focus_code": "",
    "primary_movement_pattern_code": "",
    "difficulty_code": "",
    "timing_mode_code": "",
    "default_seconds_per_rep": "",
    "default_work_seconds": "",
    "default_rest_seconds": "",
    "default_transition_seconds": "",
    "recovery_eligible": "",
    "primary_body_area_codes": "",
    "secondary_body_area_codes": "",
    "equipment_codes": "",
    "location_codes": "",
    "instruction_summary_ko": "",
    "form_cues_ko": "",
    "instruction_content_version": "",
    "attribute_status": "PENDING",
}


@dataclass(frozen=True)
class TrackSpec:
    """검토 배치의 트랙별 열 이름 차이를 흡수한다."""

    name: str
    mapping_file: str
    identity_field: str
    source_name_field: str


TRACKS = {
    "wger": TrackSpec(
        name="wger",
        mapping_file="gym_core_review_batch.csv",
        identity_field="source_exercise_id",
        source_name_field="primary_source_name_en",
    ),
    "kspo": TrackSpec(
        name="kspo",
        mapping_file="review_batch.csv",
        identity_field="source_candidate_id",
        source_name_field="source_training_name",
    ),
}


def read_csv(path: Path, expected_fields: list[str] | None = None) -> list[dict[str, str]]:
    try:
        with path.resolve().open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if expected_fields is not None and reader.fieldnames != expected_fields:
                raise PipelineError(f"CSV columns do not match the template: {path.name}")
            return list(reader)
    except FileNotFoundError as exc:
        raise PipelineError(f"CSV is missing: {path}") from exc


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def validate_results(track: TrackSpec, batch_dir: Path, mapping: Path, evidence: Path) -> None:
    """기존 트랙별 결과 validator를 그대로 사용한다."""

    if track.name == "wger":
        from validate_wger_gym_review_results import validate_review_results
    else:
        from validate_kspo_fitness100_review_results import validate_review_results
    validate_review_results(batch_dir, mapping, evidence)


def approved_exercises(
    track: TrackSpec, mapping_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    return [row for row in mapping_rows if row["review_decision"].strip() in {"INCLUDE", "MERGE"}]


def build_attribute_template(
    track: TrackSpec, batch_dir: Path, mapping: Path, output_path: Path
) -> dict[str, object]:
    mapping_rows = read_csv(mapping)
    selected = approved_exercises(track, mapping_rows)
    if not selected:
        raise PipelineError(
            "attribute template needs at least one INCLUDE or MERGE row; "
            "complete the mapping review first"
        )
    rows: list[dict[str, object]] = []
    for row in selected:
        rows.append(
            {
                "source_identity": row[track.identity_field],
                "review_normalized_exercise_id": row["review_normalized_exercise_id"],
                "review_display_name_ko": row["review_display_name_ko"],
                **PENDING_ATTRIBUTE_VALUES,
            }
        )
    write_csv(output_path, ATTRIBUTE_FIELDS, rows)
    return {
        "track": track.name,
        "batch": batch_dir.name,
        "attribute_rows": len(rows),
        "status": "template_written",
        "production_eligible": False,
    }


def load_taxonomy_registry(path: Path) -> dict[str, set[str]]:
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"taxonomy registry is missing: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError("taxonomy registry is not valid JSON") from exc

    status = str(registry.get("status", ""))
    if status != "APPROVED":
        raise PipelineError(
            f"taxonomy registry status is {status or 'missing'}; "
            "seed generation requires an APPROVED code list"
        )
    code_sets = registry.get("code_sets")
    if not isinstance(code_sets, dict):
        raise PipelineError("taxonomy registry code_sets is missing")
    resolved: dict[str, set[str]] = {}
    for name, entries in code_sets.items():
        if not isinstance(entries, list):
            raise PipelineError(f"taxonomy registry {name} must be a list")
        resolved[name] = {
            str(entry.get("code", "")) for entry in entries if isinstance(entry, dict)
        }
    return resolved


def split_codes(value: str) -> list[str]:
    return [part.strip() for part in value.split("|") if part.strip()]


def parse_seconds(value: str, field: str, problems: list[str]) -> int | None:
    text = value.strip()
    if not text:
        return None
    try:
        number = int(text)
    except ValueError:
        problems.append(f"{field} must be an integer")
        return None
    if number < 0:
        problems.append(f"{field} must be zero or greater")
        return None
    return number


def parse_boolean(value: str, field: str, problems: list[str]) -> bool | None:
    text = value.strip().upper()
    if not text:
        return None
    if text in {"TRUE", "YES"}:
        return True
    if text in {"FALSE", "NO"}:
        return False
    problems.append(f"{field} must be TRUE or FALSE")
    return None


def attribute_problems(row: dict[str, str], registry: dict[str, set[str]] | None) -> list[str]:
    """Return every reason this attribute row cannot become a production exercise."""

    problems: list[str] = []

    def coded(field: str, allowed: set[str] | None) -> None:
        value = row.get(field, "").strip()
        if not value:
            problems.append(f"{field} is empty")
            return
        if allowed is not None and value not in allowed:
            problems.append(f"{field} is not in the approved code list: {value}")

    coded("training_type_code", registry.get("training_type_code") if registry else None)
    coded("body_focus_code", registry.get("body_focus_code") if registry else None)
    coded(
        "primary_movement_pattern_code",
        registry.get("movement_pattern_code") if registry else None,
    )
    coded("difficulty_code", set(DIFFICULTY_CODES))

    timing_mode = row.get("timing_mode_code", "").strip()
    if timing_mode not in TIMING_MODE_CODES:
        problems.append("timing_mode_code must be REPS or DURATION")
    seconds_per_rep = parse_seconds(
        row.get("default_seconds_per_rep", ""), "default_seconds_per_rep", problems
    )
    work_seconds = parse_seconds(
        row.get("default_work_seconds", ""), "default_work_seconds", problems
    )
    if timing_mode == "REPS" and seconds_per_rep is None:
        problems.append("timing_mode REPS requires default_seconds_per_rep")
    if timing_mode == "DURATION" and work_seconds is None:
        problems.append("timing_mode DURATION requires default_work_seconds")

    if parse_seconds(row.get("default_rest_seconds", ""), "default_rest_seconds", problems) is None:
        problems.append("default_rest_seconds is empty")
    transition = parse_seconds(
        row.get("default_transition_seconds", ""), "default_transition_seconds", problems
    )
    if transition is None:
        problems.append("default_transition_seconds is empty")
    elif not TRANSITION_SECONDS_RANGE[0] <= transition <= TRANSITION_SECONDS_RANGE[1]:
        problems.append(
            "default_transition_seconds must be between "
            f"{TRANSITION_SECONDS_RANGE[0]} and {TRANSITION_SECONDS_RANGE[1]}"
        )

    if parse_boolean(row.get("recovery_eligible", ""), "recovery_eligible", problems) is None:
        problems.append("recovery_eligible is empty")

    primary_areas = split_codes(row.get("primary_body_area_codes", ""))
    if not primary_areas:
        problems.append("primary_body_area_codes is empty")
    for code in primary_areas + split_codes(row.get("secondary_body_area_codes", "")):
        if code not in BODY_AREA_CODES:
            problems.append(f"body area code is not in DOMAIN_RULES: {code}")

    equipment = split_codes(row.get("equipment_codes", ""))
    if not equipment:
        problems.append("equipment_codes is empty")
    if registry:
        for code in equipment:
            if code not in registry.get("equipment_code", set()):
                problems.append(f"equipment_code is not in the approved code list: {code}")
    locations = split_codes(row.get("location_codes", ""))
    if not locations:
        problems.append("location_codes is empty")
    if registry:
        for code in locations:
            if code not in registry.get("location_code", set()):
                problems.append(f"location_code is not in the approved code list: {code}")

    for field in ("instruction_summary_ko", "form_cues_ko", "instruction_content_version"):
        if not row.get(field, "").strip():
            problems.append(f"{field} is empty")

    if row.get("attribute_status", "").strip() != "DOMAIN_APPROVED":
        problems.append("attribute_status must be DOMAIN_APPROVED")
    return problems


def assess_readiness(
    track: TrackSpec,
    batch_dir: Path,
    mapping: Path,
    evidence: Path,
    attributes: Path | None,
    registry_path: Path | None,
) -> dict[str, object]:
    batch_dir = batch_dir.resolve()
    blockers: list[str] = []
    try:
        validate_results(track, batch_dir, mapping, evidence)
    except PipelineError as exc:
        blockers.append(f"review results are not valid: {exc}")

    mapping_rows = read_csv(mapping)
    selected = approved_exercises(track, mapping_rows)
    if not selected:
        blockers.append("no INCLUDE or MERGE rows; domain review has not produced any exercise")

    registry: dict[str, set[str]] | None = None
    if registry_path is not None:
        try:
            registry = load_taxonomy_registry(registry_path)
        except PipelineError as exc:
            blockers.append(str(exc))
    else:
        blockers.append("taxonomy registry was not provided")

    attribute_rows: list[dict[str, str]] = []
    if attributes is not None:
        attribute_rows = read_csv(attributes, ATTRIBUTE_FIELDS)
    else:
        blockers.append("catalog attribute sheet was not provided")

    by_identity = {row["source_identity"].strip(): row for row in attribute_rows}
    missing_field_counts: dict[str, int] = {}
    ready_rows = 0
    for row in selected:
        identity = row[track.identity_field].strip()
        attribute_row = by_identity.get(identity)
        if attribute_row is None:
            missing_field_counts["attribute_row_missing"] = (
                missing_field_counts.get("attribute_row_missing", 0) + 1
            )
            continue
        problems = attribute_problems(attribute_row, registry)
        if problems:
            for problem in problems:
                key = problem.split(":")[0]
                missing_field_counts[key] = missing_field_counts.get(key, 0) + 1
            continue
        ready_rows += 1

    return {
        "generator_version": SEED_GENERATOR_VERSION,
        "track": track.name,
        "batch": batch_dir.name,
        "mapping_rows": len(mapping_rows),
        "include_or_merge_rows": len(selected),
        "attribute_rows": len(attribute_rows),
        "seed_ready_rows": ready_rows,
        "blockers": blockers,
        "unmet_requirements": dict(sorted(missing_field_counts.items())),
        "production_eligible": False,
        "status": "ready" if ready_rows and not blockers else "not_ready",
    }


def build_seed(
    track: TrackSpec,
    batch_dir: Path,
    mapping: Path,
    evidence: Path,
    attributes: Path,
    registry_path: Path,
    output_root: Path,
    version_code: str,
) -> Path:
    batch_dir = batch_dir.resolve()
    validate_results(track, batch_dir, mapping, evidence)
    registry = load_taxonomy_registry(registry_path)

    mapping_rows = read_csv(mapping)
    selected = approved_exercises(track, mapping_rows)
    if not selected:
        raise PipelineError("no INCLUDE or MERGE rows; nothing is approved for seeding")

    evidence_rows = read_csv(evidence)
    domain_approved = {
        row["source_exercise_id" if track.name == "wger" else "source_candidate_id"].strip()
        for row in evidence_rows
        if row["reviewer_role_code"].strip() == "DOMAIN_REVIEWER"
        and row["review_status_code"].strip() == "DOMAIN_APPROVED"
    }

    attribute_rows = read_csv(attributes, ATTRIBUTE_FIELDS)
    by_identity = {row["source_identity"].strip(): row for row in attribute_rows}

    seed_rows: list[dict[str, object]] = []
    for row in selected:
        identity = row[track.identity_field].strip()
        if identity not in domain_approved:
            raise PipelineError(f"exercise {identity} has no DOMAIN_APPROVED domain review")
        attribute_row = by_identity.get(identity)
        if attribute_row is None:
            raise PipelineError(f"exercise {identity} has no catalog attribute row")
        problems = attribute_problems(attribute_row, registry)
        if problems:
            raise PipelineError(f"exercise {identity} is not seed ready: {problems[0]}")
        name_problems = display_name_problems(
            row["review_display_name_ko"], source_name=row[track.source_name_field]
        )
        if name_problems:
            raise PipelineError(f"exercise {identity} display name invalid: {name_problems[0]}")

        seed_rows.append(
            {
                "stable_code": row["review_normalized_exercise_id"].strip(),
                "name_ko": row["review_display_name_ko"].strip(),
                "name_en": row[track.source_name_field].strip() if track.name == "wger" else "",
                "training_type_code": attribute_row["training_type_code"].strip(),
                "body_focus_code": attribute_row["body_focus_code"].strip(),
                "primary_movement_pattern_code": attribute_row[
                    "primary_movement_pattern_code"
                ].strip(),
                "difficulty_code": attribute_row["difficulty_code"].strip(),
                "beginner_suitable": row["review_beginner_suitability"].strip() == "YES",
                "timing_mode_code": attribute_row["timing_mode_code"].strip(),
                "default_seconds_per_rep": attribute_row["default_seconds_per_rep"].strip() or None,
                "default_work_seconds": attribute_row["default_work_seconds"].strip() or None,
                "default_rest_seconds": int(attribute_row["default_rest_seconds"]),
                "default_transition_seconds": int(attribute_row["default_transition_seconds"]),
                "recovery_eligible": attribute_row["recovery_eligible"].strip().upper()
                in {"TRUE", "YES"},
                "primary_body_area_codes": split_codes(attribute_row["primary_body_area_codes"]),
                "secondary_body_area_codes": split_codes(
                    attribute_row["secondary_body_area_codes"]
                ),
                "equipment_codes": split_codes(attribute_row["equipment_codes"]),
                "location_codes": split_codes(attribute_row["location_codes"]),
                "instruction_summary_ko": attribute_row["instruction_summary_ko"].strip(),
                "form_cues_ko": attribute_row["form_cues_ko"].strip(),
                "instruction_content_version": attribute_row["instruction_content_version"].strip(),
                "review_status_code": "DOMAIN_APPROVED",
                "source_track": track.name,
                "source_identity": identity,
            }
        )

    stable_codes = [str(row["stable_code"]) for row in seed_rows]
    if len(set(stable_codes)) != len(stable_codes):
        raise PipelineError("stable_code must be unique within a catalog version")
    duplicates = duplicate_display_names(row["name_ko"] for row in seed_rows)
    if duplicates:
        raise PipelineError(f"Korean display name is duplicated: {', '.join(duplicates)}")

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    directory_name = f"exercise-catalog-seed-{version_code}"
    final_dir = output_root / directory_name
    partial_dir = output_root / f".{directory_name}.partial"
    if final_dir.exists():
        raise PipelineError(f"catalog seed already exists: {directory_name}")
    if partial_dir.exists():
        raise PipelineError(f"partial catalog seed already exists: {partial_dir.name}")

    partial_dir.mkdir()
    try:
        seed_path = partial_dir / "exercises.jsonl"
        with seed_path.open("w", encoding="utf-8", newline="\n") as handle:
            for seed_row in seed_rows:
                handle.write(json.dumps(seed_row, ensure_ascii=False, sort_keys=True) + "\n")
        raw = seed_path.read_bytes()
        manifest = {
            "schema_version": "1.0",
            "generator_version": SEED_GENERATOR_VERSION,
            "catalog_version": {"version_code": version_code, "status_code": "DRAFT"},
            "source": {
                "track": track.name,
                "review_batch_directory": batch_dir.name,
                "taxonomy_registry_sha256": sha256_bytes(registry_path.read_bytes()),
            },
            "review": {"status": "DOMAIN_APPROVED", "production_eligible": False},
            "summary": {"exercise_records": len(seed_rows)},
            "files": [
                {
                    "path": "exercises.jsonl",
                    "sha256": sha256_bytes(raw),
                    "bytes": len(raw),
                    "records": len(seed_rows),
                }
            ],
        }
        (partial_dir / "seed_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        verify_seed(partial_dir)
        partial_dir.replace(final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise


def verify_seed(seed_dir: Path) -> dict[str, object]:
    seed_dir = seed_dir.resolve()
    try:
        manifest = json.loads((seed_dir / "seed_manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError("seed_manifest.json is missing") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError("seed_manifest.json is not valid JSON") from exc

    if manifest.get("schema_version") != "1.0":
        raise PipelineError("unsupported seed manifest schema")
    review = manifest.get("review")
    if not isinstance(review, dict) or review.get("production_eligible") is not False:
        raise PipelineError("catalog seed must stay production-ineligible until promoted")

    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 1:
        raise PipelineError("seed manifest must list the exercises file")
    entry = files[0]
    path = seed_dir / str(entry.get("path", ""))
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise PipelineError("catalog seed file is missing") from exc
    if sha256_bytes(raw) != entry.get("sha256") or len(raw) != int(entry.get("bytes", -1)):
        raise PipelineError("catalog seed hash or size mismatch")

    records = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if len(records) != int(entry.get("records", -1)):
        raise PipelineError("catalog seed record count mismatch")
    for record in records:
        if record.get("review_status_code") != "DOMAIN_APPROVED":
            raise PipelineError("catalog seed contains a record without domain approval")
        transition = int(record.get("default_transition_seconds", 0))
        if not TRANSITION_SECONDS_RANGE[0] <= transition <= TRANSITION_SECONDS_RANGE[1]:
            raise PipelineError("catalog seed transition seconds out of range")
    return {"seed": seed_dir.name, "records": len(records), "status": "valid"}


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    template = subparsers.add_parser("template", help="write a blank catalog attribute sheet")
    template.add_argument("track", choices=sorted(TRACKS))
    template.add_argument("batch", type=Path)
    template.add_argument("mapping_results", type=Path)
    template.add_argument("--out", type=Path, required=True)

    readiness = subparsers.add_parser("readiness", help="report what blocks seed generation")
    readiness.add_argument("track", choices=sorted(TRACKS))
    readiness.add_argument("batch", type=Path)
    readiness.add_argument("mapping_results", type=Path)
    readiness.add_argument("evidence_results", type=Path)
    readiness.add_argument("--attributes", type=Path)
    readiness.add_argument("--taxonomy-registry", type=Path)

    build = subparsers.add_parser("build", help="build a catalog seed, fail-closed")
    build.add_argument("track", choices=sorted(TRACKS))
    build.add_argument("batch", type=Path)
    build.add_argument("mapping_results", type=Path)
    build.add_argument("evidence_results", type=Path)
    build.add_argument("attributes", type=Path)
    build.add_argument("taxonomy_registry", type=Path)
    build.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    build.add_argument("--version-code", required=True)

    verify = subparsers.add_parser("verify", help="verify a generated catalog seed")
    verify.add_argument("seed", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "template":
            result: dict[str, object] = build_attribute_template(
                TRACKS[args.track], args.batch, args.mapping_results, args.out
            )
        elif args.command == "readiness":
            result = assess_readiness(
                TRACKS[args.track],
                args.batch,
                args.mapping_results,
                args.evidence_results,
                args.attributes,
                args.taxonomy_registry,
            )
        elif args.command == "build":
            seed_dir = build_seed(
                TRACKS[args.track],
                args.batch,
                args.mapping_results,
                args.evidence_results,
                args.attributes,
                args.taxonomy_registry,
                args.output_root,
                args.version_code,
            )
            result = {"status": "built", "seed": str(seed_dir)}
        else:
            result = verify_seed(args.seed)
    except (PipelineError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
