import json
import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
from .model_registry import register_model, list_models, latest_usable_events
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .feedback import feedback_readiness
from .chat_analysis import analyze_chat
from .collectors import (
    collect_kobis,
    collect_tmdb,
    search_tmdb_movie_sync,
)
from .config import settings
from .database import MeetupDatabase, MySQLMeetupDatabase
from .models import ModelBundle, evaluate_for_deployment
from .preference_interface import build_preference_deltas
from .person_identity import canonical_person_name
from .deployment import activate_model
from .recommender import RECOMMENDATION_CARD_COUNT, recommend
from .semantic import SemanticPreferenceEngine
from .text_correction import KoreanTextCorrector
from .schemas import (
    ChatAnalyzeRequest,
    ChatMessage,
    ChatMessageCreate,
    GroupRecommendRequest,
    Preference,
    RecommendationEvent,
    RecommendationEventCreate,
    RoomRecommendRequest,
    ScheduleHandoffRequest,
    ScheduleHandoffResponse,
)
from .storage import JsonStore


logger = logging.getLogger(__name__)

THEATER_INTENT_KEYWORDS = (
    "영화관",
    "극장",
    "현재 상영",
    "상영 중",
    "상영중",
    "개봉작",
    "cgv",
    "메가박스",
    "롯데시네마",
)


def detect_theater_intent(text: str) -> bool:
    """
    사용자 문장에 영화관 관람 의도가 있는지 확인합니다.

    예:
    - 영화관에서 볼 거야
    - 극장에서 볼 영화 추천해줘
    - 현재 상영 중인 영화 알려줘
    """
    normalized_text = re.sub(
        r"\s+",
        "",
        text.lower(),
    )

    return any(
        re.sub(r"\s+", "", keyword.lower())
        in normalized_text
        for keyword in THEATER_INTENT_KEYWORDS
    )

OTT_PROVIDER_IDS = {
    "넷플릭스": 8,
    "왓챠": 97,
    "디즈니+": 337,
    "웨이브": 356,
}

@asynccontextmanager
async def lifespan(_: FastAPI):
    warmup_recommendation_models()
    yield


