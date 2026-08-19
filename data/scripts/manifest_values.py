"""Fail-closed coercion helpers for values read from JSON manifests.

`json.loads` 결과의 값 타입은 신뢰할 수 없다. 손상된 manifest에서 `int(value)`를 바로
호출하면 `TypeError`로 중단되어 파이프라인의 실패 처리 경로를 벗어난다. 이 헬퍼는
`ValueError`를 던지며, 두 파이프라인의 `PipelineError`가 `RuntimeError` 계열이라
호출부에서 각자의 오류로 변환하거나 기존 `except ValueError` 경로로 처리한다.
"""

from __future__ import annotations


def require_int(value: object, field_name: str) -> int:
    """Return value as int, or raise ValueError when the manifest field is unusable."""

    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def require_str(value: object, field_name: str) -> str:
    """Return value as str, or raise ValueError when the manifest field is unusable."""

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value
