from pathlib import Path
import pytest

pytest.skip("manual catalog mutation smoke script", allow_module_level=True)

from meetup_ml.api import _analyze_corrected
from meetup_ml.schemas import ChatMessage
from meetup_ml.storage import JsonStore


movies = JsonStore(Path("data")).load_movies(use_fixture=False)

before = any(
    movie.tmdb_id == 1105422
    for movie in movies
)

print("before=", before)
print("count_before=", len(movies))
def _extract_tmdb_query(text: str) -> str | None:
    value = text.strip()

    patterns = [
        r"(.+?)\s*영화\s*(?:보고\s*싶|볼래|보자|추천|봤어|봤는데)",
        r"(.+?)\s*(?:보고\s*싶|볼래|보자|추천해줘|추천)",
    ]

    for pattern in patterns:
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip(" ,.!?\"'")
            if len(candidate) >= 2:
                return candidate

    return None
result = _analyze_corrected(
    [
        ChatMessage(
            user_id="u1",
            text="Sentimental Value 영화 보고 싶어",
        )
    ],
    movies,
)

after = any(
    movie.tmdb_id == 1105422
    for movie in movies
)

print("after=", after)
print("count_after=", len(movies))

print(
    "analyses=",
    [
        (
            item.target_type,
            item.target,
            item.attitude,
        )
        for item in result.analyses
    ],
)
