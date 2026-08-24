import asyncio
import hashlib
from datetime import datetime, timezone
import httpx
from .config import settings
from .schemas import Movie, PersonCredit, Provider
from .storage import JsonStore


class ApiClient:
    def __init__(self, client: httpx.AsyncClient, interval: float | None = None):
        self.client = client
        self.interval = settings.meetup_request_interval_seconds if interval is None else interval

    async def get(self, url: str, **kwargs) -> dict:
        error = None
        for attempt in range(settings.meetup_max_retries):
            try:
                response = await self.client.get(url, timeout=20, **kwargs)
                response.raise_for_status()
                if self.interval:
                    await asyncio.sleep(self.interval)
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                error = exc
                await asyncio.sleep(2 ** attempt * 0.2)
        raise RuntimeError(f"외부 API 요청이 {settings.meetup_max_retries}회 실패했습니다: {type(error).__name__}") from error


def _internal_id(tmdb_id: int | None, kobis_code: str | None, title: str) -> str:
    source = f"{tmdb_id or ''}|{kobis_code or ''}|{title}"
    return "mov_" + hashlib.sha1(source.encode()).hexdigest()[:12]


def _completeness(movie: Movie) -> int:
    return min(100, (30 if movie.genres else 0) + (30 if (movie.overview_ko or movie.overview_en or movie.overview) else 0)
               + (15 if movie.directors else 0) + (15 if movie.cast else 0) + (10 if movie.keywords else 0))


def normalize_tmdb(detail: dict, english_detail: dict | None = None) -> Movie:
    english_detail = english_detail or {}
    credits = detail.get("credits", {})
    kr = detail.get("watch/providers", {}).get("results", {}).get("KR", {})
    providers = []
    for kind in ("flatrate", "free", "ads", "rent", "buy"):
        for row in kr.get(kind, []):
            providers.append(Provider(provider_id=row["provider_id"], name=row["provider_name"], logo_path=row.get("logo_path"), type=kind))
    cast_rows = credits.get("cast", [])[:20]
    director_rows = [p for p in credits.get("crew", []) if p.get("job") == "Director"]
    cast_people = [
        PersonCredit(
            person_id=p.get("id"), name=p.get("name") or p.get("original_name") or "",
            original_name=p.get("original_name"), role="ACTOR",
        )
        for p in cast_rows if p.get("name") or p.get("original_name")
    ]
    director_people = [
        PersonCredit(
            person_id=p.get("id"), name=p.get("name") or p.get("original_name") or "",
            original_name=p.get("original_name"), role="DIRECTOR",
        )
        for p in director_rows if p.get("name") or p.get("original_name")
    ]
    directors = [p.name for p in director_people]
    keywords = detail.get("keywords", {}).get("keywords", detail.get("keywords", {}).get("results", []))
    movie = Movie(
        internal_id=_internal_id(detail.get("id"), None, detail.get("title", "")), tmdb_id=detail.get("id"),
        title=detail.get("title") or english_detail.get("title") or detail.get("original_title") or "제목 없음",
        title_ko=detail.get("title"), title_en=english_detail.get("title"), original_title=detail.get("original_title"),
        overview=detail.get("overview") or english_detail.get("overview") or "",
        overview_ko=detail.get("overview") or "", overview_en=english_detail.get("overview") or "",
        genres=[g["name"] for g in detail.get("genres", [])],
        keywords=[k["name"] for k in keywords], cast=[p.name for p in cast_people], directors=directors,
        cast_people=cast_people, director_people=director_people,
        countries=[c["iso_3166_1"] for c in detail.get("production_countries", [])], language=detail.get("original_language"),
        release_date=detail.get("release_date"), runtime=detail.get("runtime"), vote_average=detail.get("vote_average", 0),
        vote_count=detail.get("vote_count", 0), popularity=detail.get("popularity", 0), poster_path=detail.get("poster_path"),
        providers=providers, provider_link=kr.get("link"),
        recommendations=[m["id"] for m in detail.get("recommendations", {}).get("results", [])],
        similar=[m["id"] for m in detail.get("similar", {}).get("results", [])],
        data_sources=["TMDB"],
    )
    movie.completeness_score = _completeness(movie)
    movie.recommendation_eligible = movie.completeness_score >= 60 and bool(movie.genres) and bool(movie.overview)
    return movie


