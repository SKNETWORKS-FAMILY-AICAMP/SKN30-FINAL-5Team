from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "build_v2_0_6_backend_bundle.py"
spec = importlib.util.spec_from_file_location("build_v2_0_6_backend_bundle", SCRIPT)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = builder
spec.loader.exec_module(builder)

def test_rejects_catalog_revised_after_the_v206_fallback_approval(tmp_path: Path) -> None:
    """The v2.0.6 approval hash must not be reused for the v2.0.8 source."""

    output = tmp_path / "bundle"
    with pytest.raises(builder.BundleBuildError, match="fallback approval does not match"):
        builder.build(target=output)
    assert not output.exists()


def test_v206_fallback_rejection_is_deterministic(tmp_path: Path) -> None:
    for name in ("first", "second"):
        with pytest.raises(builder.BundleBuildError, match="fallback approval does not match"):
            builder.build(target=tmp_path / name)
