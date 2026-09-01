"""Merge the approved per-track catalog seeds into one catalog version.

`docs/DATA_MODEL.md` 6.3의 루틴 생성은 ACTIVE 카탈로그 **하나**만 읽는다.
`uq_catalog_versions_single_active`가 ACTIVE 행을 하나로 제한하고
`RoutineRepository.get_creation_context`도 후보가 정확히 하나일 때만 동작한다.

그런데 검토는 트랙별로 진행해 seed가 kspo와 wger로 나뉘어 있다. 트랙 seed 하나만
활성화하면 다음 두 가지가 깨진다.

1. 홈 전용(kspo) 또는 헬스장 전용(wger) 운동만 남아 반대쪽 사용자가 후보를 못 받는다.
2. 대체 관계가 트랙을 넘나들므로 상당수가 조회되지 않는다.

이 스크립트는 승인된 트랙 seed를 결합해 단일 카탈로그 버전을 만든다. 운동 레코드는
바꾸지 않고 그대로 옮긴다. 병합은 검토가 아니므로 승인 상태를 올리지 않으며 산출물은
계속 `production_eligible=false`인 DRAFT다.

`source.track`은 `merged`이고, 운동별 `source_track`은 원천 그대로 유지해 provenance를
잃지 않는다.

    python data/scripts/build_merged_catalog_seed.py build \
      generated/exercise-catalog-seed-kspo-mvp-v0.2.0 \
      generated/exercise-catalog-seed-wger-mvp-v0.2.0 \
      --version-code merged-mvp-v0.3.0

    python data/scripts/build_merged_catalog_seed.py verify \
      generated/exercise-catalog-seed-merged-mvp-v0.3.0
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from build_exercise_catalog_seed import verify_seed
from kspo_fitness100_pipeline import PipelineError, sha256_bytes

MERGE_GENERATOR_VERSION = "0.1.0"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[1] / "generated"
MERGED_TRACK_NAME = "merged"
# 병합은 원천 트랙 seed만 입력으로 받는다. 병합 결과를 다시 병합하지 않는다.
SOURCE_TRACK_NAMES = frozenset({"kspo", "wger"})


def _load_seed(seed_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Re-verify a track seed and return its manifest and exercise records."""
    seed_dir = seed_dir.resolve()
    # 해시·건수·승인 상태를 여기서 다시 검사한다. 병합이 손상된 입력을 통과시키면
    # 하위 파생 산출물 전체가 오염되기 때문이다.
    verify_seed(seed_dir)

    manifest = json.loads((seed_dir / "seed_manifest.json").read_text(encoding="utf-8"))

    track = manifest.get("source", {}).get("track")
    if track not in SOURCE_TRACK_NAMES:
        raise PipelineError(
            f"{seed_dir.name}: only kspo and wger seeds can be merged, got {track!r}"
        )

    raw = (seed_dir / str(manifest["files"][0]["path"])).read_bytes()
    records = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    return manifest, records


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    repeated: set[str] = set()
    for value in values:
        if value in seen:
            repeated.add(value)
        seen.add(value)
    return sorted(repeated)


def build_merged_seed(
    seed_dirs: tuple[Path, ...],
    output_root: Path,
    version_code: str,
) -> Path:
    if len(seed_dirs) < 2:
        raise PipelineError("merging needs at least two track seeds")

    resolved = [path.resolve() for path in seed_dirs]
    if len(set(resolved)) != len(resolved):
        raise PipelineError("the same seed directory was supplied twice")

    manifests: list[dict[str, Any]] = []
    merged_records: list[dict[str, Any]] = []
    for seed_dir in resolved:
        manifest, records = _load_seed(seed_dir)
        manifests.append(manifest)
        merged_records.extend(records)

    # 모든 입력이 같은 taxonomy registry에서 나왔을 때만 코드 값을 섞을 수 있다.
    registries = {manifest["source"]["taxonomy_registry_sha256"] for manifest in manifests}
    if len(registries) != 1:
        raise PipelineError("track seeds were built against different taxonomy registries")

    # 카탈로그 안에서 stable_code는 유일해야 한다. 트랙별로는 통과하더라도 병합에서
    # 처음 충돌할 수 있으므로 여기서 fail-closed로 막는다.
    collisions = _duplicates([str(record["stable_code"]) for record in merged_records])
    if collisions:
        raise PipelineError(f"stable_code collides across tracks: {', '.join(collisions)}")

    duplicate_names = _duplicates([str(record["name_ko"]) for record in merged_records])
    if duplicate_names:
        raise PipelineError(f"Korean display name is duplicated: {', '.join(duplicate_names)}")

    # 사용자에게 보이는 순서가 입력 순서에 흔들리지 않도록 stable_code로 고정한다.
    merged_records.sort(key=lambda record: str(record["stable_code"]))

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
            for record in merged_records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        raw = seed_path.read_bytes()

        input_artifacts = []
        for seed_dir in resolved:
            manifest_bytes = (seed_dir / "seed_manifest.json").read_bytes()
            input_artifacts.append(
                {
                    "role": "catalog_seed_manifest",
                    # 다른 산출물과 같이 매니페스트 안에서만 유효한 상대 경로를 쓴다.
                    # 소비자는 이 경로를 열지 않고 해시만 provenance로 사용하며,
                    # importer는 artifact 디렉터리를 벗어나는 경로를 거부한다.
                    "path": f"{seed_dir.name}/seed_manifest.json",
                    "sha256": sha256_bytes(manifest_bytes),
                    "bytes": len(manifest_bytes),
                }
            )

        manifest = {
            "schema_version": "1.0",
            "generator_version": MERGE_GENERATOR_VERSION,
            "catalog_version": {"version_code": version_code, "status_code": "DRAFT"},
            "source": {
                "track": MERGED_TRACK_NAME,
                "review_batch_directory": MERGED_TRACK_NAME,
                "taxonomy_registry_sha256": next(iter(registries)),
                # 입력 seed의 매니페스트 해시를 남겨 병합 결과에서 트랙 seed까지
                # 거슬러 올라갈 수 있게 한다.
                "input_artifacts": input_artifacts,
            },
            # 병합은 검토 행위가 아니다. 입력 seed와 같은 상태를 그대로 물려받는다.
            "review": {
                "status": "DOMAIN_APPROVED",
                "review_method_code": "AGENT_ONLY",
                "status_interpretation": "PIPELINE_COMPATIBILITY_ONLY",
                "production_eligible": False,
            },
            "summary": {"exercise_records": len(merged_records)},
            "files": [
                {
                    "path": "exercises.jsonl",
                    "sha256": sha256_bytes(raw),
                    "bytes": len(raw),
                    "records": len(merged_records),
                }
            ],
        }
        (partial_dir / "seed_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        verify_seed(partial_dir)
        partial_dir.replace(final_dir)
        return final_dir
    except Exception:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="merge approved track seeds")
    build.add_argument("seeds", type=Path, nargs="+")
    build.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    build.add_argument("--version-code", required=True)
    verify = subparsers.add_parser("verify", help="verify a merged catalog seed")
    verify.add_argument("seed", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "build":
            final_dir = build_merged_seed(tuple(args.seeds), args.output_root, args.version_code)
            report = verify_seed(final_dir)
        else:
            report = verify_seed(args.seed)
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
