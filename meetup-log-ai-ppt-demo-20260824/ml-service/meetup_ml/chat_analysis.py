import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
try:
    from rapidfuzz.fuzz import ratio as rapidfuzz_ratio
    from rapidfuzz import process as rapidfuzz_process
except ImportError:  # deterministic fallback for minimal/offline installations
    rapidfuzz_process = None

    def rapidfuzz_ratio(left: str, right: str) -> float:
        return SequenceMatcher(None, left, right).ratio() * 100

from .chat_intent_model import predict_attitude
from .person_identity import canonical_person_name, resolve_person_preference
from .schemas import (
    ChatAnalyzeRequest,
    ChatAnalyzeResponse,
    MessageAnalysis,
    Movie,
    Preference,
)


GENRES = [
    "액션",
    "모험",
    "애니메이션",
    "코미디",
    "범죄",
    "다큐멘터리",
    "드라마",
    "가족",
    "판타지",
    "역사",
    "공포",
    "음악",
    "미스터리",
    "로맨스",
    "SF",
    "스릴러",
    "전쟁",
    "서부",
]

GENRE_ALIASES = {
    "애니": "애니메이션",
    "애니메": "애니메이션",
    "로코": "로맨스",
    "멜로": "로맨스",
    "에스에프": "SF",
    "공포물": "공포",
    "호러": "공포",
    "호러물": "공포",
    "horror": "공포",
    "다큐": "다큐멘터리",
    "코메디": "코미디",
    "로맨드": "로맨스",
    "로멘스": "로맨스",
    "로앤스": "로맨스",
    "뮤지컬": "음악",
    "뮤지컬영화": "음악",
}

COUNTRY_ALIASES = {
    # 한국
    "대한민국": "KR",
    "한국 영화": "KR",
    "한국영화": "KR",
    "국내 영화": "KR",
    "국내영화": "KR",
    "한국": "KR",
    "국내": "KR",
    "국산": "KR",

    # 일본
    "일본 애니메이션": "JP",
    "일본애니메이션": "JP",
    "일본 애니": "JP",
    "일본애니": "JP",
    "일본 영화": "JP",
    "일본영화": "JP",
    "재패니즈": "JP",
    "일본": "JP",

    # 미국
    "미국 영화": "US",
    "미국영화": "US",
    "할리우드": "US",
    "헐리우드": "US",
    "미국": "US",

    # 중국
    "중국 영화": "CN",
    "중국영화": "CN",
    "중국": "CN",

    # 홍콩
    "홍콩 영화": "HK",
    "홍콩영화": "HK",
    "홍콩": "HK",

    # 영국
    "영국 영화": "GB",
    "영국영화": "GB",
    "영국": "GB",

    # 프랑스
    "프랑스 영화": "FR",
    "프랑스영화": "FR",
    "프랑스": "FR",
}


COUNTRY_LABELS = {
    "KR": "한국",
    "JP": "일본",
    "US": "미국",
    "CN": "중국",
    "HK": "홍콩",
    "GB": "영국",
    "FR": "프랑스",
}

BRAND_ALIASES = {
    "마블": "Marvel",
    "mcu": "Marvel",
    "엠씨유": "Marvel",
    "디즈니": "Disney",
    "픽사": "Pixar",
    "스타워즈": "Star Wars",
    "지브리": "Ghibli",
}

MOVIE_ALIASES = {
    "귀칼": "귀멸의 칼날",
    "귀찰": "귀멸의 칼날",
    "어벤": "어벤져스",
    "스파이더멘": "스파이더맨",
    "스파이너맨": "스파이더맨",
}

# 영화 카탈로그에 인물 정보가 누락된 경우를 위한 최소 별칭 사전.
# 필요할 때 같은 형식으로 배우/감독을 추가한다.
KNOWN_PERSON_ALIASES = {
    "류준열": ("류준열", "ACTOR"),
    "혜리": ("혜리", "ACTOR"),
    "톨홀랜드": ("톰 홀랜드", "ACTOR"),
    "톨 홀랜드": ("톰 홀랜드", "ACTOR"),
}

OTT_ALIASES = {
    "넷플릭스": "넷플릭스",
    "넷플": "넷플릭스",
    "넷플릿스": "넷플릭스",
    "netflix": "넷플릭스",

    "티빙": "티빙",
    "tving": "티빙",

    "웨이브": "웨이브",
    "wavve": "웨이브",

    "디즈니플러스": "디즈니+",
    "디즈니+": "디즈니+",
    "디플": "디즈니+",
    "disneyplus": "디즈니+",

    "왓챠": "왓챠",
    "watcha": "왓챠",

    "쿠팡플레이": "쿠팡플레이",
    "쿠플": "쿠팡플레이",
    "coupangplay": "쿠팡플레이",

    "애플티비": "Apple TV+",
    "애플tv": "Apple TV+",
    "appletv": "Apple TV+",
}

TOPICS = [
    "우주",
    "우정",
    "가족",
    "사랑",
    "성장",
    "복수",
    "추리",
    "여행",
    "일상",
    "가벼운",
    "웃긴",
    "감동적인",
    "잔잔한",
    "따뜻한",
    "무서운",
    "잔인한",
    "어두운",
    "몰입감",
    "긴장감",
    "반전",
    "발랄한",
    "진지한",

    "오컬트",
    "퇴마",
    "악마",
    "빙의",
    "저주",
    "귀신",
    "종교 의식",
]

TOPIC_ALIASES = {
    "오컬트물": "오컬트",
    "occult": "오컬트",
    "퇴마물": "퇴마",
    "엑소시즘": "퇴마",
    "엑소시스트": "퇴마",
    "악령": "악마",
    "빙의물": "빙의",
    "귀신물": "귀신",
    "잔잔하게": "잔잔한",
    "잔잔하고": "잔잔한",
    "따뜻하게": "따뜻한",
    "따뜻하고": "따뜻한",
    "무섭지": "무서운",
    "몰입감있는": "몰입감",
    "몰임감": "몰입감",
    "몰입되는": "몰입감",
    "긴장감있는": "긴장감",
    "긴장되는": "긴장감",
    "스릴있는": "긴장감",
    "스릴 있는": "긴장감",
    "스릴있고": "긴장감",
    "반전있는": "반전",
    "발랄": "발랄한",
    "밝고경쾌한": "발랄한",
    "심각한": "진지한",
    "심각": "진지한",
}


def _empty_state() -> dict:
    """대화 참여자 한 명의 누적 취향 상태를 생성한다."""
    return {
        "liked_genres": {},
        "disliked_genres": {},
        "liked_topics": {},
        "disliked_topics": {},
        "liked_brands": {},
        "disliked_brands": {},
        "liked_movies": [],
        "direct_movies": [],
        "seen_movies": [],
        "rewatch_allowed_movies": [],
        "disliked_movies": [],
        "liked_people": [],
        "disliked_people": [],
        "liked_actors": [],
        "disliked_actors": [],
        "liked_directors": [],
        "disliked_directors": [],
        "countries": [],
        "excluded_countries": [],
        "allowed_providers": [],
        "allowed_provider_types": [],
        "ott_platforms": [],
        "ott_strict": False,    
        "prefers_theater": False,
        "hard_exclusions": [],
    }


def _person_reference(
    name: str,
    role: str,
    movies: list[Movie],
    strength: float,
) -> dict:
    reference = resolve_person_preference(
        name,
        role,
        movies,
        strength=min(1.0, abs(strength)),
    ).model_dump()
    # Keep the user's resolved display spelling for legacy clients and analyses.
    reference["display_name"] = name
    return reference


def _person_display_name(reference: dict | str) -> str:
    if isinstance(reference, str):
        return reference
    return str(
        reference.get("display_name")
        or reference.get("original_name")
        or reference.get("name")
        or ""
    )


def _same_person_reference(left: dict, right: dict) -> bool:
    if left.get("role") != right.get("role"):
        return False
    left_id, right_id = left.get("person_id"), right.get("person_id")
    if left_id is not None and right_id is not None:
        return left_id == right_id
    left_names = {
        canonical_person_name(str(value))
        for value in (left.get("name"), left.get("original_name"), left.get("display_name"))
        if value
    }
    right_names = {
        canonical_person_name(str(value))
        for value in (right.get("name"), right.get("original_name"), right.get("display_name"))
        if value
    }
    return bool(left_names & right_names)


def _apply_person_effect(
    state: dict,
    reference: dict | str,
    value: float,
) -> str:
    display_name = _person_display_name(reference)
    if not display_name:
        return ""

    # Legacy name lists remain synchronized for older Spring/React clients.
    positive_legacy = state["liked_people"]
    negative_legacy = state["disliked_people"]
    if value > 0:
        if display_name not in positive_legacy:
            positive_legacy.append(display_name)
        if display_name in negative_legacy:
            negative_legacy.remove(display_name)
    elif value < 0:
        if display_name not in negative_legacy:
            negative_legacy.append(display_name)
        if display_name in positive_legacy:
            positive_legacy.remove(display_name)

    if isinstance(reference, str) or reference.get("role") not in {"ACTOR", "DIRECTOR"}:
        return display_name

    role = reference["role"]
    positive_field = "liked_actors" if role == "ACTOR" else "liked_directors"
    negative_field = "disliked_actors" if role == "ACTOR" else "disliked_directors"
    reference["strength"] = min(1.0, abs(value))

    target_field = positive_field if value > 0 else negative_field
    opposite_field = negative_field if value > 0 else positive_field
    state[target_field] = [
        item
        for item in state[target_field]
        if not _same_person_reference(item, reference)
    ]
    state[target_field].append(reference)
    state[opposite_field] = [
        item
        for item in state[opposite_field]
        if not _same_person_reference(item, reference)
    ]
    return display_name


def _clean(value: str) -> str:
    return re.sub(
        r"[^0-9a-zA-Z가-힣ㄱ-ㅎㅏ-ㅣ]",
        "",
        value,
    ).casefold()


@dataclass
class _PeopleIndex:
    exact: dict[str, list[tuple[str, str]]]
    alias_owners: dict[tuple[str, str], set[str]]
    fuzzy_names: dict[str, list[str]]
    display_by_clean: dict[tuple[str, str], str]


def _build_people_index(movies: list[Movie]) -> _PeopleIndex:
    known: dict[str, set[str]] = {"ACTOR": set(), "DIRECTOR": set()}
    for movie in movies:
        known["ACTOR"].update(name for name in movie.cast if name)
        known["DIRECTOR"].update(name for name in movie.directors if name)
        for credit in movie.cast_people:
            known["ACTOR"].update(
                name
                for name in (credit.name, credit.original_name)
                if name
            )
        for credit in movie.director_people:
            known["DIRECTOR"].update(
                name
                for name in (credit.name, credit.original_name)
                if name
            )

    exact: dict[str, list[tuple[str, str]]] = {}
    alias_owners: dict[tuple[str, str], set[str]] = {}
    fuzzy_names: dict[str, list[str]] = {"ACTOR": [], "DIRECTOR": []}
    display_by_clean: dict[tuple[str, str], str] = {}

    for person_type, names in known.items():
        for name in names:
            clean_name = _clean(name)
            if len(clean_name) >= 2:
                exact.setdefault(clean_name, []).append((name, person_type))
            if len(clean_name) >= 4:
                fuzzy_names[person_type].append(clean_name)
                display_by_clean.setdefault((person_type, clean_name), name)
            for token in re.findall(r"[0-9A-Za-z가-힣]{2,}", name):
                alias_owners.setdefault(
                    (person_type, _clean(token)),
                    set(),
                ).add(name)

    return _PeopleIndex(
        exact=exact,
        alias_owners=alias_owners,
        fuzzy_names=fuzzy_names,
        display_by_clean=display_by_clean,
    )

def _detect_country(
    text: str,
) -> tuple[str, str] | None:
    """채팅에서 국가 표현을 찾는다."""

    normalized = re.sub(
        r"\s+",
        " ",
        text.strip(),
    ).casefold()

    for alias in sorted(
        COUNTRY_ALIASES,
        key=len,
        reverse=True,
    ):
        if alias.casefold() in normalized:
            return (
                COUNTRY_ALIASES[alias],
                alias,
            )

    return None

def _detect_countries(
    text: str,
) -> list[tuple[str, str]]:
    """채팅에서 여러 국가 표현을 모두 찾는다."""

    normalized = re.sub(
        r"\s+",
        " ",
        text.strip(),
    ).casefold()

    found: list[tuple[str, str]] = []
    seen_codes: set[str] = set()

    for alias in sorted(
        COUNTRY_ALIASES,
        key=len,
        reverse=True,
    ):
        if alias.casefold() not in normalized:
            continue

        country_code = COUNTRY_ALIASES[alias]

        if country_code in seen_codes:
            continue

        found.append(
            (
                country_code,
                alias,
            )
        )
        seen_codes.add(country_code)

    return found

