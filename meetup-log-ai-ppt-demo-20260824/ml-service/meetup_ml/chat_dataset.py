import json
import random
from pathlib import Path

COUNTRIES = ["한국", "미국", "일본", "프랑스", "영국"]
YEARS = ["1990년대", "2000년대", "2010년대", "2020년대"]
OTTS = ["넷플릭스", "디즈니플러스", "티빙", "웨이브", "쿠팡플레이"]
PEOPLE = ["톰 크루즈", "송강호", "마동석", "레오나르도 디카프리오", "스칼렛 요한슨"]
LANGUAGES = ["한국어", "영어", "일본어", "프랑스어"]


GENRES = ["액션", "코미디", "공포", "로맨스", "SF", "애니메이션", "스릴러", "다큐멘터리"]
TOPICS = ["우주", "우정", "가족", "복수", "추리", "가벼운", "감동적인", "잔잔한"]
BRANDS = [("마블", "Marvel"), ("디즈니", "Disney"), ("픽사", "Pixar"), ("지브리", "Ghibli")]
MOVIES = ["은하의 약속", "여름의 식탁", "검은 복도", "마지막 질주"]

LIKE = [("LIKE", .8, "좋아"), ("STRONG_LIKE", 1.0, "완전 좋아"), ("WEAK_LIKE", .3, "나쁘지 않아")]
DISLIKE = [("DISLIKE", -.6, "별로야"), ("STRONG_DISLIKE", -1.0, "절대 못 봐")]

TEMPLATES = {
    "GENRE": ["{target} {phrase}", "오늘은 {target} 영화가 {phrase}", "나는 {target} 쪽이 {phrase}", "{target} 장르로 가면 {phrase}", "솔직히 {target}은 {phrase}"],
    "TOPIC": ["{target} 소재가 {phrase}", "{target} 느낌이면 {phrase}", "오늘은 {target} 이야기 {phrase}", "나는 {target} 분위기가 {phrase}", "{target} 중심 작품은 {phrase}"],
    "BRAND": ["{surface} 영화 {phrase}", "이번엔 {surface} 작품이 {phrase}", "나는 {surface} 스타일 {phrase}", "{surface} 쪽으로 보면 {phrase}", "솔직히 {surface}는 {phrase}"],
    "MOVIE": ["{target} {phrase}", "오늘 {target} 보는 거 {phrase}", "나는 {target}이 {phrase}", "{target}으로 정하면 {phrase}", "혹시 {target}은 {phrase}"],
}

CHAT_TEMPLATES = [
    "오늘 과제 다 했어?", "저녁 뭐 먹을래", "ㅋㅋㅋㅋ 그건 인정", "내일 비 온대", "지금 지하철이야",
    "회의 몇 시에 시작해", "사진 진짜 잘 나왔다", "주말에 축구 볼 사람", "배터리 거의 없어", "카페 어디로 갈까",
    "오늘 수업 너무 어려웠어", "점심 아직 안 먹었어", "파일 다시 보내 줘", "집 도착하면 연락할게", "게임 한 판 하자",
]


def _split(template_index: int) -> str:
    # Hold out whole wording patterns so evaluation does not merely memorize
    # the same sentence template seen during training.
    return "train" if template_index % 10 < 7 else "validation" if template_index % 10 < 9 else "test"


