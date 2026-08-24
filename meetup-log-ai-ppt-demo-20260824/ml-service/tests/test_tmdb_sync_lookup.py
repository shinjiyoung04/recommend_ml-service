import json
import os
import pytest

if not (os.getenv("TMDB_API_TOKEN") or os.getenv("TMDB_API_KEY")):
    pytest.skip("manual TMDB smoke check requires credentials", allow_module_level=True)

from meetup_ml.collectors import search_tmdb_movie_sync


movies = json.load(
    open(
        "data/normalized/movies.json",
        encoding="utf-8",
    )
)

catalog_ids = {
    movie.get("tmdb_id")
    for movie in movies
}

candidates = [
    "Bugonia",
    "The Smashing Machine",
    "Rental Family",
    "Hamnet",
    "Sentimental Value",
    "Marty Supreme",
    "The Chronology of Water",
    "Mother Mary",
]

for query in candidates:
    movie = search_tmdb_movie_sync(query)

    if not movie:
        print(query, "-> TMDB_NOT_FOUND")
        continue

    registered = movie.tmdb_id in catalog_ids

    print(
        query,
        "->",
        movie.tmdb_id,
        movie.title,
        "registered=",
        registered,
    )

    if not registered:
        print("FOUND_UNREGISTERED")
        print("tmdb_id=", movie.tmdb_id)
        print("title=", movie.title)
        print("original_title=", movie.original_title)
        print("eligible=", movie.recommendation_eligible)
        break
else:
    print("NO_UNREGISTERED_FOUND")