def _detect_people(
    text: str,
    movies: list[Movie],
    people_index: _PeopleIndex | None = None,
) -> list[tuple[str, str]]:
    """
    채팅에서 배우/감독 이름을 모두 찾는다.

    반환 예:
    [
        ("톰 크루즈", "ACTOR"),
        ("미야자키 하야오", "DIRECTOR"),
    ]
    """

    people_index = people_index or _build_people_index(movies)
    people: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for alias, (person_name, person_type) in KNOWN_PERSON_ALIASES.items():
        alias_pattern = re.compile(
            rf"(?<![0-9A-Za-z가-힣]){re.escape(alias)}"
            rf"(?=(?:은|는|이|가|을|를|도|만)?(?:\s|$|[,.!?]))",
            re.IGNORECASE,
        )

        if alias_pattern.search(text):
            key = (person_name, person_type)

            if key not in seen:
                people.append(key)
                seen.add(key)

    role_context = {
        "DIRECTOR": r"(?:감독|연출|감독작|작품|영화)",
        "ACTOR": r"(?:배우|출연|나오|나온|주연)",
    }
    role_positions = {
        person_type: [match.span() for match in re.finditer(pattern, text, re.IGNORECASE)]
        for person_type, pattern in role_context.items()
    }

    # Keep one-letter Latin initials so names such as "Samuel L. Jackson"
    # can be reconstructed from adjacent tokens.
    token_matches = list(re.finditer(r"[0-9A-Za-z가-힣]+", text))
    raw_tokens = [match.group() for match in token_matches]
    message_tokens = [
        re.sub(r"(?:은|는|이|가|을|를|도|만)$", "", token)
        for token in raw_tokens
    ]
    exact_forms = {_clean(token) for token in [*raw_tokens, *message_tokens]}
    for width in (2, 3, 4):
        exact_forms.update(
            _clean("".join(message_tokens[start:start + width]))
            for start in range(0, len(message_tokens) - width + 1)
        )

    for form in exact_forms:
        for key in people_index.exact.get(form, []):
            if key not in seen:
                people.append(key)
                seen.add(key)

    # A short token is accepted only when it has one catalog owner in the
    # requested role and appears immediately before the role expression.
    for match in token_matches:
        token = match.group()
        clean_token = _clean(
            re.sub(r"(?:은|는|이|가|을|를|도|만)$", "", token)
        )
        for person_type in ("ACTOR", "DIRECTOR"):
            owners = people_index.alias_owners.get(
                (person_type, clean_token),
                set(),
            )
            if len(owners) != 1:
                continue
            if any(
                0 <= role_start - match.end() <= 6
                for role_start, _ in role_positions[person_type]
            ):
                key = (next(iter(owners)), person_type)
                if key not in seen:
                    people.append(key)
                    seen.add(key)

    # Resolve light spacing/typing errors through RapidFuzz's indexed C path.
    for token in message_tokens:
        clean_token = _clean(token)
        if len(clean_token) < 4:
            continue
        for person_type, choices in people_index.fuzzy_names.items():
            if rapidfuzz_process is not None:
                matches = rapidfuzz_process.extract(
                    clean_token,
                    choices,
                    scorer=rapidfuzz_ratio,
                    score_cutoff=88,
                    limit=3,
                )
                matched_forms = [item[0] for item in matches]
            else:
                matched_forms = [
                    choice
                    for choice in choices
                    if _fuzzy_score(clean_token, choice) >= 0.88
                ]
            for clean_name in matched_forms:
                name = people_index.display_by_clean[(person_type, clean_name)]
                key = (name, person_type)
                if key not in seen:
                    people.append(key)
                    seen.add(key)

    # 현재 영화 카탈로그에 없는 인물도 “OO 나오는 영화” 문형에서는
    # 선호 인물 후보로 보존한다. 이후 카탈로그/TMDB 동기화에 사용할 수 있다.
    raw_person = re.search(
        r"(?:^|\s)(?:나는?|난|저는?|전|근데)?\s*"
        r"([0-9A-Za-z가-힣]{2,20})(?:은|는|이|가)?\s*"
        r"(?:배우(?:가)?\s*)?(?:나오|출연|주연)",
        text,
    )
    if raw_person:
        candidate = raw_person.group(1)
        if not any(_clean(name) == _clean(candidate) for name, _ in people):
            people.append((candidate, "ACTOR"))

    # "혜리 나오는 영화", "류준열 배우 작품"처럼
    # 인물 역할 문맥이 명확한 이름을 추가로 추출한다.
    contextual_people_patterns = [
        (
            r"([가-힣]{2,5})(?:은|는|이|가)?\s*"
            r"(?:배우|출연|나오(?:는|ㄴ)?|나온|주연)",
            "ACTOR",
        ),
        (
            r"([가-힣]{2,5})(?:은|는|이|가)?\s*"
            r"(?:감독|연출|감독작|만든\s*영화)",
            "DIRECTOR",
        ),
    ]

    non_person_words = {
        "나",
        "나는",
        "근데",
        "영화",
        "작품",
        "배우",
        "배우가",
        "감독",
        "감독이",
        "연출",
        "만든",
        "나오는",
        "액션",
        "로맨스",
        "코미디",
        "스릴러",
        "애니",
        "애니메이션",
        "넷플릭스",
        "티빙",
    }

    for pattern, person_type in contextual_people_patterns:
        for match in re.finditer(pattern, text):
            person_name = match.group(1).strip()

            if (
                person_name in non_person_words
                or person_name.endswith(("배우가", "감독이"))
            ):
                continue

            key = (person_name, person_type)

            if key not in seen:
                people.append(key)
                seen.add(key)
    
    # 긴 이름을 우선해서,
    # "미야자키 하야오"와 함께 "야오"처럼
    # 일부 문자열만 중복 감지되는 것을 제거한다.
    people.sort(
        key=lambda item: len(_clean(item[0])),
        reverse=True,
    )

    filtered: list[tuple[str, str]] = []

    for person_name, person_type in people:
        clean_name = _clean(person_name)

        if any(
            clean_name in _clean(existing_name)
            and clean_name != _clean(existing_name)
            for existing_name, _existing_type
            in filtered
        ):
            continue

        filtered.append(
            (
                person_name,
                person_type,
            )
        )

    return filtered

_KOREAN_ENDINGS = (
    "으로",
    "이면",
    "이나",
    "나",
    "거나",
    "이라",
    "같은",
    "처럼",
    "장르",
    "영화",
    "물이",
    "물을",
    "물로",
    "물",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "도",
    "만",
    "랑",
    "과",
    "와",
    "쪽",
)

_PHONETIC_JAMO = str.maketrans(
    {
        "ᅢ": "ᅦ",
        "ᅤ": "ᅨ",
    }
)


def _tokens(text: str) -> list[str]:
    return [
        _clean(value)
        for value in re.findall(r"[0-9a-zA-Z가-힣]+", text)
        if _clean(value)
    ]


def _term_forms(token: str) -> set[str]:
    forms = {token}
    queue = [token]

    while queue:
        current = queue.pop()

        for ending in _KOREAN_ENDINGS:
            if not current.endswith(ending):
                continue

            stripped = current[:-len(ending)]

            if len(stripped) < 2:
                continue

            if stripped in forms:
                continue

            forms.add(stripped)
            queue.append(stripped)

    return forms


def _phonetic(value: str) -> str:
    return unicodedata.normalize("NFD", value).translate(_PHONETIC_JAMO)


def _fuzzy_score(token: str, term: str) -> float:
    if len(token) != len(term) or len(term) < 2:
        return 0.0

    raw = SequenceMatcher(None, token, term).ratio()
    phonetic = SequenceMatcher(
        None,
        _phonetic(token),
        _phonetic(term),
    ).ratio()

    minimum = 0.94 if len(term) <= 2 else 0.90 if len(term) == 3 else 0.88

    if phonetic < minimum:
        return 0.0

    if len(term) <= 2 and raw < 0.5:
        return 0.0

    return phonetic


def _best_term(
    text: str,
    terms: list[str],
    allow_fuzzy: bool = True,
):
    clean_text = _clean(text)
    tokens = _tokens(text)
    ranked: list[tuple[float, str, str]] = []

    for term in terms:
        clean_term = _clean(term)

        if clean_term and (
            clean_term in tokens
            or (len(clean_term) >= 4 and clean_term in clean_text)
        ):
            return 1.0, term, term

        if not allow_fuzzy:
            continue

        for token in tokens:
            for form in _term_forms(token):
                score = _fuzzy_score(form, clean_term)

                if score:
                    ranked.append((score, term, form))

    if not ranked:
        return 0.0, None, None

    ranked.sort(reverse=True)

    best = ranked[0]
    runner_up = next(
        (
            row
            for row in ranked[1:]
            if row[1] != best[1]
        ),
        None,
    )

    if runner_up and best[0] - runner_up[0] < 0.08:
        return 0.0, None, None

    return best


