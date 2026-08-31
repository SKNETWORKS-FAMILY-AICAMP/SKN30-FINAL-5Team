from uuid import UUID

from backend.app.modules.catalog.media_mapping import (
    MediaMappingExercise,
    map_source_objects,
    parse_source_identity,
)


def test_filename_parser_preserves_four_digit_source_identity() -> None:
    assert parse_source_identity("videos/0073-i6LWJok.gif") == "0073"
    assert parse_source_identity("videos/0001-a.gif") == "0001"


def test_filename_parser_rejects_wrong_prefix_shape_and_extension() -> None:
    assert parse_source_identity("images/0073-i6LWJok.gif") is None
    assert parse_source_identity("videos/073-i6LWJok.gif") is None
    assert parse_source_identity("videos/0073-i6LWJok.jpg") is None
    assert parse_source_identity("videos/0073-i6LWJok.GIF") is None
    assert parse_source_identity("videos/0073-.gif") is None


def test_mapping_uses_only_source_identity_and_hides_unmatched_objects() -> None:
    exercise_id = UUID("00730000-0000-0000-0000-000000000001")
    report = map_source_objects(
        (
            "videos/0073-i6LWJok.gif",
            "videos/0082-LsZkfU6.gif",
            f"videos/{exercise_id}.gif",
        ),
        (MediaMappingExercise(exercise_id=exercise_id, source_identity="0073"),),
    )

    assert report.mapped_count == 1
    assert report.unmatched_count == 2
    assert report.mappings[0].exercise_id == exercise_id
    assert report.mappings[0].source_identity == "0073"


def test_duplicate_object_prefix_or_exercise_identity_fails_closed() -> None:
    first = UUID(int=1)
    second = UUID(int=2)
    report = map_source_objects(
        (
            "videos/0073-first.gif",
            "videos/0073-second.gif",
            "videos/0082-only.gif",
        ),
        (
            MediaMappingExercise(exercise_id=first, source_identity="0073"),
            MediaMappingExercise(exercise_id=first, source_identity="0082"),
            MediaMappingExercise(exercise_id=second, source_identity="0082"),
        ),
    )

    assert report.mapped_count == 0
    assert report.duplicate_count > 0
    assert report.mappings == ()
