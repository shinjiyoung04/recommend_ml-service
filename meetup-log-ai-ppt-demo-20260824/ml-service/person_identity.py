"""Canonical actor/director identity helpers used by chat and ranking."""

import re
import unicodedata


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
