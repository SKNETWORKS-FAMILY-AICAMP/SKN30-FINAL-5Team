import re
from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

_SOURCE_OBJECT_PATTERN = re.compile(
    r"^videos/(?P<source_identity>[0-9]{4})-(?P<identifier>[A-Za-z0-9]+)\.gif$"
)


@dataclass(frozen=True)
class MediaMappingExercise:
    exercise_id: UUID
    source_identity: str


@dataclass(frozen=True)
class MediaObjectMapping:
    exercise_id: UUID
    source_identity: str
    source_object_key: str


@dataclass(frozen=True)
class MediaMappingReport:
    target_object_count: int
    mapped_count: int
    unmatched_count: int
    duplicate_count: int
    invalid_filename_count: int
    mappings: tuple[MediaObjectMapping, ...]


def parse_source_identity(source_object_key: str) -> str | None:
    match = _SOURCE_OBJECT_PATTERN.fullmatch(source_object_key)
    if match is None:
        return None
    return match.group("source_identity")


def map_source_objects(
    source_object_keys: tuple[str, ...],
    exercises: tuple[MediaMappingExercise, ...],
) -> MediaMappingReport:
    objects_by_identity: dict[str, list[str]] = defaultdict(list)
    invalid_count = 0
    for key in source_object_keys:
        source_identity = parse_source_identity(key)
        if source_identity is None:
            invalid_count += 1
            continue
        objects_by_identity[source_identity].append(key)

    exercises_by_identity: dict[str, list[UUID]] = defaultdict(list)
    for exercise in exercises:
        exercises_by_identity[exercise.source_identity].append(exercise.exercise_id)

    duplicate_identities = {
        identity
        for identity, keys in objects_by_identity.items()
        if len(keys) > 1 or len(exercises_by_identity.get(identity, ())) > 1
    }
    mappings: list[MediaObjectMapping] = []
    unmatched_count = invalid_count
    for source_identity, keys in sorted(objects_by_identity.items()):
        if source_identity in duplicate_identities:
            continue
        exercise_ids = exercises_by_identity.get(source_identity, [])
        if len(exercise_ids) != 1:
            unmatched_count += 1
            continue
        mappings.append(
            MediaObjectMapping(
                exercise_id=exercise_ids[0],
                source_identity=source_identity,
                source_object_key=keys[0],
            )
        )

    return MediaMappingReport(
        target_object_count=len(source_object_keys),
        mapped_count=len(mappings),
        unmatched_count=unmatched_count,
        duplicate_count=len(duplicate_identities),
        invalid_filename_count=invalid_count,
        mappings=tuple(mappings),
    )


__all__ = [
    "MediaMappingExercise",
    "MediaMappingReport",
    "MediaObjectMapping",
    "map_source_objects",
    "parse_source_identity",
]
