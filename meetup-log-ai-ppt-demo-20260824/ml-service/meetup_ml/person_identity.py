"""Canonical actor/director identity helpers used by chat and ranking."""

import re
import unicodedata

from .schemas import Movie, PersonCredit, PersonPreference


PERSON_ALIASES = {
    "류준열": {"류준열", "ryu jun-yeol", "ryu jun yeol"},
    "혜리": {"혜리", "이혜리", "lee hye-ri", "lee hyeri"},
    "엄정화": {"엄정화", "uhm jung-hwa", "um jung hwa"},
    "봉준호": {"봉준호", "bong joon-ho", "bong joon ho"},
    "송강호": {"송강호", "song kang-ho", "song kang ho"},
}


def normalize_person_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^0-9a-z가-힣]", "", normalized)


_ALIAS_TO_CANONICAL = {
    normalize_person_name(alias): normalize_person_name(canonical)
    for canonical, aliases in PERSON_ALIASES.items()
    for alias in aliases | {canonical}
}


def canonical_person_name(value: str) -> str:
    normalized = normalize_person_name(value)
    return _ALIAS_TO_CANONICAL.get(normalized, normalized)


def movie_person_aliases(movie, role: str | None = None) -> set[str]:
    """Return comparable credit aliases, optionally restricted to one role."""
    values: list[str] = []
    credits: list[PersonCredit] = []
    if role in (None, "ACTOR"):
        values.extend(movie.cast)
        credits.extend(getattr(movie, "cast_people", []))
    if role in (None, "DIRECTOR"):
        values.extend(movie.directors)
        credits.extend(getattr(movie, "director_people", []))
    for credit in credits:
        values.append(credit.name)
        if credit.original_name:
            values.append(credit.original_name)
    return {canonical_person_name(value) for value in values if value}


def _credit_aliases(credit: PersonCredit) -> set[str]:
    return {
        canonical_person_name(value)
        for value in (credit.name, credit.original_name)
        if value
    }


def resolve_person_preference(
    name: str,
    role: str,
    movies: list[Movie],
    strength: float = 1.0,
) -> PersonPreference:
    """Resolve a chat mention to one role-specific TMDB person identity.

    An ID is emitted only when all matching catalog credits agree on the same
    TMDB person.  Ambiguous or catalog-missing mentions keep their role and
    normalized name, so they can be resolved after a later catalog refresh.
    """
    if role not in {"ACTOR", "DIRECTOR"}:
        raise ValueError(f"unsupported person role: {role}")

    query = canonical_person_name(name)
    matched_credits: list[PersonCredit] = []
    flat_names: list[str] = []

    for movie in movies:
        if role == "ACTOR":
            credits = movie.cast_people
            flat_names.extend(movie.cast)
        else:
            credits = movie.director_people
            flat_names.extend(movie.directors)
        for credit in credits:
            if query and query in _credit_aliases(credit):
                matched_credits.append(credit)

    person_ids = {
        credit.person_id
        for credit in matched_credits
        if credit.person_id is not None
    }
    resolved_id = next(iter(person_ids)) if len(person_ids) == 1 else None
    selected = next(
        (
            credit
            for credit in matched_credits
            if resolved_id is not None and credit.person_id == resolved_id
        ),
        matched_credits[0] if matched_credits else None,
    )

    if selected is not None:
        source = "TMDB_ID" if resolved_id is not None else "CATALOG_ALIAS"
        return PersonPreference(
            person_id=resolved_id,
            name=selected.name,
            original_name=selected.original_name,
            role=role,
            strength=strength,
            identity_source=source,
        )

    catalog_name = next(
        (
            candidate
            for candidate in flat_names
            if canonical_person_name(candidate) == query
        ),
        None,
    )
    return PersonPreference(
        name=catalog_name or name,
        role=role,
        strength=strength,
        identity_source="CATALOG_ALIAS" if catalog_name else "TEXT_ONLY",
    )


def person_identity_keys(person: PersonPreference) -> set[tuple[str, str]]:
    """Build role-scoped ID and alias keys for one stored preference."""
    keys: set[tuple[str, str]] = set()
    if person.person_id is not None:
        keys.add((person.role, f"id:{person.person_id}"))
    for value in (person.name, person.original_name):
        canonical = canonical_person_name(value) if value else ""
        if canonical:
            keys.add((person.role, f"name:{canonical}"))
    return keys


def movie_person_identity_keys(movie: Movie, role: str) -> set[tuple[str, str]]:
    """Build role-scoped ID and alias keys for all matching movie credits."""
    keys: set[tuple[str, str]] = set()
    credits = movie.cast_people if role == "ACTOR" else movie.director_people
    flat_names = movie.cast if role == "ACTOR" else movie.directors

    for credit in credits:
        if credit.person_id is not None:
            keys.add((role, f"id:{credit.person_id}"))
        for alias in (credit.name, credit.original_name):
            canonical = canonical_person_name(alias) if alias else ""
            if canonical:
                keys.add((role, f"name:{canonical}"))
    for name in flat_names:
        canonical = canonical_person_name(name)
        if canonical:
            keys.add((role, f"name:{canonical}"))
    return keys


def matching_person_preferences(
    movie: Movie,
    preferences: list[PersonPreference],
    role: str,
) -> list[PersonPreference]:
    movie_keys = movie_person_identity_keys(movie, role)
    credits = movie.cast_people if role == "ACTOR" else movie.director_people
    movie_ids = {
        credit.person_id
        for credit in credits
        if credit.person_id is not None
    }
    matches: list[PersonPreference] = []
    for person in preferences:
        if person.role != role:
            continue
        # When both sides carry TMDB IDs, a different ID must never be rescued
        # by a coincidentally identical stage/name string.
        if person.person_id is not None and movie_ids:
            if person.person_id in movie_ids:
                matches.append(person)
            continue
        if person_identity_keys(person) & movie_keys:
            matches.append(person)
    return matches
