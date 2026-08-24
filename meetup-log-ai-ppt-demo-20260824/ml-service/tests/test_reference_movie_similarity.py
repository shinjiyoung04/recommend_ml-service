from meetup_ml.recommender import member_fit, reference_movie_similarity
from meetup_ml.schemas import Movie, PersonCredit, Preference


def movie(movie_id, title, genres, keywords, overview="", cast_people=None, tmdb_id=None):
    return Movie(
        internal_id=movie_id, tmdb_id=tmdb_id, title=title, genres=genres,
        keywords=keywords, overview=overview, recommendation_eligible=True,
        cast_people=cast_people or [],
    )


def test_explicitly_liked_movie_adds_explainable_similarity_score():
    reference = movie("greatest", "위대한 쇼맨", ["드라마", "음악"], ["뮤지컬", "공연", "꿈"], "공연으로 꿈을 이루는 이야기")
    similar = movie("musical", "뮤지컬 후보", ["드라마", "음악"], ["뮤지컬", "공연"], "공연 무대에서 꿈을 이루는 이야기")
    unrelated = movie("action", "액션 후보", ["액션"], ["추격"], "도시 추격전")
    pref = Preference(user_id="A", liked_movies=["greatest"])
    similar_score = member_fit(similar, pref, reference_movies=[reference])
    unrelated_score = member_fit(unrelated, pref, reference_movies=[reference])
    assert similar_score.score > unrelated_score.score
    assert similar_score.score_breakdown["reference_movie_similarity"] > 0
    assert "'위대한 쇼맨'와 유사" in similar_score.matched


def test_tmdb_original_person_name_matches_korean_and_foreign_credit():
    credit = PersonCredit(person_id=1, name="Ji Sung", original_name="지성", role="ACTOR")
    candidate = movie("m1", "지성 영화", ["드라마"], [], cast_people=[credit])
    result = member_fit(candidate, Preference(user_id="A", liked_people=["지성"]))
    assert "선호 배우/감독" in result.matched
    assert result.score > 0.8


def test_tmdb_related_movie_is_similarity_evidence():
    reference = movie("a", "기준", ["음악"], [], tmdb_id=10)
    reference.similar = [20]
    candidate = movie("b", "후보", ["음악"], [], tmdb_id=20)
    score, breakdown = reference_movie_similarity(reference, candidate)
    assert score > 0
    assert breakdown["reference_tmdb_relation"] == 1.0
