from meetup_ml.chat_analysis import analyze_chat
from meetup_ml.schemas import ChatAnalyzeRequest


def analyze(messages):
    return analyze_chat(
        ChatAnalyzeRequest(messages=messages),
        [],
    )


def member(result, user_id):
    return next(
        value
        for value in result.members
        if value.user_id == user_id
    )


def test_animation_typo_keeps_negative_meaning():
    result = analyze([
        {
            "user_id": "A",
            "text": "애니메이션은 보고 싶지 않아",
        },
    ])

    preference = member(result, "A")

    assert "애니메이션" not in preference.liked_genres
    assert preference.disliked_genres["애니메이션"] == 0.6