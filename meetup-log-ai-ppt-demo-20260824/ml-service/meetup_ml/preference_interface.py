from __future__ import annotations

from .schemas import Preference, PreferenceDelta


_MAPPING = {
    "liked_genres": ("GENRE", 1.0, "SOFT"),
    "disliked_genres": ("GENRE", -1.0, "SOFT"),
    "liked_topics": ("TOPIC", 1.0, "SOFT"),
    "disliked_topics": ("TOPIC", -1.0, "SOFT"),
    "liked_movies": ("MOVIE", 1.0, "SOFT"),
    "direct_movies": ("MOVIE", 1.0, "SOFT"),
    "disliked_movies": ("MOVIE", -1.0, "SOFT"),
    "liked_people": ("PERSON", 1.0, "SOFT"),
    "disliked_people": ("PERSON", -1.0, "SOFT"),
    "liked_actors": ("PERSON", 1.0, "SOFT"),
    "disliked_actors": ("PERSON", -1.0, "SOFT"),
    "liked_directors": ("PERSON", 1.0, "SOFT"),
    "disliked_directors": ("PERSON", -1.0, "SOFT"),
    "liked_brands": ("BRAND", 1.0, "SOFT"),
    "disliked_brands": ("BRAND", -1.0, "SOFT"),
    "countries": ("COUNTRY", 1.0, "HARD"),
    "excluded_countries": ("COUNTRY", -1.0, "HARD"),
    "languages": ("LANGUAGE", 1.0, "HARD"),
    "certifications": ("CERTIFICATION", 1.0, "HARD"),
    "allowed_providers": ("PROVIDER", 1.0, "HARD"),
    "ott_platforms": ("PROVIDER", 1.0, "SOFT"),
    "preferred_original_platforms": ("PROVIDER", 1.0, "SOFT"),
    "hard_exclusions": ("CONSTRAINT", -1.0, "HARD"),
}

_SCALARS = {
    "max_runtime": "LTE",
    "min_runtime": "GTE",
    "min_year": "GTE_YEAR",
    "max_year": "LTE_YEAR",
    "ott_strict": "BOOLEAN",
    "prefers_theater": "BOOLEAN",
}


def _values(preference: Preference, field: str) -> dict[str, float]:
    value = getattr(preference, field)
    if isinstance(value, dict):
        return {str(key): float(score) for key, score in value.items()}
    result: dict[str, float] = {}
    for item in value:
        if hasattr(item, "role") and hasattr(item, "name"):
            identity = (
                f"id:{item.person_id}"
                if item.person_id is not None
                else f"name:{item.name}"
            )
            result[f"{item.role}:{identity}"] = float(item.strength)
        else:
            result[str(item)] = 1.0
    return result


def build_preference_deltas(
    before: list[Preference],
    after: list[Preference],
    source_message_id: str | None,
) -> list[PreferenceDelta]:
    old_by_user = {item.user_id: item for item in before}
    new_by_user = {item.user_id: item for item in after}
    deltas: list[PreferenceDelta] = []

    for user_id in sorted(set(old_by_user) | set(new_by_user)):
        old = old_by_user.get(user_id, Preference(user_id=user_id))
        new = new_by_user.get(user_id, Preference(user_id=user_id))
        for field, (target_type, sign, preference_type) in _MAPPING.items():
            old_values = _values(old, field)
            new_values = _values(new, field)
            for target in sorted(set(old_values) | set(new_values)):
                if target not in new_values:
                    operation, score = "REMOVE", None
                elif target not in old_values or new_values[target] != old_values[target]:
                    operation, score = "UPSERT", sign * new_values[target]
                else:
                    continue
                deltas.append(PreferenceDelta(
                    user_id=user_id,
                    target_type=target_type,
                    target_value=target,
                    operation=operation,
                    preference_type=preference_type,
                    score=score,
                    confidence=new.confidence,
                    source_message_id=source_message_id,
                ))

        for field, operator in _SCALARS.items():
            old_value, new_value = getattr(old, field), getattr(new, field)
            if old_value == new_value:
                continue
            deltas.append(PreferenceDelta(
                user_id=user_id,
                target_type="CONSTRAINT",
                target_value=f"{field}:{operator}:{new_value}" if new_value is not None else f"{field}:{operator}",
                operation="UPSERT" if new_value is not None else "REMOVE",
                preference_type="HARD",
                score=1.0 if new_value is not None else None,
                confidence=new.confidence,
                source_message_id=source_message_id,
            ))
    return deltas


