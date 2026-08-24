import numpy as np

import meetup_ml.api as api_module
from meetup_ml.database import MeetupDatabase
from meetup_ml.models import ModelBundle
from meetup_ml.schemas import ChatAnalyzeResponse, Movie


def test_api_module_imports_without_running_room_analysis():
    assert api_module.app.title == "MeetupLog Recommendation API"


def test_room_analysis_runs_once_for_only_the_pending_tail(tmp_path, monkeypatch):
    database = MeetupDatabase(tmp_path / "incremental.db")
    for index in range(1, 21):
        database.add_message("room", "user", f"액션 영화 {index}")
    database.save_analysis_checkpoint("room", 19)

    calls = []
    saves = []

    def fake_analyze(messages, movies, room_id, enrichment_message_ids=None):
        calls.append((messages, enrichment_message_ids))
        return ChatAnalyzeResponse(members=[], analyses=[])

    original_save = database.save_preferences

    def save_once(room_id, members):
        saves.append((room_id, members))
        return original_save(room_id, members)

    monkeypatch.setattr(api_module, "database", database)
    monkeypatch.setattr(api_module.store, "load_movies", lambda: [])
    monkeypatch.setattr(api_module, "_analyze_corrected", fake_analyze)
    monkeypatch.setattr(database, "save_preferences", save_once)

    response = api_module._room_analysis("room")

    assert len(calls) == 1
    assert len(calls[0][0]) == 13
    assert calls[0][1] == {20}
    assert len(saves) == 1
    assert response["analysis"] == {
        "mode": "INCREMENTAL",
        "processed": 1,
        "last_message_id": 20,
    }


def test_ai_only_pending_message_advances_checkpoint_without_analysis(
    tmp_path,
    monkeypatch,
):
    database = MeetupDatabase(tmp_path / "ai-only.db")
    database.add_message("room", "AI", "추천 결과입니다")

    monkeypatch.setattr(api_module, "database", database)
    monkeypatch.setattr(api_module.store, "load_movies", lambda: [])

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("AI messages must not invoke preference analysis")

    monkeypatch.setattr(api_module, "_analyze_corrected", fail_if_called)

    response = api_module._room_analysis("room")

    assert response["analysis"] == {
        "mode": "INCREMENTAL",
        "processed": 0,
        "last_message_id": 1,
    }


def test_sqlite_database_releases_its_file(tmp_path):
    path = tmp_path / "releasable.db"
    database = MeetupDatabase(path)
    database.add_message("room", "user", "액션 좋아")

    path.unlink()

    assert not path.exists()


def test_learned_model_is_bound_to_catalog_order():
    movies = [
        Movie(internal_id="m1", title="첫 영화"),
        Movie(internal_id="m2", title="둘째 영화"),
    ]
    bundle = ModelBundle()
    bundle.matrix = np.ones((2, 2), dtype=np.float32)
    bundle.catalog_ids = [movie.internal_id for movie in movies]
    bundle.catalog_sha256 = bundle._catalog_digest(movies)

    assert bundle.matches_catalog(movies)
    assert not bundle.matches_catalog(list(reversed(movies)))
    changed = movies[0].model_copy(update={"genres": ["액션"]})
    assert not bundle.matches_catalog([changed, movies[1]])


def test_model_bundle_trains_a_compact_catalog_bound_matrix():
    movies = [
        Movie(
            internal_id=f"m{index}",
            title=f"영화 {index}",
            overview=f"서로 다른 평가 문서 {index}",
            genres=["드라마" if index % 2 else "액션"],
            keywords=[f"키워드{index}"],
            release_date=f"202{index}-01-01",
        )
        for index in range(1, 5)
    ]
    bundle = ModelBundle()

    report = bundle.fit(movies)

    assert bundle.matches_catalog(movies)
    assert bundle.matrix.shape == (4, 3)
    assert report["model_feature_dimensions"] == 3
    assert report["source_feature_dimensions"] > 3


def test_person_identity_readiness_requires_real_structured_ids():
    movies = [Movie(internal_id="m1", title="이름만", cast=["배우 A"])]

    readiness = api_module._person_identity_readiness(movies)

    assert readiness == {
        "structured_credits": 0,
        "identified_credits": 0,
        "id_coverage": 0.0,
        "production_ready": False,
    }
