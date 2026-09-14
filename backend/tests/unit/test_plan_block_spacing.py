"""A movement split across blocks must be spread through the session.

`_subsets` builds a split candidate as adjacent blocks, so two deadlift blocks
arrived next to each other and the session read as one long deadlift rather than
a sequence. The V3 path already refuses that shape through
`has_consecutive_main_repetition`; the base-routine composer had no such rule.
"""

from __future__ import annotations

from backend.app.domain.rules.plan_shape import (
    has_adjacent_duplicate,
    space_repeated_blocks,
)


def _ids(blocks: tuple[str, ...]) -> str:
    return "".join(blocks)


def test_a_split_movement_is_separated_by_the_others() -> None:
    # Deadlift twice, arriving adjacent the way _subsets builds it.
    spaced = space_repeated_blocks(("D", "D", "G", "S"), key=lambda block: block)

    assert not has_adjacent_duplicate(spaced, key=lambda block: block)
    assert sorted(spaced) == ["D", "D", "G", "S"]


def test_order_is_left_alone_when_nothing_repeats_adjacently() -> None:
    original = ("D", "G", "S", "D")

    assert space_repeated_blocks(original, key=lambda block: block) == original


def test_every_block_survives_the_reordering() -> None:
    original = ("D", "D", "D", "G", "G", "S")

    spaced = space_repeated_blocks(original, key=lambda block: block)

    assert sorted(spaced) == sorted(original)
    assert not has_adjacent_duplicate(spaced, key=lambda block: block)


def test_a_movement_with_no_room_to_separate_still_yields_every_block() -> None:
    # Three of one movement and one of another cannot be fully separated. The
    # plan must still contain every block rather than being refused.
    original = ("D", "D", "D", "G")

    spaced = space_repeated_blocks(original, key=lambda block: block)

    assert sorted(spaced) == sorted(original)
    # The unavoidable repeat is pushed to the end rather than left at the front.
    assert _ids(spaced).startswith("DGD")


def test_repeated_blocks_keep_their_own_relative_order() -> None:
    # Blocks carry a prescribed sequence, so a split must not be shuffled
    # against itself even while it is spread apart.
    original = (("D", 1), ("D", 2), ("G", 1), ("S", 1))

    spaced = space_repeated_blocks(original, key=lambda block: block[0])

    deadlifts = [block for block in spaced if block[0] == "D"]
    assert deadlifts == [("D", 1), ("D", 2)]


def test_adjacent_duplicate_detection_reads_neighbours_only() -> None:
    key = lambda block: block  # noqa: E731

    assert has_adjacent_duplicate(("D", "D", "G"), key=key)
    assert not has_adjacent_duplicate(("D", "G", "D"), key=key)
    assert not has_adjacent_duplicate((), key=key)
    assert not has_adjacent_duplicate(("D",), key=key)
