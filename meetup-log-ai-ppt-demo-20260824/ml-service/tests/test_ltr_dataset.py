from datetime import datetime, timezone

from meetup_ml.ltr_dataset import (
    build_ltr_rows,
    summarize_ltr_rows,
)
from meetup_ml.schemas import RecommendationEvent


def _event(
    event_id: str,
    event_type: str,
    movie_id: str,
    user_id: str = "user1",
):
    return RecommendationEvent(
        id=1,
        event_id=event_id,
        room_id="room1",
        round_id="round1",
        user_id=user_id,
        movie_id=movie_id,
        rank_no=1,
        event_type=event_type,
        model_version="test-model",
        payload={},
        occurred_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )


def _history():
    return [
        {
            "room_id": "room1",
            "round_id": "round1",
            "movie_id": "movie_select",
            "movie_title": "선택 영화",
            "rank_no": 1,
            "group_score": 0.91,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "room_id": "room1",
            "round_id": "round1",
            "movie_id": "movie_like",
            "movie_title": "좋아요 영화",
            "rank_no": 2,
            "group_score": 0.82,
            "created_at": datetime.now(timezone.utc),
        },
        {
            "room_id": "room1",
            "round_id": "round1",
            "movie_id": "movie_dislike",
            "movie_title": "싫어요 영화",
            "rank_no": 3,
            "group_score": 0.73,
            "created_at": datetime.now(timezone.utc),
        },
    ]


def test_feedback_events_are_converted_to_ltr_labels():
    events = [
        _event("e1", "SELECT", "movie_select"),
        _event("e2", "LIKE", "movie_like"),
        _event("e3", "DISLIKE", "movie_dislike"),
    ]

    rows = build_ltr_rows(
        _history(),
        events,
    )

    by_movie = {
        row.movie_id: row
        for row in rows
    }

    assert len(rows) == 3

    assert by_movie["movie_select"].label == 3.0
    assert by_movie["movie_like"].label == 2.0
    assert by_movie["movie_dislike"].label == -2.0


def test_impression_is_not_used_as_preference_label():
    events = [
        _event(
            "e1",
            "IMPRESSION",
            "movie_select",
        ),
    ]

    rows = build_ltr_rows(
        _history(),
        events,
    )

    assert rows == []


def test_event_without_recommendation_history_is_excluded():
    events = [
        _event(
            "e1",
            "LIKE",
            "movie_not_recommended",
        ),
    ]

    rows = build_ltr_rows(
        _history(),
        events,
    )

    assert rows == []


def test_stronger_event_wins_for_same_user_movie():
    events = [
        _event(
            "e1",
            "CLICK",
            "movie_select",
        ),
        _event(
            "e2",
            "LIKE",
            "movie_select",
        ),
        _event(
            "e3",
            "SELECT",
            "movie_select",
        ),
    ]

    rows = build_ltr_rows(
        _history(),
        events,
    )

    assert len(rows) == 1
    assert rows[0].event_type == "SELECT"
    assert rows[0].label == 3.0


def test_ltr_summary_counts_positive_and_negative_rows():
    events = [
        _event("e1", "SELECT", "movie_select"),
        _event("e2", "LIKE", "movie_like"),
        _event("e3", "DISLIKE", "movie_dislike"),
    ]

    rows = build_ltr_rows(
        _history(),
        events,
    )

    summary = summarize_ltr_rows(rows)

    assert summary["rows"] == 3
    assert summary["rounds"] == 1
    assert summary["users"] == 1
    assert summary["positive_rows"] == 2
    assert summary["negative_rows"] == 1
    assert summary["event_counts"]["SELECT"] == 1
    assert summary["event_counts"]["LIKE"] == 1
    assert summary["event_counts"]["DISLIKE"] == 1