"""Catalog-grounded evaluation for person scoring, context inheritance and 3-card output.

This is a component validation over real TMDB credit IDs in the frozen catalog.
It deliberately does not label the result as real-user acceptance evidence.
"""

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from meetup_ml.chat_analysis import analyze_chat
from meetup_ml.person_identity import canonical_person_name, movie_person_aliases
from meetup_ml.recommender import member_fit, recommend
from meetup_ml.schemas import (
    ChatAnalyzeRequest,
    GroupRecommendRequest,
    PersonCredit,
    PersonPreference,
    Preference,
)
from meetup_ml.storage import JsonStore


POSITIVE_REPLIES = [
    "나도", "동의", "인정", "찬성", "그건 인정", "맞지", "그러게", "+1", "ㅇㅈ",
]
NEGATIVE_REPLIES = [
    "동의 못 해", "인정 못해", "찬성 안 해", "반대", "나도 싫어",
]


def _credit_index(movies, role: str):
    index = defaultdict(list)
    for movie in movies:
        credits = movie.cast_people if role == "ACTOR" else movie.director_people
        if not credits:
            names = movie.cast if role == "ACTOR" else movie.directors
            credits = [PersonCredit(name=name, role=role) for name in names]
        seen_in_movie = set()
        for credit in credits:
            canonical = canonical_person_name(credit.original_name or credit.name)
            if not canonical:
                continue
            identity = (
                f"id:{credit.person_id}"
                if credit.person_id is not None
                else f"name:{canonical}"
            )
            if identity in seen_in_movie:
                continue
            seen_in_movie.add(identity)
            index[identity].append((movie, credit))
    return index


def _candidate_pool(movies, target, credit, role: str, size: int = 10):
    target_genres = set(target.genres)

    def contains_person(movie) -> bool:
        movie_credits = movie.cast_people if role == "ACTOR" else movie.director_people
        if credit.person_id is not None and movie_credits:
            return any(item.person_id == credit.person_id for item in movie_credits)
        aliases = {
            canonical_person_name(value)
            for value in (credit.name, credit.original_name)
            if value
        }
        return bool(aliases & movie_person_aliases(movie, role))

    distractors = [
        movie
        for movie in movies
        if movie.internal_id != target.internal_id
        and not contains_person(movie)
        and target_genres.intersection(movie.genres)
    ]
    distractors.sort(
        key=lambda movie: (
            abs(movie.vote_average - target.vote_average),
            abs(movie.popularity - target.popularity),
            movie.internal_id,
        )
    )
    if len(distractors) < size - 1:
        existing = {movie.internal_id for movie in distractors}
        distractors.extend(
            movie
            for movie in movies
            if movie.internal_id != target.internal_id
            and movie.internal_id not in existing
            and not contains_person(movie)
        )
    return [target, *distractors[: size - 1]]


def _person_preference(credit, role: str, polarity: str) -> Preference:
    field = {
        ("ACTOR", "LIKE"): "liked_actors",
        ("ACTOR", "DISLIKE"): "disliked_actors",
        ("DIRECTOR", "LIKE"): "liked_directors",
        ("DIRECTOR", "DISLIKE"): "disliked_directors",
    }[(role, polarity)]
    person = PersonPreference(
        person_id=credit.person_id,
        name=credit.name,
        original_name=credit.original_name,
        role=role,
        identity_source="TMDB_ID",
    )
    return Preference(user_id="eval-user", **{field: [person]})


def evaluate_role(movies, role: str, max_people: int = 12) -> dict:
    index = _credit_index(movies, role)
    selected = sorted(
        index.items(),
        key=lambda item: (-len(item[1]), item[0]),
    )[:max_people]

    lifts, drops = [], []
    like_hits = dislike_avoids = exact_three = 0
    scenarios = []

    id_scenarios = 0
    for identity, rows in selected:
        target, credit = max(
            rows,
            key=lambda row: (row[0].vote_count, row[0].popularity),
        )
        pool = _candidate_pool(movies, target, credit, role)
        id_scenarios += int(credit.person_id is not None)
        liked = _person_preference(credit, role, "LIKE")
        disliked = _person_preference(credit, role, "DISLIKE")
        neutral = Preference(user_id="eval-user")

        neutral_score = member_fit(target, neutral).score
        liked_score = member_fit(target, liked).score
        disliked_score = member_fit(target, disliked).score
        lifts.append(liked_score - neutral_score)
        drops.append(neutral_score - disliked_score)

        liked_result = recommend(
            pool,
            GroupRecommendRequest(
                room_id=f"{role}-{identity}-like",
                round_id="eval",
                members=[liked],
                limit=3,
            ),
        )
        disliked_result = recommend(
            pool,
            GroupRecommendRequest(
                room_id=f"{role}-{identity}-dislike",
                round_id="eval",
                members=[disliked],
                limit=3,
            ),
        )
        liked_ids = [item.movie.internal_id for item in liked_result.recommendations]
        disliked_ids = [item.movie.internal_id for item in disliked_result.recommendations]

        like_hit = target.internal_id in liked_ids
        dislike_avoid = target.internal_id not in disliked_ids
        three_ok = (
            len(liked_ids) == len(set(liked_ids)) == 3
            and len(disliked_ids) == len(set(disliked_ids)) == 3
        )
        like_hits += int(like_hit)
        dislike_avoids += int(dislike_avoid)
        exact_three += int(three_ok)
        scenarios.append({
            "identity": identity,
            "person_id": credit.person_id,
            "person_name": credit.original_name or credit.name,
            "target_movie_id": target.internal_id,
            "liked_top3": liked_ids,
            "disliked_top3": disliked_ids,
            "score_lift": round(liked_score - neutral_score, 4),
            "score_drop": round(neutral_score - disliked_score, 4),
            "like_hit_at_3": like_hit,
            "dislike_avoidance_at_3": dislike_avoid,
            "exact_three": three_ok,
        })

    count = len(selected)
    return {
        "scenario_count": count,
        "person_id_scenario_count": id_scenarios,
        "person_id_coverage": round(id_scenarios / count, 4) if count else 0.0,
        "mean_preference_score_lift": round(mean(lifts), 4) if lifts else 0.0,
        "mean_dislike_score_drop": round(mean(drops), 4) if drops else 0.0,
        "preference_hit_rate_at_3": round(like_hits / count, 4) if count else 0.0,
        "dislike_avoidance_rate_at_3": round(dislike_avoids / count, 4) if count else 0.0,
        "exact_three_rate": round(exact_three / count, 4) if count else 0.0,
        "scenarios": scenarios,
    }


