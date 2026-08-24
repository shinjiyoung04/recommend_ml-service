import math
import re
from datetime import date

from .models import ModelBundle
from .schemas import (
    GroupRecommendRequest,
    MemberScore,
    Movie,
    Recommendation,
    RecommendationEvent,
    RecommendResponse,
)
from .person_identity import (
    canonical_person_name,
    matching_person_preferences,
    movie_person_aliases,
)


DEFAULT_WEIGHTS = {
    # 사용자 취향 점수를 최우선으로 사용한다.
    "mean": 0.42,
    "minimum": 0.18,
    "bottom": 0.10,

    # 의미 유사도와 인기·평점은 보조 기준으로만 사용한다.
    "semantic": 0.18,
    "popularity": 0.07,
    "rating": 0.05,
}

RECOMMENDATION_CARD_COUNT = 3

PLATFORM_ALIASES = {
    "넷플릭스": {"넷플릭스", "netflix"},
    "티빙": {"티빙", "tving"},
    "웨이브": {"웨이브", "wavve"},
    "디즈니+": {"디즈니+", "디즈니플러스", "disney+", "disney plus"},
    "왓챠": {"왓챠", "watcha"},
    "쿠팡플레이": {"쿠팡플레이", "coupang play"},
    "apple tv+": {"apple tv+", "애플티비", "애플 tv+"},
}


def _normalized_provider_names(movie: Movie) -> set[str]:
    return {
        provider.name.strip().casefold()
        for provider in movie.providers
        if provider.name
    }


def _requested_platform_names(platforms: list[str]) -> set[str]:
    names: set[str] = set()
    for platform in platforms:
        normalized = platform.strip().casefold()
        names.add(normalized)
        for canonical, aliases in PLATFORM_ALIASES.items():
            normalized_aliases = {value.casefold() for value in aliases}
            if normalized == canonical.casefold() or normalized in normalized_aliases:
                names.update(normalized_aliases)
    return names

RERANK_CONFIG = {
    # 이미 뽑힌 영화와 장르가 많이 겹치면 감점
    "diversity_penalty": 0.08,

    # 인기도 상위 후보에 대한 작은 감점
    "popularity_penalty": 0.03,

    # 최근 2년 이내 영화에 작은 노출 보너스
    "recent_boost": 0.025,

    # 명시적으로 사용자가 지목한 영화는 rerank 감점에서 보호
    "direct_movie_bonus": 0.20,
}

BRAND_TERMS = {
    "Marvel": [
        "마블",
        "marvel",
        "어벤져스",
        "아이언맨",
        "캡틴 아메리카",
        "토르",
        "스파이더맨",
        "가디언즈 오브 갤럭시",
        "블랙 팬서",
        "닥터 스트레인지",
        "앤트맨",
        "데드풀",
    ],
    "Disney": [
        "디즈니",
        "disney",
        "미키",
        "겨울왕국",
        "라이온 킹",
        "알라딘",
    ],
    "Pixar": [
        "픽사",
        "pixar",
        "토이 스토리",
        "인사이드 아웃",
        "카",
        "니모",
        "코코",
        "몬스터 주식회사",
    ],
    "Star Wars": [
        "스타워즈",
        "star wars",
        "제다이",
    ],
    "Ghibli": [
        "지브리",
        "ghibli",
        "미야자키 하야오",
    ],
}


def _country_code(value: str) -> str:
    aliases = {
        "한국": "KR",
        "대한민국": "KR",
        "south korea": "KR",
        "korea": "KR",
    }

    clean = value.strip().casefold()

    return aliases.get(
        clean,
        value.strip().upper(),
    )


def _normalize_movie_title(value: str | None) -> str:
    if not value:
        return ""

    return re.sub(
        r"[^0-9a-zA-Z가-힣]",
        "",
        value,
    ).casefold()


def _set_similarity(left: list[str], right: list[str]) -> float:
    a = {value.strip().casefold() for value in left if value}
    b = {value.strip().casefold() for value in right if value}
    return len(a & b) / len(a | b) if a and b else 0.0