def _genre_match(text: str):
    token_forms = {
        form
        for token in _tokens(text)
        for form in _term_forms(token)
    }

    for alias, genre in sorted(
        GENRE_ALIASES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if _clean(alias) in token_forms:
            return 0.98, genre, alias

    return _best_term(text, GENRES)

def _topic_match(text: str):
    """소재의 표준 표현과 별칭을 분석한다."""
    token_forms = {
        form
        for token in _tokens(text)
        for form in _term_forms(token)
    }

    clean_text = _clean(text)

    for alias, topic in sorted(
        TOPIC_ALIASES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        clean_alias = _clean(alias)

        if (
            clean_alias in token_forms
            or (
                len(clean_alias) >= 4
                and clean_alias in clean_text
            )
        ):
            return 0.98, topic, alias

    return _best_term(
        text,
        TOPICS,
        allow_fuzzy=False,
    )


def _attitude(text: str):
    value = re.sub(r"\s+", "", text).casefold()

    # 질문형 선호 표현은 실제 선호로 확정하지 않는다. 단, 문장 앞에
    # 이미 명시적 선호가 있고 끝에 "어때?"만 붙은 경우에는 아래의
    # 명시적 극성 규칙이 우선한다.
    if re.search(
        r"(어디|뭐야|무엇|몇분|좋아(?:해|하니|하냐|하지않아)|"
        r"싫어(?:해|하니|하냐)|보실|볼까)\?$",
        value,
    ):
        return "QUESTION", 0.0, 0.9

    if re.search(
        r"(절대.*싫|못봐|못보겠|빼줘|제외해|극혐)",
        value,
    ):
        return "STRONG_DISLIKE", -1.0, 0.96

    if re.search(
        r"(완전.*좋|진짜.*좋|꼭보고싶|최고|인생영화)",
        value,
    ):
        return "STRONG_LIKE", 1.0, 0.95

    if re.search(
        r"(있어야|필수|꼭있)",
        value,
    ):
        return "STRONG_LIKE", 1.0, 0.9

    if re.search(
        r"(나쁘지않|괜찮을듯|볼만|상관없진)",
        value,
    ):
        return "WEAK_LIKE", 0.3, 0.82

    if re.search(
        r"(한번더봐|또보자|다시보자|한번더보자)",
        value,
    ):
        return "WEAK_LIKE", 0.3, 0.86

    if re.search(
        r"(애매|잘모르겠|모르겠다|고민되|글쎄)",
        value,
    ):
        return "UNCERTAIN", -0.1, 0.72

    if re.search(
        r"(싫|별로|안좋아|좋아하지않|안보고싶|보고싶지않|말고|"
        r"취향아니|스타일아니|끌리지는않|아닌것같|재미없|"
        r"만아니면|아니면돼|아니면됨|빼고|제외)",
        value,
    ):
        return "DISLIKE", -0.6, 0.9

    if re.search(
        r"(좋|보고싶|끌려|재밌|취향|좋아해)",
        value,
    ):
        return "LIKE", 0.8, 0.9

    if re.search(
        r"(상관없|아무거나)",
        value,
    ):
        return "NEUTRAL", 0.0, 0.9

    if re.search(
        r"(?:\d{2,3}분|\d(?:\.\d)?시간).*(?:이하|안쪽|보다짧|넘지않)",
        value,
    ):
        return "WEAK_LIKE", 0.3, 0.86

    if re.search(
        r"(보자|이걸로얘기해보자|가능하면그렇게하자|내의견은그래)",
        value,
    ):
        return "WEAK_LIKE", 0.3, 0.78

    if re.search(r"(?:영화|작품|거)(?:없나|없어)\??$", value):
        return "QUESTION", 0.0, 0.9

    if text.rstrip().endswith("?"):
        return "QUESTION", 0.0, 0.85

    label, score, confidence = predict_attitude(text)

    return label, score, max(0.5, confidence)

def _split_preference_clauses(text: str) -> list[str]:
    """
    한 문장에 긍정·부정 취향이 섞였을 때
    대상별로 감정을 판단할 수 있도록 의미 단위로 분리한다.

    예:
    "마블 좋아하는데 로맨스는 별로야. 액션이나 SF가 좋아"
    ->
    [
        "마블 좋아",
        "로맨스는 별로야",
        "액션이나 SF가 좋아",
    ]
    """
    normalized = re.sub(r"\s+", " ", text).strip()
    # Do not treat the period in an English middle initial as a sentence end.
    normalized = re.sub(
        r"(?<=\b[A-Za-z])\.(?=\s+[A-Z])",
        "\u2024",
        normalized,
    )

    clauses = re.split(
        r"(?<=[.!?])\s*"
        r"|(?:지만|는데|은데|으나|반면에|하지만|그리고|그러나)\s*"
        r"|(?<=별로)고\s*"
        r"|(?<=싫)고\s*"
        r"|(?<=싫어)서\s*"
        r"|(?<=싫어)\s+(?=[0-9A-Za-z가-힣])"
        r"|(?<=싫음)\s+(?=[0-9A-Za-z가-힣])"
        r"|(?<=별로)\s+(?=[0-9A-Za-z가-힣])"
        r"|(?<=좋)고\s*"
        r"|(?<=좋아)\s+(?=[0-9A-Za-z가-힣])"
        r"|(?<=좋음)\s+(?=[0-9A-Za-z가-힣])",
        normalized,
    )
    return [
        clause.replace("\u2024", ".").strip(" ,.")
        for clause in clauses
        if clause and clause.strip(" ,.")
    ]


def _contains_term(clause: str, terms: list[str]) -> bool:
    clean_clause = _clean(clause)

    return any(
        _clean(term) and _clean(term) in clean_clause
        for term in terms
    )


def _local_preference_attitude(clause: str) -> tuple[str, float]:
    """
    특정 대상이 포함된 짧은 구절에서 긍정·부정을 판정한다.
    부정 표현을 먼저 검사해 '안 좋아', '별로'를 긍정으로
    잘못 해석하지 않도록 한다.
    """
    compact = _clean(clause)

    strong_dislike_patterns = (
        r"절대.*싫",
        r"극혐",
        r"못봐",
        r"못보겠",
        r"빼줘",
        r"제외",
    )

    dislike_patterns = (
        r"별로",
        r"별도다",
        r"싫",
        r"안좋",
        r"좋아하지않",
        r"안보고싶",
        r"취향아니",
        r"재미없",
        r"말고",
        r"아니면돼",
        r"아니면됨",
        r"만아니면",
        r"빼고",
        r"제외",
    )

    strong_like_patterns = (
        r"완전.*좋",
        r"진짜.*좋",
        r"꼭보고싶",
        r"최고",
        r"인생영화",
    )

    like_patterns = (
        r"좋$",
        r"좋아",
        r"선호",
        r"보고싶",
        r"재밌",
        r"끌려",
        r"더좋",
        r"추천",
        r"보고싶네",
        r"볼래",
        r"땡겨",
        r"땡긴",
        r"괜찮겠",
        r"한번볼까",
        r"보고싶은데",
        r"궁금",
    )

    if any(
        re.search(pattern, compact)
        for pattern in strong_dislike_patterns
    ):
        return "STRONG_DISLIKE", -1.0

    if any(
        re.search(pattern, compact)
        for pattern in dislike_patterns
    ):
        return "DISLIKE", -0.6

    if any(
        re.search(pattern, compact)
        for pattern in strong_like_patterns
    ):
        return "STRONG_LIKE", 1.0

    if any(
        re.search(pattern, compact)
        for pattern in like_patterns
    ):
        return "LIKE", 0.8

    return "NEUTRAL", 0.0


def _all_genre_mentions(text: str) -> list[tuple[str, list[str]]]:
    """
    문장에 포함된 모든 장르를 반환한다.

    반환 예:
    [
        ("코미디", ["코미디", "코메디"]),
        ("로맨스", ["로맨스", "로코", "멜로"]),
    ]
    """
    mentions: list[tuple[str, list[str]]] = []
    token_forms = {
        form
        for token in _tokens(text)
        for form in _term_forms(token)
    }

    for genre in GENRES:
        aliases = [
            alias
            for alias, mapped_genre in GENRE_ALIASES.items()
            if mapped_genre == genre
        ]

        terms = [genre, *aliases]

        if any(
            _clean(term) in token_forms
            for term in terms
            if _clean(term)
        ):
            mentions.append((genre, terms))

    return mentions


def _all_brand_mentions(text: str) -> list[tuple[str, list[str]]]:
    mentions: list[tuple[str, list[str]]] = []
    clean_text = _clean(text)

    grouped: dict[str, list[str]] = {}

    for alias, brand in BRAND_ALIASES.items():
        grouped.setdefault(brand, []).append(alias)

    for brand, aliases in grouped.items():
        terms = [brand, *aliases]

        if any(
            _clean(term) in clean_text
            for term in terms
            if _clean(term)
        ):
            mentions.append((brand, terms))

    return mentions


def _apply_multi_attribute_preferences(
    text: str,
    state: dict,
) -> None:
    """
    한 문장 안에 섞여 있는 여러 취향 조건을 각각 누적한다.

    처리 대상:
    - 복수 장르
    - 장르별 긍정·부정
    - 복수 브랜드
    - 브랜드별 긍정·부정
    - 2시간/120분 이하 조건
    """
    clauses = _split_preference_clauses(text)
    topic_groups: dict[str, list[str]] = {topic: [topic] for topic in TOPICS}
    for alias, topic in TOPIC_ALIASES.items():
        topic_groups.setdefault(topic, [topic]).append(alias)

    comparative_topic = re.search(
        r"(.+?)(?:것|거)?\s*(?:보다는|보단|보다)\s*(.+)",
        text,
    )
    comparative_topics: set[str] = set()
    if comparative_topic and re.search(
        r"좋|선호|낫|원해|보고\s*싶",
        comparative_topic.group(2),
    ):
        less_clause, preferred_clause = comparative_topic.groups()
        less_topics = {
            topic
            for topic, terms in topic_groups.items()
            if _contains_term(less_clause, terms)
        }
        preferred_topics = {
            topic
            for topic, terms in topic_groups.items()
            if _contains_term(preferred_clause, terms)
        }
        for topic in less_topics - preferred_topics:
            state["disliked_topics"][topic] = 0.6
            state["liked_topics"].pop(topic, None)
            comparative_topics.add(topic)
        for topic in preferred_topics:
            state["liked_topics"][topic] = 0.8
            state["disliked_topics"].pop(topic, None)
            comparative_topics.add(topic)
    comparative_country = re.search(
        r"(한국|국내|미국|미국산|일본|중국|영국|프랑스|외국|해외)\s*(?:영화|작품)?\s*보다는?\s*"
        r"(한국|국내|미국|미국산|일본|중국|영국|프랑스|외국|해외)\s*(?:영화|작품)?.{0,16}(?:좋|선호|보고\s*싶|낫)",
        text,
    )
    comparative_codes: tuple[str, str] | None = None
    if comparative_country:
        less_preferred = COUNTRY_ALIASES.get(comparative_country.group(1))
        preferred = COUNTRY_ALIASES.get(comparative_country.group(2))
        if less_preferred and preferred and less_preferred != preferred:
            comparative_codes = (less_preferred, preferred)
            if less_preferred not in state["excluded_countries"]:
                state["excluded_countries"].append(less_preferred)
            if less_preferred in state["countries"]:
                state["countries"].remove(less_preferred)
            if preferred not in state["countries"]:
                state["countries"].append(preferred)
            if preferred in state["excluded_countries"]:
                state["excluded_countries"].remove(preferred)

        # 국가별 긍정·부정 분석
    for clause in clauses:
        clause_countries = _detect_countries(
            clause
        )

        if not clause_countries:
            continue

        label, _score = (
            _local_preference_attitude(
                clause
            )
        )

        for country_code, _alias in clause_countries:
            if comparative_codes and country_code in comparative_codes:
                continue
            if label in {
                "DISLIKE",
                "STRONG_DISLIKE",
            }:
                if (
                    country_code
                    not in state["excluded_countries"]
                ):
                    state["excluded_countries"].append(
                        country_code
                    )

                if country_code in state["countries"]:
                    state["countries"].remove(
                        country_code
                    )

            elif label in {
                "LIKE",
                "STRONG_LIKE",
            }:
                if country_code not in state["countries"]:
                    state["countries"].append(
                        country_code
                    )

                if (
                    country_code
                    in state["excluded_countries"]
                ):
                    state["excluded_countries"].remove(
                        country_code
                    )

    # 장르별 감정 분석
    for genre, terms in _all_genre_mentions(text):
        matched_clauses = [
            clause
            for clause in clauses
            if _contains_term(clause, terms)
        ]

        if not matched_clauses:
            continue

        attitudes = [
            _local_preference_attitude(clause)
            for clause in matched_clauses
        ]

        negative = next(
            (
                score
                for label, score in attitudes
                if label in {"DISLIKE", "STRONG_DISLIKE"}
            ),
            None,
        )

        positive = next(
            (
                score
                for label, score in attitudes
                if label in {"LIKE", "STRONG_LIKE"}
            ),
            None,
        )

        if negative is not None:
            state["disliked_genres"][genre] = abs(negative)
            state["liked_genres"].pop(genre, None)

            if (
                negative <= -1.0
                and genre not in state["hard_exclusions"]
            ):
                state["hard_exclusions"].append(genre)

        elif positive is not None:
            state["liked_genres"][genre] = positive
            state["disliked_genres"].pop(genre, None)

    # 브랜드별 감정 분석
    for brand, terms in _all_brand_mentions(text):
        matched_clauses = [
            clause
            for clause in clauses
            if _contains_term(clause, terms)
        ]

        if not matched_clauses:
            continue

        attitudes = [
            _local_preference_attitude(clause)
            for clause in matched_clauses
        ]

        negative = next(
            (
                score
                for label, score in attitudes
                if label in {"DISLIKE", "STRONG_DISLIKE"}
            ),
            None,
        )

        positive = next(
            (
                score
                for label, score in attitudes
                if label in {"LIKE", "STRONG_LIKE"}
            ),
            None,
        )

        if negative is not None:
            state["disliked_brands"][brand] = abs(negative)
            state["liked_brands"].pop(brand, None)

        elif positive is not None:
            state["liked_brands"][brand] = positive
            state["disliked_brands"].pop(brand, None)

    # 분위기·소재별 감정 분석
    for topic, terms in topic_groups.items():
        if topic in comparative_topics:
            continue
        matched_clauses = [clause for clause in clauses if _contains_term(clause, terms)]
        attitudes = [_local_preference_attitude(clause) for clause in matched_clauses]
        negative = next((score for label, score in attitudes if label in {"DISLIKE", "STRONG_DISLIKE"}), None)
        positive = next((score for label, score in attitudes if label in {"LIKE", "STRONG_LIKE"}), None)
        if negative is not None:
            state["disliked_topics"][topic] = abs(negative)
            state["liked_topics"].pop(topic, None)
        elif positive is not None:
            state["liked_topics"][topic] = positive
            state["disliked_topics"].pop(topic, None)

    # 분 단위 러닝타임
    runtime_match = re.search(
        r"(\d{2,3})\s*분\s*"
        r"(?:이하|안쪽|안으로|내외|넘지\s*않|보다\s*짧)",
        text,
    )

    # 시간 단위 러닝타임
    hours_match = re.search(
        r"(\d(?:\.\d)?)\s*시간\s*"
        r"(?:이하|안쪽|안으로|내외|넘지\s*않|보다\s*짧)",
        text,
    )

    if runtime_match:
        state["max_runtime"] = int(runtime_match.group(1))

    elif hours_match:
        state["max_runtime"] = round(
            float(hours_match.group(1)) * 60
        )

def _extract_year_runtime_effects(
    text: str,
) -> list[tuple[str, str, float, str]]:
    effects: list[tuple[str, str, float, str]] = []
    compact = re.sub(r"\s+", "", text)

    year_after = re.search(
        r"(19\d{2}|20\d{2})\s*년?\s*(?:이후|부터)",
        text,
    )
    year_before = re.search(
        r"(19\d{2}|20\d{2})\s*년?\s*(?:이전|까지|보다\s*전)",
        text,
    )
    decade = re.search(
        r"((?:19|20)\d0)\s*년대",
        text,
    )
    recent = bool(
        re.search(
            r"(?:최신|최근|요즘|새로\s*나온|신작)",
            text,
        )
    )

    if year_after:
        effects.append(
            (
                "YEAR_MIN",
                year_after.group(1),
                0.8,
                "LIKE",
            )
        )
    elif year_before:
        effects.append(
            (
                "YEAR_MAX",
                year_before.group(1),
                0.8,
                "LIKE",
            )
        )
    elif decade:
        effects.append(
            (
                "YEAR_RANGE",
                decade.group(1),
                0.8,
                "LIKE",
            )
        )
    elif recent:
        effects.append(
            (
                "YEAR_MIN",
                "2020",
                0.9,
                "STRONG_LIKE",
            )
        )

    runtime_match = re.search(
        r"(\d{2,3})\s*분",
        text,
    )
    hours_match = re.search(
        r"(\d(?:\.\d)?)\s*시간",
        text,
    )
    korean_hours_match = re.search(
        r"([한두세])\s*시간",
        text,
    )

    minutes: int | None = None

    if runtime_match:
        minutes = int(runtime_match.group(1))
    elif hours_match:
        minutes = round(float(hours_match.group(1)) * 60)
    elif korean_hours_match:
        minutes = {
            "한": 60,
            "두": 120,
            "세": 180,
        }[korean_hours_match.group(1)]

    if minutes is not None:
        maximum_intent = bool(
            re.search(
                r"(?:이하|안쪽|안으로|내로|안넘|넘지않|보다짧)",
                compact,
            )
            or re.search(
                r"(?:이상|넘는|초과).{0,12}"
                r"(?:싫|안돼|별로|힘들|부담)",
                compact,
            )
        )

        minimum_intent = bool(
            re.search(
                r"(?:최소|적어도).{0,8}"
                r"(?:\d{2,3}분|\d(?:\.\d)?시간)",
                compact,
            )
            or re.search(
                r"(?:이상|넘는|초과).{0,12}"
                r"(?:좋|보고싶|원해|괜찮|상관없)",
                compact,
            )
        )

        if maximum_intent:
            effects.append(
                (
                    "CONSTRAINT",
                    str(minutes),
                    0.9,
                    "STRONG_LIKE",
                )
            )
        elif minimum_intent:
            effects.append(
                (
                    "MIN_RUNTIME",
                    str(minutes),
                    0.8,
                    "LIKE",
                )
            )

    return effects
    

def _extract_clause_effects(text: str) -> list[tuple[str, str, float, str]]:
    """한 발화의 복수 취향을 다음 발화의 '나도'가 계승할 수 있게 추출한다."""
    clauses = _split_preference_clauses(text)
    effects: list[tuple[str, str, float, str]] = []
    effects.extend(
        _extract_year_runtime_effects(text)
    )
    comparison_keys: set[tuple[str, str]] = set()

    # "액션보단 로맨스", "공포보다 코미디" 비교 표현은
    # 앞 대상을 약한 비선호, 뒤 대상을 선호로 각각 보존한다.
    comparison = re.search(
        r"([0-9A-Za-z가-힣]+?)\s*(?:보단|보다는|보다)\s*"
        r"([0-9A-Za-z가-힣]+)",
        text,
    )

    if comparison:
        left_text = comparison.group(1)
        right_text = comparison.group(2)

        _, left_genre, _ = _genre_match(left_text)
        _, right_genre, _ = _genre_match(right_text)

        if left_genre and right_genre and left_genre != right_genre:
            left_effect = (
                "GENRE",
                left_genre,
                -0.4,
                "DISLIKE",
            )
            right_effect = (
                "GENRE",
                right_genre,
                0.8,
                "LIKE",
            )

            effects.extend([left_effect, right_effect])
            comparison_keys.update(
                {
                    ("GENRE", left_genre),
                    ("GENRE", right_genre),
                }
            )

    groups: list[tuple[str, str, list[str]]] = []
    groups.extend(("GENRE", name, terms) for name, terms in _all_genre_mentions(text))
    groups.extend(("BRAND", name, terms) for name, terms in _all_brand_mentions(text))
    folded_text = text.casefold()
    compact_text = _clean(text)

    for alias, platform in OTT_ALIASES.items():
        folded_alias = alias.casefold()

        if platform == "디즈니+":
            matched = bool(
                re.search(
                    r"(?:디즈니\s*(?:플러스|\+)|디플|disney\s*plus)",
                    text,
                    re.IGNORECASE,
                )
            )
        else:
            matched = (
                folded_alias in folded_text
                if "+" in alias
                else _clean(alias) in compact_text
            )

        if not matched:
            continue

        groups.append(
            (
                "OTT",
                platform,
                [alias, platform],
            )
        )
    topic_groups: dict[str, list[str]] = {topic: [topic] for topic in TOPICS}
    for alias, topic in TOPIC_ALIASES.items():
        topic_groups.setdefault(topic, [topic]).append(alias)
    groups.extend(
        ("TOPIC", topic, terms)
        for topic, terms in topic_groups.items()
        if any(_contains_term(clause, terms) for clause in clauses)
    )

    for kind, target, terms in groups:
        # 비교 표현에서 이미 방향을 결정한 대상은
        # 문장 전체 감정으로 다시 계산하지 않는다.
        if (kind, target) in comparison_keys:
            continue

        clause = next(
            (
                value
                for value in clauses
                if _contains_term(value, terms)
            ),
            None,
        )

        if not clause:
            continue

        attitude, score = _local_preference_attitude(clause)

        if score != 0:
            effect = (
                kind,
                target,
                score,
                attitude,
            )
            if effect not in effects:
                effects.append(effect)
    # 국가별 복합문 성향을 개별 effect로 보존한다.
    # 예: "한국 영화는 좋아하는데 일본 영화는 싫어"
    #     -> COUNTRY/KR/LIKE + COUNTRY_EXCLUDE/JP/DISLIKE
    for clause in clauses:
        clause_countries = _detect_countries(clause)

        if not clause_countries:
            continue

        country_attitude, country_score = _local_preference_attitude(clause)

        if country_score == 0:
            continue

        for country_code, _alias in clause_countries:
            if country_score < 0:
                effect = (
                    "COUNTRY_EXCLUDE",
                    country_code,
                    country_score,
                    country_attitude,
                )
            else:
                effect = (
                    "COUNTRY",
                    country_code,
                    country_score,
                    country_attitude,
                )

            if effect not in effects:
                effects.append(effect)
              

    return effects


def _movie_match(
    text: str,
    movies: list[Movie],
):
    titles: list[tuple[str, str]] = []

    for movie in movies:
        titles.append((movie.title, movie.internal_id))

        if movie.original_title:
            titles.append(
                (
                    movie.original_title,
                    movie.internal_id,
                )
            )

    score = 0.0
    title = None
    token = None
    movie_id = None

    clean_text = _clean(text)
    tokens = [
        _clean(value)
        for value in re.findall(
            r"[0-9a-zA-Z가-힣]+",
            text,
        )
    ]
    domain_terms = {
        _clean(value)
        for value in [*GENRES, *GENRE_ALIASES, *TOPICS, *TOPIC_ALIASES]
    }
    non_title_terms = domain_terms | {
        "영화", "작품", "장르", "분위기", "형식", "추천", "좋아", "좋음",
        "싫어", "싫음", "별로", "나오는", "나온", "중에", "보고", "볼수있는",
    }
    tokens = [
        part
        for part in tokens
        if not (_term_forms(part) & non_title_terms)
    ]

    for candidate, candidate_id in titles:
        clean_candidate = _clean(candidate)

        if len(clean_candidate) < 2:
            continue

        token_exact = next(
            (
                part
                for part in tokens
                if part == clean_candidate
            ),
            None,
        )

        if token_exact or (
            len(clean_candidate) >= 5
            and clean_candidate in clean_text
        ):
            return (
                1.0,
                candidate,
                token_exact or candidate,
                candidate_id,
            )

        for part in tokens:
            if (
                len(part) >= 4
                and part in clean_candidate
                and len(part) / len(clean_candidate) >= 0.55
            ):
                return (
                    0.94,
                    candidate,
                    part,
                    candidate_id,
                )

            if (
                abs(len(part) - len(clean_candidate)) > 3
                or min(len(part), len(clean_candidate)) < 3
            ):
                continue

            current = rapidfuzz_ratio(
                part,
                clean_candidate,
            ) / 100.0

            if current > score:
                score = current
                title = candidate
                token = part
                movie_id = candidate_id

            for segment in re.split(
                r"[:：\-]",
                candidate,
            ):
                clean_segment = _clean(segment)

                if (
                    len(clean_segment) >= 3
                    and abs(len(part) - len(clean_segment)) <= 3
                ):
                    segment_score = rapidfuzz_ratio(
                        part,
                        clean_segment,
                    ) / 100.0

                    if segment_score > score:
                        score = segment_score
                        title = candidate
                        token = part
                        movie_id = candidate_id

    for alias, title_fragment in MOVIE_ALIASES.items():
        alias_score = 0.0
        alias_token = None

        for part in tokens:
            current = SequenceMatcher(
                None,
                part,
                _clean(alias),
            ).ratio()

            if current > alias_score:
                alias_score = current
                alias_token = part

        if alias_score >= 0.65:
            matched = next(
                (
                    movie
                    for movie in movies
                    if _clean(title_fragment)
                    in _clean(movie.title)
                ),
                None,
            )

            if matched:
                return (
                    0.9,
                    matched.title,
                    alias_token,
                    matched.internal_id,
                )

    has_movie_context = bool(
        re.search(
            r"(영화|작품|보고|보자|봤|같은|비슷|추천|재밌|싫|좋)",
            text,
        )
    )

    threshold = 0.84 if has_movie_context else 0.9

    if score >= threshold:
        return score, title, token, movie_id

    return 0.0, None, None, None


def _referenced_user(
    message,
    participant_ids: list[str],
):
    second_person = bool(
        re.search(
            r"(?<![가-힣])(?:넌|너는|네가|니가)(?![가-힣])"
            r"|너\s*따라"
            r"|너.*좋아하"
            r"|네.*취향",
            message.text,
        )
    )

    if second_person and len(participant_ids) == 2:
        return next(
            user_id
            for user_id in participant_ids
            if user_id != message.user_id
        )

    return None


def _apply_effect(
    state: dict,
    effect: tuple,
    movies: list[Movie],
) -> str:
    kind, target, value, _ = effect

    if kind == "GENRE":
        if value > 0:
            state["liked_genres"][target] = abs(value)
            state["disliked_genres"].pop(target, None)
        elif value < 0:
            state["disliked_genres"][target] = abs(value)
            state["liked_genres"].pop(target, None)

    elif kind == "TOPIC":
        if value > 0:
            state["liked_topics"][target] = abs(value)
            state["disliked_topics"].pop(target, None)
        elif value < 0:
            state["disliked_topics"][target] = abs(value)
            state["liked_topics"].pop(target, None)
    elif kind == "THEATER":
        state["prefers_theater"] = value > 0
    elif kind == "BRAND":
        if value > 0:
            state["liked_brands"][target] = abs(value)
            state["disliked_brands"].pop(target, None)
        elif value < 0:
            state["disliked_brands"][target] = abs(value)
            state["liked_brands"].pop(target, None)
    elif kind == "CONSTRAINT":
        runtime_match = re.search(r"\d{1,4}", str(target))
        if runtime_match is None:
            return str(target)
        state["max_runtime"] = int(runtime_match.group())

    elif kind == "MIN_RUNTIME":
        runtime_match = re.search(r"\d{1,4}", str(target))
        if runtime_match is None:
            return str(target)
        state["min_runtime"] = int(runtime_match.group())
        state["max_runtime"] = None
    elif kind == "YEAR":
        # 과거 코드 및 '나도' 호환용
        state["min_year"] = int(target)

    elif kind == "YEAR_MIN":
        state["min_year"] = int(target)

    elif kind == "YEAR_MAX":
        state["max_year"] = int(target)

    elif kind == "YEAR_RANGE":
        decade = int(target)
        state["min_year"] = decade
        state["max_year"] = decade + 9

    elif kind == "COUNTRY":
        state["countries"] = [target]
        if target in state["excluded_countries"]:
            state["excluded_countries"].remove(target)

    elif kind == "PERSON":
        return _apply_person_effect(state, target, value)
    
    elif kind == "COUNTRY_EXCLUDE":
        if target not in state["excluded_countries"]:
            state["excluded_countries"].append(target)

        if target in state["countries"]:
            state["countries"].remove(target)

    elif kind == "YEAR":
        year = int(target)

        if value >= 0:
            state["min_year"] = year
        else:
            state["max_year"] = year

    elif kind == "MOVIE":
        if value > 0:
            if target not in state["liked_movies"]:
                state["liked_movies"].append(target)
            if target not in state["direct_movies"]:
                state["direct_movies"].append(target)
            if target in state["disliked_movies"]:
                state["disliked_movies"].remove(target)
        elif value < 0:
            if target not in state["disliked_movies"]:
                state["disliked_movies"].append(target)
            if target in state["liked_movies"]:
                state["liked_movies"].remove(target)
            if target in state["direct_movies"]:
                state["direct_movies"].remove(target)

    elif kind == "OTT" and value > 0:
        if target not in state["ott_platforms"]:
            state["ott_platforms"].append(target)

    if kind == "MOVIE":
        return next(
            (
                movie.title
                for movie in movies
                if movie.internal_id == target
            ),
            target,
        )

    if kind == "YEAR":
        return f"{target}년 기준"

    return target


def _agreement_intent(text: str) -> str | None:
    """Classify short Korean agreement/rejection replies conservatively."""
    compact = _clean(text)
    raw = re.sub(r"\s+", "", text).casefold().strip(".!?~,，")

    if raw in {"+1", "＋1"}:
        return "AGREE"

    if re.fullmatch(
        r"(?:(?:그건|그거|나는|난|저는|전))?"
        r"(?:동의|인정|찬성)(?:은|는)?"
        r"(?:못해|못함|못하겠어|안해|안함|안할래|어려워|아니야)"
        r"|(?:나는|난|저는|전)?반대(?:야|함|합니다)?"
        r"|그건아니야|그거아니야|그건좀아닌데|그거좀아닌데",
        compact,
    ):
        return "DISAGREE"

    positive = {
        "나도", "저도", "저도요", "나역시", "저역시",
        "ㅇㅇ", "ㅇㅈ", "ㄹㅇ", "ㅇㅋ", "응", "네", "예",
        "맞아", "맞지", "그러게", "그렇지", "그래", "그러자",
        "콜", "오케이", "옼", "좋아", "좋지",
        "동의", "동의해", "동의함", "동의합니다",
        "인정", "인정해", "인정함", "인정합니다",
        "찬성", "찬성해", "찬성함", "찬성합니다",
        "그건인정", "그거인정", "완전동의", "진짜동의",
        "나는찬성", "난찬성", "저는찬성", "전찬성",
        "나도동의", "나도인정", "나도찬성",
    }
    if compact in positive or re.fullmatch(r"(?:ㅇㅈ|ㅇㅋ|응|맞아|콜)+", compact):
        return "AGREE"
    return None


def _contextual_polarity_reply(text: str) -> tuple[str, float] | None:
    """Return explicit polarity in replies such as '나도 싫어'."""
    compact = _clean(text)
    if not re.fullmatch(
        r"(?:나도|저도|나역시|저역시)(?:는)?"
        r"(?:완전|진짜)?(?:좋아|좋음|좋지|싫어|싫음|별로|극혐)",
        compact,
    ):
        return None
    attitude, score, _confidence = _attitude(text)
    if score == 0:
        return None
    return attitude, score


def _invert_inherited_effect(effect: tuple) -> tuple | None:
    kind, target, value, _attitude_label = effect
    if kind not in {"GENRE", "TOPIC", "BRAND", "PERSON", "MOVIE"}:
        return None
    if value > 0:
        return kind, target, -max(0.6, min(1.0, abs(value))), "DISLIKE"
    if value < 0:
        # Rejecting a dislike means tolerance/weak preference, not a strong like.
        return kind, target, 0.3, "WEAK_LIKE"
    return None


def analyze_chat(
    request: ChatAnalyzeRequest,
    movies: list[Movie],
) -> ChatAnalyzeResponse:
    states: dict[str, dict] = {}
    analyses: list[MessageAnalysis] = []
    people_index = _build_people_index(movies)

    last_effect = None
    last_effects: list[tuple[str, str, float, str]] = []

    focus_movie = None

    effects_by_message: dict[int, tuple] = {}
    questions_by_message: dict[int, tuple] = {}
    pending_question_by_user: dict[str, tuple] = {}

    participant_ids = list(
        dict.fromkeys(
            message.user_id
            for message in request.messages
        )
    )

    for message in request.messages:
        state = states.setdefault(
            message.user_id,
            _empty_state(),
        )

        compact = _clean(message.text)
        disney_plus_detected = bool(
            re.search(
                r"(?:디즈니\s*(?:플러스|\+)|디플|disney\s*plus)",
                message.text,
                re.IGNORECASE,
            )
        )

        detected_otts = list(
            dict.fromkeys(
                platform
                for alias, platform in OTT_ALIASES.items()
                if (
                    (
                        platform == "디즈니+"
                        and disney_plus_detected
                    )
                    or (
                        platform != "디즈니+"
                        and (
                            (
                                "+" in alias
                                and alias.casefold()
                                in message.text.casefold()
                            )
                            or (
                                "+" not in alias
                                and _clean(alias) in compact
                            )
                        )
                    )
                )
            )
        )

        detected_ott = (
            detected_otts[0]
            if detected_otts
            else None
        )
        detected_ott = detected_otts[0] if detected_otts else None

        if detected_ott:
            ott_negative = bool(re.search(
                r"(싫|안\s*써|안\s*씀|구독\s*안|해지|없어|빼|제외)",
                message.text,
            ))
            ott_usage_intent = bool(re.search(
                r"(구독|가입|가임|사용|쓰고|써|보유|결제|결재|"
                r"(?:에서|으로|로)\s*(?:볼|보는|볼수|볼\s*수|보자|추천)|"
                r"만\s*(?:볼|보는|보자|추천)|플러스|\+|디플)",
                message.text,
                re.IGNORECASE,
            ))
            if ott_negative:
                for platform in detected_otts:
                    if platform in state["ott_platforms"]:
                        state["ott_platforms"].remove(platform)
            elif ott_usage_intent:
                for platform in detected_otts:
                    if platform not in state["ott_platforms"]:
                        state["ott_platforms"].append(platform)
                ott_effects = [
                    ("OTT", platform, 1.0, "LIKE")
                    for platform in detected_otts
                ]

                last_effects = ott_effects

                if ott_effects:
                    last_effect = ott_effects[-1]

                ott_effects = [
                    ("OTT", platform, 1.0, "LIKE")
                    for platform in detected_otts
                ]
                last_effects = ott_effects
                last_effect = ott_effects[-1]

            strict_ott = bool(
                re.search(
                    r"(에서만|만\s*볼|만\s*보자|"
                    r"만\s*추천|그거만|해당\s*OTT만|"
                    r"(?:에서|으로|로)\s*볼\s*수\s*있는\s*(?:영화|작품)(?:로|만)?)",
                    message.text,
                    re.IGNORECASE,
                )
            )

            if strict_ott:
                state["ott_strict"] = True

        theater_keywords = (
            "영화관",
            "극장",
            "현재상영",
            "상영중",
            "지금상영",
            "지금하는영화",
            "현재하는영화",
            "개봉작",
            "cgv",
            "메가박스",
            "롯데시네마",
        )

        theater_negative = bool(
            re.search(
                r"(?:영화관|극장).{0,8}(?:말고|빼고|싫|안\s*가|가지\s*말)",
                message.text,
                re.IGNORECASE,
            )
        )

        if any(
            keyword in compact
            for keyword in theater_keywords
        ) and not theater_negative:
            state["prefers_theater"] = True
        elif theater_negative:
            state["prefers_theater"] = False

        question_context = (
            questions_by_message.get(
                message.reply_to_message_id
            )
            if message.reply_to_message_id
            else None
        ) or pending_question_by_user.get(
            message.user_id
        )

        agreement_intent = _agreement_intent(message.text)
        agrees = agreement_intent == "AGREE"
        disagrees = agreement_intent == "DISAGREE"
        contextual_polarity = _contextual_polarity_reply(message.text)
        inline_agreement = bool(
            re.match(
                r"^\s*(?:나도|저도|나 역시|저 역시)(?:\s+|[,，])",
                message.text,
            )
        ) and contextual_polarity is None

        ambiguous_rejection = bool(
            re.fullmatch(
                r"아니+|아니야+|ㄴㄴ+|노+",
                compact,
            )
        )

        if ambiguous_rejection and question_context:
            kind, target, _, _ = question_context

            display_target = (
                next(
                    (
                        movie.title
                        for movie in movies
                        if movie.internal_id == target
                    ),
                    target,
                )
                if kind == "MOVIE"
                else target
            )

            analyses.append(
                MessageAnalysis(
                    user_id=message.user_id,
                    text=message.text,
                    target=display_target,
                    target_type=kind,
                    attitude="UNCERTAIN",
                    preference_score=0.0,
                    confidence=0.35,
                    note=(
                        "단답 '아니'는 의미가 모호해 "
                        "성향에 반영하지 않음"
                    ),
                )
            )

            pending_question_by_user.pop(
                message.user_id,
                None,
            )
            continue

        agreement_effect = (
            question_context
            or (
                effects_by_message.get(
                    message.reply_to_message_id
                )
                if message.reply_to_message_id
                else last_effect
            )
        )

        inherited_effects = (
            [agreement_effect]
            if question_context or message.reply_to_message_id
            else (last_effects or ([agreement_effect] if agreement_effect else []))
        )

        resolved_agreement_effects: list[tuple] = []
        if agrees:
            resolved_agreement_effects = list(inherited_effects)
        elif disagrees:
            resolved_agreement_effects = [
                inverted
                for inherited_effect in inherited_effects
                if (inverted := _invert_inherited_effect(inherited_effect)) is not None
            ]
        elif contextual_polarity:
            contextual_attitude, contextual_score = contextual_polarity
            resolved_agreement_effects = [
                (kind, target, contextual_score, contextual_attitude)
                for kind, target, _value, _attitude_label in inherited_effects
                if kind in {"GENRE", "TOPIC", "BRAND", "PERSON", "MOVIE"}
            ]

        if resolved_agreement_effects:
            for inherited_effect in resolved_agreement_effects:
                kind, target, value, attitude = inherited_effect
                display_target = _apply_effect(state, inherited_effect, movies)
                if kind == "CONSTRAINT":
                    display_target = f"최대 {target}분"
                elif kind == "MIN_RUNTIME":
                    display_target = f"최소 {target}분"
                elif kind == "YEAR":
                    display_target = f"{target}년 기준"
                analyses.append(
                    MessageAnalysis(
                        user_id=message.user_id,
                        text=message.text,
                        target=display_target,
                        target_type=kind,
                        attitude=attitude,
                        preference_score=value,
                        confidence=0.82 if agrees else 0.78,
                        person_id=(
                            target.get("person_id")
                            if kind == "PERSON" and isinstance(target, dict)
                            else None
                        ),
                        person_role=(
                            target.get("role")
                            if kind == "PERSON" and isinstance(target, dict)
                            else None
                        ),
                        note=(
                            "직전 의견의 복수 성향에 동의하여 본인 성향으로 반영"
                            if agrees
                            else (
                                "직전 의견에 대한 명시적 반대를 반대 극성으로 반영"
                                if disagrees
                                else "직전 대상에 대한 현재 답장의 명시적 극성을 반영"
                            )
                        ),
                    )
                )

            if message.message_id is not None:
                effects_by_message[
                    message.message_id
                ] = resolved_agreement_effects[-1]

            last_effect = resolved_agreement_effects[-1]
            last_effects = resolved_agreement_effects

            pending_question_by_user.pop(
                message.user_id,
                None,
            )
            continue

        if inline_agreement and agreement_effect:
            inherited_kind, inherited_target, inherited_value, inherited_attitude = agreement_effect
            inherited_display_target = _apply_effect(state, agreement_effect, movies)
            analyses.append(
                MessageAnalysis(
                    user_id=message.user_id,
                    text=message.text,
                    target=inherited_display_target,
                    target_type=inherited_kind,
                    attitude=inherited_attitude,
                    preference_score=inherited_value,
                    confidence=0.78,
                    person_id=(
                        inherited_target.get("person_id")
                        if inherited_kind == "PERSON" and isinstance(inherited_target, dict)
                        else None
                    ),
                    person_role=(
                        inherited_target.get("role")
                        if inherited_kind == "PERSON" and isinstance(inherited_target, dict)
                        else None
                    ),
                    note="문장 앞의 동의 표현을 직전 의견과 연결해 본인 성향으로 반영",
                )
            )

        (
            attitude,
            preference_score,
            attitude_confidence,
        ) = _attitude(message.text)

        # 배우/감독 문맥을 영화 제목 유사도 검색보다 먼저 판정한다.
        # "혜리 나오는 영화"가 제목 "혜리"로 잘못 연결되는 것을 막는다.
        detected_people = _detect_people(
            message.text,
            movies,
            people_index,
        )

        # 이름 뒤에 역할이 명시된 경우 해당 역할만 남긴다.
        # 예: "장항준 감독"을 ACTOR와 DIRECTOR로 중복 저장하지 않음.
        explicit_director_names = {
            _clean(match.group(1))
            for match in re.finditer(
                r"([0-9A-Za-z가-힣]{2,20})(?:은|는|이|가)?\s*"
                r"(?:감독|연출)",
                message.text,
                re.IGNORECASE,
            )
        }

        explicit_actor_names = {
            _clean(match.group(1))
            for match in re.finditer(
                r"([0-9A-Za-z가-힣]{2,20})(?:은|는|이|가)?\s*"
                r"(?:배우|출연|주연|나오(?:는|ㄴ)?|나온)",
                message.text,
                re.IGNORECASE,
            )
        }

        detected_people = [
            (name, role)
            for name, role in detected_people
            if not (
                (_clean(name) in explicit_director_names and role != "DIRECTOR")
                or
                (_clean(name) in explicit_actor_names and role != "ACTOR")
            )
        ]

        # "A 감독보다는 B 감독" 비교문을 따로 판별한다.
        person_comparison = re.search(
            r"([0-9A-Za-z가-힣]{2,20})(?:은|는|이|가)?\s*"
            r"(?:배우|감독|연출)?\s*(?:보단|보다는|보다)\s*"
            r"([0-9A-Za-z가-힣]{2,20})(?:은|는|이|가)?\s*"
            r"(?:배우|감독|연출)?",
            message.text,
            re.IGNORECASE,
        )
        person_request_context = bool(
            detected_people
            and re.search(
                r"(?:배우|감독|연출|출연|나오|나온|나오는|주연|감독작|만든\s*영화)",
                message.text,
                re.IGNORECASE,
            )
        )

        if person_request_context:
            movie_score = 0.0
            movie_title = None
            original_token = None
            movie_id = None
        else:
            (
                movie_score,
                movie_title,
                original_token,
                movie_id,
            ) = _movie_match(
                message.text,
                movies,
            )

        if (
            not movie_title
            and focus_movie
            and re.fullmatch(
                r"(?:나는?|난|저는?|전)?\s*"
                r"(?:(?:이거|그거|그\s*영화)(?:는|은|이|가)?\s*)?"
                r"(?:이미\s*(?:봤(?:어|음)?|봄)|봤어|봤음|"
                r"한\s*번\s*더\s*봐|다시\s*볼래|"
                r"싫어|싫음|별로(?:야|임)?|좋아|좋음|괜찮아|상관없어?)",
                message.text.strip(),
            )
        ):
            movie_id, movie_title = focus_movie
            movie_score = 0.84
            original_token = None

        if movie_title and movie_id:
            focus_movie = (
                movie_id,
                movie_title,
            )

        observed_only = bool(re.fullmatch(
            r"(?:나는?|난|저는?|전)?\s*"
            r"(?:(?:이거|그거|그\s*영화)(?:는|은|이|가)?\s*)?"
            r"(?:이미\s*)?(?:봤(?:어|음)?|봄|본\s*적\s*있어)",
            message.text.strip(),
        ))
        if observed_only and movie_title:
            attitude = "NEUTRAL"
            preference_score = 0.0
            attitude_confidence = 0.95

        (
            genre_score,
            genre,
            genre_token,
        ) = _genre_match(message.text)

        (
            topic_score,
            topic,
            topic_token,
        ) = _topic_match(message.text)

        brand = next(
            (
                name
                for alias, name
                in BRAND_ALIASES.items()
                if _clean(alias)
                in _clean(message.text)
            ),
            None,
        )

        # "디즈니+ 구독"은 Disney 콘텐츠 브랜드 취향이 아니라 OTT
        # 이용 조건이다. 명시적인 OTT 표현에서는 브랜드 판정을 막는다.
        if detected_ott and re.search(
            r"(플러스|\+|디플|구독|가입|가임|OTT|(?:에서|으로|로)\s*(?:볼|보는|볼\s*수|보자|추천))",
            message.text,
            re.IGNORECASE,
        ):
            brand = None

        referenced_user = _referenced_user(
            message,
            participant_ids,
        )

        ambiguous_reference = (
            referenced_user is None
            and len(participant_ids) > 2
            and bool(
                re.search(
                    r"(넌|너는|네가|니가|너\s*따라|"
                    r"너.*좋아하|네.*취향)",
                    message.text,
                )
            )
        )

        if ambiguous_reference:
            attitude = "UNCERTAIN"
            preference_score = 0.0
            attitude_confidence = 0.35

        if (
            brand
            and referenced_user
            and re.search(
                r"(너\s*따라|네가.*좋아|니가.*좋아)",
                message.text,
            )
            and preference_score < 0
        ):
            other_state = states.setdefault(
                referenced_user,
                _empty_state(),
            )

            other_state["liked_brands"][brand] = 0.8
            state["disliked_brands"][brand] = abs(
                preference_score
            )

            analyses.append(
                MessageAnalysis(
                    user_id=referenced_user,
                    text=message.text,
                    target=brand,
                    target_type="BRAND",
                    attitude="LIKE",
                    preference_score=0.8,
                    confidence=0.82,
                    note=(
                        f"{message.user_id}의 상대방 선호 언급을 "
                        f"{referenced_user} 성향으로 반영"
                    ),
                )
            )

            analyses.append(
                MessageAnalysis(
                    user_id=message.user_id,
                    text=message.text,
                    target=brand,
                    target_type="BRAND",
                    attitude=attitude,
                    preference_score=preference_score,
                    confidence=0.9,
                    note=(
                        "직접 표현한 비선호를 "
                        "본인 성향으로 반영"
                    ),
                )
            )

            last_effect = (
                "BRAND",
                brand,
                preference_score,
                attitude,
            )

            if message.message_id is not None:
                effects_by_message[
                    message.message_id
                ] = last_effect

            continue

        analysis_user_id = message.user_id

        if referenced_user and (
            genre
            or brand
            or topic
        ):
            analysis_user_id = referenced_user
            state = states.setdefault(
                referenced_user,
                _empty_state(),
            )

        target = None
        target_type = "UNKNOWN"
        corrected_from = None

        if detected_ott:
            target = detected_ott
            target_type = "OTT"
            if detected_ott in state["ott_platforms"]:
                last_effects = [
                    ("OTT", platform, 1.0, "LIKE")
                    for platform in detected_otts
                    if platform in state["ott_platforms"]
                ]
                last_effect = last_effects[-1]

        detected_country = _detect_country(
            message.text
        )
        detected_countries = _detect_countries(
            message.text
        )
        # "외국/해외 영화"는 특정 국가가 아니라
        # 한국(KR)을 제외한 전체 국가 범위로 처리한다.
        foreign_movie_mentioned = bool(
            re.search(
                r"(?:외국|해외)\s*(?:영화|작품)",
                message.text,
            )
        )

        foreign_movie_negative = bool(
            foreign_movie_mentioned
            and re.search(
                r"(?:싫|별로|빼|제외|말고|안\s*봐|못\s*봐)",
                message.text,
            )
        )

        foreign_movie_positive = bool(
            foreign_movie_mentioned
            and not foreign_movie_negative
            and re.search(
                r"(?:좋|좋아|선호|잘\s*봐|잘봐|잘\s*보|"
                r"보고\s*싶|볼래|괜찮|상관\s*없)",
                message.text,
            )
        )
        if detected_people and original_token:
            clean_movie_token = _clean(original_token)
            if any(
                clean_movie_token in _clean(person_name)
                or _clean(person_name) in clean_movie_token
                for person_name, _person_type in detected_people
            ) and re.search(r"(?:배우|감독|출연|나오|나온|주연|작품)", message.text):
                if focus_movie and focus_movie[0] == movie_id:
                    focus_movie = None
                movie_score = 0.0
                movie_title = None
                movie_id = None
                original_token = None

        korean_only = bool(
            re.search(
                r"(?:외국|해외)\s*영화.{0,8}"
                r"(?:별로|싫|빼|제외|안\s*봐|못\s*봐)",
                message.text,
            )
            or re.search(
                r"(?:한국|국내)\s*영화.{0,5}"
                r"(?:만|위주)",
                message.text,
            )
        )

        year_after_match = re.search(
            r"(19\d{2}|20\d{2})\s*년?\s*"
            r"(?:이후|뒤|부터)",
            message.text,
        )

        year_before_match = re.search(
            r"(19\d{2}|20\d{2})\s*년?\s*"
            r"(?:이전|전까지|보다\s*전)",
            message.text,
        )

        decade_match = re.search(
            r"((?:19|20)\d0)\s*년대",
            message.text,
        )

        recent_intent = bool(
            re.search(
                r"(?:최신|최근|요즘|새로\s*나온|신작)"
                r"\s*영화",
                message.text,
            )
            or re.search(
                r"(?:최신|최근|요즘|신작).*"
                r"(?:보고|볼래|추천|원해|좋아|보자)",
                message.text,
            )
        )

        old_dislike_intent = bool(
            re.search(
                r"(?:오래된|옛날|고전).*"
                r"(?:안\s*봐|빼줘|제외|말고|별로|싫어)",
                message.text,
            )
        )

        old_like_intent = bool(
            re.search(
                r"(?:오래된|옛날|고전|레트로).*"
                r"(?:좋아|보고|볼래|선호)",
                message.text,
            )
        )

        runtime = re.search(
            r"(\d{2,3})\s*분",
            message.text,
        )

        hours = re.search(
            r"(\d(?:\.\d)?)\s*시간",
            message.text,
        )
        korean_hours = re.search(r"([한두세])\s*시간", message.text)

        person_results: list[tuple[dict, str, float]] = []

        if detected_people:
            people_clauses = _split_preference_clauses(message.text)

            for person_name, person_type in detected_people:
                clean_person_name = _clean(person_name)
                person_tokens = [
                    _clean(token)
                    for token in re.findall(
                        r"[0-9A-Za-z가-힣]{2,}",
                        person_name,
                    )
                ]
                person_tokens.extend(
                    _clean(alias)
                    for alias, (canonical_name, alias_role)
                    in KNOWN_PERSON_ALIASES.items()
                    if canonical_name == person_name
                    and alias_role == person_type
                )

                matching_clause = next(
                    (
                        clause
                        for clause in people_clauses
                        if clean_person_name in _clean(clause)
                        or any(
                            token and token in _clean(clause)
                            for token in person_tokens
                        )
                    ),
                    None,
                )

                if matching_clause is None:
                    continue

                person_forms = {
                    clean_person_name,
                    *person_tokens,
                }

                if person_comparison:
                    less_preferred = _clean(
                        person_comparison.group(1)
                    )
                    more_preferred = _clean(
                        person_comparison.group(2)
                    )

                    if less_preferred in person_forms:
                        # "봉준호보다는 장항준"의 봉준호
                        person_attitude = "DISLIKE"
                        person_score = -0.4

                    elif more_preferred in person_forms:
                        # "봉준호보다는 장항준"의 장항준
                        person_attitude = "LIKE"
                        person_score = 0.8

                    else:
                        person_attitude, person_score = (
                            _local_preference_attitude(
                                matching_clause
                            )
                        )
                else:
                    person_attitude, person_score = (
                        _local_preference_attitude(
                            matching_clause
                        )
                    )

                if person_score == 0:
                    continue

                person_reference = _person_reference(
                    person_name,
                    person_type,
                    movies,
                    person_score,
                )
                person_results.append(
                    (person_reference, person_attitude, person_score)
                )
                _apply_person_effect(state, person_reference, person_score)
            # "엠마 왓슨 나왔으면 좋겠다", "봉준호 감독 영화 좋아"처럼
            # 인물 역할 문맥이 명확한 경우에는 짧은 영화 제목 오탐보다
            # 인물 분석 결과를 우선한다.
            explicit_person_context = bool(
                person_results
                and re.search(
                    r"(?:배우|감독|출연|주연|"
                    r"나오(?:는|면|길|고|ㄴ)?|나왔|나온|"
                    r"연출|만든\s*영화)",
                    message.text,
                )
            )

            if explicit_person_context and movie_title:
                movie_score = 0.0
                movie_title = None
                movie_id = None
                original_token = None
                focus_movie = None
            if not movie_title and person_results:
                # 인물 선호와 최신작 조건은 동시에 존재할 수 있다.
                if recent_intent:
                    state["min_year"] = 2020

                for person_reference, person_attitude, person_score in person_results:
                    person_name = _person_display_name(person_reference)
                    analyses.append(
                        MessageAnalysis(
                            user_id=message.user_id,
                            text=message.text,
                            target=person_name,
                            target_type="PERSON",
                            attitude=person_attitude,
                            preference_score=person_score,
                            confidence=0.9,
                            person_id=person_reference.get("person_id"),
                            person_role=person_reference.get("role"),
                            note="인물별 구절의 성향을 분리해 반영",
                        )
                    )

                last_effects = [
                    ("PERSON", reference, score, label)
                    for reference, label, score in person_results
                ]
                if recent_intent:
                    analyses.append(
                        MessageAnalysis(
                            user_id=message.user_id,
                            text=message.text,
                            target="2020년 이후 최신 영화",
                            target_type="YEAR",
                            attitude="LIKE",
                            preference_score=0.8,
                            confidence=0.9,
                            note="인물 선호와 최신작 조건을 함께 반영",
                        )
                    )
                    last_effects.append(
                        ("YEAR", "2020", 0.8, "LIKE")
                    )
                last_effect = last_effects[-1]
                continue

        if foreign_movie_positive:
            # 외국 영화 선호
            # = 특정 한 국가를 지정하는 것이 아니라 한국만 제외
            state["countries"] = []

            if "KR" not in state["excluded_countries"]:
                state["excluded_countries"].append("KR")

            target = "외국 영화 (한국 제외)"
            target_type = "COUNTRY"

            # "잘봐"는 기존 일반 attitude 규칙에서 선호로 잡히지 않을 수 있으므로
            # 이 문맥에서는 명시적으로 선호로 확정한다.
            attitude = "LIKE"
            preference_score = 0.8
            attitude_confidence = max(
                attitude_confidence,
                0.95,
            )

            # 다음 사람이 "나도"라고 했을 때도
            # 동일하게 한국 제외 조건을 계승할 수 있도록 effect 저장
            last_effect = (
                "COUNTRY_EXCLUDE",
                "KR",
                -1.0,
                "STRONG_DISLIKE",
            )

            last_effects = [last_effect]


        elif korean_only:
            state["countries"] = ["KR"]

            # 이전에 "외국 영화 좋아"라고 해서 KR이 제외되어 있었다면 해제
            if "KR" in state["excluded_countries"]:
                state["excluded_countries"].remove("KR")

            target = "한국 영화만"
            target_type = "COUNTRY"

            attitude = "STRONG_LIKE"
            preference_score = 1.0

            last_effect = (
                "COUNTRY",
                "KR",
                1.0,
                "STRONG_LIKE",
            )

            last_effects = [last_effect]


        elif detected_countries:
            country_codes = [
                code
                for code, _alias in detected_countries
            ]
            comparative_country_match = re.search(
                r"(한국|국내|미국|미국산|일본|중국|영국|프랑스|외국|해외)\s*(?:영화|작품)?\s*보다는?\s*"
                r"(한국|국내|미국|미국산|일본|중국|영국|프랑스|외국|해외)\s*(?:영화|작품)?.{0,16}(?:좋|선호|보고\s*싶|낫)",
                message.text,
            )

            negative_country_intent = bool(
                re.search(
                    r"(?:싫|별로|빼|제외|말고|"
                    r"안\s*봐|못\s*봐)",
                    message.text,
                )
            )

            if comparative_country_match:
                less_raw = comparative_country_match.group(1)
                preferred_raw = comparative_country_match.group(2)

                # 한국보다 외국 영화 선호
                if (
                    less_raw in {"한국", "국내"}
                    and preferred_raw in {"외국", "해외"}
                ):
                    state["countries"] = []

                    if "KR" not in state["excluded_countries"]:
                        state["excluded_countries"].append("KR")

                    target = "외국 영화 선호 / 한국 영화 제외"
                    target_type = "COUNTRY"

                    attitude = "STRONG_LIKE"
                    preference_score = 0.9

                    last_effect = (
                        "COUNTRY_EXCLUDE",
                        "KR",
                        -1.0,
                        "STRONG_DISLIKE",
                    )

                    last_effects = [last_effect]

                # 외국보다 한국 영화 선호
                elif (
                    less_raw in {"외국", "해외"}
                    and preferred_raw in {"한국", "국내"}
                ):
                    state["countries"] = ["KR"]

                    if "KR" in state["excluded_countries"]:
                        state["excluded_countries"].remove("KR")

                    target = "한국 영화 선호"
                    target_type = "COUNTRY"

                    attitude = "STRONG_LIKE"
                    preference_score = 0.9

                    last_effect = (
                        "COUNTRY",
                        "KR",
                        0.9,
                        "STRONG_LIKE",
                    )

                    last_effects = [last_effect]

                else:
                    less_preferred = COUNTRY_ALIASES.get(less_raw)
                    preferred = COUNTRY_ALIASES.get(preferred_raw)

                    if (
                        less_preferred
                        and preferred
                        and less_preferred != preferred
                    ):
                        state["countries"] = [preferred]

                        if less_preferred not in state["excluded_countries"]:
                            state["excluded_countries"].append(
                                less_preferred
                            )

                        if preferred in state["excluded_countries"]:
                            state["excluded_countries"].remove(
                                preferred
                            )

                        target = (
                            f"{COUNTRY_LABELS.get(preferred, preferred)} 영화 선호 / "
                            f"{COUNTRY_LABELS.get(less_preferred, less_preferred)} 영화 비선호"
                        )

                        target_type = "COUNTRY"

                        last_effect = (
                            "COUNTRY",
                            preferred,
                            0.9,
                            "STRONG_LIKE",
                        )

                        last_effects = [last_effect]
            
                state["countries"] = [preferred]
                if less_preferred not in state["excluded_countries"]:
                    state["excluded_countries"].append(less_preferred)
                if preferred in state["excluded_countries"]:
                    state["excluded_countries"].remove(preferred)
                target = (
                    f"{COUNTRY_LABELS.get(preferred, preferred)} 영화 선호 / "
                    f"{COUNTRY_LABELS.get(less_preferred, less_preferred)} 영화 비선호"
                )
                target_type = "COUNTRY"
                last_effect = ("COUNTRY", preferred, 0.9, "STRONG_LIKE")

            elif negative_country_intent:
                for country_code in country_codes:
                    if (
                        country_code
                        not in state["excluded_countries"]
                    ):
                        state["excluded_countries"].append(
                            country_code
                        )

                    if country_code in state["countries"]:
                        state["countries"].remove(
                            country_code
                        )

                target = " / ".join(
                    COUNTRY_LABELS.get(
                        code,
                        alias,
                    )
                    for code, alias
                    in detected_countries
                ) + " 영화 제외"

                target_type = "COUNTRY"

                last_effect = (
                    "COUNTRY_EXCLUDE",
                    country_codes[0],
                    -1.0,
                    "STRONG_DISLIKE",
                )

            else:
                state["countries"] = country_codes

                for country_code in country_codes:
                    if (
                        country_code
                        in state["excluded_countries"]
                    ):
                        state["excluded_countries"].remove(
                            country_code
                        )

                target = " / ".join(
                    COUNTRY_LABELS.get(
                        code,
                        alias,
                    )
                    for code, alias
                    in detected_countries
                ) + " 영화"

                target_type = "COUNTRY"

                last_effect = (
                    "COUNTRY",
                    country_codes[0],
                    0.9,
                    "STRONG_LIKE",
                )


        elif year_after_match:
            year = int(
                year_after_match.group(1)
            )

            state["min_year"] = year
            target = f"{year}년 이후 개봉작"
            target_type = "YEAR"

            last_effect = (
                "YEAR",
                str(year),
                0.8,
                attitude,
            )

        elif year_before_match:
            year = int(
                year_before_match.group(1)
            )

            state["max_year"] = year
            target = f"{year}년 이전 개봉작"
            target_type = "YEAR"

            last_effect = (
                "YEAR",
                str(year),
                -0.8,
                attitude,
            )

        elif decade_match:
            decade = int(
                decade_match.group(1)
            )

            state["min_year"] = decade
            state["max_year"] = decade + 9

            target = f"{decade}년대 영화"
            target_type = "YEAR"

            last_effect = (
                "YEAR",
                str(decade),
                0.8,
                attitude,
            )

        elif old_dislike_intent or recent_intent:
            state["min_year"] = 2020
            target = "2020년 이후 최신 영화"
            target_type = "YEAR"

            last_effect = (
                "YEAR",
                "2020",
                0.9,
                "STRONG_LIKE",
            )

        elif old_like_intent:
            state["max_year"] = 2018
            target = "2018년 이전 고전 영화"
            target_type = "YEAR"

            last_effect = (
                "YEAR",
                "2018",
                -0.8,
                "LIKE",
            )

        elif runtime or hours or korean_hours:
            minutes = (
                int(runtime.group(1))
                if runtime
                else ({"한": 60, "두": 120, "세": 180}[korean_hours.group(1)] if korean_hours else int(
                    float(hours.group(1))
                    * 60
                ))
            )

            compact_message = message.text.replace(
                " ",
                "",
            )

            maximum_runtime_intent = bool(
                re.search(r"(?:이하|안쪽|안으로|내로|안넘|넘지않|보다짧)", compact_message)
                or re.search(
                    r"(?:이상|넘는|초과).{0,12}(?:싫|안돼|별로|힘들|떨어|부담)",
                    compact_message,
                )
            )
            minimum_runtime_intent = bool(
                re.search(
                    r"(?:이상|넘는|초과).{0,12}(?:좋|보고싶|원해|괜찮|상관없|길|잘봄|잘봐|가능|문제없)",
                    compact_message,
                )
                or re.search(
                    r"(?:최소|적어도).{0,8}(?:\d{2,3}분|\d(?:\.\d)?시간)",
                    compact_message,
                )
            )

            if maximum_runtime_intent:
                state["max_runtime"] = minutes

                last_effect = (
                    "CONSTRAINT",
                    str(minutes),
                    preference_score,
                    attitude,
                )

                target = f"최대 {minutes}분"
            elif minimum_runtime_intent:
                state["min_runtime"] = minutes
                state["max_runtime"] = None
                last_effect = (
                    "MIN_RUNTIME",
                    str(minutes),
                    max(preference_score, 0.6),
                    "LIKE",
                )
                target = f"최소 {minutes}분"
            else:
                target = f"러닝타임 {minutes}분 언급"
            target_type = "CONSTRAINT"

        elif detected_people and not movie_title:
            target = ", ".join(name for name, _kind in detected_people)
            target_type = "PERSON"

        elif movie_title and not brand:
            target = movie_title
            target_type = "MOVIE"

            corrected_from = (
                original_token
                if (
                    original_token
                    and _clean(original_token)
                    != _clean(movie_title)
                )
                else None
            )

            similar_request = bool(
                re.search(
                    r"(같은|비슷한|느낌의)",
                    message.text,
                )
            )

            already_seen = bool(
                re.search(
                    r"(봤|봐서|많이\s*봐|여러\s*번\s*봐|본\s*적|이미\s*봄|"
                    r"재밌었|인생영화)",
                    message.text,
                )
            )

            rewatch_allowed = bool(
                re.search(
                    r"(다시|또).*"
                    r"(봐도|볼래|보자|괜찮|상관없|돼)",
                    message.text,
                )
            )

            wants_different = bool(
                re.search(
                    r"(봤|봐서|많이\s*봐|여러\s*번\s*봐|본\s*적|이미).*"
                    r"(다른\s*(거|영화).*"
                    r"(보고\s*싶|보자)|새로운\s*거)",
                    message.text,
                )
            )

            watched_dislike = bool(
                re.search(
                    r"(봤|본\s*적|이미).*"
                    r"(별로|재미없|싫|취향\s*아니)",
                    message.text,
                )
            )

            if rewatch_allowed:
                if re.search(
                    r"상관없",
                    message.text,
                ):
                    attitude = "NEUTRAL"
                    preference_score = 0.0
                else:
                    attitude = "WEAK_LIKE"
                    preference_score = 0.3

            direct_request = bool(
                re.search(
                    r"(보고싶|보자|볼래|보실|볼까|예매)",
                    message.text,
                )
            ) and not similar_request

            if (
                already_seen
                or similar_request
            ) and movie_id not in state["seen_movies"]:
                state["seen_movies"].append(
                    movie_id
                )

            if (
                rewatch_allowed
                and movie_id
                not in state["rewatch_allowed_movies"]
            ):
                state[
                    "rewatch_allowed_movies"
                ].append(movie_id)

            if (
                watched_dislike
                and movie_title
                not in state["disliked_movies"]
            ):
                state["disliked_movies"].append(
                    movie_title
                )

            if preference_score > 0:
                if (
                    movie_id
                    not in state["liked_movies"]
                ):
                    state["liked_movies"].append(
                        movie_id
                    )

                if (
                    direct_request
                    and movie_id
                    not in state["direct_movies"]
                ):
                    state["direct_movies"].append(
                        movie_id
                    )

                last_effect = (
                    "MOVIE",
                    movie_id,
                    preference_score,
                    attitude,
                )

            elif preference_score < -0.4:
                if (
                    movie_title
                    not in state["disliked_movies"]
                ):
                    state["disliked_movies"].append(
                        movie_title
                    )

            if (
                wants_different
                and movie_id
                in state["rewatch_allowed_movies"]
            ):
                state[
                    "rewatch_allowed_movies"
                ].remove(movie_id)

        elif brand:
            target = brand
            target_type = "BRAND"

            if preference_score > 0:
                state["liked_brands"][brand] = (
                    preference_score
                )
                state["disliked_brands"].pop(
                    brand,
                    None,
                )

            elif preference_score < 0:
                state["disliked_brands"][brand] = abs(
                    preference_score
                )
                state["liked_brands"].pop(
                    brand,
                    None,
                )

            if preference_score != 0:
                last_effect = (
                    "BRAND",
                    brand,
                    preference_score,
                    attitude,
                )

        elif genre:
            target = genre
            target_type = "GENRE"

            corrected_from = (
                genre_token
                if (
                    genre_token
                    and _clean(genre_token)
                    != _clean(genre)
                )
                else None
            )

            compact_message = _clean(
                message.text
            )

            normalized_genre = _clean(
                genre_token or genre
            )

            short_genre_preference = bool(
                preference_score == 0
                and attitude
                not in {
                    "QUESTION",
                    "DISLIKE",
                    "STRONG_DISLIKE",
                    "UNCERTAIN",
                }
                and (
                    re.search(
                        (
                            r"^(?:나|난|나는|저|전|저는)?"
                            rf".{{0,6}}{re.escape(normalized_genre)}"
                            r"(?:영화|장르|으로|로)?$"
                        ),
                        compact_message,
                        re.IGNORECASE,
                    )
                    or re.search(
                        (
                            rf"{re.escape(normalized_genre)}"
                            r".{0,12}"
                            r"(?:아무거나|상관없|괜찮|"
                            r"좋음|좋아|보자|보고싶|볼래)"
                        ),
                        compact_message,
                        re.IGNORECASE,
                    )
                )
            )

            if short_genre_preference:
                preference_score = 0.6
                attitude = "WEAK_LIKE"
                attitude_confidence = max(
                    attitude_confidence,
                    0.82,
                )

            if preference_score > 0:
                state["liked_genres"][genre] = (
                    preference_score
                )

                state["disliked_genres"].pop(
                    genre,
                    None,
                )

            elif preference_score < 0:
                state["disliked_genres"][genre] = abs(
                    preference_score
                )

                state["liked_genres"].pop(
                    genre,
                    None,
                )

            if (
                attitude == "STRONG_DISLIKE"
                and genre
                not in state["hard_exclusions"]
            ):
                state["hard_exclusions"].append(
                    genre
                )

            if preference_score != 0:
                last_effect = (
                    "GENRE",
                    genre,
                    preference_score,
                    attitude,
                )

            if (
                topic
                and preference_score < 0
            ):
                state["disliked_topics"][topic] = abs(
                    preference_score
                )

        elif topic:
            target = topic
            target_type = "TOPIC"

            corrected_from = (
                topic_token
                if (
                    topic_token
                    and _clean(topic_token)
                    != _clean(topic)
                )
                else None
            )

            if preference_score > 0:
                state["liked_topics"][topic] = (
                    preference_score
                )
                state["disliked_topics"].pop(
                    topic,
                    None,
                )

            elif preference_score < 0:
                state["disliked_topics"][topic] = abs(
                    preference_score
                )
                state["liked_topics"].pop(
                    topic,
                    None,
                )

            if preference_score != 0:
                last_effect = (
                    "TOPIC",
                    topic,
                    preference_score,
                    attitude,
                )

        if genre and target_type != "GENRE":
            genre_expression = re.escape(
                genre_token or genre
            )

            genre_like = bool(
                re.search(
                    rf"(?:{genre_expression}).{{0,12}}"
                    rf"(?:좋아|좋음|좋고|선호|보고\s*싶|재밌)",
                    message.text,
                    re.IGNORECASE,
                )
                or re.search(
                    rf"(?:좋아|선호|재밌|보고\s*싶).{{0,12}}"
                    rf"(?:{genre_expression})",
                    message.text,
                    re.IGNORECASE,
                )
            )

            genre_dislike = bool(
                re.search(
                    rf"(?:{genre_expression}).{{0,8}}"
                    rf"(?:싫어|싫음|별로|비선호|안\s*좋아)",
                    message.text,
                    re.IGNORECASE,
                )
                or re.search(
                    rf"(?:싫어|별로|비선호|안\s*좋아).{{0,8}}"
                    rf"(?:{genre_expression})",
                    message.text,
                    re.IGNORECASE,
                )
            )

            if genre_like and not genre_dislike:
                state["liked_genres"][genre] = 0.8
                state["disliked_genres"].pop(
                    genre,
                    None,
                )

            elif genre_dislike:
                state["disliked_genres"][genre] = 0.6
                state["liked_genres"].pop(
                    genre,
                    None,
                )

        _apply_multi_attribute_preferences(
            message.text,
            state,
        )
        current_clause_effects = _extract_clause_effects(message.text)

        if current_clause_effects:
            # 복합문 분석 결과를 화면 출력에만 사용하지 않고
            # 실제 사용자 누적 상태에도 모두 적용한다.
            for clause_effect in current_clause_effects:
                _apply_effect(state, clause_effect, movies)
                effect_kind, effect_target, effect_score, _ = clause_effect
                if (
                    effect_kind == "GENRE"
                    and effect_score <= -1.0
                    and effect_target not in state["hard_exclusions"]
                ):
                    state["hard_exclusions"].append(effect_target)
            last_effects = current_clause_effects
            last_effect = current_clause_effects[-1]
        elif detected_otts and ott_usage_intent:
            last_effects = [
                ("OTT", platform, 1.0, "LIKE")
                for platform in detected_otts
            ]
            last_effect = last_effects[-1]
        if len(current_clause_effects) > 1:
            for (
                multi_kind,
                multi_target,
                multi_score,
                multi_attitude,
            ) in current_clause_effects:
                normalized_kind = (
                    "YEAR"
                    if multi_kind in {"YEAR_MIN", "YEAR_MAX", "YEAR_RANGE"}
                    else "CONSTRAINT"
                    if multi_kind == "MIN_RUNTIME"
                    else "COUNTRY"
                    if multi_kind == "COUNTRY_EXCLUDE"
                    else multi_kind
                )
                analyses.append(
                    MessageAnalysis(
                        user_id=analysis_user_id,
                        text=message.text,
                        target=str(multi_target),
                        target_type=normalized_kind,
                        attitude=multi_attitude,
                        preference_score=multi_score,
                        confidence=0.9,
                        note="복합문장에서 개별 취향을 분리 추출",
                    )
                )

        if False and len(current_clause_effects) > 1:
            for (
                effect_kind,
                effect_target,
                effect_score,
                effect_attitude,
            ) in current_clause_effects:

                display_target = effect_target
                display_type = effect_kind
            if effect_kind == "YEAR_MIN":
                display_target = f"{effect_target}년 이후 개봉작"
                display_type = "YEAR"

            elif effect_kind == "YEAR_MAX":
                display_target = f"{effect_target}년 이전 개봉작"
                display_type = "YEAR"

            elif effect_kind == "YEAR_RANGE":
                display_target = f"{effect_target}년대 영화"
                display_type = "YEAR"

            elif effect_kind == "CONSTRAINT":
                display_target = f"최대 {effect_target}분"
                display_type = "CONSTRAINT"

            elif effect_kind == "MIN_RUNTIME":
                display_target = f"최소 {effect_target}분"
                display_type = "CONSTRAINT"
                if effect_kind in {
                    "COUNTRY",
                    "COUNTRY_EXCLUDE",
                }:
                    display_target = (
                        COUNTRY_LABELS.get(
                            effect_target,
                            effect_target,
                        )
                        + " 영화"
                    )
                    display_type = "COUNTRY"

                analyses.append(
                    MessageAnalysis(
                        user_id=analysis_user_id,
                        text=message.text,
                        target=display_target,
                        target_type=display_type,
                        attitude=effect_attitude,
                        preference_score=effect_score,
                        confidence=0.9,
                        note="복합문에서 개별 취향을 분리 추출",
                    )
                )        
        if detected_ott and re.search(
            r"(플러스|\+|디플|구독|가입|가임|OTT|(?:에서|으로|로)\s*(?:볼|보는|볼\s*수|보자|추천))",
            message.text,
            re.IGNORECASE,
        ):
            state["liked_brands"].pop("Disney", None)
            state["disliked_brands"].pop("Disney", None)

        # 세 명 이상인 방에서 '너'의 대상이 특정되지 않으면 어떤
        # 사용자에게도 추측 반영하지 않는다. 위의 복합문장 추출기가
        # 먼저 잡은 값도 이 지점에서 되돌린다.
        if ambiguous_reference:
            if genre:
                state["liked_genres"].pop(genre, None)
                state["disliked_genres"].pop(genre, None)
                if genre in state["hard_exclusions"]:
                    state["hard_exclusions"].remove(genre)
            if brand:
                state["liked_brands"].pop(brand, None)
                state["disliked_brands"].pop(brand, None)
            if topic:
                state["liked_topics"].pop(topic, None)
                state["disliked_topics"].pop(topic, None)

        if (
            target is None
            and question_context
            and attitude
            not in {
                "QUESTION",
                "NEUTRAL",
                "UNCERTAIN",
            }
            and preference_score != 0
        ):
            (
                kind,
                context_target,
                _,
                _,
            ) = question_context

            contextual_effect = (
                kind,
                context_target,
                preference_score,
                attitude,
            )

            display_target = _apply_effect(
                state,
                contextual_effect,
                movies,
            )

            if kind == "CONSTRAINT":
                target = f"최대 {context_target}분"

            elif kind == "YEAR":
                target = f"{context_target}년 기준"

            else:
                target = display_target

            target_type = kind
            last_effect = contextual_effect

            pending_question_by_user.pop(
                message.user_id,
                None,
            )

        target_confidence = (
            movie_score
            or genre_score
            or topic_score
            or (0.98 if brand else 0)
            or (
                0.98
                if target_type == "COUNTRY"
                else 0
            )
            or (
                0.95
                if target_type == "YEAR"
                else 0
            )
            or (
                0.9
                if target_type == "CONSTRAINT"
                else 0.45
            )
        )

        confidence = round(
            min(
                attitude_confidence,
                target_confidence,
            ),
            2,
        )

        if (
            preference_score != 0
            and target_type
            in {
                "GENRE",
                "TOPIC",
                "BRAND",
            }
        ):
            last_effect = (
                target_type,
                target,
                preference_score,
                attitude,
            )

        if (
            attitude == "QUESTION"
            and target is not None
            and target_type != "UNKNOWN"
        ):
            compact_question = _clean(
                message.text
            )

            negative_question = bool(
                re.search(
                    r"싫|별로|안좋아",
                    compact_question,
                )
            ) and (
                "좋아하지않아"
                not in compact_question
            )

            proposed_value = (
                -0.6
                if negative_question
                else 0.8
            )

            proposed_attitude = (
                "DISLIKE"
                if negative_question
                else "LIKE"
            )

            if target_type == "COUNTRY":
                proposed_target = "KR"

            elif (
                target_type == "MOVIE"
                and movie_id
            ):
                proposed_target = movie_id

            elif (
                target_type == "YEAR"
                and (
                    year_after_match
                    or year_before_match
                    or decade_match
                )
            ):
                year_match = (
                    year_after_match
                    or year_before_match
                    or decade_match
                )

                proposed_target = (
                    year_match.group(1)
                )

            else:
                proposed_target = target

            question_effect = (
                target_type,
                proposed_target,
                proposed_value,
                proposed_attitude,
            )

            question_user = (
                analysis_user_id
                if analysis_user_id
                != message.user_id
                else next(
                    (
                        user
                        for user in participant_ids
                        if user
                        != message.user_id
                    ),
                    message.user_id,
                )
            )

            pending_question_by_user[
                question_user
            ] = question_effect

            if message.message_id is not None:
                questions_by_message[
                    message.message_id
                ] = question_effect

        elif (
            message.message_id is not None
            and last_effect is not None
            and target is not None
        ):
            effects_by_message[
                message.message_id
            ] = last_effect

        if ambiguous_reference:
            note = (
                "대상 사용자가 불명확해 "
                "성향에 반영하지 않음"
            )

        elif analysis_user_id != message.user_id:
            note = (
                f"{message.user_id}가 말한 상대방 성향을 "
                f"{analysis_user_id}에게 반영"
            )

        elif attitude == "QUESTION":
            note = (
                "질문은 답변 전까지 "
                "성향에 반영하지 않음"
            )

        elif (
            target
            and attitude
            not in {
                "NEUTRAL",
                "UNCERTAIN",
            }
        ):
            note = "문맥을 연결해 점수 반영"

        else:
            note = "성향 점수 미반영"

        if len(current_clause_effects) > 1:
            continue

        analyses.append(
            MessageAnalysis(
                user_id=analysis_user_id,
                text=message.text,
                target=target,
                target_type=target_type,
                attitude=attitude,
                preference_score=preference_score,
                confidence=confidence,
                corrected_from=corrected_from,
                note=note,
            )
        )

    invalid_people = {
        "나", "나는", "근데", "배우", "배우가",
        "감독", "감독이", "연출", "만든", "나오는",
    }

    # 세부 분석은 올바른데 후속 보조 규칙이 누적 상태를 다시
    # 뒤집는 경우를 방지한다. 동일 사용자의 최신 명시적 분석을
    # 최종 상태의 극성 기준으로 확정한다.
    for analysis in analyses:
        if analysis.preference_score == 0 or analysis.target is None:
            continue

        final_state = states.get(analysis.user_id)
        if final_state is None:
            continue

        if analysis.target_type == "GENRE":
            genre_name = str(analysis.target)
            if analysis.preference_score > 0:
                final_state["liked_genres"][genre_name] = (
                    analysis.preference_score
                )
                final_state["disliked_genres"].pop(
                    genre_name,
                    None,
                )
            else:
                final_state["disliked_genres"][genre_name] = abs(
                    analysis.preference_score
                )
                final_state["liked_genres"].pop(
                    genre_name,
                    None,
                )
                if (
                    analysis.attitude == "STRONG_DISLIKE"
                    and genre_name not in final_state["hard_exclusions"]
                ):
                    final_state["hard_exclusions"].append(genre_name)

        elif analysis.target_type == "PERSON":
            person_name = str(analysis.target)
            if person_name in invalid_people:
                continue
            if analysis.preference_score > 0:
                if person_name not in final_state["liked_people"]:
                    final_state["liked_people"].append(person_name)
                if person_name in final_state["disliked_people"]:
                    final_state["disliked_people"].remove(person_name)
            else:
                if person_name not in final_state["disliked_people"]:
                    final_state["disliked_people"].append(person_name)
                if person_name in final_state["liked_people"]:
                    final_state["liked_people"].remove(person_name)

    # 이전 경로에서 이미 들어온 역할 단어도 최종 결과에서 제거한다.
    for final_state in states.values():
        final_state["liked_people"] = [
            name
            for name in final_state["liked_people"]
            if name not in invalid_people
        ]
        final_state["disliked_people"] = [
            name
            for name in final_state["disliked_people"]
            if name not in invalid_people
        ]

    members = [
        Preference(
            user_id=user_id,
            **state,
        )
        for user_id, state in states.items()
    ]

    return ChatAnalyzeResponse(
        members=members,
        analyses=analyses,
    )
