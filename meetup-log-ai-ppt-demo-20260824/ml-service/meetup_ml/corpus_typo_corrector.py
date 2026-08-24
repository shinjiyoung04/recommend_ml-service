from __future__ import annotations

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

DICT_PATH = DATA_DIR / "colloquial_normalization.json"
TYPO_DICT_PATH = DATA_DIR / "chat_typo_dictionary.json"

HYPHEN_TOKEN = re.compile(r"-(\S+?)-")
TILDE = re.compile(r"~+")
WHITESPACE = re.compile(r"\s+")

_dict_cache: dict[str, str] | None = None
_typo_cache: dict[str, str] | None = None

SAFE_CHAT_TYPO_RULES = {
    # 좋아/싫어
    "싫ㅇ": "싫어",
    "실어": "싫어",
    "시러": "싫어",
    "시름": "싫음",
    "조아": "좋아",
    "죠아": "좋아",
    "조음": "좋음",
    "죠음": "좋음",
    "좋움": "좋음",

    # 장르
    "로멘스": "로맨스",
    "로맨쓰": "로맨스",
    "애니매이션": "애니메이션",
    "애니메숀": "애니메이션",
    "액숀": "액션",
    "액션영화": "액션 영화",
    "공포영하": "공포 영화",
    "스릴러영화": "스릴러 영화",

    # OTT
    "넷플": "넷플릭스",
    "넷플릭": "넷플릭스",
    "넷플릭": "넷플릭스",
    "넷플릭쓰": "넷플릭스",
    "디플": "디즈니+",
    "디즈니플러스": "디즈니+",
    "티빙이": "티빙",

    # 배우/감독
    "봉준호감독": "봉준호 감독",
    "봉감독": "봉준호 감독",
    "톰홀랜드": "톰 홀랜드",
    "젠대이아": "젠데이아",
    "젠다야": "젠데이아",

    # 조사
    "잔잔한게": "잔잔하게",
    "잔인한건": "잔인한 거",
    "슬픈건": "슬픈 거",
    "무서운건": "무서운 거",

    # 일반
    "보고시퍼": "보고 싶어",
    "보고시픔": "보고 싶음",
    "보고픔": "보고 싶음",
    "보구싶어": "보고 싶어",
    "보고십어": "보고 싶어",
}

_INFORMAL_YO_SUFFIX_RULES = [
    ("이에여", "이에요"),
    ("해여", "해요"),
    ("돼여", "돼요"),
    ("봐여", "봐요"),
    ("와여", "와요"),
    ("예여", "예요"),
    ("네여", "네요"),
    ("게여", "게요"),
    ("지여", "지요"),
    ("나여", "나요"),
    ("구여", "구요"),
    ("가여", "가요"),
    ("아여", "아요"),
    ("어여", "어요"),
]

_INFORMAL_YO_MAP = dict(_INFORMAL_YO_SUFFIX_RULES)

_INFORMAL_YO_ALTERNATION = "|".join(
    re.escape(suffix)
    for suffix, _ in sorted(
        _INFORMAL_YO_SUFFIX_RULES,
        key=lambda item: -len(item[0]),
    )
)

INFORMAL_YO_PATTERN = re.compile(
    rf"({_INFORMAL_YO_ALTERNATION})([!?.,~ㅋㅎㅠㅜ]*)$"
)


def _normalize_informal_yo(token: str) -> str:
    match = INFORMAL_YO_PATTERN.search(token)

    if not match:
        return token

    suffix = match.group(1)
    trailing = match.group(2)

    return (
        token[: match.start()]
        + _INFORMAL_YO_MAP[suffix]
        + trailing
    )


def _load_dict() -> dict[str, str]:
    global _dict_cache

    if _dict_cache is None:
        if DICT_PATH.exists():
            with open(DICT_PATH, encoding="utf-8") as file:
                _dict_cache = json.load(file)
        else:
            _dict_cache = {}

    return _dict_cache

def _load_typo_dict() -> dict[str, str]:
    global _typo_cache

    if _typo_cache is None:
        if TYPO_DICT_PATH.exists():
            with open(TYPO_DICT_PATH, encoding="utf-8") as file:
                _typo_cache = json.load(file)
        else:
            _typo_cache = {}

    return _typo_cache

def correct(text: str) -> str:
    result = HYPHEN_TOKEN.sub(r"\1", text)
    result = TILDE.sub("", result)
    result = WHITESPACE.sub(" ", result).strip()

    colloquial_dict = _load_dict()

    normalized: list[str] = []

    typo_dict =  _load_typo_dict()

    for token in result.split():
        # MeetupLog 채팅에서 확인된 안전한 단순 오타
        token = typo_dict.get(token, token)

        if colloquial_dict:
            token = colloquial_dict.get(token, token)

        token = _normalize_informal_yo(token)

        normalized.append(token)

    return " ".join(normalized)