def _word_similarity(left: str, right: str) -> float:
    tokens = lambda value: set(re.findall(r"[0-9a-zA-Z가-힣]{2,}", value.casefold()))
    a, b = tokens(left), tokens(right)
    return len(a & b) / len(a | b) if a and b else 0.0


def reference_movie_similarity(reference: Movie, candidate: Movie) -> tuple[float, dict[str, float]]:
    """Explainable, offline-safe similarity for an explicitly liked movie."""
    if reference.internal_id == candidate.internal_id:
        return 0.0, {}
    genre = _set_similarity(reference.genres, candidate.genres)
    keyword = _set_similarity(reference.keywords, candidate.keywords)
    people_left = movie_person_aliases(reference)
    people_right = movie_person_aliases(candidate)
    people = len(people_left & people_right) / len(people_left | people_right) if people_left and people_right else 0.0
    overview = _word_similarity(
        " ".join([reference.overview, *reference.keywords]),
        " ".join([candidate.overview, *candidate.keywords]),
    )
    related = float(
        candidate.tmdb_id is not None
        and candidate.tmdb_id in set(reference.similar + reference.recommendations)
    )
    available_weight = 0.30 + (0.25 if reference.keywords and candidate.keywords else 0) \
        + (0.15 if people_left and people_right else 0) \
        + (0.20 if reference.overview and candidate.overview else 0) + 0.10
    raw = 0.30 * genre + 0.25 * keyword + 0.15 * people + 0.20 * overview + 0.10 * related
    score = raw / available_weight if available_weight else 0.0
    return min(1.0, score), {
        "reference_genre": round(genre, 4), "reference_keyword": round(keyword, 4),
        "reference_people": round(people, 4), "reference_overview": round(overview, 4),
        "reference_tmdb_relation": related,
    }

def _genre_overlap(
    left: Movie,
    right: Movie,
) -> float:
    """두 영화의 장르 겹침 정도를 0~1로 반환한다."""

    left_genres = {
        genre.strip().casefold()
        for genre in left.genres
        if genre
    }

    right_genres = {
        genre.strip().casefold()
        for genre in right.genres
        if genre
    }

    if not left_genres or not right_genres:
        return 0.0

    union = left_genres | right_genres

    if not union:
        return 0.0

    return len(
        left_genres & right_genres
    ) / len(union)


def _release_year(movie: Movie) -> int | None:
    if not movie.release_date:
        return None

    try:
        return int(movie.release_date[:4])
    except (TypeError, ValueError):
        return None


def rerank_candidates(
    candidates: list[Recommendation],
    limit: int,
    direct_movie_ids: set[str] | None = None,
    config: dict[str, float] | None = None,
) -> list[Recommendation]:
    """추천 적합도를 유지하면서 다양성·인기 편향·신작 노출을 보정한다.

    원래 group_score 값은 변경하지 않고 최종 노출 순서만 조정한다.
    """

    if not candidates or limit <= 0:
        return []

    config = config or RERANK_CONFIG
    direct_movie_ids = direct_movie_ids or set()

    remaining = list(candidates)
    selected: list[Recommendation] = []

    popularities = [
        max(0.0, item.movie.popularity)
        for item in remaining
    ]

    max_popularity = max(
        popularities,
        default=0.0,
    )

    current_year = date.today().year

    while remaining and len(selected) < limit:
        best_item = None
        best_score = float("-inf")

        for item in remaining:
            movie = item.movie
            rerank_score = item.group_score

            # 1. 장르 다양성
            if selected:
                max_overlap = max(
                    _genre_overlap(
                        movie,
                        chosen.movie,
                    )
                    for chosen in selected
                )

                rerank_score -= (
                    config["diversity_penalty"]
                    * max_overlap
                )

            # 2. 인기 편향 완화
            if max_popularity > 0:
                normalized_popularity = (
                    max(0.0, movie.popularity)
                    / max_popularity
                )

                rerank_score -= (
                    config["popularity_penalty"]
                    * normalized_popularity
                )

            # 3. 최근 영화에 제한적인 노출 기회 제공
            release_year = _release_year(movie)

            if (
                release_year is not None
                and current_year - 1
                <= release_year
                <= current_year
            ):
                rerank_score += config["recent_boost"]

            # 4. 사용자가 직접 지목한 영화는 다양성 보정 때문에
            # 뒤로 밀리지 않도록 보호한다.
            if movie.internal_id in direct_movie_ids:
                rerank_score += config[
                    "direct_movie_bonus"
                ]

            if rerank_score > best_score:
                best_score = rerank_score
                best_item = item

        if best_item is None:
            break

        selected.append(best_item)
        remaining.remove(best_item)

    return selected

