from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .schemas import RecommendationEvent


EVENT_LABELS = {
    "SELECT": 3.0,
    "LIKE": 2.0,
    "CLICK": 1.0,
    "PROVIDER_CLICK": 1.0,
    "SKIP": -1.0,
    "DISLIKE": -2.0,
}

EVENT_PRIORITY = {
    "SELECT": 60,
    "DISLIKE": 50,
    "LIKE": 40,
    "PROVIDER_CLICK": 30,
    "CLICK": 20,
    "SKIP": 10,
}


@dataclass
class LTRRow:
    room_id: str
    round_id: str
    user_id: str | None
    movie_id: str
    rank_no: int
    group_score: float
    event_type: str
    label: float
    model_version: str | None


def _strongest_events(
    events: Iterable[RecommendationEvent],
) -> dict[tuple[str, str, str | None, str], RecommendationEvent]:
    selected: dict[
        tuple[str, str, str | None, str],
        RecommendationEvent,
    ] = {}

    for event in events:
        if (
            not event.movie_id
            or event.event_type not in EVENT_LABELS
        ):
            continue

        key = (
            event.room_id,
            event.round_id,
            event.user_id,
            event.movie_id,
        )

        previous = selected.get(key)

        if previous is None:
            selected[key] = event
            continue

        previous_priority = EVENT_PRIORITY.get(
            previous.event_type,
            0,
        )
        current_priority = EVENT_PRIORITY.get(
            event.event_type,
            0,
        )

        if current_priority > previous_priority:
            selected[key] = event

        elif (
            current_priority == previous_priority
            and event.occurred_at > previous.occurred_at
        ):
            selected[key] = event

    return selected


def build_ltr_rows(
    recommendation_history: list[dict],
    events: list[RecommendationEvent],
) -> list[LTRRow]:
    history_lookup: dict[
        tuple[str, str, str],
        dict,
    ] = {}

    for row in recommendation_history:
        key = (
            str(row["room_id"]),
            str(row["round_id"]),
            str(row["movie_id"]),
        )

        history_lookup[key] = row

    selected_events = _strongest_events(events)

    result: list[LTRRow] = []

    for (
        room_id,
        round_id,
        user_id,
        movie_id,
    ), event in selected_events.items():

        history = history_lookup.get(
            (
                room_id,
                round_id,
                movie_id,
            )
        )

        if history is None:
            continue

        result.append(
            LTRRow(
                room_id=room_id,
                round_id=round_id,
                user_id=user_id,
                movie_id=movie_id,
                rank_no=int(history["rank_no"]),
                group_score=float(history["group_score"]),
                event_type=event.event_type,
                label=EVENT_LABELS[event.event_type],
                model_version=event.model_version,
            )
        )

    result.sort(
        key=lambda row: (
            row.room_id,
            row.round_id,
            row.user_id or "",
            row.rank_no,
            row.movie_id,
        )
    )

    return result


def summarize_ltr_rows(
    rows: list[LTRRow],
) -> dict:
    labels = defaultdict(int)
    event_counts = defaultdict(int)
    rounds = set()
    users = set()

    for row in rows:
        labels[row.label] += 1
        event_counts[row.event_type] += 1
        rounds.add((row.room_id, row.round_id))

        if row.user_id:
            users.add(row.user_id)

    positive = sum(
        1
        for row in rows
        if row.label > 0
    )

    negative = sum(
        1
        for row in rows
        if row.label < 0
    )

    return {
        "rows": len(rows),
        "rounds": len(rounds),
        "users": len(users),
        "positive_rows": positive,
        "negative_rows": negative,
        "event_counts": dict(event_counts),
        "label_counts": {
            str(label): count
            for label, count in labels.items()
        },
    }