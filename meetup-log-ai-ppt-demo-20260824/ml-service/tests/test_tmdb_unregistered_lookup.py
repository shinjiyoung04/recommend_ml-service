import asyncio
import json
import os
import pytest

if not (os.getenv("TMDB_API_TOKEN") or os.getenv("TMDB_API_KEY")):
    pytest.skip("manual TMDB smoke check requires credentials", allow_module_level=True)

from meetup_ml.collectors import search_tmdb_movie


async def main():
    movies = json.load(
        open(
            "data/normalized/movies.json",
            encoding="utf-8",
        )
    )

    catalog_tmdb_ids = {
        movie.get("tmdb_id")
        for movie in movies
    }

    candidates = [
        "더 웨일",
        "애프터썬",
        "패스트 라이브즈",
        "로봇 드림",
        "퍼펙트 데이즈",
    ]

    for title in candidates:
        movie = await search_tmdb_movie(title)

        if movie and movie.tmdb_id not in catalog_tmdb_ids:
            print("query=", title)
            print("catalog_has=False")
            print("tmdb_id=", movie.tmdb_id)
            print("title=", movie.title)
            print("original_title=", movie.original_title)
            print("eligible=", movie.recommendation_eligible)
            return

    print("NO_UNREGISTERED_FOUND")


asyncio.run(main())