def hard_violations(
    movie: Movie,
    pref,
) -> list[str]:
    reasons: list[str] = []

    try:
        year = int(
            (movie.release_date or "0")[:4]
            or 0
        )
    except ValueError:
        year = 0

    if (
        pref.max_runtime
        and movie.runtime
        and movie.runtime > pref.max_runtime
    ):
        reasons.append(
            f"{pref.user_id}: 최대 러닝타임 초과"
        )

    if (
        pref.min_runtime
        and movie.runtime
        and movie.runtime < pref.min_runtime
    ):
        reasons.append(
            f"{pref.user_id}: 최소 러닝타임 미달"
        )

    if (
        pref.min_year
        and year
        and year < pref.min_year
    ):
        reasons.append(
            f"{pref.user_id}: 최소 제작연도 미달"
        )

    if (
        pref.max_year
        and year
        and year > pref.max_year
    ):
        reasons.append(
            f"{pref.user_id}: 최대 제작연도 초과"
        )

    if (
        pref.certifications
        and movie.certification
        and movie.certification
        not in pref.certifications
    ):
        reasons.append(
            f"{pref.user_id}: 관람등급 제외"
        )

    if pref.countries:
        allowed_countries = {
            _country_code(value)
            for value in pref.countries
        }

        movie_countries = {
            _country_code(value)
            for value in movie.countries
        }

        if not movie_countries:
            reasons.append(
                f"{pref.user_id}: 제작 국가 정보 없음"
            )

        elif not allowed_countries.intersection(
            movie_countries
        ):
            reasons.append(
                f"{pref.user_id}: 선호 제작 국가와 불일치"
            )

    if pref.excluded_countries:
        excluded_countries = {
            _country_code(value)
            for value in pref.excluded_countries
        }

        movie_countries = {
            _country_code(value)
            for value in movie.countries
        }

        if excluded_countries.intersection(
            movie_countries
        ):
            reasons.append(
                f"{pref.user_id}: 제외 제작 국가"
            )            

    text = " ".join(
        [
            movie.title,
            movie.overview,
            *movie.genres,
            *movie.keywords,
        ]
    ).casefold()

    for phrase in pref.hard_exclusions:
        if phrase.casefold() in text:
            reasons.append(
                f"{pref.user_id}: HARD 제외 '{phrase}'"
            )

    movie_titles = {
        _normalize_movie_title(movie.title),
        _normalize_movie_title(movie.original_title),
        _normalize_movie_title(movie.title_ko),
        _normalize_movie_title(movie.title_en),
    }

    movie_titles.discard("")

    disliked_titles = {
        _normalize_movie_title(value)
        for value in pref.disliked_movies
        if value
    }

    disliked_movie_match = any(
        disliked_title == movie_title
        or (
            len(disliked_title) >= 4
            and disliked_title in movie_title
        )
        or (
            len(movie_title) >= 4
            and movie_title in disliked_title
        )
        for disliked_title in disliked_titles
        for movie_title in movie_titles
    )

    if disliked_movie_match:
        reasons.append(
            f"{pref.user_id}: 비선호 영화와 일치"
        )

    if (
        movie.internal_id in pref.seen_movies
        and movie.internal_id
        not in pref.rewatch_allowed_movies
    ):
        reasons.append(
            f"{pref.user_id}: 이미 본 영화"
        )

    return reasons


