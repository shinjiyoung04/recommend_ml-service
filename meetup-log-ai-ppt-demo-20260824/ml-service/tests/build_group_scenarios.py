import json
from itertools import combinations
from pathlib import Path

MOVIE_PATH = Path("data/normalized/movies.json")
OUTPUT_PATH = Path("data/group_recommendation_scenarios.json")

movies = json.load(open(MOVIE_PATH, encoding="utf-8"))

genre_pairs = [
    ("SF", "드라마"),
    ("액션", "SF"),
    ("판타지", "모험"),
    ("범죄", "스릴러"),
    ("로맨스", "드라마"),
    ("코미디", "드라마"),
    ("액션", "모험"),
    ("미스터리", "스릴러"),
    ("판타지", "액션"),
    ("범죄", "드라마"),
    ("SF", "모험"),
    ("코미디", "로맨스"),
    ("드라마", "스릴러"),
    ("액션", "범죄"),
    ("애니메이션", "모험"),
    ("가족", "판타지"),
    ("전쟁", "드라마"),
    ("서부", "드라마"),
    ("공포", "스릴러"),
    ("미스터리", "드라마"),
]

# 20개 조합을 두 번씩 사용해 40개 시나리오 생성
pairs = (genre_pairs * 2)[:40]

eligible = [
    m for m in movies
    if m.get("recommendation_eligible")
    and m.get("genres")
    and m.get("overview")
]

scenarios = []

for i, (g1, g2) in enumerate(pairs, start=1):
    candidates = []

    for movie in eligible:
        genres = set(movie.get("genres", []))

        both_match = g1 in genres and g2 in genres
        one_match = g1 in genres or g2 in genres

        if both_match or one_match:
            score = (
                (2 if both_match else 1),
                movie.get("vote_count", 0),
                movie.get("vote_average", 0),
            )
            candidates.append((score, movie))

    candidates.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    # A valid group result must satisfy both members when the catalog contains
    # such titles. Do not encode popularity rank into ground truth: reranking is
    # intentionally allowed to trade popularity for fairness and diversity.
    both = [movie["internal_id"] for _, movie in candidates if g1 in movie.get("genres", []) and g2 in movie.get("genres", [])]
    acceptable = both or [movie["internal_id"] for _, movie in candidates]

    scenarios.append(
        {
            "scenario_id": f"group-{i:03d}",
            "members": [
                {
                    "user_id": "u1",
                    "liked_genres": {g1: 1.0},
                },
                {
                    "user_id": "u2",
                    "liked_genres": {g2: 1.0},
                },
            ],
            "acceptable_movie_ids": acceptable,
        }
    )

json.dump(
    scenarios,
    open(OUTPUT_PATH, "w", encoding="utf-8"),
    ensure_ascii=False,
    indent=2,
)

print("saved=", len(scenarios))
print("output=", OUTPUT_PATH)