app = FastAPI(
    title="MeetupLog Recommendation API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)

store = JsonStore(settings.meetup_data_dir)
text_corrector = KoreanTextCorrector(
    hf_token=settings.hf_token,
    typo_model_name=settings.meetup_typo_model_name,
    spacer_dir=settings.meetup_electra_spacer_dir,
    use_typo_model=(
        settings.meetup_use_typo_model
        and settings.meetup_realtime_heavy_correction
    ),
    use_spacer_model=(
        settings.meetup_use_spacer_model
        and settings.meetup_realtime_heavy_correction
    ),
    max_chars=settings.meetup_correction_max_chars,
)

def _extract_tmdb_query(text: str) -> str | None:
    value = text.strip()

    patterns = [
        r"(.+?)\s*영화\s*(?:보고\s*싶|볼래|보자|추천|봤어|봤는데)",
        r"(.+?)\s*(?:보고\s*싶|볼래|보자|추천해줘|추천)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            value,
            re.IGNORECASE,
        )

        if match:
            candidate = match.group(1).strip(
                " ,.!?\"'"
            )

            if len(candidate) >= 2:
                return candidate

    return None





def _analyze_corrected(
    messages: list[ChatMessage],
    movies,
    room_id: str = "__direct__",
    enrichment_message_ids: set[int] | None = None,
):
    corrected_messages: list[ChatMessage] = []
    corrections: list[tuple[str, str, str, str]] = []
    catalog_updated = False
    for message in messages:
        correction = text_corrector.correct(message.text)
        corrected_messages.append(
            message.model_copy(update={"text": correction.corrected})
        )
        corrections.append(
            (message.user_id, correction.corrected, correction.original, correction.backend)
        )
    for message in corrected_messages:
        if (
            enrichment_message_ids is not None
            and message.message_id not in enrichment_message_ids
        ):
            continue

        text = message.text.strip()

        # 너무 짧거나 일반 잡담은 TMDB 검색하지 않음
        if len(text) < 2:
            continue

        # 이미 카탈로그 영화가 문장에 포함돼 있으면 검색 생략
        normalized_text = text.casefold()
        already_known = any(
            movie.title.casefold() in normalized_text
            or (
                movie.original_title
                and movie.original_title.casefold() in normalized_text
            )
            for movie in movies
        )

        if already_known:
            continue

        query = _extract_tmdb_query(text)

        if not query:
            continue

        try:
            tmdb_movie = search_tmdb_movie_sync(query)
        except Exception as exc:
            logger.info(
                "TMDB enrichment skipped for room=%s message_id=%s: %s",
                room_id,
                message.message_id,
                exc,
            )
            tmdb_movie = None

        if (
            tmdb_movie
            and tmdb_movie.tmdb_id
            and all(
                movie.tmdb_id != tmdb_movie.tmdb_id
                for movie in movies
            )
        ):
            movies.append(tmdb_movie)
            catalog_updated = True

    if catalog_updated:
        store.save_movies(movies)

    result = analyze_chat(
        ChatAnalyzeRequest(messages=corrected_messages),
        movies,
    )
    for analysis in result.analyses:
        correction = next(
            (
                item
                for item in reversed(corrections)
                if item[0] == analysis.user_id and item[1] == analysis.text
            ),
            None,
        )
        if correction and correction[1] != correction[2]:
            analysis.text = correction[2]
            analysis.corrected_from = analysis.corrected_from or correction[2]
            analysis.note = f"{correction[3]} 교정 후 분석 · {analysis.note}"
    return result

database = (
    MySQLMeetupDatabase(
        settings.meetup_mysql_host,
        settings.meetup_mysql_port,
        settings.meetup_mysql_database,
        settings.meetup_mysql_user,
        settings.meetup_mysql_password,
    )
    if settings.meetup_db_backend == "mysql"
    else MeetupDatabase(settings.meetup_db_path)
)

jobs: dict[str, dict] = {}
_bundle = None
_bundle_load_error: str | None = None
_semantic_engine = SemanticPreferenceEngine(
    settings.meetup_model_name,
    use_embedding=settings.meetup_use_embedding,
    cache_dir=settings.meetup_model_dir / "semantic",
    precomputed_dir=settings.meetup_data_dir / "normalized",
)

training_state = {
    "running": False,
    "last_trained_usable_events": latest_usable_events(
        settings.meetup_model_dir
    ),
}
AUTO_RETRAIN_MIN_NEW_EVENTS = 500

def _load_bundle():
    global _bundle, _bundle_load_error

    path = settings.meetup_model_dir / "current.joblib"

    if _bundle is None and path.exists():
        try:
            _bundle = joblib.load(path)
            _bundle_load_error = None
        except Exception as exc:
            # Incompatible model artifacts must not take the API down.
            # The deterministic and semantic fallback paths remain available.
            _bundle_load_error = f"{type(exc).__name__}: {exc}"
            return None

    return _bundle


def _learned_scores(movies, request):
    bundle = _load_bundle()

    semantic = _semantic_engine.score(
        movies,
        request.members,
    ).scores

    if (
        bundle is None
        or bundle.matrix is None
        or not bundle.matches_catalog(movies)
    ):
        return semantic or None

    lookup: dict[str, int] = {}

    for index, movie in enumerate(movies):
        lookup[movie.internal_id.casefold()] = index
        lookup[movie.title.casefold()] = index

        if movie.original_title:
            lookup[movie.original_title.casefold()] = index

    result: dict[str, list[float]] = {}

    for member in request.members:
        seeds = [
            lookup[value.casefold()]
            for value in member.liked_movies
            if value.casefold() in lookup
        ]

        seed_scores = bundle.scores_for_seeds(seeds).tolist() if seeds else None
        semantic_scores = semantic.get(member.user_id)
        if seed_scores and semantic_scores:
            result[member.user_id] = [
                0.55 * seed + 0.45 * meaning
                for seed, meaning in zip(seed_scores, semantic_scores)
            ]
        elif seed_scores:
            result[member.user_id] = seed_scores
        elif semantic_scores:
            result[member.user_id] = semantic_scores

    return result or None


_warmup_state = {
    "completed": False,
    "seconds": None,
    "error": None,
}


def warmup_recommendation_models():
    """Load and validate the catalog/model before the first recommendation."""
    started = time.perf_counter()
    try:
        movies = [
            movie
            for movie in store.load_movies()
            if movie.recommendation_eligible
        ]
        bundle = _load_bundle()
        if bundle is not None and not bundle.matches_catalog(movies):
            raise ValueError("learned model catalog does not match the active catalog")
        _semantic_engine.fit_catalog(movies)
        _warmup_state.update({
            "completed": True,
            "seconds": round(time.perf_counter() - started, 3),
            "error": None,
        })
    except Exception as exc:
        _warmup_state.update({
            "completed": True,
            "seconds": round(time.perf_counter() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
        })


def _person_identity_readiness(movies) -> dict:
    credits = [
        person
        for movie in movies
        for person in [*movie.cast_people, *movie.director_people]
    ]
    identified = sum(person.person_id is not None for person in credits)
    coverage = identified / len(credits) if credits else 0.0
    return {
        "structured_credits": len(credits),
        "identified_credits": identified,
        "id_coverage": round(coverage, 4),
        "production_ready": bool(credits) and coverage >= 0.95,
    }


def model_readiness() -> dict:
    movies = [
        movie
        for movie in store.load_movies()
        if movie.recommendation_eligible
    ]
    bundle = _load_bundle()
    model_path = settings.meetup_model_dir / "current.joblib"
    learned_matches = bool(
        bundle is not None
        and bundle.matrix is not None
        and bundle.matches_catalog(movies)
    )
    return {
        "model_version": ModelBundle.version,
        "catalog_movies": len(movies),
        "baseline_ready": bool(movies),
        "learned_model": {
            "available": model_path.exists(),
            "loaded": bundle is not None,
            "catalog_matches": learned_matches,
            "error": _bundle_load_error,
        },
        "semantic_backend": _semantic_engine.backend,
        "person_identity": _person_identity_readiness(movies),
        "warmup": dict(_warmup_state),
    }


@app.exception_handler(RuntimeError)
async def runtime_error(_, exc: RuntimeError):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "SERVICE_NOT_READY",
                "message": str(exc),
                "retryable": True,
            }
        },
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "meetup-log-ml",
        "version": app.version,
        "model": model_readiness(),
        "correction": text_corrector.status(),
    }