def _matched_people_by_role(movie: Movie, pref) -> dict[str, list[tuple[str, float]]]:
    """Match stored person IDs first and use role-scoped names as fallback."""
    fields = {
        "liked_actors": "ACTOR",
        "disliked_actors": "ACTOR",
        "liked_directors": "DIRECTOR",
        "disliked_directors": "DIRECTOR",
    }
    result: dict[str, list[tuple[str, float]]] = {field: [] for field in fields}

    structured_names = {
        canonical_person_name(value)
        for field in fields
        for person in getattr(pref, field, [])
        for value in (person.name, person.original_name)
        if value
    }

    for field, role in fields.items():
        structured = list(getattr(pref, field, []))
        for person in matching_person_preferences(movie, structured, role):
            result[field].append((person.original_name or person.name, person.strength))

        # Old clients send only combined names.  Use that path only for names
        # not already represented by a role-aware preference, preventing a
        # duplicate score when chat analysis emits both interfaces.
        legacy_field = "liked_people" if field.startswith("liked") else "disliked_people"
        legacy_names = [
            name
            for name in getattr(pref, legacy_field, [])
            if canonical_person_name(name) not in structured_names
        ]
        catalog_aliases = movie_person_aliases(movie, role)
        for name in legacy_names:
            if canonical_person_name(name) in catalog_aliases:
                result[field].append((name, 1.0))

    return result


