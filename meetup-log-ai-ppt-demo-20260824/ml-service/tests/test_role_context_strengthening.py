import pytest

from meetup_ml.chat_analysis import analyze_chat
from meetup_ml.collectors import apply_tmdb_person_credits
from meetup_ml.recommender import member_fit, recommend
from meetup_ml.schemas import (
    ChatAnalyzeRequest,
    GroupRecommendRequest,
    Movie,
    PersonCredit,
    PersonPreference,
    Preference,
)


ACTOR = PersonCredit(
    person_id=101,
    name="Song Kang-ho",
    original_name="송강호",
    role="ACTOR",
)
DIRECTOR = PersonCredit(
    person_id=202,
    name="Bong Joon-ho",
    original_name="봉준호",
    role="DIRECTOR",
)


def _movie(
    movie_id: str,
    *,
    cast_people: list[PersonCredit] | None = None,
    director_people: list[PersonCredit] | None = None,
    runtime: int = 110,
) -> Movie:
    return Movie(
        internal_id=movie_id,
        title=f"영화 {movie_id}",
        genres=["드라마"],
        overview="같은 조건의 평가용 영화",
        cast_people=cast_people or [],
        director_people=director_people or [],
        runtime=runtime,
        vote_average=7.0,
        vote_count=100,
        popularity=10.0,
        recommendation_eligible=True,
    )


def _member(result, user_id: str) -> Preference:
    return next(member for member in result.members if member.user_id == user_id)


def test_chat_resolves_actor_and_director_to_role_specific_tmdb_ids():
    movies = [_movie("credit", cast_people=[ACTOR], director_people=[DIRECTOR])]
    result = analyze_chat(
        ChatAnalyzeRequest(messages=[
            {"user_id": "A", "text": "송강호 배우 좋아"},
            {"user_id": "A", "text": "봉준호 감독은 별로야"},
        ]),
        movies,
    )
    member = _member(result, "A")

    assert [(person.person_id, person.role) for person in member.liked_actors] == [(101, "ACTOR")]
    assert [(person.person_id, person.role) for person in member.disliked_directors] == [(202, "DIRECTOR")]
    assert member.liked_directors == []
    assert member.disliked_actors == []


def test_existing_catalog_movie_can_be_backfilled_with_tmdb_person_ids():
    movie = _movie("legacy")
    movie.cast = ["송강호"]
    movie.directors = ["봉준호"]

    changed = apply_tmdb_person_credits(movie, {
        "cast": [
            {"id": 101, "name": "Song Kang-ho", "original_name": "송강호"},
        ],
        "crew": [
            {"id": 202, "name": "Bong Joon-ho", "original_name": "봉준호", "job": "Director"},
        ],
    })

    assert changed is True
    assert [(person.person_id, person.role) for person in movie.cast_people] == [(101, "ACTOR")]
    assert [(person.person_id, person.role) for person in movie.director_people] == [(202, "DIRECTOR")]


def test_person_id_and_role_control_scoring_without_name_collision():
    actor_movie = _movie("actor", cast_people=[ACTOR])
    director_movie = _movie("director", director_people=[DIRECTOR])
    neutral_movie = _movie("neutral")
    preference = Preference(
        user_id="A",
        liked_actors=[PersonPreference(
            person_id=101,
            name="송강호",
            role="ACTOR",
        )],
        disliked_directors=[PersonPreference(
            person_id=202,
            name="봉준호",
            role="DIRECTOR",
        )],
    )

    actor_score = member_fit(actor_movie, preference)
    director_score = member_fit(director_movie, preference)
    neutral_score = member_fit(neutral_movie, preference)

    assert actor_score.score > neutral_score.score
    assert director_score.score < neutral_score.score
    assert actor_score.score_breakdown["liked_actors"] > 0
    assert director_score.score_breakdown["disliked_directors"] < 0
    assert "선호 배우: 송강호" in actor_score.matched
    assert "비선호 감독: 봉준호" in director_score.penalties