@app.get("/v1/readiness")
def readiness():
    return model_readiness()


@app.get("/v1/version")
def version():
    return {
        "api": "v1",
        "model": ModelBundle.version,
        "data": f"movies-{len(store.load_movies())}",
    }


async def _collect(
    job_id: str,
    source: str,
    pages: int,
    incremental: bool,
):
    jobs[job_id] = {"status": "RUNNING"}

    try:
        if source == "tmdb":
            result = await collect_tmdb(
                store,
                pages,
                incremental,
            )
        else:
            result = await collect_kobis(
                store,
                pages,
            )

        jobs[job_id] = {
            "status": "SUCCEEDED",
            "count": len(result),
        }

    except Exception as exc:
        jobs[job_id] = {
            "status": "FAILED",
            "error": str(exc),
        }


@app.post("/v1/collections", status_code=202)
async def start_collection(
    source: str,
    background: BackgroundTasks,
    pages: int = 1,
    incremental: bool = False,
):
    if source not in {"tmdb", "kobis"}:
        raise HTTPException(
            status_code=422,
            detail="source는 tmdb 또는 kobis여야 합니다.",
        )

    job_id = f"collect-{source}-{len(jobs) + 1}"

    background.add_task(
        _collect,
        job_id,
        source,
        pages,
        incremental,
    )

    return {
        "job_id": job_id,
        "status": "QUEUED",
    }


@app.get("/v1/jobs/{job_id}")
def job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(
            status_code=404,
            detail="작업을 찾을 수 없습니다.",
        )

    return jobs[job_id]

@app.post("/v1/training")
def train():
    global _bundle
    print("[TRAIN] 1. movies loading", flush=True)

    movies = [
        movie
        for movie in store.load_movies()
        if movie.recommendation_eligible
    ]

    print(f"[TRAIN] 2. movies loaded: {len(movies)}", flush=True)

    bundle = ModelBundle(
        settings.meetup_model_name
        if settings.meetup_use_embedding
        else None
    )

    print("[TRAIN] 3. bundle.fit start", flush=True)
    report = bundle.fit(movies)
    print("[TRAIN] 4. bundle.fit complete", flush=True)

    settings.meetup_model_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("[TRAIN] 5. saving model", flush=True)

    print("[TRAIN] 6. candidate ready", flush=True)
    print("[TRAIN] 7. evaluation start", flush=True)

    metrics, deployment_guardrail = evaluate_for_deployment(bundle, movies)

    print("[TRAIN] 8. evaluation complete", flush=True)

    output = {
        **report,
        "metrics": metrics,
        "deployment_guardrail": deployment_guardrail,
    }

    # 평가가 끝난 후보만 원자적으로 활성화한다. 로드/검증 실패 시
    # previous.joblib에서 기존 모델을 즉시 복원한다.
    _bundle = activate_model(bundle, settings.meetup_model_dir)

    (
        settings.meetup_model_dir
        / "evaluation.json"
    ).write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    current_feedback = feedback_readiness(
        database.recommendation_events()
    )

    register_model(
        settings.meetup_model_dir,
        ModelBundle.version,
        output,
        usable_events=current_feedback["usable_events"],
    )

    print("[TRAIN] 9. evaluation.json saved", flush=True)

    return output

