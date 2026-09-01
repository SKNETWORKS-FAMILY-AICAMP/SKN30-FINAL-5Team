"""The stable code shape has to admit v2.0.2 derived records and nothing looser.

v2.0.2 names a pain-area safe variant after the exercise it was derived from,
separated by a double underscore. The identifier contract was written before
derived records existed and rejected them.
"""

import pytest
from pydantic import BaseModel, ValidationError

from backend.app.modules.catalog.schemas import StableCode


class _Code(BaseModel):
    stable_code: StableCode


@pytest.mark.parametrize(
    "value",
    [
        "glute_bridge",
        "abs_core_brace_core_brace_mat",
        # The shape v2.0.2 uses for a derived safe variant.
        "one_arm_wall_lats_isolation_bodyweight__knee_no_load_safe_v1",
    ],
)
def test_accepts_catalog_and_derived_codes(value: str) -> None:
    assert _Code(stable_code=value).stable_code == value


@pytest.mark.parametrize(
    "value",
    [
        "_leading",
        "trailing_",
        "Upper_Case",
        "double__",
        "__leading_double",
        # Widening the separator must not open the door to arbitrary runs.
        "three___underscores",
        "spaced code",
    ],
)
def test_rejects_malformed_codes(value: str) -> None:
    with pytest.raises(ValidationError):
        _Code(stable_code=value)
