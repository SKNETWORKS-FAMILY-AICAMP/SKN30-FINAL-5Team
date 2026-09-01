"""Bootstrap the permanent integrated catalog ID registry from a review CSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from integrated_catalog_registry import REGISTRY_PATH, bootstrap_registry


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--out", type=Path, default=REGISTRY_PATH)
    args = parser.parse_args()
    rows = load_rows(args.input_csv)
    bootstrap_registry(rows, output_path=args.out)
    print(args.out)


if __name__ == "__main__":
    main()