def apply_tmdb_person_credits(movie: Movie, credits: dict) -> bool:
    """Attach role-specific TMDB person IDs to an existing catalog movie."""
    cast_rows = credits.get("cast", [])[:20]
    director_rows = [
        row
        for row in credits.get("crew", [])
        if row.get("job") == "Director"
    ]
    cast_people = [
        PersonCredit(
            person_id=row.get("id"),
            name=row.get("name") or row.get("original_name") or "",
            original_name=row.get("original_name"),
            role="ACTOR",
        )
        for row in cast_rows
        if row.get("name") or row.get("original_name")
    ]
    director_people = [
        PersonCredit(
            person_id=row.get("id"),
            name=row.get("name") or row.get("original_name") or "",
            original_name=row.get("original_name"),
            role="DIRECTOR",
        )
        for row in director_rows
        if row.get("name") or row.get("original_name")
    ]
    if not cast_people and not director_people:
        return False
    movie.cast_people = cast_people
    movie.director_people = director_people
    movie.cast = list(dict.fromkeys(person.name for person in cast_people))
    movie.directors = list(dict.fromkeys(person.name for person in director_people))
    return True


async def enrich_tmdb_person_credits(
    store: JsonStore,
    limit: int | None = None,
    checkpoint_every: int = 250,
    concurrency: int = 2,
) -> dict:
    """Backfill missing actor/director TMDB IDs without recollecting movies.

    The catalog is checkpointed periodically, so an interrupted multi-thousand
    movie synchronization can resume by running the same command again.
    """
    credential = settings.require_tmdb()
    is_v4_token = credential.startswith("eyJ") or len(credential) > 80
    headers = {"accept": "application/json"}
    auth_params = {}
    if is_v4_token:
        headers["Authorization"] = f"Bearer {credential}"
    else:
        auth_params["api_key"] = credential

    movies = store.load_movies(use_fixture=False)
    pending = [
        movie
        for movie in movies
        if movie.tmdb_id is not None
        and not any(
            person.person_id is not None
            for person in [*movie.cast_people, *movie.director_people]
        )
    ]
    if limit is not None:
        pending = pending[: max(0, limit)]

    updated = failed = 0
    batch_size = checkpoint_every if checkpoint_every > 0 else max(1, len(pending))
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async with httpx.AsyncClient(
        base_url=settings.tmdb_base_url,
        headers=headers,
    ) as http:
        api = ApiClient(http)

        async def fetch(movie: Movie):
            async with semaphore:
                try:
                    detail = await api.get(
                        f"/movie/{movie.tmdb_id}",
                        params={
                            **auth_params,
                            "language": "ko-KR",
                            "append_to_response": "credits",
                        },
                    )
                    return movie, detail.get("credits", {}), None
                except RuntimeError as exc:
                    return movie, None, exc

        for start in range(0, len(pending), batch_size):
            batch = pending[start:start + batch_size]
            results = await asyncio.gather(*(fetch(movie) for movie in batch))
            for movie, credits, error in results:
                if error is not None or credits is None:
                    failed += 1
                elif apply_tmdb_person_credits(movie, credits):
                    updated += 1
                else:
                    failed += 1
            store.save_movies(movies)

    return {
        "catalog_movies": len(movies),
        "requested": len(pending),
        "updated": updated,
        "failed": failed,
        "concurrency": max(1, concurrency),
        "remaining_without_person_ids": sum(
            movie.tmdb_id is not None
            and not any(
                person.person_id is not None
                for person in [*movie.cast_people, *movie.director_people]
            )
            for movie in movies
        ),
    }

async def search_tmdb_movie(title: str) -> Movie | None:
    credential = settings.require_tmdb()

    is_v4_token = (
        credential.startswith("eyJ")
        or len(credential) > 80
    )

    headers = {
        "accept": "application/json",
    }

    auth_params = {}

    if is_v4_token:
        headers["Authorization"] = f"Bearer {credential}"
    else:
        auth_params["api_key"] = credential

    async with httpx.AsyncClient(
        base_url=settings.tmdb_base_url,
        headers=headers,
    ) as http:
        api = ApiClient(http)

        search = await api.get(
            "/search/movie",
            params={
                **auth_params,
                "query": title,
                "language": "ko-KR",
                "region": "KR",
            },
        )

        results = search.get("results", [])

        if not results:
            return None

        tmdb_id = results[0]["id"]

        detail = await api.get(
            f"/movie/{tmdb_id}",
            params={
                **auth_params,
                "language": "ko-KR",
                "append_to_response": (
                    "credits,keywords,recommendations,"
                    "similar,watch/providers"
                ),
            },
        )

        english = await api.get(
            f"/movie/{tmdb_id}",
            params={
                **auth_params,
                "language": "en-US",
            },
        )

        return normalize_tmdb(
            detail,
            english,
        )

