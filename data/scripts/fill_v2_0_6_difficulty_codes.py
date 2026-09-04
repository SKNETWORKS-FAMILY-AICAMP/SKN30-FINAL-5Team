#!/usr/bin/env python3
"""Apply the user-reviewed intrinsic difficulty for the v2.0.6 catalog.

The normalized CSV is the editable source of truth.  Existing non-empty
values are preserved unless explicitly listed as a revised review value.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = PROJECT_ROOT / "data/normalized/v2_0_6_exercise_catalog.csv"
ALLOWED_DIFFICULTIES = {"BEGINNER", "INTERMEDIATE"}

# Review basis: assisted or externally supported movements and simple
# bodyweight/isolation movements are BEGINNER.  Loaded compound movements,
# cable movements (per the approved v2.0.2 policy), unilateral/balance-demanding
# movements, explosive movements, and advanced bodyweight variations are
# INTERMEDIATE.
DIFFICULTY_BY_SOURCE_ID = {
    "0002": "BEGINNER",
    "0006": "BEGINNER",
    "0007": "INTERMEDIATE",
    "0017": "BEGINNER",
    "0019": "BEGINNER",
    "0020": "INTERMEDIATE",
    "0022": "INTERMEDIATE",
    "0026": "INTERMEDIATE",
    "0027": "INTERMEDIATE",
    "0031": "BEGINNER",
    "0034": "INTERMEDIATE",
    "0035": "INTERMEDIATE",
    "0043": "INTERMEDIATE",
    "0044": "INTERMEDIATE",
    "0047": "INTERMEDIATE",
    "0049": "INTERMEDIATE",
    "0053": "INTERMEDIATE",
    "0054": "INTERMEDIATE",
    "0056": "BEGINNER",
    "0058": "BEGINNER",
    "0059": "BEGINNER",
    "0063": "INTERMEDIATE",
    "0069": "INTERMEDIATE",
    "0070": "BEGINNER",
    "0074": "INTERMEDIATE",
    "0076": "INTERMEDIATE",
    "0085": "INTERMEDIATE",
    "0090": "INTERMEDIATE",
    "0091": "INTERMEDIATE",
    "0094": "INTERMEDIATE",
    "0095": "BEGINNER",
    "0096": "INTERMEDIATE",
    "0108": "BEGINNER",
    "0111": "INTERMEDIATE",
    "0117": "INTERMEDIATE",
    "0121": "INTERMEDIATE",
    "0129": "BEGINNER",
    "0130": "BEGINNER",
    "0137": "BEGINNER",
    "0138": "BEGINNER",
    "0158": "INTERMEDIATE",
    "0159": "INTERMEDIATE",
    "0168": "INTERMEDIATE",
    "0169": "INTERMEDIATE",
    "0180": "INTERMEDIATE",
    "0199": "INTERMEDIATE",
    "0214": "INTERMEDIATE",
    "0218": "INTERMEDIATE",
    "0228": "INTERMEDIATE",
    "0233": "INTERMEDIATE",
    "0239": "INTERMEDIATE",
    "0260": "INTERMEDIATE",
    "0262": "INTERMEDIATE",
    "0271": "INTERMEDIATE",
    "0272": "INTERMEDIATE",
    "0276": "BEGINNER",
    "0285": "BEGINNER",
    "0287": "INTERMEDIATE",
    "0291": "BEGINNER",
    "0292": "INTERMEDIATE",
    "0293": "INTERMEDIATE",
    "0299": "INTERMEDIATE",
    "0300": "BEGINNER",
    "0303": "INTERMEDIATE",
    "0314": "INTERMEDIATE",
    "0317": "BEGINNER",
    "0321": "INTERMEDIATE",
    "0326": "BEGINNER",
    "0327": "INTERMEDIATE",
    "0371": "INTERMEDIATE",
    "0379": "BEGINNER",
    "0389": "BEGINNER",
    "0410": "INTERMEDIATE",
    "0443": "INTERMEDIATE",
    "0456": "INTERMEDIATE",
    "0459": "INTERMEDIATE",
    "0469": "INTERMEDIATE",
    "0513": "INTERMEDIATE",
    "0514": "INTERMEDIATE",
    "0548": "INTERMEDIATE",
    "0549": "INTERMEDIATE",
    "0555": "INTERMEDIATE",
    "0584": "BEGINNER",
    "0585": "BEGINNER",
    "0586": "BEGINNER",
    "0596": "BEGINNER",
    "0597": "BEGINNER",
    "0598": "BEGINNER",
    "0601": "BEGINNER",
    "0602": "BEGINNER",
    "0620": "INTERMEDIATE",
    "0628": "BEGINNER",
    "0630": "INTERMEDIATE",
    "0635": "INTERMEDIATE",
    "0659": "BEGINNER",
    "0668": "BEGINNER",
    "0684": "INTERMEDIATE",
    "0689": "BEGINNER",
    "0691": "BEGINNER",
    "0705": "INTERMEDIATE",
    "0709": "BEGINNER",
    "0710": "BEGINNER",
    "0730": "INTERMEDIATE",
    "0740": "BEGINNER",
    "0748": "BEGINNER",
    "0749": "INTERMEDIATE",
    "0751": "BEGINNER",
    "0760": "BEGINNER",
    "0761": "BEGINNER",
    "0768": "INTERMEDIATE",
    "0769": "INTERMEDIATE",
    "0798": "BEGINNER",
    "0856": "BEGINNER",
    "1001": "INTERMEDIATE",
    "1259": "BEGINNER",
    "1297": "BEGINNER",
    "1358": "BEGINNER",
    "1362": "BEGINNER",
    "1366": "BEGINNER",
    "1388": "BEGINNER",
    "1389": "BEGINNER",
    "1397": "BEGINNER",
    "1407": "BEGINNER",
    "1419": "INTERMEDIATE",
    "1423": "INTERMEDIATE",
    "1430": "INTERMEDIATE",
    "1432": "BEGINNER",
    "1460": "BEGINNER",
    "1476": "INTERMEDIATE",
    "1564": "INTERMEDIATE",
    "1687": "BEGINNER",
    "1689": "INTERMEDIATE",
    "1700": "INTERMEDIATE",
    "1771": "INTERMEDIATE",
    "2133": "BEGINNER",
    "2141": "BEGINNER",
    "2203": "BEGINNER",
    "2204": "BEGINNER",
    "2205": "BEGINNER",
    "2206": "BEGINNER",
    "2207": "BEGINNER",
    "2209": "BEGINNER",
    "2271": "BEGINNER",
    "2398": "BEGINNER",
    "2571": "BEGINNER",
    "3006": "BEGINNER",
    "3007": "BEGINNER",
    "3011": "BEGINNER",
    "3016": "BEGINNER",
    "3147": "BEGINNER",
    "3195": "INTERMEDIATE",
    "3201": "BEGINNER",
    "3220": "BEGINNER",
    "3221": "BEGINNER",
    "3231": "BEGINNER",
    "3239": "INTERMEDIATE",
    "3533": "INTERMEDIATE",
    "3544": "BEGINNER",
    "3552": "BEGINNER",
    "3640": "INTERMEDIATE",
    "3645": "INTERMEDIATE",
    "3656": "INTERMEDIATE",
    "3662": "INTERMEDIATE",
    "3667": "BEGINNER",
    "3671": "INTERMEDIATE",
    "3769": "INTERMEDIATE",
}

# Follow-up review overrides for values that were already populated.  These
# reflect the user's broader beginner-accessibility rule for stable,
# bodyweight, mobility, foam-roller, and balance-board movements.
DIFFICULTY_OVERRIDES = {
    "0020": "BEGINNER",  # balance board
    "0443": "BEGINNER",  # elbow-to-knee
    "0489": "BEGINNER",  # hyperextension
    "0499": "BEGINNER",  # inverted row
    "0635": "BEGINNER",  # oblique crunch
    "0872": "BEGINNER",  # reverse crunch
    "1352": "BEGINNER",  # lower back curl
    "1419": "BEGINNER",  # mobility stretch
    "1512": "BEGINNER",  # mobility stretch
    "1559": "BEGINNER",  # mobility stretch
    "1564": "BEGINNER",  # mobility stretch
    "1587": "BEGINNER",  # mobility stretch
    "1604": "BEGINNER",  # mobility stretch
    "1689": "BEGINNER",  # bodyweight push-up progression
    "2202": "BEGINNER",  # foam roller
    "2208": "BEGINNER",  # foam roller
    "2368": "BEGINNER",  # split squat
    "0456": "BEGINNER",  # bent-knee sit-up
    "0469": "BEGINNER",  # groin crunch
    "0459": "BEGINNER",  # flutter kicks
    "0513": "BEGINNER",  # bodyweight jump squat
    "0514": "BEGINNER",  # bodyweight jump squat
    "0630": "BEGINNER",  # mountain climber
    "3640": "BEGINNER",  # knee-touch crunch
    "3645": "BEGINNER",  # single-leg bridge
    "3769": "BEGINNER",  # curtsy squat
}


class DifficultyReviewError(ValueError):
    """Raised when the normalized catalog does not match the review scope."""


def apply_review(path: Path) -> tuple[int, int]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    if "source_identity" not in fields or "difficulty_code" not in fields:
        raise DifficultyReviewError("catalog must contain source_identity and difficulty_code")

    identities = {row.get("source_identity", "") for row in rows}
    unknown = sorted(set(DIFFICULTY_BY_SOURCE_ID) - identities)
    if unknown:
        raise DifficultyReviewError(f"review IDs are missing from catalog: {', '.join(unknown)}")

    updated = 0
    preserved = 0
    for row in rows:
        identity = row["source_identity"]
        current = (row.get("difficulty_code") or "").strip()
        if current and current not in ALLOWED_DIFFICULTIES:
            raise DifficultyReviewError(
                f"unsupported existing difficulty for {identity}: {current}"
            )
        if identity in DIFFICULTY_OVERRIDES:
            expected = DIFFICULTY_OVERRIDES[identity]
            if current != expected:
                row["difficulty_code"] = expected
                updated += 1
            else:
                preserved += 1
            continue
        if current:
            preserved += 1
            continue
        if identity not in DIFFICULTY_BY_SOURCE_ID:
            raise DifficultyReviewError(f"blank difficulty has no review value: {identity}")
        row["difficulty_code"] = DIFFICULTY_BY_SOURCE_ID[identity]
        updated += 1

    if any(not (row.get("difficulty_code") or "").strip() for row in rows):
        raise DifficultyReviewError("difficulty_code remains blank after review")

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return updated, preserved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    args = parser.parse_args()
    updated, preserved = apply_review(args.catalog)
    print(f"updated={updated} preserved={preserved} total={updated + preserved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