def member_fit(
    movie: Movie,
    pref,
    learned_similarity: float | None = None,
    reference_movies: list[Movie] | None = None,
) -> MemberScore:
    score = 0.5
    matched: list[str] = []
    penalties: list[str] = []
    score_breakdown: dict[str, float] = {}

    genres = {
        genre.strip().casefold()
        for genre in movie.genres
        if genre
    }

    for genre, strength in pref.liked_genres.items():
        normalized_genre = genre.strip().casefold()

        if normalized_genre in genres:
            score += (
                0.18
                * strength
                * pref.confidence
            )

            matched.append(
                f"{genre} 선호"
            )

    for genre, strength in pref.disliked_genres.items():
        normalized_genre = genre.strip().casefold()

        if normalized_genre in genres:
            score -= (
                0.35
                * strength
                * pref.confidence
            )

            penalties.append(
                f"{genre} 비선호"
            )

    text = " ".join(
        [
            movie.overview,
            *movie.keywords,
        ]
    ).casefold()

    brand_text = " ".join(
        [
            movie.title,
            movie.original_title or "",
            movie.overview,
            *movie.keywords,
        ]
    ).casefold()

    for brand, strength in pref.liked_brands.items():
        terms = BRAND_TERMS.get(
            brand,
            [brand],
        )

        if any(
            term.casefold() in brand_text
            for term in terms
        ):
            score += 0.14 * strength

            matched.append(
                f"{brand} 선호"
            )

    for brand, strength in pref.disliked_brands.items():
        terms = BRAND_TERMS.get(
            brand,
            [brand],
        )

        if any(
            term.casefold() in brand_text
            for term in terms
        ):
            score -= 0.20 * strength

            penalties.append(
                f"{brand} 비선호"
            )

    for topic, strength in pref.liked_topics.items():
        if topic.casefold() in text:
            score += 0.12 * strength

            matched.append(
                f"{topic} 소재"
            )

    for topic, strength in pref.disliked_topics.items():
        if topic.casefold() in text:
            score -= 0.20 * strength

            penalties.append(
                f"{topic} 비선호"
            )

    person_matches = _matched_people_by_role(movie, pref)
    person_adjustments = {
        "liked_actors": min(
            0.42,
            sum(0.32 * strength for _name, strength in person_matches["liked_actors"]),
        ),
        "disliked_actors": -min(
            0.70,
            sum(0.50 * strength for _name, strength in person_matches["disliked_actors"]),
        ),
        "liked_directors": min(
            0.36,
            sum(0.28 * strength for _name, strength in person_matches["liked_directors"]),
        ),
        "disliked_directors": -min(
            0.65,
            sum(0.45 * strength for _name, strength in person_matches["disliked_directors"]),
        ),
    }
    for key, adjustment in person_adjustments.items():
        score += adjustment
        score_breakdown[key] = round(adjustment, 4)

    if person_matches["liked_actors"]:
        names = ", ".join(name for name, _strength in person_matches["liked_actors"])
        matched.extend(["선호 배우/감독", f"선호 배우: {names}"])
    if person_matches["liked_directors"]:
        names = ", ".join(name for name, _strength in person_matches["liked_directors"])
        matched.extend(["선호 배우/감독", f"선호 감독: {names}"])
    if person_matches["disliked_actors"]:
        names = ", ".join(name for name, _strength in person_matches["disliked_actors"])
        penalties.extend(["비선호 배우/감독", f"비선호 배우: {names}"])
    if person_matches["disliked_directors"]:
        names = ", ".join(name for name, _strength in person_matches["disliked_directors"])
        penalties.extend(["비선호 배우/감독", f"비선호 감독: {names}"])

    if movie.internal_id in pref.direct_movies:
        score += 0.65

        matched.append(
            "직접 보고 싶다고 한 영화"
        )

    best_reference = None
    best_similarity = 0.0
    best_breakdown: dict[str, float] = {}
    for reference in reference_movies or []:
        similarity, breakdown = reference_movie_similarity(reference, movie)
        if similarity > best_similarity:
            best_reference, best_similarity, best_breakdown = reference, similarity, breakdown
    if best_reference is not None and best_similarity >= 0.12:
        reference_bonus = min(0.40, best_similarity * 0.40)
        score += reference_bonus
        score_breakdown.update(best_breakdown)
        score_breakdown["reference_movie_bonus"] = round(reference_bonus, 4)
        score_breakdown["reference_movie_similarity"] = round(best_similarity, 4)
        matched.append(f"'{best_reference.title}'와 유사")

    release_year = _release_year(movie)

    # 제한 조건은 위반 시 hard_violations에서 제외되고,
    # 충족했을 때도 명시적인 가점을 준다.
    if pref.max_runtime and movie.runtime and movie.runtime <= pref.max_runtime:
        score += 0.08
        matched.append(f"{pref.max_runtime}분 이하 충족")

    if pref.min_runtime and movie.runtime and movie.runtime >= pref.min_runtime:
        score += 0.08
        matched.append(f"{pref.min_runtime}분 이상 충족")

    if pref.min_year and release_year and release_year >= pref.min_year:
        score += 0.08
        matched.append(f"{pref.min_year}년 이후 조건 충족")

    if pref.max_year and release_year and release_year <= pref.max_year:
        score += 0.08
        matched.append(f"{pref.max_year}년 이전 조건 충족")

    if pref.countries:
        preferred_countries = {
            _country_code(value)
            for value in pref.countries
        }
        movie_countries = {
            _country_code(value)
            for value in movie.countries
        }
        if preferred_countries & movie_countries:
            score += 0.08
            matched.append("선호 제작 국가 충족")

    if pref.ott_platforms:
        requested_names = _requested_platform_names(pref.ott_platforms)
        provider_names = _normalized_provider_names(movie)
        if requested_names & provider_names:
            score += 0.15
            matched.append("선호 OTT에서 시청 가능")
        elif pref.ott_strict:
            score -= 0.45
            penalties.append("필수 OTT 조건 불일치")

    if pref.prefers_theater and movie.is_now_playing:
        score += 0.10
        matched.append("현재 극장 상영 조건 충족")

    
    score += min(
        0.08,
        movie.vote_average / 10 * 0.05
        + math.log1p(movie.vote_count) / 200,
    )

    return MemberScore(
        user_id=pref.user_id,
        score=round(
            max(
                0,
                min(
                    1,
                    score,
                ),
            ),
            4,
        ),
        matched=matched,
        penalties=penalties,
        score_breakdown=score_breakdown,
    )


