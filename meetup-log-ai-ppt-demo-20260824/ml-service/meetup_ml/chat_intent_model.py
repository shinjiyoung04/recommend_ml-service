from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline


TRAINING_DATA = {
    "STRONG_LIKE": ["완전 내 취향", "무조건 이거", "꼭 보고 싶어", "이건 필수야", "이런 영화 최고", "진짜 너무 좋아", "이건 있어야 돼", "제일 좋아해"],
    "LIKE": ["좋아", "보고 싶다", "재밌을 것 같아", "이런 거 끌려", "괜찮아 보여", "내 취향이야", "이걸로 보자", "나는 찬성"],
    "WEAK_LIKE": ["나쁘지 않아", "볼 만할 듯", "괜찮을 것 같아", "상관없긴 해", "그럭저럭 좋아", "한번 봐도 될 듯", "나는 오케이", "뭐 괜찮지"],
    "NEUTRAL": ["아무거나", "상관없어", "다 괜찮아", "너희가 골라", "딱히 없어", "그냥 그래", "난 중립", "아무거나 보자"],
    "UNCERTAIN": ["잘 모르겠어", "좀 애매한데", "글쎄", "고민된다", "확신은 없어", "봐도 그만", "잘 모르겠다", "선뜻 안 끌려"],
    "DISLIKE": ["별로야", "안 보고 싶어", "내 취향 아니야", "그건 좀 싫어", "그거 말고", "재미없을 듯", "별로 안 끌려", "나는 반대",
                "이건 정말 내 취향 아닌 듯", "내 스타일은 아닌데", "취향과 거리가 멀어", "딱히 끌리지는 않아", "좋아하는 쪽은 아니야", "좀 아닌 것 같아"],
    "STRONG_DISLIKE": ["절대 싫어", "무조건 빼줘", "난 못 봐", "이건 제외해", "극혐이야", "죽어도 안 봐", "진짜 못 보겠어", "절대 안 돼"],
    "QUESTION": ["뭐 볼까", "어떤 영화야", "몇 분짜리야", "어디서 볼 수 있어", "이거 재밌어", "누가 나와", "추천할 거 있어", "이건 어때"],
}

SCORES = {"STRONG_LIKE": 1.0, "LIKE": .8, "WEAK_LIKE": .3, "NEUTRAL": 0.0, "UNCERTAIN": -.1,
          "DISLIKE": -.6, "STRONG_DISLIKE": -1.0, "QUESTION": 0.0}


@lru_cache(maxsize=1)
def trained_intent_model():
    texts, labels = [], []
    for label, examples in TRAINING_DATA.items():
        texts.extend(examples); labels.extend([label] * len(examples))
    model = Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=1, sublinear_tf=True)),
        ("classifier", LogisticRegression(max_iter=500, class_weight="balanced", random_state=42)),
    ])
    model.fit(texts, labels)
    return model


def predict_attitude(text: str):
    model = trained_intent_model()
    probabilities = model.predict_proba([text])[0]
    index = int(probabilities.argmax())
    label = str(model.classes_[index])
    return label, SCORES[label], round(float(probabilities[index]), 3)
