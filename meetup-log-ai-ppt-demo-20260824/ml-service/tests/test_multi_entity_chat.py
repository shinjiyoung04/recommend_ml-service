from pathlib import Path

from meetup_ml.chat_analysis import analyze_chat
from meetup_ml.schemas import ChatAnalyzeRequest, ChatMessage
from meetup_ml.storage import JsonStore


def test_multi_entity_attitude_extraction():
    movies = JsonStore(Path("data")).load_movies(use_fixture=False)

    result = analyze_chat(
        ChatAnalyzeRequest(
            messages=[
                ChatMessage(
                    user_id="u1",
                    text="액션은 좋아하지만 공포는 싫고 넷플릭스에 있는 영화면 좋아",
                )
            ]
        ),
        movies,
    )

    actual = {
        (
            item.target_type,
            item.target,
            item.attitude,
            item.preference_score,
        )
        for item in result.analyses
    }

    assert ("GENRE", "액션", "LIKE", 0.8) in actual
    assert ("GENRE", "공포", "DISLIKE", -0.6) in actual
    assert ("OTT", "넷플릭스", "LIKE", 0.8) in actual