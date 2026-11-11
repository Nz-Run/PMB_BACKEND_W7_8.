from itertools import product

import pytest

from app.models import KRS


STATES = [
    "draft",
    "submitted",
    "approved",
    "revision",
]

ACTORS = [
    "mahasiswa",
    "dosen_pa",
]

VALID_TRANSITIONS = [
    ("draft", "submitted", "mahasiswa"),
    ("submitted", "approved", "dosen_pa"),
    ("submitted", "revision", "dosen_pa"),
    ("revision", "submitted", "mahasiswa"),
]

ALL_COMBINATIONS = list(
    product(STATES, STATES, ACTORS)
)

INVALID_TRANSITIONS = [
    combination
    for combination in ALL_COMBINATIONS
    if combination not in VALID_TRANSITIONS
]


@pytest.mark.parametrize(
    "current_status,target_status,actor",
    VALID_TRANSITIONS,
)
def test_four_valid_transitions(current_status, target_status, actor):
    krs = KRS(
        nim="261640001",
        semester="20261",
        status=current_status,
    )

    assert krs.can_transition(target_status, actor) is True

    krs.transition(target_status, actor)

    assert krs.status == target_status


@pytest.mark.parametrize(
    "current_status,target_status,actor",
    INVALID_TRANSITIONS,
)
def test_28_invalid_transitions(current_status, target_status, actor):
    krs = KRS(
        nim="261640001",
        semester="20261",
        status=current_status,
    )

    assert krs.can_transition(target_status, actor) is False

    with pytest.raises(ValueError):
        krs.transition(target_status, actor)


def test_all_combinations_are_32():
    assert len(ALL_COMBINATIONS) == 32
    assert len(VALID_TRANSITIONS) == 4
    assert len(INVALID_TRANSITIONS) == 28
