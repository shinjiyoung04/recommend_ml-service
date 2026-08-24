from collections import Counter

from .schemas import RecommendationEvent


POSITIVE_EVENTS = {"CLICK", "LIKE", "SELECT", "PROVIDER_CLICK"}
NEGATIVE_EVENTS = {"DISLIKE", "SKIP"}


def feedback_readiness(events: list[RecommendationEvent], min_events: int = 1000, min_rounds: int = 200) -> dict:
    usable = [event for event in events if event.movie_id and event.event_type in POSITIVE_EVENTS | NEGATIVE_EVENTS]
    rounds = {event.round_id for event in usable}
    users = {event.user_id for event in usable if event.user_id}
    counts = Counter(event.event_type for event in usable)
    positives = sum(counts[event] for event in POSITIVE_EVENTS)
    negatives = sum(counts[event] for event in NEGATIVE_EVENTS)
    reasons = []
    if len(usable) < min_events:
        reasons.append(f"usable events {len(usable)} < {min_events}")
    if len(rounds) < min_rounds:
        reasons.append(f"rounds {len(rounds)} < {min_rounds}")
    if not positives or not negatives:
        reasons.append("both positive and negative feedback are required")
    return {"ready": not reasons, "usable_events": len(usable), "rounds": len(rounds), "users": len(users),
            "positive_events": positives, "negative_events": negatives, "event_counts": dict(counts), "reasons": reasons}
