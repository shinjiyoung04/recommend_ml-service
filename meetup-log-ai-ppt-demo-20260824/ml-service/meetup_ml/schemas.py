from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field

ProviderType = Literal["flatrate", "free", "ads", "rent", "buy"]
RecommendationMode = Literal["CONSENSUS", "PREFERENCE_DISCOVERY", "CONFLICT_DISCOVERY", "LOW_EVIDENCE"]


class Provider(BaseModel):
    provider_id: int
    name: str
    logo_path: str | None = None
    type: ProviderType


class PersonCredit(BaseModel):
    """Stable TMDB person identity with localized/original name aliases."""
    person_id: int | None = None
    name: str
    original_name: str | None = None
    role: Literal["ACTOR", "DIRECTOR"]


class PersonPreference(BaseModel):
    """Role-aware person preference resolved from chat to a catalog identity."""
    person_id: int | None = None
    name: str
    original_name: str | None = None
    role: Literal["ACTOR", "DIRECTOR"]
    strength: float = Field(1.0, ge=0, le=1)
    identity_source: Literal["TMDB_ID", "CATALOG_ALIAS", "TEXT_ONLY"] = "TEXT_ONLY"


class Movie(BaseModel):
    internal_id: str
    tmdb_id: int | None = None
    kobis_code: str | None = None
    title: str
    title_ko: str | None = None
    title_en: str | None = None
    original_title: str | None = None
    overview: str = ""
    overview_ko: str = ""
    overview_en: str = ""
    genres: list[str] = []
    keywords: list[str] = []
    cast: list[str] = []
    directors: list[str] = []
    cast_people: list[PersonCredit] = []
    director_people: list[PersonCredit] = []
    production_companies: list[str] = []
    original_platforms: list[str] = []
    content_flags: list[str] = []
    countries: list[str] = []
    language: str | None = None
    release_date: str | None = None
    runtime: int | None = None
    certification: str | None = None
    vote_average: float = 0
    vote_count: int = 0
    popularity: float = 0
    poster_path: str | None = None
    providers: list[Provider] = []
    provider_link: str | None = None
    recommendations: list[int] = []
    similar: list[int] = []
    data_sources: list[Literal["TMDB", "KOBIS"]] = []
    completeness_score: int = Field(0, ge=0, le=100)
    recommendation_eligible: bool = True
    is_now_playing: bool = False
    watch_path: str | None = None
    cinema_sources: list[dict] = []
    now_playing_updated_at: str | None = None


class Preference(BaseModel):
    user_id: str
    liked_genres: dict[str, float] = {}
    disliked_genres: dict[str, float] = {}
    liked_topics: dict[str, float] = {}
    disliked_topics: dict[str, float] = {}
    liked_movies: list[str] = []
    direct_movies: list[str] = []
    seen_movies: list[str] = []
    rewatch_allowed_movies: list[str] = []
    disliked_movies: list[str] = []
    liked_people: list[str] = []
    disliked_people: list[str] = []
    # New role-aware fields are the ranking source of truth.  The legacy
    # liked_people/disliked_people fields remain for API compatibility.
    liked_actors: list[PersonPreference] = []
    disliked_actors: list[PersonPreference] = []
    liked_directors: list[PersonPreference] = []
    disliked_directors: list[PersonPreference] = []
    liked_brands: dict[str, float] = {}
    disliked_brands: dict[str, float] = {}
    max_runtime: int | None = None
    min_runtime: int | None = None
    min_year: int | None = None
    max_year: int | None = None
    countries: list[str] = []
    excluded_countries: list[str] = []
    languages: list[str] = []
    certifications: list[str] = []
    allowed_providers: list[int] = []
    allowed_provider_types: list[ProviderType] = []
    ott_platforms: list[str] = []
    preferred_original_platforms: list[str] = []
    ott_strict: bool = False
    prefers_theater: bool = False
    hard_exclusions: list[str] = []
    confidence: float = Field(1, ge=0, le=1)
    evidence_message_ids: list[str] = []


class GroupRecommendRequest(BaseModel):
    room_id: str
    round_id: str
    members: list[Preference] = Field(min_length=1, max_length=20)
    allowed_providers: list[int] = []
    allowed_provider_types: list[ProviderType] = []
    limit: int = Field(3, ge=1, le=20)
    include_unknown_watch_path: bool = True
    require_now_playing: bool = False
    excluded_movie_ids: list[str] = []


class MemberScore(BaseModel):
    user_id: str
    score: float
    matched: list[str] = []
    penalties: list[str] = []
    score_breakdown: dict[str, float] = {}


class Recommendation(BaseModel):
    movie: Movie
    group_score: float
    member_scores: list[MemberScore]
    reasons: list[str]
    evidence_level: Literal["LOW", "MEDIUM", "HIGH"]
    watch_path_status: Literal["AVAILABLE", "UNKNOWN"]