def search_tmdb_movie_sync(title: str) -> Movie | None:
    credential = settings.require_tmdb()

    is_v4_token = (
        credential.startswith("eyJ")
        or len(credential) > 80
    )

    headers = {
        "accept": "application/json",
    }

    params = {}

    if is_v4_token:
        headers["Authorization"] = f"Bearer {credential}"
    else:
        params["api_key"] = credential

    with httpx.Client(
        base_url=settings.tmdb_base_url,
        headers=headers,
        timeout=20,
    ) as http:
        search_response = http.get(
            "/search/movie",
            params={
                **params,
                "query": title,
                "language": "ko-KR",
                "region": "KR",
            },
        )
        search_response.raise_for_status()
        results = search_response.json().get("results", [])

        if not results:
            return None

        tmdb_id = results[0]["id"]

        detail_response = http.get(
            f"/movie/{tmdb_id}",
            params={
                **params,
                "language": "ko-KR",
                "append_to_response": (
                    "credits,keywords,recommendations,"
                    "similar,watch/providers"
                ),
            },
        )
        detail_response.raise_for_status()

        english_response = http.get(
            f"/movie/{tmdb_id}",
            params={
                **params,
                "language": "en-US",
            },
        )
        english_response.raise_for_status()

        return normalize_tmdb(
            detail_response.json(),
            english_response.json(),
        )

async def collect_tmdb(store: JsonStore, pages: int = 1, incremental: bool = False, with_english: bool = False) -> list[Movie]:
    credential = settings.require_tmdb()
    # TMDB v4 Read Access Token is a long JWT-like token. The legacy v3 API
    # key is a short hexadecimal value and must be sent as the api_key query.
    is_v4_token = credential.startswith("eyJ") or len(credential) > 80
    headers = {"accept": "application/json"}
    auth_params = {}
    if is_v4_token:
        headers["Authorization"] = f"Bearer {credential}"
    else:
        auth_params["api_key"] = credential
    state_file = store.state / "tmdb.json"
    start = 1
    if incremental and state_file.exists():
        import json
        start = json.loads(state_file.read_text(encoding="utf-8")).get("last_page", 0) + 1
    movies = []
    async with httpx.AsyncClient(base_url=settings.tmdb_base_url, headers=headers) as http:
        api = ApiClient(http)
        for page in range(start, start + pages):
            listing = await api.get("/discover/movie", params={**auth_params, "language": "ko-KR", "region": "KR", "page": page, "sort_by": "popularity.desc"})
            store.append_jsonl(store.raw / "tmdb" / "discover.jsonl", listing)
            for row in listing.get("results", []):
                detail = await api.get(f"/movie/{row['id']}", params={**auth_params, "language": "ko-KR", "append_to_response": "credits,keywords,recommendations,similar,watch/providers"})
                store.append_jsonl(store.raw / "tmdb" / "details.jsonl", detail)
                english = await api.get(f"/movie/{row['id']}", params={**auth_params, "language": "en-US"}) if with_english else None
                if english:
                    store.append_jsonl(store.raw / "tmdb" / "details_en.jsonl", english)
                movies.append(normalize_tmdb(detail, english))
            state_file.write_text(__import__("json").dumps({"last_page": page, "collected_at": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")
    existing = store.load_movies(use_fixture=False) if incremental else []
    by_id = {(m.tmdb_id or m.internal_id): m for m in existing}
    by_id.update({(m.tmdb_id or m.internal_id): m for m in movies})
    merged = list(by_id.values())
    store.save_movies(merged)
    return movies


async def collect_kobis(store: JsonStore, pages: int = 1) -> list[dict]:
    key = settings.require_kobis()
    rows = []
    async with httpx.AsyncClient(base_url=settings.kobis_base_url) as http:
        api = ApiClient(http)
        for page in range(1, pages + 1):
            result = await api.get("/movie/searchMovieList.json", params={"key": key, "curPage": page, "itemPerPage": 100})
            store.append_jsonl(store.raw / "kobis" / "lists.jsonl", result)
            for item in result.get("movieListResult", {}).get("movieList", []):
                detail = await api.get("/movie/searchMovieInfo.json", params={"key": key, "movieCd": item["movieCd"]})
                store.append_jsonl(store.raw / "kobis" / "details.jsonl", detail)
                rows.append(detail.get("movieInfoResult", {}).get("movieInfo", {}))
    return rows
