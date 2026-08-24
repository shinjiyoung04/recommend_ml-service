from meetup_ml.recommender import recommend
from meetup_ml.schemas import (
    Movie,
    Preference,
    GroupRecommendRequest,
)


def _request(pref: Preference) -> GroupRecommendRequest:
    return GroupRecommendRequest(
        room_id="grounding-test-room",
        round_id="grounding-test-round",
        members=[pref],
        limit=1,
    )


def test_recommendation_reason_is_grounded_in_member_match():
    """추천 이유는 실제 member_scores.matched 근거에서 나와야 한다."""

    movie = Movie(
        internal_id="movie_action",
        title="액션 테스트 영화",
        genres=["액션"],
        overview="액션 중심의 테스트 영화",
        vote_average=7.5,
        popularity=10.0,
    )

    pref = Preference(
        user_id="user1",
        liked_genres={
            "액션": 1.0,
        },
    )

    result = recommend(
        [movie],
        _request(pref),
    )

    recommendation = result.recommendations[0]
    member_score = recommendation.member_scores[0]

    print("matched =", member_score.matched)
    print("reasons =", recommendation.reasons)
    print("evidence_level =", recommendation.evidence_level)

    assert "액션 선호" in member_score.matched
    assert "액션 선호" in recommendation.reasons

    # 현재 추천기는 실제 matched 근거를 reasons로 승격한다.
    for reason in recommendation.reasons:
        assert reason in member_score.matched

    assert recommendation.evidence_level in {
        "MEDIUM",
        "HIGH",
    }


def test_disliked_genre_is_not_invented_as_positive_reason():
    """비선호 장르가 긍정 추천 이유로 뒤집혀서는 안 된다."""

    movie = Movie(
        internal_id="movie_mixed",
        title="복합 장르 테스트 영화",
        genres=[
            "액션",
            "공포",
        ],
        overview="액션과 공포가 섞인 테스트 영화",
        vote_average=7.0,
        popularity=8.0,
    )

    pref = Preference(
        user_id="user1",
        liked_genres={
            "액션": 1.0,
        },
        disliked_genres={
            "공포": 1.0,
        },
    )

    result = recommend(
        [movie],
        _request(pref),
    )

    recommendation = result.recommendations[0]
    member_score = recommendation.member_scores[0]

    print("matched =", member_score.matched)
    print("penalties =", member_score.penalties)
    print("reasons =", recommendation.reasons)

    assert "액션 선호" in member_score.matched

    # 사용자가 공포를 싫다고 했는데
    # "공포 선호"라는 허위 근거가 생성되면 실패.
    assert "공포 선호" not in member_score.matched
    assert "공포 선호" not in recommendation.reasons


def test_reasons_are_subset_of_actual_member_matches_when_evidence_exists():
    """근거가 존재하는 추천에서는 reasons가 실제 matched 밖에서 만들어지면 안 된다."""

    movie = Movie(
        internal_id="movie_drama",
        title="드라마 테스트 영화",
        genres=["드라마"],
        overview="인물 관계 중심의 드라마",
        vote_average=8.0,
        popularity=12.0,
    )

    pref = Preference(
        user_id="user1",
        liked_genres={
            "드라마": 0.9,
        },
    )

    result = recommend(
        [movie],
        _request(pref),
    )

    recommendation = result.recommendations[0]

    actual_matches = {
        matched
        for score in recommendation.member_scores
        for matched in score.matched
    }

    print("actual_matches =", actual_matches)
    print("reasons =", recommendation.reasons)

    assert actual_matches

    for reason in recommendation.reasons:
        assert reason in actual_matches


def test_no_preference_evidence_uses_low_evidence_fallback():
    """실제 선호 근거가 없으면 근거를 꾸며내지 않고 LOW evidence를 사용한다."""

    movie = Movie(
        internal_id="movie_no_evidence",
        title="근거 없음 테스트 영화",
        genres=["드라마"],
        overview="추천 근거 fallback 검증용 영화",
        vote_average=7.8,
        popularity=15.0,
    )

    pref = Preference(
        user_id="user1",
    )

    result = recommend(
        [movie],
        _request(pref),
    )

    recommendation = result.recommendations[0]
    member_score = recommendation.member_scores[0]

    print("matched =", member_score.matched)
    print("reasons =", recommendation.reasons)
    print("evidence_level =", recommendation.evidence_level)

    assert member_score.matched == []
    assert recommendation.evidence_level == "LOW"

    # 사용자 선호 근거가 없는데 특정 취향을 만들어내면 안 된다.
    assert all(
        "선호" not in reason
        for reason in recommendation.reasons
    )

    assert any(
        "평점" in reason
        or "인기도" in reason
        for reason in recommendation.reasons
    )