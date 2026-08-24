from meetup_ml.recommender import DEFAULT_WEIGHTS

from meetup_ml.recommender import recommend
from meetup_ml.schemas import Movie, Preference, GroupRecommendRequest


def test_semantic_similarity_changes_final_score():
    movie = Movie(
        internal_id="test_movie",
        title="테스트 영화",
        genres=["드라마"],
        overview="테스트용 영화",
        vote_average=5.0,
        popularity=1.0,
    )

    request = GroupRecommendRequest(
        room_id="test-room",
        round_id="test-round",
        members=[
            Preference(
                user_id="user1",
            )
        ],
        limit=1,
    )

    low = recommend(
        [movie],
        request,
        learned_scores={"user1": [0.0]},
    )

    high = recommend(
        [movie],
        request,
        learned_scores={"user1": [1.0]},
    )

    low_score = low.recommendations[0].group_score
    high_score = high.recommendations[0].group_score

    print("low_semantic_score =", low_score)
    print("high_semantic_score =", high_score)

    assert high_score > low_score
def test_semantic_weight_is_18_percent():
    assert DEFAULT_WEIGHTS["semantic"] == 0.18
    assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9