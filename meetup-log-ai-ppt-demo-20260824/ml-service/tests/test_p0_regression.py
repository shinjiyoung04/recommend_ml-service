from meetup_ml.chat_analysis import analyze_chat
from meetup_ml.schemas import ChatAnalyzeRequest


def analyze(messages):
    return analyze_chat(ChatAnalyzeRequest(messages=messages), [])


def member(result, user_id):
    return next(value for value in result.members if value.user_id == user_id)


def test_negative_animation_is_not_flipped():
    result = analyze([{"user_id": "A", "text": "애니메이션은 보고 싶지 않아"}])
    pref = member(result, "A")
    assert "애니메이션" not in pref.liked_genres
    assert "애니메이션" in pref.disliked_genres


def test_comparative_genres_are_both_saved():
    result = analyze([{"user_id": "A", "text": "액션보단 로맨스가 좋아"}])
    pref = member(result, "A")
    assert "액션" in pref.disliked_genres
    assert "로맨스" in pref.liked_genres


def test_nine_members_are_isolated():
    genres = ["액션", "로맨스", "코미디", "공포", "SF", "드라마", "애니메이션", "범죄", "판타지"]
    result = analyze([
        {"user_id": f"user-{index}", "text": f"나는 {genre} 좋아"}
        for index, genre in enumerate(genres)
    ])
    assert len(result.members) == 9
    for index, genre in enumerate(genres):
        pref = member(result, f"user-{index}")
        assert genre in pref.liked_genres


def test_people_and_runtime():
    result = analyze([
        {"user_id": "A", "text": "류준열 나오는 영화 보고 싶어"},
        {"user_id": "A", "text": "혜리 나오는 영화는 별로야"},
        {"user_id": "A", "text": "두시간 안넘는 영화로 보자"},
    ])
    pref = member(result, "A")
    assert "류준열" in pref.liked_people
    assert "혜리" in pref.disliked_people
    assert pref.max_runtime == 120
