from meetup_ml.chat_analysis import _apply_effect


def test_runtime_effect_extracts_minutes_from_display_text():
    state = {"max_runtime": None, "min_runtime": None}

    displayed = _apply_effect(
        state,
        ("CONSTRAINT", "상영시간은 120분 정도", 0.8, "LIKE"),
        [],
    )

    assert displayed == "상영시간은 120분 정도"
    assert state["max_runtime"] == 120


def test_invalid_runtime_effect_does_not_crash_or_change_state():
    state = {"max_runtime": None, "min_runtime": None}

    displayed = _apply_effect(
        state,
        ("CONSTRAINT", "상영시간 조건", 0.8, "LIKE"),
        [],
    )

    assert displayed == "상영시간 조건"
    assert state["max_runtime"] is None
