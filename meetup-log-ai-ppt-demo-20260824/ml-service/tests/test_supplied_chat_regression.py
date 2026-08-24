from pathlib import Path

from meetup_ml.chat_analysis import analyze_chat
from meetup_ml.schemas import ChatAnalyzeRequest, ChatMessage
from meetup_ml.storage import JsonStore


def test_supplied_multi_user_chat_keeps_distinct_meanings():
    movies = JsonStore(Path("data")).load_movies(use_fixture=False)
    messages = [
        (416, "A", "나 넷플릭스랑 티빙 가입함"),
        (417, "B", "나도"),
        (418, "A", "어제 원더우먼 봤는데 비슷한 영화로 또 보고 싶음"),
        (419, "B", "원더우먼 재미있는데 나 많이 봐서 다른거 보고 싶음"),
        (420, "A", "그럼 마블이면 다 좋을 듯"),
        (421, "B", "이번에 개봉한 스파이더맨 봄?"),
        (422, "A", "이미 봄"),
        (423, "A", "젠데이아는 좋지만 톨홀랜드는 별로"),
        (424, "B", "류준열 나오는 영화 보고 싶다."),
    ]

    result = analyze_chat(
        ChatAnalyzeRequest(
            messages=[
                ChatMessage(message_id=message_id, user_id=user_id, text=text)
                for message_id, user_id, text in messages
            ]
        ),
        movies,
    )
    members = {member.user_id: member for member in result.members}

    assert set(members["A"].ott_platforms) == {"넷플릭스", "티빙"}
    assert set(members["B"].ott_platforms) == {"넷플릭스", "티빙"}
    assert members["B"].seen_movies

    assert "젠데이아" in members["A"].liked_people
    assert "톰 홀랜드" in members["A"].disliked_people
    assert "류준열" in members["B"].liked_people

    question = next(item for item in result.analyses if item.text.endswith("봄?"))
    assert question.user_id == "B"
    assert question.attitude == "QUESTION"

    observed = next(item for item in result.analyses if item.text == "이미 봄")
    assert observed.user_id == "A"
    assert observed.attitude == "NEUTRAL"
    assert observed.preference_score == 0.0

    person_results = {
        (item.target, item.attitude)
        for item in result.analyses
        if item.text == "젠데이아는 좋지만 톨홀랜드는 별로"
    }
    assert ("젠데이아", "LIKE") in person_results
    assert ("톰 홀랜드", "DISLIKE") in person_results
