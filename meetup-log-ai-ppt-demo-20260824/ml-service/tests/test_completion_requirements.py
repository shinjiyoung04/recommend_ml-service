import hashlib
import json

import joblib
import numpy as np

from meetup_ml.chat_analysis import analyze_chat
from meetup_ml.deployment import activate_model
from meetup_ml.schemas import ChatAnalyzeRequest, Movie, Preference
from meetup_ml.semantic import SemanticPreferenceEngine


class FakeEncoder:
    def encode(self, texts, **_):
        return np.asarray([[1.0, 0.0] for _ in texts], dtype=np.float32)


def test_precomputed_embeddings_are_loaded_and_catalog_additions_are_encoded(tmp_path):
    movies = [Movie(internal_id="m1", title="첫 영화"), Movie(internal_id="m2", title="새 영화")]
    vectors = np.asarray([[0.0, 1.0]], dtype=np.float32)
    vector_path = tmp_path / "movie_embeddings.npy"
    np.save(vector_path, vectors)
    digest = hashlib.sha256(vector_path.read_bytes()).hexdigest()
    (tmp_path / "catalog_manifest.json").write_text(json.dumps({
        "catalog_sha256": "fixed", "ordered_movie_ids": ["m1"]
    }), encoding="utf-8")
    (tmp_path / "movie_embeddings_meta.json").write_text(json.dumps({
        "catalog_sha256": "fixed", "model_name": "fake", "movie_count": 1,
        "embedding_dimension": 2, "embeddings_sha256": digest,
    }), encoding="utf-8")
    engine = SemanticPreferenceEngine("fake", precomputed_dir=tmp_path)
    engine._encoder = FakeEncoder()
    result = engine.score(movies, [Preference(user_id="u", liked_genres={"액션": 1.0})])
    assert result.backend == "sentence-transformers-precomputed"
    assert engine._movie_vectors.tolist() == [[0.0, 1.0], [1.0, 0.0]]


def test_multiple_otts_and_full_me_too_inheritance():
    result = analyze_chat(ChatAnalyzeRequest(messages=[
        {"user_id": "u1", "text": "넷플릭스랑 티빙에서 볼 액션이나 코미디 좋아"},
        {"user_id": "u2", "text": "나도"},
    ]), [])
    first, second = result.members
    assert first.ott_platforms == ["넷플릭스", "티빙"]
    assert second.ott_platforms == first.ott_platforms
    assert second.liked_genres == first.liked_genres


def test_over_two_hours_dislike_is_maximum_not_minimum():
    result = analyze_chat(ChatAnalyzeRequest(messages=[
        {"user_id": "u", "text": "2시간 이상은 싫어"},
    ]), [])
    member = result.members[0]
    assert member.max_runtime == 120
    assert member.min_runtime is None


class Bundle:
    def __init__(self, matrix):
        self.matrix = matrix

    def save(self, path):
        joblib.dump(self, path)


def test_failed_activation_keeps_current_model(tmp_path):
    activate_model(Bundle(np.ones((1, 1))), tmp_path)
    try:
        activate_model(Bundle(None), tmp_path)
    except ValueError:
        pass
    assert joblib.load(tmp_path / "current.joblib").matrix.tolist() == [[1.0]]