def recommend(
    movies: list[Movie],
    request: GroupRecommendRequest,
    weights: dict | None = None,
    learned_scores: (
        dict[str, list[float]]
        | None
    ) = None,
    reactions: (
        list[RecommendationEvent]
        | None
    ) = None,
    _allow_soft_backfill: bool = True,
) -> RecommendResponse:
    weights = weights or DEFAULT_WEIGHTS

    candidates: list[Recommendation] = []
    excluded: list[dict] = []

    latest_reactions: dict[
        tuple[str, str],
        str,
    ] = {}

    for event in sorted(
        reactions or [],
        key=lambda item: (
            item.occurred_at,
            item.id,
        ),
    ):
        if (
            event.user_id
            and event.movie_id
            and event.event_type
            in {
                "LIKE",
                "DISLIKE",
                "HOLD",
                "SELECT",
            }
        ):
            latest_reactions[
                (
                    event.user_id,
                    event.movie_id,
                )
            ] = event.event_type

    allowed_ids = set(
        request.allowed_providers
    )

    allowed_types = set(
        request.allowed_provider_types
    )

    reroll_exclusions = set(
        request.excluded_movie_ids
    )
    movie_lookup = {movie.internal_id.casefold(): movie for movie in movies}
    for item in movies:
        for title in (item.title, item.title_ko, item.title_en, item.original_title):
            if title:
                movie_lookup[_normalize_movie_title(title)] = item
    member_references: dict[str, list[Movie]] = {}
    for preference in request.members:
        found: list[Movie] = []
        for value in preference.liked_movies:
            reference = movie_lookup.get(value.casefold()) or movie_lookup.get(_normalize_movie_title(value))
            if reference and reference not in found:
                found.append(reference)
        member_references[preference.user_id] = found

    for movie_index, movie in enumerate(
        movies
    ):
        if (
            request.require_now_playing
            and not movie.is_now_playing
        ):
            continue

        if not movie.recommendation_eligible:
            excluded.append(
                {
                    "movie_id": movie.internal_id,
                    "title": movie.title,
                    "reasons": [
                        "추천 학습 정보 부족"
                    ],
                }
            )
            continue

        if (
            movie.internal_id
            in reroll_exclusions
        ):
            continue

        violations = sum(
            (
                hard_violations(
                    movie,
                    preference,
                )
                for preference
                in request.members
            ),
            [],
        )

        if violations:
            excluded.append(
                {
                    "movie_id": movie.internal_id,
                    "title": movie.title,
                    "reasons": violations,
                }
            )
            continue

        providers = [
            provider
            for provider in movie.providers
            if (
                not allowed_ids
                or provider.provider_id
                in allowed_ids
            )
            and (
                not allowed_types
                or provider.type
                in allowed_types
            )
        ]

        if not request.require_now_playing:
            if (
                (allowed_ids or allowed_types)
                and movie.providers
                and not providers
            ):
                excluded.append(
                    {
                        "movie_id":
                            movie.internal_id,
                        "title":
                            movie.title,
                        "reasons": [
                            "허용한 시청 제공처/방식과 불일치"
                        ],
                    }
                )
                continue

            if (
                (allowed_ids or allowed_types)
                and not movie.providers
                and not request
                .include_unknown_watch_path
            ):
                excluded.append(
                    {
                        "movie_id":
                            movie.internal_id,
                        "title":
                            movie.title,
                        "reasons": [
                            "KR 시청 경로 확인 안 됨"
                        ],
                    }
                )
                continue

        scores: list[MemberScore] = []

        for preference in request.members:
            learned_similarity = None

            if (
                learned_scores
                and preference.user_id
                in learned_scores
                and movie_index
                < len(
                    learned_scores[
                        preference.user_id
                    ]
                )
            ):
                learned_similarity = (
                    learned_scores[
                        preference.user_id
                    ][movie_index]
                )

            scores.append(
                member_fit(
                    movie,
                    preference,
                    learned_similarity,
                    member_references.get(preference.user_id),
                )
            )

        values = sorted(
            item.score
            for item in scores
        )
        semantic_values = []

        for preference in request.members:
            if (
                learned_scores
                and preference.user_id in learned_scores
                and movie_index < len(learned_scores[preference.user_id])
            ):
                semantic_values.append(
                    learned_scores[preference.user_id][movie_index]
                )

        semantic_mean = (
            sum(semantic_values) / len(semantic_values)
            if semantic_values
            else 0.0
        )

        mean = (
            sum(values)
            / len(values)
        )

        minimum = values[0]

        bottom_count = max(
            1,
            len(values) // 3,
        )

        bottom = (
            sum(
                values[:bottom_count]
            )
            / bottom_count
        )

        quality = min(
            1,
            movie.vote_average / 10,
        )

        popularity = min(
            1,
            math.log1p(
                movie.popularity
            )
            / 8,
        )

        final = (
            weights["mean"] * mean
            + weights["minimum"] * minimum
            + weights["bottom"] * bottom
            + weights["semantic"] * semantic_mean
            + weights["popularity"]
            * popularity
            + weights["rating"]
            * quality
        )

        # 배우와 감독을 역할별로 다시 집계하여 그룹 평균에서 인물
        # 선호가 희석되지 않게 한다. ID 일치가 이름 일치보다 우선한다.
        group_person_matches = [
            _matched_people_by_role(movie, preference)
            for preference in request.members
        ]
        positive_actor_members = sum(
            bool(matches["liked_actors"])
            for matches in group_person_matches
        )
        positive_director_members = sum(
            bool(matches["liked_directors"])
            for matches in group_person_matches
        )
        negative_actor_members = sum(
            bool(matches["disliked_actors"])
            for matches in group_person_matches
        )
        negative_director_members = sum(
            bool(matches["disliked_directors"])
            for matches in group_person_matches
        )

        final += min(0.24, positive_actor_members * 0.12)
        final += min(0.24, positive_director_members * 0.12)
        final -= min(0.45, negative_actor_members * 0.22)
        final -= min(0.42, negative_director_members * 0.20)

        direct_request_members = sum(
            movie.internal_id in preference.direct_movies
            for preference in request.members
        )
        final += min(0.35, direct_request_members * 0.20)

        # 여러 종류의 명시적 조건을 동시에 만족한 후보에 작은
        # 근거 충족 보너스를 주어 단일 장르만 맞는 영화를 누른다.
        distinct_evidence = {
            reason
            for member_score in scores
            for reason in member_score.matched
        }
        final += min(0.12, len(distinct_evidence) * 0.025)

        reasons = sorted(
            {
                matched_reason
                for member_score in scores
                for matched_reason
                in member_score.matched
            }
        )[:4]

        if movie.is_now_playing:
            reasons.append(
                "현재 영화관에서 상영 중"
            )

        votes = [
            value
            for (
                user_id,
                movie_id,
            ), value
            in latest_reactions.items()
            if movie_id
            == movie.internal_id
        ]

        vote_adjustment = sum(
            {
                "LIKE": 0.08,
                "SELECT": 0.15,
                "DISLIKE": -0.12,
                "HOLD": -0.02,
            }[vote]
            for vote in votes
        )

        final = max(
            0,
            min(
                1,
                final + vote_adjustment,
            ),
        )

        if votes:
            positive = sum(
                vote
                in {
                    "LIKE",
                    "SELECT",
                }
                for vote in votes
            )

            negative = sum(
                vote == "DISLIKE"
                for vote in votes
            )

            reasons.append(
                f"후보 반응 찬성 "
                f"{positive}명·"
                f"반대 {negative}명 반영"
            )

        if not reasons:
            reasons = [
                (
                    f"평점 "
                    f"{movie.vote_average:.1f}점과 "
                    f"인기도를 보조 기준으로 선정"
                )
            ]

            spread = (
                max(values)
                - min(values)
            )

            if (
                len(values) > 1
                and spread <= 0.08
            ):
                reasons.append(
                    (
                        "구성원 적합도 차이가 "
                        f"{round(spread * 100)}점으로 "
                        "고른 후보"
                    )
                )

        evidence_count = sum(
            len(item.matched)
            for item in scores
        )

        if evidence_count >= 3:
            evidence_level = "HIGH"

        elif any(
            item.matched
            for item in scores
        ):
            evidence_level = "MEDIUM"

        else:
            evidence_level = "LOW"

        watch_path_status = (
            "AVAILABLE"
            if (
                providers
                or movie.is_now_playing
            )
            else "UNKNOWN"
        )

        candidates.append(
            Recommendation(
                movie=movie,
                group_score=round(
                    final,
                    4,
                ),
                member_scores=scores,
                reasons=reasons,
                evidence_level=evidence_level,
                watch_path_status=(
                    watch_path_status
                ),
            )
        )

    candidates.sort(
        key=lambda item: (
            item.group_score
        ),
        reverse=True,
    )

    direct_movies = {
        movie_id
        for member in request.members
        for movie_id
        in member.direct_movies
    }

    reranked_candidates = rerank_candidates(
        candidates,
        request.limit,
        direct_movie_ids=direct_movies,
    )

    # Production cards are a fixed set of three.  If soft filters leave one
    # or two results, refill in explicit stages while preserving member hard
    # exclusions and catalog eligibility.  Direct unit calls with limit=1/2
    # retain their requested size.
    if (
        _allow_soft_backfill
        and request.limit == RECOMMENDATION_CARD_COUNT
        and len(reranked_candidates) < RECOMMENDATION_CARD_COUNT
    ):
        seen_ids = {
            item.movie.internal_id
            for item in reranked_candidates
        }
        fallback_stages = [
            (
                {
                    "allowed_providers": [],
                    "allowed_provider_types": [],
                    "include_unknown_watch_path": True,
                },
                "시청 경로 조건을 완화해 3편 구성",
            ),
            (
                {
                    "allowed_providers": [],
                    "allowed_provider_types": [],
                    "include_unknown_watch_path": True,
                    "excluded_movie_ids": [],
                },
                "이전 추천 제외 조건을 완화해 3편 구성",
            ),
            (
                {
                    "allowed_providers": [],
                    "allowed_provider_types": [],
                    "include_unknown_watch_path": True,
                    "excluded_movie_ids": [],
                    "require_now_playing": False,
                },
                "현재 상영 조건을 완화해 3편 구성",
            ),
        ]
        for updates, reason in fallback_stages:
            if len(reranked_candidates) >= RECOMMENDATION_CARD_COUNT:
                break
            fallback_request = request.model_copy(update=updates, deep=True)
            fallback_response = recommend(
                movies,
                fallback_request,
                weights=weights,
                learned_scores=learned_scores,
                reactions=reactions,
                _allow_soft_backfill=False,
            )
            for item in fallback_response.recommendations:
                movie_id = item.movie.internal_id
                if movie_id in seen_ids:
                    continue
                if reason not in item.reasons:
                    item.reasons.append(reason)
                reranked_candidates.append(item)
                seen_ids.add(movie_id)
                if len(reranked_candidates) >= RECOMMENDATION_CARD_COUNT:
                    break

    has_conflict = any(
        movie_id in direct_movies
        and vote == "DISLIKE"
        for (
            user_id,
            movie_id,
        ), vote
        in latest_reactions.items()
    )

    consensus_threshold = max(
        2,
        math.ceil(
            len(request.members) / 2
        ),
    )

    has_consensus = any(
        movie_id in direct_movies
        and sum(
            value
            in {
                "LIKE",
                "SELECT",
            }
            for (
                user_id,
                target,
            ), value
            in latest_reactions.items()
            if target == movie_id
        )
        >= consensus_threshold
        and not any(
            value == "DISLIKE"
            for (
                user_id,
                target,
            ), value
            in latest_reactions.items()
            if target == movie_id
        )
        for movie_id in direct_movies
    )

    if has_consensus:
        mode = "CONSENSUS"

    elif (
        direct_movies
        and (
            has_conflict
            or len(direct_movies) > 1
        )
    ):
        mode = "CONFLICT_DISCOVERY"

    elif (
        reranked_candidates
        and reranked_candidates[0].evidence_level
        == "LOW"
        and not latest_reactions
    ):
        mode = "LOW_EVIDENCE"

    else:
        mode = "PREFERENCE_DISCOVERY"

    return RecommendResponse(
        room_id=request.room_id,
        round_id=request.round_id,
        mode=mode,
        recommendations=(
            reranked_candidates
        ),
        excluded=excluded,
        model_version=ModelBundle.version,
        data_version=(
            f"movies-{len(movies)}"
        ),
    )