def build_chat_dataset(size: int = 3000, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    records = []
    types = (
        ["GENRE"] * 8
        + ["TOPIC"] * 4
        + ["BRAND"] * 3
        + ["MOVIE"] * 3
        + ["CONSTRAINT"] * 3
        + ["COUNTRY"] * 2
        + ["YEAR"] * 2
        + ["OTT"] * 2
        + ["PERSON"] * 2
        + ["LANGUAGE"] * 2
        + ["CHAT"] * 4
    )
    fillers = ["", " ㅎㅎ", "ㅋㅋ", "근데 ", "나는 ", "이번에는 "]
    times = ["오늘", "내일", "이번 주말", "금요일 밤", "토요일 오후", "다음 모임", "시험 끝나고", "저녁 먹고", "퇴근 후", "방학 때",
             "이번 달", "비 오는 날", "늦은 밤", "점심 지나서", "약속 전에", "카페 갔다가", "수업 마치고", "다 같이 모이면", "시간 될 때", "이번 번개"]
    groups = ["우리끼리", "동아리 애들이랑", "친구들이랑", "방 사람들하고", "넷이서", "다 같이", "두 명이서", "모임에서", "팀원들이랑", "새로 온 친구랑",
              "영화 좋아하는 애들이랑", "오랜만에 모여서", "집에서", "극장에서", "온라인으로"]
    endings = ["어때?", "어떻게 생각해?", "내 의견은 그래", "가능하면 그렇게 하자", "다들 괜찮아?", "일단 나는 그래", "의견 남겨 줘", "이걸로 얘기해 보자", "너희는 어때", "한번 정해 보자"]
    for index in range(size):
        kind = types[index % len(types)]
        template_index = (index // len(types)) % 10
        split = _split(template_index)
        if kind == "CHAT":
            text = CHAT_TEMPLATES[(index // len(types) + index) % len(CHAT_TEMPLATES)]
            record = {"relevance": "CHAT", "target_type": "UNKNOWN", "target": None,
                      "attitude": "NEUTRAL", "preference_score": 0.0}
        elif kind == "CONSTRAINT":
            minutes = [90, 100, 120, 150, 180][index % 5]
            hours = f"{minutes / 60:g}"

            variants = [
                f"{minutes}분 넘는 영화는 싫어",
                f"최대 {minutes}분 이하로 보자",
                f"{hours}시간 이상은 힘들어",
                f"러닝타임 {minutes}분 안쪽이면 좋겠어",
                f"영화는 {minutes}분보다 짧은 걸로",
            ]

            text = variants[template_index % len(variants)]

            record = {
                "relevance": "MOVIE",
                "target_type": "CONSTRAINT",
                "target": f"최대 {minutes}분",
                "attitude": (
                    "DISLIKE"
                    if "싫" in text or "힘들" in text
                    else "WEAK_LIKE"
                ),
                "preference_score": (
                    -0.6
                    if "싫" in text or "힘들" in text
                    else 0.3
                ),
            }
        elif kind == "COUNTRY":
            target = COUNTRIES[index % len(COUNTRIES)]
            text = f"{target} 영화로 보고 싶어"
            record = {
                "relevance": "MOVIE",
                "target_type": "COUNTRY",
                "target": target,
                "attitude": "LIKE",
                "preference_score": 0.8,
            }

        elif kind == "YEAR":
            target = YEARS[index % len(YEARS)]
            text = f"{target} 영화로 보자"
            record = {
                "relevance": "MOVIE",
                "target_type": "YEAR",
                "target": target,
                "attitude": "LIKE",
                "preference_score": 0.8,
            }

        elif kind == "OTT":
            target = OTTS[index % len(OTTS)]
            text = f"{target}에 있는 영화만 보고 싶어"
            record = {
                "relevance": "MOVIE",
                "target_type": "OTT",
                "target": target,
                "attitude": "LIKE",
                "preference_score": 0.8,
            }

        elif kind == "PERSON":
            target = PEOPLE[index % len(PEOPLE)]
            text = f"{target} 나오는 영화 좋아"
            record = {
                "relevance": "MOVIE",
                "target_type": "PERSON",
                "target": target,
                "attitude": "LIKE",
                "preference_score": 0.8,
            }

        elif kind == "LANGUAGE":
            target = LANGUAGES[index % len(LANGUAGES)]
            text = f"{target} 영화 보고 싶어"
            record = {
                "relevance": "MOVIE",
                "target_type": "LANGUAGE",
                "target": target,
                "attitude": "LIKE",
                "preference_score": 0.8,
            }        
        
        else:
            sentiment = (LIKE + DISLIKE)[(index // 3) % len(LIKE + DISLIKE)]
            attitude, score, phrase = sentiment
            if kind == "GENRE":
                target = GENRES[index % len(GENRES)]; surface = target
            elif kind == "TOPIC":
                target = TOPICS[index % len(TOPICS)]; surface = target
            elif kind == "BRAND":
                surface, target = BRANDS[index % len(BRANDS)]
            else:
                target = MOVIES[index % len(MOVIES)]; surface = target
            template = TEMPLATES[kind][template_index % len(TEMPLATES[kind])]
            text = template.format(target=surface, surface=surface, phrase=phrase)
            record = {"relevance": "MOVIE", "target_type": kind, "target": target,
                      "attitude": attitude, "preference_score": score}
        prefix = rng.choice(fillers)
        if prefix and not prefix.endswith(" "):
            text += prefix
        else:
            text = prefix + text
        # The mixed-radix context tuple is unique for the first 3,000 rows and
        # keeps the examples conversational without appending artificial IDs.
        context = f"{times[index % len(times)]} {groups[(index // len(times)) % len(groups)]}"
        ending = endings[(index // (len(times) * len(groups))) % len(endings)]
        text = f"{context}, {text.strip()}. {ending}"
        records.append({"id": f"chat-{index + 1:04d}", "text": text.strip(), "split": split,
                        "source": "synthetic_scenario_v1", **record})
    return records


def write_chat_dataset(path: Path, size: int = 3000, seed: int = 42) -> dict:
    records = build_chat_dataset(size=size, seed=seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    split_counts = {split: sum(row["split"] == split for row in records) for split in ("train", "validation", "test")}
    return {"path": str(path), "rows": len(records), "splits": split_counts}


def load_chat_dataset(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]