def _run_auto_training():
    if training_state["running"]:
        return

    training_state["running"] = True

    try:
        train()
    finally:
        training_state["running"] = False

@app.get("/v1/evaluation")
def evaluation():
    path = (
        settings.meetup_model_dir
        / "evaluation.json"
    )

    if path.exists():
        return json.loads(
            path.read_text(encoding="utf-8")
        )

    component_path = (
        Path(__file__).resolve().parents[1]
        / "evaluation"
        / "role_context_validation.json"
    )
    if component_path.exists():
        return json.loads(component_path.read_text(encoding="utf-8"))

    return {
        "status": "NOT_EVALUATED",
    }

@app.get("/v1/models")
def models_registry():
    return {
        "models": list_models(
            settings.meetup_model_dir
        )
    }

def _normalize_provider_name(value: str) -> str:
    """
    OTT 제공자 이름을 비교하기 쉽게 정규화한다.

    예:
    - "Disney Plus" -> "disneyplus"
    - "Apple TV Plus" -> "appletvplus"
    - "쿠팡 플레이" -> "쿠팡플레이"
    """
    return "".join(
        character
        for character in value.casefold()
        if character.isalnum()
    )


OTT_PROVIDER_ALIASES = {
    "넷플릭스": {
        "넷플릭스",
        "넷플",
        "netflix",
    },
    "티빙": {
        "티빙",
        "tving",
    },
    "웨이브": {
        "웨이브",
        "wavve",
    },
    "디즈니+": {
        "디즈니+",
        "디즈니플러스",
        "디플",
        "disney+",
        "disneyplus",
    },
    "왓챠": {
        "왓챠",
        "watcha",
    },
    "쿠팡플레이": {
        "쿠팡플레이",
        "쿠플",
        "coupangplay",
    },
    "Apple TV+": {
        "애플티비",
        "애플tv",
        "애플티비플러스",
        "appletv",
        "appletv+",
        "appletvplus",
    },
}


def _provider_ids_for_platforms(
    movies,
    platforms: list[str],
) -> set[int]:
    """
    사용자가 말한 OTT 이름을 현재 영화 데이터에 들어 있는
    TMDB provider_id로 변환한다.

    provider ID를 코드에 고정하지 않고, movies.runtime.json 또는
    movies.json의 실제 provider 데이터를 기준으로 찾는다.
    """
    if not platforms:
        return set()

    requested_names: set[str] = set()

    for platform in platforms:
        platform_aliases = OTT_PROVIDER_ALIASES.get(
            platform,
            {platform},
        )

        requested_names.update(
            _normalize_provider_name(alias)
            for alias in platform_aliases
        )

    provider_ids: set[int] = set()

    for movie in movies:
        for provider in movie.providers:
            provider_name = _normalize_provider_name(
                provider.name
            )

            if provider_name in requested_names:
                provider_ids.add(
                    provider.provider_id
                )

    return provider_ids


def _apply_watch_preferences(
    request: GroupRecommendRequest,
    movies,
) -> None:
    """
    채팅 분석 결과에 저장된 OTT 및 영화관 조건을
    실제 추천 요청 필터에 반영한다.
    """
    requested_platforms = list(
        dict.fromkeys(
            platform
            for member in request.members
            for platform in member.ott_platforms
        )
    )

    detected_provider_ids = (
        _provider_ids_for_platforms(
            movies,
            requested_platforms,
        )
    )

    if detected_provider_ids:
        existing_provider_ids = set(
            request.allowed_providers
        )

        request.allowed_providers = sorted(
            existing_provider_ids
            | detected_provider_ids
        )

    strict_ott_requested = any(
        member.ott_strict
        for member in request.members
    )

    if strict_ott_requested:
        request.include_unknown_watch_path = False

    theater_requested = any(
        member.prefers_theater
        for member in request.members
    )

    if theater_requested:
        request.require_now_playing = True


