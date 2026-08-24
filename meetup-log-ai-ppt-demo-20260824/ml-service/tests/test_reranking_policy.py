from meetup_ml.recommender import rerank_candidates
from meetup_ml.schemas import (
    MemberScore,
    Movie,
    Recommendation,
)


def _recommendation(
    movie_id: str,
    title: str,
    genres: list[str],
    score: float,
    popularity: float = 0.0,
    release_date: str | None = None,
) -> Recommendation:
    return Recommendation(
        movie=Movie(
            internal_id=movie_id,
            title=title,
            genres=genres,
            popularity=popularity,
            release_date=release_date,
        ),
        group_score=score,
        member_scores=[
            MemberScore(
                user_id="user1",
                score=score,
                matched=[],
                penalties=[],
            )
        ],
        reasons=[],
        evidence_level="LOW",
        watch_path_status="UNKNOWN",
    )


def test_diversity_can_promote_different_genre():
    candidates = [
        _recommendation(
            "action1",
            "액션 1",
            ["액션"],
            0.90,
        ),
        _recommendation(
            "action2",
            "액션 2",
            ["액션"],
            0.87,
        ),
        _recommendation(
            "drama1",
            "드라마 1",
            ["드라마"],
            0.84,
        ),
    ]

    result = rerank_candidates(
        candidates,
        limit=2,
    )

    assert result[0].movie.internal_id == "action1"
    assert result[1].movie.internal_id == "drama1"


def test_recent_movie_gets_small_exposure_boost():
    candidates = [
        _recommendation(
            "old_movie",
            "기존 영화",
            ["드라마"],
            0.80,
            release_date="2018-01-01",
        ),
        _recommendation(
            "recent_movie",
            "신작 영화",
            ["스릴러"],
            0.79,
            release_date="2026-01-01",
        ),
    ]

    result = rerank_candidates(
        candidates,
        limit=1,
    )

    assert result[0].movie.internal_id == "recent_movie"


def test_high_score_is_not_destroyed_by_reranking():
    candidates = [
        _recommendation(
            "strong",
            "압도적 후보",
            ["액션"],
            0.98,
            popularity=100.0,
        ),
        _recommendation(
            "weak",
            "낮은 후보",
            ["드라마"],
            0.60,
            popularity=1.0,
        ),
    ]

    result = rerank_candidates(
        candidates,
        limit=1,
    )

    assert result[0].movie.internal_id == "strong"


def test_direct_movie_is_protected():
    candidates = [
        _recommendation(
            "normal",
            "일반 후보",
            ["드라마"],
            0.90,
        ),
        _recommendation(
            "direct",
            "직접 지목 후보",
            ["액션"],
            0.75,
        ),
    ]

    result = rerank_candidates(
        candidates,
        limit=1,
        direct_movie_ids={"direct"},
    )

    assert result[0].movie.internal_id == "direct"


def test_popularity_penalty_can_reduce_popularity_bias():
    candidates = [
        _recommendation(
            "popular",
            "초인기 영화",
            ["액션"],
            0.82,
            popularity=100.0,
        ),
        _recommendation(
            "less_popular",
            "덜 알려진 영화",
            ["스릴러"],
            0.81,
            popularity=5.0,
        ),
    ]

    result = rerank_candidates(
        candidates,
        limit=1,
    )

    assert result[0].movie.internal_id == "less_popular"