class RecommendResponse(BaseModel):
    room_id: str
    round_id: str
    mode: RecommendationMode
    recommendations: list[Recommendation]
    excluded: list[dict]
    model_version: str
    data_version: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatMessage(BaseModel):
    message_id: int | None = None
    user_id: str
    text: str = Field(min_length=1, max_length=500)
    reply_to_message_id: int | None = None


class ChatAnalyzeRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=200)


class ChatMessageCreate(ChatMessage):
    room_id: str = Field(min_length=1, max_length=64)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    round_id: str | None = Field(default=None, min_length=1, max_length=64)


class MessageAnalysis(BaseModel):
    user_id: str
    text: str
    target: str | None = None
    target_type: Literal["GENRE", "MOVIE", "PERSON", "BRAND", "TOPIC", "COUNTRY", "CONSTRAINT", "THEATER", "YEAR", "OTT", "UNKNOWN"] = "UNKNOWN"
    attitude: Literal["STRONG_LIKE", "LIKE", "WEAK_LIKE", "NEUTRAL", "UNCERTAIN", "DISLIKE", "STRONG_DISLIKE", "QUESTION"]
    preference_score: float
    confidence: float
    person_id: int | None = None
    person_role: Literal["ACTOR", "DIRECTOR"] | None = None
    corrected_from: str | None = None
    note: str


class ChatAnalyzeResponse(BaseModel):
    members: list[Preference]
    analyses: list[MessageAnalysis]


class ScheduleHandoffRequest(BaseModel):
    room_id: str = Field(min_length=1, max_length=64)
    round_id: str = Field(min_length=1, max_length=64)
    selected_movie_id: str = Field(min_length=1, max_length=64)
    participant_ids: list[str] = Field(min_length=1, max_length=20)


class ScheduleHandoffResponse(BaseModel):
    room_id: str
    round_id: str
    source_type: Literal["MOVIE_RECOMMENDATION"] = "MOVIE_RECOMMENDATION"
    selected_movie_id: str
    selected_movie_title: str
    participant_ids: list[str]
    suggested_duration_minutes: None = None
    duration_policy: Literal["HOST_INPUT_REQUIRED"] = "HOST_INPUT_REQUIRED"
    availability_policy: Literal["BUSY_ONLY_NO_EVENT_DETAILS"] = "BUSY_ONLY_NO_EVENT_DETAILS"
    schedule_api: str = "/api/v1/schedules/rounds"


PreferenceOperation = Literal["UPSERT", "REMOVE"]
PreferenceType = Literal["SOFT", "HARD"]


class PreferenceDelta(BaseModel):
    user_id: str
    target_type: Literal[
        "GENRE", "TOPIC", "MOVIE", "PERSON", "BRAND", "COUNTRY",
        "LANGUAGE", "CERTIFICATION", "PROVIDER", "CONSTRAINT"
    ]
    target_value: str
    operation: PreferenceOperation
    preference_type: PreferenceType = "SOFT"
    score: float | None = Field(default=None, ge=-1, le=1)
    confidence: float = Field(1, ge=0, le=1)
    source_message_id: str | None = None


class ChatStateResponse(BaseModel):
    room_id: str
    round_id: str | None = None
    processing_status: Literal["APPLIED", "DUPLICATE", "UNCHANGED"]
    state_version: int = Field(ge=0)
    idempotency_key: str | None = None
    preference_deltas: list[PreferenceDelta] = []
    members: list[Preference] = []
    analyses: list[MessageAnalysis] = []
    messages: list[ChatMessage] = []
    recommended_movie_ids: list[str] = []
    model_version: str


class RoomRecommendRequest(BaseModel):
    round_id: str = Field(min_length=1, max_length=64)
    expected_state_version: int | None = Field(default=None, ge=0)
    allowed_providers: list[int] = []
    allowed_provider_types: list[ProviderType] = []
    limit: int = Field(3, ge=1, le=20)
    include_unknown_watch_path: bool = True
    require_now_playing: bool = False
    excluded_movie_ids: list[str] = []


RecommendationEventType = Literal["IMPRESSION", "CLICK", "LIKE", "DISLIKE", "HOLD", "SELECT", "REROLL", "SKIP", "PROVIDER_CLICK"]


class RecommendationEventCreate(BaseModel):
    event_id: str = Field(min_length=1, max_length=64)
    room_id: str = Field(min_length=1, max_length=64)
    round_id: str = Field(min_length=1, max_length=64)
    event_type: RecommendationEventType
    user_id: str | None = Field(default=None, max_length=64)
    movie_id: str | None = Field(default=None, max_length=64)
    rank_no: int | None = Field(default=None, ge=1, le=100)
    model_version: str | None = Field(default=None, max_length=64)
    payload: dict = {}
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RecommendationEvent(RecommendationEventCreate):
    id: int
    created_at: datetime