def evaluate_context(movies) -> dict:
    cases = []
    for role in ("ACTOR", "DIRECTOR"):
        index = _credit_index(movies, role)
        identity, rows = max(index.items(), key=lambda item: len(item[1]))
        _target, credit = rows[0]
        name = credit.original_name or credit.name
        role_word = "배우" if role == "ACTOR" else "감독"
        liked_field = "liked_actors" if role == "ACTOR" else "liked_directors"
        disliked_field = "disliked_actors" if role == "ACTOR" else "disliked_directors"

        for reply in POSITIVE_REPLIES + NEGATIVE_REPLIES:
            result = analyze_chat(
                ChatAnalyzeRequest(messages=[
                    {"message_id": 1, "user_id": "A", "text": f"{name} {role_word} 좋아"},
                    {"message_id": 2, "user_id": "B", "text": reply},
                ]),
                movies,
            )
            member = next(item for item in result.members if item.user_id == "B")
            expected_positive = reply in POSITIVE_REPLIES
            stored = getattr(member, liked_field if expected_positive else disliked_field)
            passed = any(
                item.role == role
                and (
                    item.person_id == credit.person_id
                    if credit.person_id is not None
                    else canonical_person_name(item.original_name or item.name)
                    == canonical_person_name(credit.original_name or credit.name)
                )
                for item in stored
            )
            cases.append({
                "role": role,
                "identity": identity,
                "person_id": credit.person_id,
                "reply": reply,
                "expected": "INHERIT" if expected_positive else "NEGATIVE",
                "passed": passed,
            })

    passed = sum(case["passed"] for case in cases)
    return {
        "case_count": len(cases),
        "passed": passed,
        "accuracy": round(passed / len(cases), 4) if cases else 0.0,
        "cases": cases,
    }


def main() -> None:
    movies = [
        movie
        for movie in JsonStore(Path("data")).load_movies(use_fixture=False)
        if movie.recommendation_eligible
    ]
    actor = evaluate_role(movies, "ACTOR")
    director = evaluate_role(movies, "DIRECTOR")
    context = evaluate_context(movies)

    report = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_type": "catalog_grounded_component_validation",
        "catalog_movie_count": len(movies),
        "actor": actor,
        "director": director,
        "context_inheritance": context,
        "thresholds": {
            "minimum_mean_score_lift": 0.15,
            "minimum_mean_score_drop": 0.20,
            "minimum_hit_or_avoidance_rate_at_3": 0.80,
            "required_exact_three_rate": 1.0,
            "required_context_accuracy": 1.0,
            "minimum_tmdb_person_id_coverage_for_production": 0.95,
        },
        "limitations": [
            "TMDB catalog credits validate model behavior but are not real-user acceptance labels.",
            "Real chat logs and impression/click/select outcomes must be evaluated separately before claiming product accuracy.",
            "A catalog without TMDB person IDs is evaluated by role-scoped canonical names and is not production identity-ready.",
        ],
    }
    report["behavior_passed"] = (
        actor["mean_preference_score_lift"] >= 0.15
        and director["mean_preference_score_lift"] >= 0.15
        and actor["mean_dislike_score_drop"] >= 0.20
        and director["mean_dislike_score_drop"] >= 0.20
        and actor["preference_hit_rate_at_3"] >= 0.80
        and director["preference_hit_rate_at_3"] >= 0.80
        and actor["dislike_avoidance_rate_at_3"] >= 0.80
        and director["dislike_avoidance_rate_at_3"] >= 0.80
        and actor["exact_three_rate"] == 1.0
        and director["exact_three_rate"] == 1.0
        and context["accuracy"] == 1.0
    )
    report["person_id_data_ready"] = (
        actor["person_id_coverage"] >= 0.95
        and director["person_id_coverage"] >= 0.95
    )
    report["production_ready"] = (
        report["behavior_passed"]
        and report["person_id_data_ready"]
    )
    report["passed"] = report["behavior_passed"]

    output = Path("evaluation/role_context_validation.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "production_ready": report["production_ready"],
        "person_id_data_ready": report["person_id_data_ready"],
        "catalog_movie_count": report["catalog_movie_count"],
        "actor": {key: value for key, value in actor.items() if key != "scenarios"},
        "director": {key: value for key, value in director.items() if key != "scenarios"},
        "context_inheritance": {key: value for key, value in context.items() if key != "cases"},
        "saved": str(output),
    }, ensure_ascii=False, indent=2))

    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