@app.post("/v1/recommendations/group")
def group_recommendation(
    request: GroupRecommendRequest,
):
    # The product contract is three cards, not "up to three".
    request.limit = RECOMMENDATION_CARD_COUNT
    # 현재 채팅방의 최근 사용자 메시지를 가져온다.
    room_messages = [
        message
        for message in database.messages(
            request.room_id
        )
        if message.user_id != "AI"
    ][-20:]

    # 최근 채팅에서 영화관 관람 의도가 감지되면
    # 현재 상영 중인 영화만 추천하도록 설정한다.
    request.require_now_playing = (
        request.require_now_playing
        or any(
            detect_theater_intent(
                message.text
            )
            for message in room_messages
        )
    )

    movies = [
        movie
        for movie in store.load_movies()
        if movie.recommendation_eligible
    ]

    # 분석된 OTT와 영화관 관람 조건을
    # 실제 추천 요청에 연결한다.
    _apply_watch_preferences(
        request,
        movies,
    )

    result = recommend(
        movies,
        request,
        learned_scores=_learned_scores(
            movies,
            request,
        ),
    )

    if len(result.recommendations) != RECOMMENDATION_CARD_COUNT:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "INSUFFICIENT_RECOMMENDATION_CANDIDATES",
                    "message": (
                        "하드 제외 조건을 지키면서 서로 다른 영화 3편을 "
                        "구성할 수 없습니다."
                    ),
                    "retryable": False,
                    "candidate_count": len(result.recommendations),
                }
            },
        )

    database.save_recommendations(
        request.room_id,
        request.round_id,
        result.recommendations,
    )

    return result


@app.post(
    "/v1/recommendation-events",
    response_model=RecommendationEvent,
)


def save_recommendation_event(
    event: RecommendationEventCreate,
    background: BackgroundTasks,
):
    if event.event_type == "SELECT":
        existing_selection = next(
            (
                item
                for item in reversed(database.recommendation_events())
                if item.room_id == event.room_id
                and item.event_type == "SELECT"
            ),
            None,
        )
        if existing_selection:
            if existing_selection.movie_id == event.movie_id:
                return existing_selection
            raise HTTPException(
                status_code=409,
                detail="이미 확정된 영화는 변경할 수 없습니다.",
            )

    saved = database.save_recommendation_event(
        event
    )

    events = database.recommendation_events()
    readiness = feedback_readiness(events)

    if (
        readiness["ready"]
        and not training_state["running"]
        and readiness["usable_events"]
            >= training_state["last_trained_usable_events"]
            + AUTO_RETRAIN_MIN_NEW_EVENTS
    ):
        training_state["last_trained_usable_events"] = (
            readiness["usable_events"]
        )

        background.add_task(
            _run_auto_training
        )

    return saved


@app.get(
    "/v1/recommendation-events",
    response_model=list[RecommendationEvent],
)
def list_recommendation_events(
    round_id: str | None = None,
):
    return database.recommendation_events(
        round_id
    )

@app.get("/v1/feedback/readiness")
def feedback_status():
    events = database.recommendation_events()
    return feedback_readiness(events)

@app.get("/v1/training/status")
def training_status():
    readiness = feedback_readiness(
        database.recommendation_events()
    )

    return {
        "running": training_state["running"],
        "last_trained_usable_events": (
            training_state["last_trained_usable_events"]
        ),
        "usable_events": readiness["usable_events"],
        "ready": readiness["ready"],
        "next_auto_retrain_at": max(
            1000,
            training_state["last_trained_usable_events"]
            + AUTO_RETRAIN_MIN_NEW_EVENTS,
        ),
    }

@app.post("/v1/chat/analyze")
def chat_analysis(
    request: ChatAnalyzeRequest,
):
    user_messages = [
        message
        for message in request.messages
        if message.user_id != "AI"
    ]

    return _analyze_corrected(
        user_messages,
        store.load_movies(),
    )


@app.get("/v1/correction/status")
def correction_status():
    return text_corrector.status()


