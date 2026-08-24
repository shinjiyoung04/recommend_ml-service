import json
from pathlib import Path

from meetup_ml.recommender import _normalize_movie_title


def test_required_movies_100():
    movies = json.load(
        open(
            Path("data/normalized/movies.json"),
            encoding="utf-8",
        )
    )

    required = json.load(
        open(
            Path("tests/required_movies_100.json"),
            encoding="utf-8",
        )
    )

    index = {}

    for movie in movies:
        for value in (
            movie.get("title"),
            movie.get("title_ko"),
            movie.get("title_en"),
            movie.get("original_title"),
        ):
            normalized = _normalize_movie_title(value)

            if normalized:
                key = (
                    normalized,
                    movie.get("tmdb_id"),
                )
                index[key] = movie["internal_id"]

    failed = []

    for expected in required:
        key = (
            _normalize_movie_title(expected["title"]),
            expected.get("tmdb_id"),
        )

        actual_id = index.get(key)

        if actual_id != expected["internal_id"]:
            failed.append(
                {
                    "title": expected["title"],
                    "tmdb_id": expected.get("tmdb_id"),
                    "expected": expected["internal_id"],
                    "actual": actual_id,
                }
            )

    assert failed == [], f"검색 회귀 실패: {failed}"