def test_same_person_id_in_the_wrong_role_does_not_match():
    directing_credit = PersonCredit(
        person_id=101,
        name="Song Kang-ho",
        original_name="송강호",
        role="DIRECTOR",
    )
    movie = _movie("wrong-role", director_people=[directing_credit])
    preference = Preference(
        user_id="A",
        liked_actors=[PersonPreference(
            person_id=101,
            name="송강호",
            role="ACTOR",
        )],
    )

    result = member_fit(movie, preference)
    assert result.score_breakdown["liked_actors"] == 0
    assert not any(reason.startswith("선호 배우:") for reason in result.matched)


@pytest.mark.parametrize("reply", ["동의", "인정", "찬성", "그건 인정", "맞지", "그러게", "+1", "ㅇㅈ"])
def test_positive_agreement_variants_inherit_role_aware_person(reply: str):
    movies = [_movie("credit", cast_people=[ACTOR])]
    result = analyze_chat(
        ChatAnalyzeRequest(messages=[
            {"message_id": 1, "user_id": "A", "text": "송강호 배우 좋아"},
            {"message_id": 2, "user_id": "B", "text": reply},
        ]),
        movies,
    )
    inherited = _member(result, "B").liked_actors
    assert [(person.person_id, person.role) for person in inherited] == [(101, "ACTOR")]


def test_negated_agreement_inverts_the_inherited_preference():
    result = analyze_chat(
        ChatAnalyzeRequest(messages=[
            {"message_id": 1, "user_id": "A", "text": "액션 좋아"},
            {"message_id": 2, "user_id": "B", "text": "동의 못 해"},
        ]),
        [],
    )
    member = _member(result, "B")
    assert "액션" in member.disliked_genres
    assert "액션" not in member.liked_genres


def test_me_too_with_explicit_negative_polarity_keeps_target_and_changes_sign():
    movies = [_movie("credit", director_people=[DIRECTOR])]
    result = analyze_chat(
        ChatAnalyzeRequest(messages=[
            {"message_id": 1, "user_id": "A", "text": "봉준호 감독 좋아"},
            {"message_id": 2, "user_id": "B", "text": "나도 싫어"},
        ]),
        movies,
    )
    member = _member(result, "B")
    assert [(person.person_id, person.role) for person in member.disliked_directors] == [(202, "DIRECTOR")]
    assert member.liked_directors == []


def test_english_middle_initial_person_is_detected_and_inherited():
    actor = PersonCredit(
        person_id=2231,
        name="사무엘 L. 잭슨",
        original_name="Samuel L. Jackson",
        role="ACTOR",
    )
    movies = [_movie("initial", cast_people=[actor])]
    result = analyze_chat(
        ChatAnalyzeRequest(messages=[
            {"message_id": 1, "user_id": "A", "text": "Samuel L. Jackson 배우 좋아"},
            {"message_id": 2, "user_id": "B", "text": "나도"},
        ]),
        movies,
    )

    inherited = _member(result, "B").liked_actors
    assert [(person.person_id, person.role) for person in inherited] == [(2231, "ACTOR")]


def test_three_cards_are_backfilled_when_soft_watch_filters_are_too_narrow():
    movies = [_movie(str(index)) for index in range(5)]
    request = GroupRecommendRequest(
        room_id="room",
        round_id="round",
        members=[Preference(user_id="A")],
        allowed_providers=[999999],
        include_unknown_watch_path=False,
        limit=3,
    )

    result = recommend(movies, request)
    ids = [item.movie.internal_id for item in result.recommendations]
    assert len(ids) == 3
    assert len(set(ids)) == 3
    assert all(
        "시청 경로 조건을 완화해 3편 구성" in item.reasons
        for item in result.recommendations
    )


def test_three_card_backfill_never_breaks_member_hard_exclusions():
    movies = [
        _movie("too-long", runtime=190),
        _movie("one"),
        _movie("two"),
        _movie("three"),
        _movie("four"),
    ]
    request = GroupRecommendRequest(
        room_id="room",
        round_id="round",
        members=[Preference(user_id="A", max_runtime=120)],
        allowed_providers=[999999],
        include_unknown_watch_path=False,
        limit=3,
    )

    result = recommend(movies, request)
    ids = {item.movie.internal_id for item in result.recommendations}
    assert len(ids) == 3
    assert "too-long" not in ids