def _merge_preferences(
    current: list[Preference],
    updates: list[Preference],
) -> list[Preference]:
    merged = {
        member.user_id:
            member.model_copy(deep=True)
        for member in current
    }

    dictionary_pairs = [
        (
            "liked_genres",
            "disliked_genres",
        ),
        (
            "disliked_genres",
            "liked_genres",
        ),
        (
            "liked_topics",
            "disliked_topics",
        ),
        (
            "disliked_topics",
            "liked_topics",
        ),
        (
            "liked_brands",
            "disliked_brands",
        ),
        (
            "disliked_brands",
            "liked_brands",
        ),
    ]

    list_fields = [
        "liked_movies",
        "direct_movies",
        "seen_movies",
        "rewatch_allowed_movies",
        "disliked_movies",
        "liked_people",
        "disliked_people",
        "countries",
        "excluded_countries",
        "languages",
        "certifications",
        "allowed_providers",
        "allowed_provider_types",
        "ott_platforms",
        "hard_exclusions",
        "evidence_message_ids",
    ]
    list_opposites = {
        "liked_movies": ("disliked_movies",),
        "direct_movies": ("disliked_movies",),
        "disliked_movies": ("liked_movies", "direct_movies"),
        "liked_people": ("disliked_people",),
        "disliked_people": ("liked_people",),
        "countries": ("excluded_countries",),
        "excluded_countries": ("countries",),
    }

    scalar_fields = [
        "max_runtime",
        "min_runtime",
        "min_year",
        "max_year",
    ]

    # False 기본값으로 기존 True를 덮어쓰면 안 되는 필드다.
    positive_boolean_fields = [
        "prefers_theater",
        "ott_strict",
    ]

    person_list_pairs = [
        ("liked_actors", "disliked_actors"),
        ("disliked_actors", "liked_actors"),
        ("liked_directors", "disliked_directors"),
        ("disliked_directors", "liked_directors"),
    ]

    def person_key(person):
        identity = (
            f"id:{person.person_id}"
            if person.person_id is not None
            else f"name:{canonical_person_name(person.original_name or person.name)}"
        )
        return person.role, identity

    for update in updates:
        target = merged.setdefault(
            update.user_id,
            Preference(
                user_id=update.user_id
            ),
        )

        for field, opposite in dictionary_pairs:
            values = getattr(
                update,
                field,
            )

            if not values:
                continue

            getattr(
                target,
                field,
            ).update(values)

            for key in values:
                getattr(
                    target,
                    opposite,
                ).pop(
                    key,
                    None,
                )

        for field in list_fields:
            values = getattr(
                update,
                field,
            )

            if not values:
                continue

            existing_values = getattr(
                target,
                field,
            )

            setattr(
                target,
                field,
                list(
                    dict.fromkeys(
                        [
                            *existing_values,
                            *values,
                        ]
                    )
                ),
            )

            for opposite in list_opposites.get(field, ()):
                setattr(
                    target,
                    opposite,
                    [
                        item
                        for item in getattr(target, opposite)
                        if item not in values
                    ],
                )

        for field, opposite in person_list_pairs:
            values = getattr(update, field)
            if not values:
                continue
            incoming = {person_key(person): person for person in values}
            existing = {
                person_key(person): person
                for person in getattr(target, field)
            }
            existing.update(incoming)
            setattr(target, field, list(existing.values()))
            setattr(
                target,
                opposite,
                [
                    person
                    for person in getattr(target, opposite)
                    if person_key(person) not in incoming
                ],
            )

        for field in scalar_fields:
            value = getattr(
                update,
                field,
            )

            if value is not None:
                setattr(
                    target,
                    field,
                    value,
                )

        # 새 분석 결과가 True일 때만 기존 상태를 True로 변경한다.
        # 새 메시지의 기본값 False가 기존 True를 지우지 않게 한다.
        for field in positive_boolean_fields:
            if getattr(
                update,
                field,
                False,
            ):
                setattr(
                    target,
                    field,
                    True,
                )

        target.confidence = (
            update.confidence
        )

    return list(
        merged.values()
    )


