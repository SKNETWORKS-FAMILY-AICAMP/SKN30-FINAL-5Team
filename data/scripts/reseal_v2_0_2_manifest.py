"""Re-seal the v2.0.2 manifest against the artifact bytes actually shipped.

``manifest.json`` records a SHA-256 for each artifact so an importer can fail
closed on drift. Twelve of the thirty seals no longer verify, for two unrelated
reasons:

* ``alternatives/resolved_discomfort_alternative_map_v2_0_2.jsonl`` changed after
  the manifest was written. Commit ``029bbea`` dropped the four per-row approval
  fields and set ``production_eligible`` to false on all 1,104 rows, which is the
  conservative posture the handoff describes - the batch approval is kept once in
  ``manifest.batch_approval`` instead of repeated on every row - but the seal was
  not recomputed.
* Eleven CSV artifacts were committed before ``.gitattributes`` exempted
  ``data/generated/**/*.csv`` from line-ending normalization, so their checked-out
  bytes differ from the bytes that were hashed. The rows are unchanged; only the
  line endings are. The original bytes never entered the repository, so they
  cannot be restored - the seal has to be recomputed from what is stored.

This script recomputes every recorded hash from the shipped bytes and records
what it changed under ``manifest.reseal``. It never edits an artifact, so it
cannot make a payload agree with a seal by altering the payload. Run it only
when the artifact content is known-good and the drift is understood; use
``--check`` in CI to assert the seals verify.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

DATA_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FINAL = DATA_ROOT / "generated/exercise-catalog-v2.0.2-final"
RESEAL_REFERENCE = "V2_0_2_MANIFEST_RESEAL_2026_08_30"


class ResealError(RuntimeError):
    """Raised when the manifest cannot be verified or re-sealed."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_manifest(final: Path) -> dict[str, Any]:
    path = final / "manifest.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResealError(f"v2.0.2 manifest is unreadable: {path}") from exc


def audit(final: Path = DEFAULT_FINAL) -> dict[str, Any]:
    """Report every recorded artifact whose bytes no longer match its seal."""
    manifest = _load_manifest(final)
    recorded: dict[str, str] = manifest.get("artifact_sha256") or {}
    if not recorded:
        raise ResealError("v2.0.2 manifest records no artifact hashes")
    missing: list[str] = []
    drifted: list[dict[str, str]] = []
    for relative, expected in sorted(recorded.items()):
        path = final / relative
        if not path.is_file():
            missing.append(relative)
            continue
        raw = path.read_bytes()
        actual = _sha256(raw)
        if actual == expected:
            continue
        # Distinguish a rewritten line ending from a content change, so the two
        # causes never get reported as one number.
        normalized = raw.replace(b"\r\n", b"\n")
        as_crlf = normalized.replace(b"\n", b"\r\n")
        if _sha256(as_crlf) == expected:
            cause = "LINE_ENDING_NORMALIZED"
        elif _sha256(normalized) == expected:
            cause = "LINE_ENDING_NORMALIZED"
        else:
            cause = "CONTENT_CHANGED"
        drifted.append({"path": relative, "recorded": expected, "actual": actual, "cause": cause})
    return {
        "recorded_artifacts": len(recorded),
        "missing": missing,
        "drifted": drifted,
        "verified": len(recorded) - len(missing) - len(drifted),
    }


def reseal(final: Path = DEFAULT_FINAL) -> dict[str, Any]:
    """Rewrite the recorded hashes from the shipped bytes and log the change."""
    report = audit(final)
    if report["missing"]:
        raise ResealError(f"cannot re-seal while artifacts are missing: {report['missing']}")
    if not report["drifted"]:
        return {"status": "ALREADY_SEALED", **report}

    manifest = _load_manifest(final)
    recorded: dict[str, str] = manifest["artifact_sha256"]
    for entry in report["drifted"]:
        recorded[entry["path"]] = entry["actual"]
    manifest["reseal"] = {
        "reference": RESEAL_REFERENCE,
        "resealed_on": "2026-08-30",
        "directed_by": "PROJECT_OWNER",
        "artifact_count": len(report["drifted"]),
        "causes": sorted({entry["cause"] for entry in report["drifted"]}),
        "entries": [
            {
                "path": entry["path"],
                "previous_sha256": entry["recorded"],
                "sha256": entry["actual"],
                "cause": entry["cause"],
            }
            for entry in report["drifted"]
        ],
        "note": (
            "Seals were recomputed from the shipped bytes. No artifact content was "
            "edited by the re-seal."
        ),
    }
    (final / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {"status": "RESEALED", **report}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", type=Path, default=DEFAULT_FINAL)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift and exit non-zero instead of re-sealing",
    )
    args = parser.parse_args(argv)
    if args.check:
        report = audit(args.final)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 1 if report["drifted"] or report["missing"] else 0
    report = reseal(args.final)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
