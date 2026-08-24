from datetime import datetime, timezone

from fastapi import BackgroundTasks

from meetup_ml import api
from meetup_ml.schemas import RecommendationEventCreate


class FakeDatabase:
    def __init__(self, readiness_events):
        self.readiness_events = readiness_events
        self.saved = None

    def save_recommendation_event(self, event):
        self.saved = event
        return event

    def recommendation_events(self):
        return self.readiness_events


def _event():
    return RecommendationEventCreate(
        event_id="event-test",
        room_id="room-test",
        round_id="round-test",
        user_id="user-test",
        movie_id="movie-test",
        rank_no=1,
        event_type="LIKE",
        model_version="test-model",
        payload={},
        occurred_at=datetime.now(timezone.utc),
    )


def test_auto_retrain_not_scheduled_when_not_ready(monkeypatch):
    fake_db = FakeDatabase([])

    monkeypatch.setattr(
        api,
        "database",
        fake_db,
    )

    monkeypatch.setattr(
        api,
        "feedback_readiness",
        lambda events: {
            "ready": False,
            "usable_events": 999,
        },
    )

    api.training_state["running"] = False
    api.training_state["last_trained_usable_events"] = 0

    background = BackgroundTasks()

    api.save_recommendation_event(
        _event(),
        background,
    )

    assert len(background.tasks) == 0
    assert api.training_state["last_trained_usable_events"] == 0


def test_auto_retrain_scheduled_when_threshold_reached(monkeypatch):
    fake_db = FakeDatabase([])

    monkeypatch.setattr(
        api,
        "database",
        fake_db,
    )

    monkeypatch.setattr(
        api,
        "feedback_readiness",
        lambda events: {
            "ready": True,
            "usable_events": 1000,
        },
    )

    api.training_state["running"] = False
    api.training_state["last_trained_usable_events"] = 0

    background = BackgroundTasks()

    api.save_recommendation_event(
        _event(),
        background,
    )

    assert len(background.tasks) == 1
    assert api.training_state["last_trained_usable_events"] == 1000


def test_auto_retrain_not_scheduled_before_next_500_events(monkeypatch):
    fake_db = FakeDatabase([])

    monkeypatch.setattr(
        api,
        "database",
        fake_db,
    )

    monkeypatch.setattr(
        api,
        "feedback_readiness",
        lambda events: {
            "ready": True,
            "usable_events": 1499,
        },
    )

    api.training_state["running"] = False
    api.training_state["last_trained_usable_events"] = 1000

    background = BackgroundTasks()

    api.save_recommendation_event(
        _event(),
        background,
    )

    assert len(background.tasks) == 0
    assert api.training_state["last_trained_usable_events"] == 1000


def test_auto_retrain_scheduled_at_next_500_events(monkeypatch):
    fake_db = FakeDatabase([])

    monkeypatch.setattr(
        api,
        "database",
        fake_db,
    )

    monkeypatch.setattr(
        api,
        "feedback_readiness",
        lambda events: {
            "ready": True,
            "usable_events": 1500,
        },
    )

    api.training_state["running"] = False
    api.training_state["last_trained_usable_events"] = 1000

    background = BackgroundTasks()

    api.save_recommendation_event(
        _event(),
        background,
    )

    assert len(background.tasks) == 1
    assert api.training_state["last_trained_usable_events"] == 1500


def test_auto_retrain_not_scheduled_while_training(monkeypatch):
    fake_db = FakeDatabase([])

    monkeypatch.setattr(
        api,
        "database",
        fake_db,
    )

    monkeypatch.setattr(
        api,
        "feedback_readiness",
        lambda events: {
            "ready": True,
            "usable_events": 1500,
        },
    )

    api.training_state["running"] = True
    api.training_state["last_trained_usable_events"] = 1000

    background = BackgroundTasks()

    api.save_recommendation_event(
        _event(),
        background,
    )

    assert len(background.tasks) == 0
    assert api.training_state["last_trained_usable_events"] == 1000