def _room_analysis(room_id: str):
    room_movies = store.load_movies()
    movie_titles = {
        movie.internal_id: movie.title
        for movie in room_movies
    }
    messages = database.messages(
        room_id
    )

    if not messages:
        return {
            "messages": [],
            "members": [],
            "analyses": [],
            "recommended_movie_ids":
                database.recommended_movie_ids(
                    room_id
                ),
            "movie_titles": movie_titles,
            "analysis": {
                "mode": "INCREMENTAL",
                "processed": 0,
                "last_message_id": 0,
            },
        }

    checkpoint = (
        database.analysis_checkpoint(
            room_id
        )
    )

    pending = (
        database.messages_after(
            room_id,
            checkpoint,
        )
    )

    members = database.preferences(
        room_id
    )

    analyses = []
    processed_user_messages = 0

    if pending:
        context = (
            database.context_messages(
                room_id,
                checkpoint,
                limit=12,
            )
            if checkpoint
            else []
        )

        # AI가 생성한 추천 안내 메시지는
        # 사용자 취향 분석 대상에서 제외한다.
        selected = {
            message.message_id: message
            for message in [
                *context,
                *pending,
            ]
            if (
                message.message_id
                is not None
                and message.user_id != "AI"
            )
        }

        analysis_input = [
            selected[key]
            for key in sorted(
                selected
            )
        ][-200:]

        pending_user_messages = [
            message
            for message in pending
            if message.user_id != "AI"
        ]

        processed_user_messages = len(
            pending_user_messages
        )
        if analysis_input and pending_user_messages:
            result = _analyze_corrected(
                analysis_input,
                room_movies,
                room_id,
                enrichment_message_ids={
                    message.message_id
                    for message in pending_user_messages
                    if message.message_id is not None
                },
            )

            members = _merge_preferences(
                members,
                result.members,
            )
            database.save_preferences(
                room_id,
                members,
            )

            analyses = result.analyses[
                -processed_user_messages:
            ]

        # AI 메시지만 pending에 있어도
        # 체크포인트는 반드시 전진시킨다.
        checkpoint = max(
            message.message_id or 0
            for message in pending
        )

        database.save_analysis_checkpoint(
            room_id,
            checkpoint,
        )

    selected_event = next(
        (
            item
            for item in reversed(database.recommendation_events())
            if item.room_id == room_id
            and item.event_type == "SELECT"
        ),
        None,
    )

    return {
        "members": [
            member.model_dump()
            for member in members
        ],
        "analyses": [
            item.model_dump()
            for item in analyses
        ],
        "messages": [
            message.model_dump()
            for message in messages
        ],
        "recommended_movie_ids":
            database.recommended_movie_ids(
                room_id
            ),
        "movie_titles": movie_titles,
        "selected_movie_id": (
            selected_event.movie_id
            if selected_event
            else None
        ),
        "analysis": {
            "mode": "INCREMENTAL",
            "processed":
                processed_user_messages,
            "last_message_id":
                checkpoint,
        },
    }

def _room_snapshot(room_id: str):
    """Return saved room state without running NLP/ET5 again."""

    room_movies = store.load_movies()

    movie_titles = {
        movie.internal_id: movie.title
        for movie in room_movies
    }

    messages = database.messages(room_id)
    members = database.preferences(room_id)

    checkpoint = database.analysis_checkpoint(
        room_id
    )

    selected_event = next(
        (
            item
            for item in reversed(
                database.recommendation_events()
            )
            if item.room_id == room_id
            and item.event_type == "SELECT"
        ),
        None,
    )

    return {
        "members": [
            member.model_dump()
            for member in members
        ],
        "analyses": [],
        "messages": [
            message.model_dump()
            for message in messages
        ],
        "recommended_movie_ids":
            database.recommended_movie_ids(
                room_id
            ),
        "movie_titles": movie_titles,
        "selected_movie_id": (
            selected_event.movie_id
            if selected_event
            else None
        ),
        "analysis": {
            "mode": "SNAPSHOT",
            "processed": 0,
            "last_message_id": checkpoint,
        },
    }

@app.post("/v1/chat/messages")
def save_chat_message(
    request: ChatMessageCreate,
):
    before = database.preferences(
        request.room_id
    )
    receipt = database.add_message(
        request.room_id,
        request.user_id,
        request.text,
        request.reply_to_message_id,
        request.idempotency_key,
    )
    response = _room_analysis(
        request.room_id
    )
    response.update({
        "room_id": request.room_id,
        "round_id": request.round_id,
        "processing_status": (
            "DUPLICATE"
            if not receipt["created"]
            else "UNCHANGED"
        ),
        "state_version": receipt["state_version"],
        "idempotency_key": request.idempotency_key,
        "preference_deltas": [],
        "model_version": ModelBundle.version,
    })
    if receipt["created"]:
        after = database.preferences(
            request.room_id
        )
        source_message_id = (
            request.idempotency_key
            or str(receipt["message_id"])
        )
        deltas = build_preference_deltas(
            before,
            after,
            source_message_id,
        )
        response["preference_deltas"] = [
            item.model_dump()
            for item in deltas
        ]
        response["processing_status"] = (
            "APPLIED" if deltas else "UNCHANGED"
        )
    return response


@app.get("/v1/chat/rooms/{room_id}")
def room_chat(room_id: str):
    response = _room_snapshot(
        room_id
    )

    response.update({
        "room_id": room_id,
        "round_id": None,
        "processing_status": "UNCHANGED",
        "state_version": database.state_version(room_id),
        "idempotency_key": None,
        "preference_deltas": [],
        "model_version": ModelBundle.version,
    })
    return response


