from fastapi.testclient import TestClient

import meetup_ml.api as api_module
from meetup_ml.api import app
from meetup_ml.database import MeetupDatabase
from meetup_ml.preference_interface import build_preference_deltas
from meetup_ml.schemas import Preference


def test_preference_deltas_include_upsert_remove_and_source():
    before = [Preference(user_id="A", liked_genres={"Action": .8}, max_runtime=120)]
    after = [Preference(user_id="A", disliked_genres={"Horror": .7})]
    deltas = build_preference_deltas(before, after, "message-2")
    keys = {(item.target_type, item.target_value, item.operation): item for item in deltas}

    assert ("GENRE", "Action", "REMOVE") in keys
    assert keys[("GENRE", "Horror", "UPSERT")].score == -.7
    assert ("CONSTRAINT", "max_runtime:LTE", "REMOVE") in keys
    assert all(item.source_message_id == "message-2" for item in deltas)


def test_message_idempotency_and_state_version(tmp_path, monkeypatch):
    database = MeetupDatabase(tmp_path / "interface.db")
    monkeypatch.setattr(api_module, "database", database)
    client = TestClient(app)
    payload = {
        "room_id": "room-interface",
        "round_id": "round-1",
        "user_id": "A",
        "text": "액션 영화 좋아",
        "idempotency_key": "message-100",
    }

    first = client.post("/v1/chat/messages", json=payload)
    duplicate = client.post("/v1/chat/messages", json=payload)

    assert first.status_code == 200
    assert first.json()["state_version"] == 1
    assert duplicate.status_code == 200
    assert duplicate.json()["processing_status"] == "DUPLICATE"
    assert duplicate.json()["state_version"] == 1
    assert len(database.messages("room-interface")) == 1


def test_stale_room_state_is_rejected(tmp_path, monkeypatch):
    database = MeetupDatabase(tmp_path / "stale.db")
    monkeypatch.setattr(api_module, "database", database)
    database.add_message("room-state", "A", "액션 영화 좋아", idempotency_key="m-1")
    database.save_preferences("room-state", [Preference(user_id="A", liked_genres={"Action": .8})])
    response = TestClient(app).post(
        "/v1/chat/rooms/room-state/recommendations",
        json={"round_id": "r-1", "expected_state_version": 0},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "STALE_PREFERENCE_STATE"
