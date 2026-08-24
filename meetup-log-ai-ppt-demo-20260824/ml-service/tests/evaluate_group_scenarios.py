import json
from datetime import datetime, timezone
from pathlib import Path

from meetup_ml.recommender import recommend
from meetup_ml.schemas import GroupRecommendRequest, Preference
from meetup_ml.storage import JsonStore


movies = JsonStore(Path("data")).load_movies(use_fixture=False)

scenarios = json.load(
    open(
        "data/group_recommendation_scenarios.json",
        encoding="utf-8",
    )
)

hits = 0
accepted_count = 0
total_recommendations = 0

for scenario in scenarios:
    request = GroupRecommendRequest(
        room_id=scenario["scenario_id"],
        round_id="eval",
        members=[
            Preference(**member)
            for member in scenario["members"]
        ],
        limit=3,
    )

    result = recommend(movies, request)

    top3 = [
        item.movie.internal_id
        for item in result.recommendations[:3]
    ]

    acceptable = set(scenario["acceptable_movie_ids"])

    matched = acceptable.intersection(top3)

    hit = bool(matched)

    hits += int(hit)
    accepted_count += len(matched)
    total_recommendations += len(top3)

    print(
        scenario["scenario_id"],
        "HIT" if hit else "MISS",
        top3,
        "accepted=",
        len(matched),
    )

hit_rate = hits / len(scenarios)

acceptance_rate = (
    accepted_count / total_recommendations
    if total_recommendations
    else 0.0
)

report = {
    "evaluated_at": datetime.now(timezone.utc).isoformat(),
    "scenario_count": len(scenarios),
    "hit_rate_at_3": round(hit_rate, 4),
    "acceptance_rate_at_3": round(acceptance_rate, 4),
    "hits": hits,
}
output = Path("evaluation/group_scenarios_40.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
print("saved=", output)
