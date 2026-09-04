#!/usr/bin/env python3
"""Migrate v2.0.6 foam-roller stable-code references after canonical renaming."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CODE_MAP = {
    "roller_back_stretch_mobility_stretch_foam_roller": "roller_back_stretch",
    "roller_hip_stretch_mobility_stretch_foam_roller": "roller_hip_stretch",
    "roller_seated_shoulder_flexor_depresor_retractor": "foam_roller_hamstring_stretch",
    "roller_body_saw": "foam_roller_thigh_stretch",
    "roller_hip_lat_stretch": "foam_roller_outer_thigh_stretch_2205",
    "roller_reverse_crunch": "foam_roller_calf_stretch_2206",
    "roller_side_lat_stretch": "foam_roller_outer_thigh_stretch_2207",
    "roller_seated_single_leg_shoulder_flexor_depresor_retractor": "foam_roller_calf_stretch_2209",
}
TEXT_SUFFIXES = {
    ".csv",
    ".json",
    ".jsonl",
    ".md",
    ".py",
}


def migrate(root: Path = ROOT) -> list[Path]:
    changed: list[Path] = []
    for directory in (root / "data/normalized", root / "data/reports", root / "data/scripts"):
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            if path == Path(__file__).resolve():
                continue
            original = path.read_text(encoding="utf-8")
            updated = original
            for before, after in CODE_MAP.items():
                updated = updated.replace(before, after)
            if updated != original:
                path.write_text(updated, encoding="utf-8", newline="")
                changed.append(path)
    return changed


if __name__ == "__main__":
    for path in migrate():
        print(path.relative_to(ROOT))
