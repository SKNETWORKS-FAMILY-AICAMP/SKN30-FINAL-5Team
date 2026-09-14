from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "apply_v2_0_6_gif_content_review.py"
spec = importlib.util.spec_from_file_location("apply_v2_0_6_gif_content_review", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def review_record(identity: str, stable_code: str, **fields: str) -> dict[str, object]:
    return {
        "source_identity": identity,
        "stable_code": stable_code,
        "video_filename": f"{identity}-demo.gif",
        "fields": {
            "name_ko": fields.get("name_ko", "GIF 운동"),
            "instruction_summary_ko": "GIF 시작 자세에서 움직인 뒤 돌아옵니다.",
            "form_cues_ko": ["반동을 사용하지 않습니다.", "자세를 천천히 통제합니다."],
        },
    }


def review_payload(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "review_version": "test",
        "review_method": "DIRECT_LOCAL_GIF",
        "video_root": "data/videos",
        "content_version": "test-content-version",
        "records": records,
    }


def catalog_row(identity: str, stable_code: str) -> dict[str, str]:
    return {
        "source_identity": identity,
        "stable_code": stable_code,
        "name_ko": "기존 이름",
        "instruction_summary_ko": "기존 설명",
        "form_cues_ko": "기존 안내",
        "equipment_codes": "BODYWEIGHT",
        "instruction_content_version": "old",
        "form_cues_review_status": "OLD",
        "form_cues_source": "old-source",
    }


def test_apply_review_updates_only_permitted_fields_and_deletes_exact_target(
    tmp_path: Path,
) -> None:
    rows = [catalog_row("0001", "first"), catalog_row("0002", "second")]
    payload = review_payload(
        [
            review_record("0001", "first", name_ko="GIF 이름"),
            {
                "source_identity": "0002",
                "stable_code": "second",
                "action": "DELETE",
                "reason": "USER_REQUESTED_DELETE",
            },
        ]
    )
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(payload), encoding="utf-8")
    review, records = module.read_review(review_path)
    retained, report = module.apply_review(rows, review, records)

    assert retained == [
        {
            **catalog_row("0001", "first"),
            "name_ko": "GIF 이름",
            "instruction_summary_ko": "GIF 시작 자세에서 움직인 뒤 돌아옵니다.",
            "form_cues_ko": "반동을 사용하지 않습니다.|자세를 천천히 통제합니다.",
            "instruction_content_version": "test-content-version",
            "form_cues_review_status": "REVIEW_REQUIRED",
            "form_cues_source": "data/videos/0001-demo.gif",
        }
    ]
    assert report["deleted_records"] == [
        {
            "source_identity": "0002",
            "stable_code": "second",
            "name_ko": "기존 이름",
            "reason": "USER_REQUESTED_DELETE",
        }
    ]


def test_read_review_rejects_unapproved_field(tmp_path: Path) -> None:
    payload = review_payload([review_record("0001", "first")])
    payload["records"][0]["fields"]["training_type_code"] = "CARDIO"  # type: ignore[index]
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(module.GifReviewApplyError, match="unsupported fields"):
        module.read_review(review_path)