@app.post(
    "/v1/chat/rooms/{room_id}/recommendations"
)
def recommend_from_room_state(
    room_id: str,
    request: RoomRecommendRequest,
):
    state_version = database.state_version(
        room_id
    )
    if (
        request.expected_state_version is not None
        and request.expected_state_version
        != state_version
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "STALE_PREFERENCE_STATE",
                    "message": (
                        f"expected state "
                        f"{request.expected_state_version}, "
                        f"current state is {state_version}"
                    ),
                    "retryable": True,
                }
            },
        )

    members = database.preferences(room_id)
    if not members:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "PREFERENCE_STATE_EMPTY",
                    "message": "분석된 누적 선호가 없습니다.",
                    "retryable": False,
                }
            },
        )

    group_request = GroupRecommendRequest(
        room_id=room_id,
        round_id=request.round_id,
        members=members,
        allowed_providers=request.allowed_providers,
        allowed_provider_types=(
            request.allowed_provider_types
        ),
        limit=request.limit,
        include_unknown_watch_path=(
            request.include_unknown_watch_path
        ),
        require_now_playing=(
            request.require_now_playing
        ),
        excluded_movie_ids=(
            request.excluded_movie_ids
        ),
    )
    return group_recommendation(group_request)


@app.delete("/v1/chat/rooms/{room_id}")
def reset_room_chat(room_id: str):
    database.reset_room(
        room_id
    )

    return {
        "room_id": room_id,
        "status": "RESET",
    }


@app.post("/v1/recommendations/user")
def user_recommendation(
    request: GroupRecommendRequest,
):
    if len(request.members) != 1:
        raise HTTPException(
            status_code=422,
            detail=(
                "단일 사용자 API에는 "
                "members가 1명이어야 합니다."
            ),
        )

    # 채팅방의 최근 사용자 메시지를 가져온다.
    room_messages = [
        message
        for message in database.messages(
            request.room_id
        )
        if message.user_id != "AI"
    ][-20:]

    # 사용자가 직접 require_now_playing=True를 보냈거나,
    # 최근 채팅에서 영화관 관람 의도가 감지되면
    # 현재 상영작만 추천한다.
    request.require_now_playing = (
        request.require_now_playing
        or any(
            detect_theater_intent(
                message.text
            )
            for message in room_messages
        )
    )

    movies = [
        movie
        for movie in store.load_movies()
        if movie.recommendation_eligible
    ]

    # 단일 사용자 추천에도 OTT와 영화관 조건을 반영한다.
    _apply_watch_preferences(
        request,
        movies,
    )

    return recommend(
        movies,
        request,
        learned_scores=_learned_scores(
            movies,
            request,
        ),
    )


@app.get(
    "/v1/movies/{movie_id}/watch-providers"
)
def providers(movie_id: str):
    movie = next(
        (
            item
            for item in store.load_movies()
            if (
                item.internal_id == movie_id
                or str(item.tmdb_id)
                == movie_id
            )
        ),
        None,
    )

    if not movie:
        raise HTTPException(
            status_code=404,
            detail="영화를 찾을 수 없습니다.",
        )

    return {
        "movie_id": movie.internal_id,
        "region": "KR",
        "status": (
            "AVAILABLE"
            if (
                movie.providers
                or movie.is_now_playing
            )
            else "UNKNOWN"
        ),
        "providers": movie.providers,
        "link": movie.provider_link,
        "watch_path": movie.watch_path,
        "is_now_playing":
            movie.is_now_playing,
        "cinema_sources":
            movie.cinema_sources,
        "attribution": (
            "TMDB watch provider data "
            "powered by JustWatch"
        ),
    }


@app.post(
    "/v1/schedule-handoffs",
    response_model=ScheduleHandoffResponse,
)
def schedule_handoff(
    request: ScheduleHandoffRequest,
):
    movie = next(
        (
            item
            for item in store.load_movies()
            if (
                item.internal_id
                == request.selected_movie_id
            )
        ),
        None,
    )

    if not movie:
        raise HTTPException(
            status_code=404,
            detail=(
                "선택한 영화를 "
                "찾을 수 없습니다."
            ),
        )

    return ScheduleHandoffResponse(
        room_id=request.room_id,
        round_id=request.round_id,
        selected_movie_id=movie.internal_id,
        selected_movie_title=movie.title,
        participant_ids=list(
            dict.fromkeys(
                request.participant_ids
            )
        ),
    )
