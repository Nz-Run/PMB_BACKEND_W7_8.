from datetime import time
from types import SimpleNamespace

from hypothesis import given, settings, strategies as st

from app.validators.krs_validators import (
    ValidationContext,
    SKSValidator,
    ConflictValidator,
)


@settings(max_examples=1000, deadline=None)
@given(
    current_sks=st.lists(
        st.integers(min_value=1, max_value=4),
        min_size=0,
        max_size=12,
    ),
    new_sks=st.integers(min_value=1, max_value=4),
)
def test_sks_never_exceeds_24(current_sks, new_sks):
    details = [
        SimpleNamespace(
            mata_kuliah=SimpleNamespace(sks=sks)
        )
        for sks in current_sks
    ]

    context = ValidationContext(
        nim="261640001",
        semester="20261",
        current_details=details,
        new_course=SimpleNamespace(sks=new_sks),
        db=None,
    )

    result = SKSValidator().check(context)
    total_sks = sum(current_sks) + new_sks

    assert result.ok == (total_sks <= 24)

    if total_sks > 24:
        assert "Maksimal 24 SKS" in result.message


@st.composite
def course_strategy(draw):
    hari = draw(st.integers(min_value=1, max_value=6))
    start_total = draw(st.integers(min_value=0, max_value=1379))

    max_duration = min(180, 1439 - start_total)
    duration = draw(
        st.integers(min_value=1, max_value=max_duration)
    )

    end_total = start_total + duration

    start_hour, start_minute = divmod(start_total, 60)
    end_hour, end_minute = divmod(end_total, 60)

    return SimpleNamespace(
        nama_mk="Mata Kuliah Uji",
        hari=hari,
        jam_mulai=time(start_hour, start_minute),
        jam_selesai=time(end_hour, end_minute),
    )


@settings(max_examples=1000, deadline=None)
@given(
    new_course=course_strategy(),
    current_courses=st.lists(
        course_strategy(),
        min_size=0,
        max_size=8,
    ),
)
def test_schedule_never_overlaps(new_course, current_courses):
    details = [
        SimpleNamespace(mata_kuliah=course)
        for course in current_courses
    ]

    context = ValidationContext(
        nim="261640001",
        semester="20261",
        current_details=details,
        new_course=new_course,
        db=None,
    )

    result = ConflictValidator().check(context)

    has_conflict = any(
        existing.hari == new_course.hari
        and new_course.jam_mulai < existing.jam_selesai
        and existing.jam_mulai < new_course.jam_selesai
        for existing in current_courses
    )

    assert result.ok == (not has_conflict)
