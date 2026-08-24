import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { MOVIES } from "./server/moviesData";
import "./App.css";
import "./compact.css";
import "./events.css";
import "./evidence.css";
import "./showcase.css";

type Provider = {
  provider_id: number;
  name: string;
  type: string;
};

type PersonPreference = {
  person_id?: number | null;
  name: string;
  original_name?: string | null;
  role: "ACTOR" | "DIRECTOR";
  strength?: number;
  identity_source?: "TMDB_ID" | "CATALOG_ALIAS" | "TEXT_ONLY";
};

type Preference = {
  user_id: string;
  liked_genres: Record<string, number>;
  disliked_genres: Record<string, number>;
  liked_topics: Record<string, number>;
  disliked_topics: Record<string, number>;
  liked_brands: Record<string, number>;
  disliked_brands: Record<string, number>;
  prefers_theater?: boolean;
  liked_movies: string[];
  direct_movies: string[];
  seen_movies: string[];
  rewatch_allowed_movies: string[];
  disliked_movies?: string[];
  liked_people?: string[];
  disliked_people?: string[];
  liked_actors?: PersonPreference[];
  disliked_actors?: PersonPreference[];
  liked_directors?: PersonPreference[];
  disliked_directors?: PersonPreference[];
  countries: string[];
  excluded_countries?: string[];
  max_runtime?: number;
  min_runtime?: number;
  min_year?: number;
  max_year?: number;
  ott_platforms?: string[];
  preferred_original_platforms?: string[];
  ott_strict?: boolean;
  hard_exclusions: string[];
  confidence?: number;
  evidence_message_ids?: string[];
};

type Analysis = {
  user_id: string;
  text: string;
  target?: string;
  attitude: string;
  preference_score: number;
  confidence: number;
  corrected_from?: string;
  note: string;
};

type Message = {
  message_id?: number;
  user_id: "A" | "B" | "AI";
  text: string;
  reply_to_message_id?: number;
  is_recommendation?: boolean;
  recommendations?: Result[];
  recommendationMeta?: RecommendationMeta | null;
  roundId?: string;
};

type Result = {
  movie: {
    internal_id: string;
    title: string;
    overview: string;
    release_date?: string;
    runtime?: number;
    vote_average: number;
    poster_path?: string;
    providers: Provider[];
    provider_link?: string;
    genres: string[];
    certification?: string;
    cast?: string[];
    directors?: string[];
    countries?: string[];

    is_now_playing?: boolean;
    watch_path?: string;
    cinema_sources?: {
      cinema: string;
      rank?: number;
      reservation_rate?: number | null;
      booking_available?: boolean;
      source_url?: string;
      collected_at?: string;
    }[];
  };
  group_score: number;
  reasons: string[];
  evidence_level: "LOW" | "MEDIUM" | "HIGH";
  member_scores: {
    user_id: string;
    score: number;
    matched: string[];
    penalties: string[];
  }[];
};

type RecommendationMeta = {
  mode: string;
  modelVersion: string;
  dataVersion: string;
  reflectedMembers: Preference[];
};

type RoomData = {
  messages?: Message[];
  members?: Preference[];
  analyses?: Analysis[];
  recommended_movie_ids?: string[];
  movie_titles?: Record<string, string>;
  selected_movie_id?: string | null;
  processing_status?: "APPLIED" | "DUPLICATE" | "UNCHANGED";
  state_version?: number;
  preference_deltas?: PreferenceDelta[];
  model_version?: string;
};

type PreferenceDelta = {
  user_id: string;
  target_type: string;
  target_value: string;
  operation: "UPSERT" | "REMOVE";
  preference_type: "SOFT" | "HARD";
  score?: number | null;
  confidence: number;
};

type EvaluationMetrics = {
  model_name?: string;
  data_source?: string;
  status?: string;
  evaluation_type?: string;
  catalog_movie_count?: number;
  passed?: boolean;
  production_ready?: boolean;
  person_id_data_ready?: boolean;
  dataset_stats?: {
    eligible_movies?: number;
  };
  actor?: RoleEvaluationMetrics;
  director?: RoleEvaluationMetrics;
  context_inheritance?: {
    case_count?: number;
    passed?: number;
    accuracy?: number;
  };
  limitations?: string[];
};

type RoleEvaluationMetrics = {
  scenario_count?: number;
  mean_preference_score_lift?: number;
  mean_dislike_score_drop?: number;
  preference_hit_rate_at_3?: number;
  dislike_avoidance_rate_at_3?: number;
  exact_three_rate?: number;
};

function formatRate(value?: number) {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "측정 전";
}

function formatSignedScore(value: number) {
  const formatted = Math.abs(value)
    .toFixed(2)
    .replace(/0+$/, "")
    .replace(/\.$/, "");
  return `${value >= 0 ? "+" : "-"}${formatted}`;
}

function personPreferenceText(values?: PersonPreference[], negative = false) {
  return (values ?? [])
    .map((person) =>
      person.strength !== undefined && person.strength !== 1
        ? `${person.name} ${negative ? "-" : "+"}${person.strength}`
        : person.name,
    )
    .join(", ");
}

function MoviePoster({
  posterPath,
  title,
  releaseDate,
}: {
  posterPath?: string;
  title: string;
  releaseDate?: string;
}) {
  const [failed, setFailed] = useState(false);

  const posterUrl = posterPath
    ? posterPath.startsWith("http")
      ? posterPath
      : `https://image.tmdb.org/t/p/w500${posterPath}`
    : null;

  if (!failed && posterUrl) {
    return (
      <img
        src={posterUrl}
        alt={`${title} 포스터`}
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
      />
    );
  }

  const year = releaseDate ? releaseDate.slice(0, 4) : "";

  return (
    <div className="poster-fallback-card">
      <div className="poster-fallback-icon">🎬</div>
      <div className="poster-fallback-title">{title}</div>
      {year && <div className="poster-fallback-year">{year}</div>}
    </div>
  );
}

function getApiBase() {
  const envUrl = import.meta.env.VITE_API_BASE_URL;

  if (!envUrl) {
    return "";
  }

  if (typeof window !== "undefined") {
    try {
      const url = new URL(envUrl, window.location.origin);

      const isApiLocalhost =
        url.hostname === "localhost" || url.hostname === "127.0.0.1";

      const isBrowserLocalhost =
        window.location.hostname === "localhost" ||
        window.location.hostname === "127.0.0.1";

      if (isApiLocalhost && !isBrowserLocalhost) {
        return "";
      }
    } catch {
      return "";
    }
  }

  return envUrl;
}

const apiBase = getApiBase();
const recommendationApi = `${apiBase}/api/v1/recommendations`;

async function apiFetch(
  path: string,
  options?: RequestInit,
): Promise<Response> {
  const primaryUrl = `${recommendationApi}${path}`;

  try {
    const response = await fetch(primaryUrl, options);

    if (response.ok) {
      return response;
    }

    if (primaryUrl.startsWith("http")) {
      const fallbackUrl = `/api/v1/recommendations${path}`;
      const fallbackResponse = await fetch(fallbackUrl, options);

      if (fallbackResponse.ok) {
        return fallbackResponse;
      }
    }

    return response;
  } catch (error) {
    if (primaryUrl.startsWith("http")) {
      const fallbackUrl = `/api/v1/recommendations${path}`;
      return fetch(fallbackUrl, options);
    }

    throw error;
  }
}

const roomId = "chat-test";

const emptyMember = (user_id: string): Preference => ({
  user_id,
  liked_genres: {},
  disliked_genres: {},
  liked_topics: {},
  disliked_topics: {},
  liked_brands: {},
  disliked_brands: {},
  liked_movies: [],
  direct_movies: [],
  seen_movies: [],
  rewatch_allowed_movies: [],
  disliked_movies: [],
  liked_people: [],
  disliked_people: [],
  countries: [],
  hard_exclusions: [],
});

const labels: Record<string, string> = {
  flatrate: "구독",
  free: "무료",
  ads: "광고",
  rent: "대여",
  buy: "구매",
};

const attitudeLabels: Record<string, string> = {
  STRONG_LIKE: "강한 선호",
  LIKE: "선호",
  WEAK_LIKE: "약한 선호",
  NEUTRAL: "중립",
  UNCERTAIN: "불확실",
  DISLIKE: "비선호",
  STRONG_DISLIKE: "강한 비선호",
  QUESTION: "질문",
};

function mergeRecommendationMessage(
  serverMessages: Message[],
  recommendationMessage: Message,
): Message[] {
  const mergedMessages = [...serverMessages];

  for (let index = mergedMessages.length - 1; index >= 0; index -= 1) {
    const message = mergedMessages[index];

    const isMatchingAiMessage =
      message.user_id === "AI" && message.text === recommendationMessage.text;

    if (isMatchingAiMessage && !message.recommendations?.length) {
      mergedMessages[index] = {
        ...message,
        ...recommendationMessage,
        message_id: message.message_id ?? recommendationMessage.message_id,
      };

      return mergedMessages;
    }
  }

  const alreadyExists = mergedMessages.some(
    (message) =>
      message.user_id === "AI" &&
      message.roundId === recommendationMessage.roundId &&
      message.recommendations?.length,
  );

  if (!alreadyExists) {
    mergedMessages.push(recommendationMessage);
  }

  return mergedMessages;
}

function App() {
  const chatMessagesRef = useRef<HTMLDivElement>(null);

  const [speaker, setSpeaker] = useState<"A" | "B">("A");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [members, setMembers] = useState<Preference[]>([
    emptyMember("A"),
    emptyMember("B"),
  ]);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [movieTitles, setMovieTitles] = useState<Record<string, string>>({});
  const [detailMovie, setDetailMovie] = useState<Result | null>(null);
  const [confirmMovie, setConfirmMovie] = useState<{
    result: Result;
    rank: number;
    roundId: string;
    modelVersion?: string;
  } | null>(null);
  const [selectedMovieId, setSelectedMovieId] = useState<string | null>(null);
  const [selectingMovie, setSelectingMovie] = useState(false);
  const [selectionSuccess, setSelectionSuccess] = useState<Result | null>(null);
  const [results, setResults] = useState<Result[]>([]);
  const [excludedMovieIds, setExcludedMovieIds] = useState<string[]>([]);
  const [roundId, setRoundId] = useState("");
  const [analysisPage, setAnalysisPage] = useState(0);
  const [preferenceStateVersion, setPreferenceStateVersion] = useState(0);
  const [recentPreferenceDeltas, setRecentPreferenceDeltas] = useState<
    PreferenceDelta[]
  >([]);
  const [replyTo, setReplyTo] = useState<Message | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [, setRecommendationMeta] = useState<RecommendationMeta | null>(null);

  const [showEvalModal, setShowEvalModal] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [evalMetrics, setEvalMetrics] = useState<EvaluationMetrics | null>(
    null,
  );

  function applyRoomData(
    data: RoomData,
    options: {
      replaceMessages?: boolean;
    } = {},
  ) {
    const { replaceMessages = true } = options;

    if (replaceMessages && Array.isArray(data.messages)) {
      setMessages(data.messages);
    }

    if (Array.isArray(data.members)) {
      setMembers(
        ["A", "B"].map(
          (id) =>
            data.members?.find((member) => member.user_id === id) ??
            emptyMember(id),
        ),
      );
    }

    // Snapshot 조회는 analyses: []를 반환한다. 추천 직전에 snapshot을 읽어도
    // 방금 화면에 표시된 문장 분석 근거가 사라지지 않도록 새 분석이 있을 때만 갱신한다.
    if (Array.isArray(data.analyses) && data.analyses.length > 0) {
      setAnalyses(data.analyses);
      setAnalysisPage(0);
    }

    if (typeof data.state_version === "number") {
      setPreferenceStateVersion(data.state_version);
    }

    if (
      Array.isArray(data.preference_deltas) &&
      data.preference_deltas.length > 0
    ) {
      setRecentPreferenceDeltas(data.preference_deltas);
    }

    if (Array.isArray(data.recommended_movie_ids)) {
      setExcludedMovieIds(data.recommended_movie_ids);
    }

    if (data.movie_titles) {
      setMovieTitles((current) => ({ ...current, ...data.movie_titles }));
    }

    if (data.selected_movie_id) {
      setSelectedMovieId(data.selected_movie_id);
    }
  }

  useEffect(() => {
    apiFetch(`/chat/rooms/${roomId}`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        return response.json();
      })
      .then((data: RoomData) => {
        applyRoomData(data);
        setError("");
      })
      .catch((errorValue) => {
        console.error("Chat load error:", errorValue);

        setError(
          "저장된 채팅을 불러오지 못했습니다. 서버 상태를 확인해 주세요.",
        );
      });

    apiFetch("/evaluation")
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (data) {
          setEvalMetrics(data);
        }
      })
      .catch(() => null);
  }, []);

  useEffect(() => {
    if (chatMessagesRef.current) {
      chatMessagesRef.current.scrollTop = chatMessagesRef.current.scrollHeight;
    }
  }, [messages]);

  async function sendMessage(event: FormEvent) {
    event.preventDefault();

    if (!input.trim()) {
      return;
    }

    const text = input.trim();

    const optimisticMessage: Message = {
      message_id: Date.now(),
      user_id: speaker,
      text,
      reply_to_message_id: replyTo?.message_id,
    };

    setMessages((previous) => [...previous, optimisticMessage]);

    setInput("");
    setError("");

    try {
      const response = await apiFetch("/chat/messages", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          room_id: roomId,
          user_id: speaker,
          text,
          reply_to_message_id: replyTo?.message_id,
          idempotency_key: crypto.randomUUID(),
          round_id: roundId || "chat-session",
        }),
      });

      if (!response.ok) {
        throw new Error("채팅 분석에 실패했습니다.");
      }

      const data: RoomData = await response.json();

      applyRoomData(data);
      setReplyTo(null);
    } catch (exception) {
      setError(
        exception instanceof Error ? exception.message : "채팅 분석 실패",
      );
    }
  }
  async function recommend() {
    if (selectedMovieId) {
      setError("이미 영화가 확정되어 다른 추천으로 변경할 수 없습니다.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      let currentMembers = members;
      let currentStateVersion = preferenceStateVersion;

      // 초기 화면 로딩과 추천 클릭이 겹쳐도 오래된 상태 버전을 보내지 않도록
      // 추천 직전에 항상 ML 서버의 최신 누적 성향과 상태 버전을 확인한다.
      {
        const analysisResponse = await apiFetch(`/chat/rooms/${roomId}`);

        if (!analysisResponse.ok) {
          throw new Error("대화 재분석에 실패했습니다.");
        }

        const analysisData: RoomData = await analysisResponse.json();

        currentMembers = ["A", "B"].map(
          (id) =>
            analysisData.members?.find((member) => member.user_id === id) ??
            emptyMember(id),
        );

        if (typeof analysisData.state_version === "number") {
          currentStateVersion = analysisData.state_version;
        }

        applyRoomData(analysisData);
      }

      if (roundId && results.length > 0) {
        await sendEvent("REROLL", undefined, undefined, undefined, roundId);
      }

      const nextRoundId = `round-${crypto.randomUUID()}`;

      const recommendationRequest = {
        round_id: nextRoundId,
        expected_state_version: currentStateVersion,
        excluded_movie_ids: excludedMovieIds,
        allowed_provider_types: ["flatrate", "free", "ads", "rent", "buy"],
        limit: 3,
        include_unknown_watch_path: false,
      };

      let response = await apiFetch(`/chat/rooms/${roomId}/recommendations`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(recommendationRequest),
      });

      if (!response.ok) {
        const errorBody = await response.text().catch(() => "");

        console.error("추천 API 오류:", response.status, errorBody);

        throw new Error(`추천 서비스를 확인해 주세요. HTTP ${response.status}`);
      }

      let data = await response.json();

      if (
        !Array.isArray(data.recommendations) ||
        data.recommendations.length !== 3
      ) {
        setExcludedMovieIds([]);

        response = await apiFetch(`/chat/rooms/${roomId}/recommendations`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            ...recommendationRequest,
            excluded_movie_ids: [],
          }),
        });

        if (response.ok) {
          data = await response.json();
        }
      }

      if (
        !Array.isArray(data.recommendations) ||
        data.recommendations.length !== 3
      ) {
        throw new Error("서로 다른 추천 영화 3편을 구성하지 못했습니다.");
      }

      const recommendations: Result[] = data.recommendations;

      const meta: RecommendationMeta = {
        mode: data.mode,
        modelVersion: data.model_version,
        dataVersion: data.data_version,
        reflectedMembers: currentMembers,
      };

      setResults(recommendations);
      setRecommendationMeta(meta);
      setRoundId(nextRoundId);

      setExcludedMovieIds((previous) => [
        ...new Set([
          ...previous,
          ...recommendations.map(
            (recommendation) => recommendation.movie.internal_id,
          ),
        ]),
      ]);

      const aiMessageText =
        "🤖 A와 B의 대화를 기반으로 맞춤 영화 TOP 3를 추천해 드릴게요!";

      const aiMessageRequest = {
        room_id: roomId,
        user_id: "AI",
        text: aiMessageText,
        is_recommendation: true,
        recommendations,
        recommendationMeta: meta,
        roundId: nextRoundId,
      };

      const uiRecommendationMessage: Message = {
        message_id: Date.now(),
        user_id: "AI",
        text: aiMessageText,
        is_recommendation: true,
        recommendations,
        recommendationMeta: meta,
        roundId: nextRoundId,
      };

      try {
        const savedResponse = await apiFetch("/chat/messages", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(aiMessageRequest),
        });

        if (!savedResponse.ok) {
          const errorBody = await savedResponse.text().catch(() => "");

          console.error(
            "AI 추천 메시지 저장 실패:",
            savedResponse.status,
            errorBody,
          );

          throw new Error(
            `AI 추천 메시지 저장 실패: HTTP ${savedResponse.status}`,
          );
        }

        const roomData: RoomData = await savedResponse.json();

        applyRoomData(roomData, {
          replaceMessages: false,
        });

        setMessages((previousMessages) => {
          const serverMessages = Array.isArray(roomData.messages)
            ? roomData.messages
            : previousMessages;

          return mergeRecommendationMessage(
            serverMessages,
            uiRecommendationMessage,
          );
        });
      } catch (saveError) {
        console.error("AI 추천 메시지 저장 처리 오류:", saveError);

        setMessages((previousMessages) =>
          mergeRecommendationMessage(previousMessages, uiRecommendationMessage),
        );
      }

      const impressionResults = await Promise.allSettled(
        recommendations.map((item, index) =>
          sendEvent(
            "IMPRESSION",
            item.movie.internal_id,
            index + 1,
            data.model_version,
            nextRoundId,
          ),
        ),
      );

      const failedImpressions = impressionResults.filter(
        (result) => result.status === "rejected",
      );

      if (failedImpressions.length > 0) {
        console.warn(
          `${failedImpressions.length}개의 IMPRESSION 이벤트 저장에 실패했습니다.`,
        );
      }
    } catch (exception) {
      console.error("영화 추천 처리 오류:", exception);

      setError(
        exception instanceof Error ? exception.message : "추천 요청 실패",
      );
    } finally {
      setLoading(false);
    }
  }

  async function sendEvent(
    eventType: string,
    movieId?: string,
    rankNo?: number,
    modelVersion?: string,
    eventRoundId = roundId,
    payload: Record<string, unknown> = {},
  ) {
    if (!eventRoundId) {
      return;
    }

    const response = await apiFetch("/events", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        event_id: crypto.randomUUID(),
        room_id: roomId,
        round_id: eventRoundId,
        user_id: speaker,
        movie_id: movieId,
        rank_no: rankNo,
        event_type: eventType,
        model_version: modelVersion ?? "weighted-hybrid-0.3.0",
        payload,
        occurred_at: new Date().toISOString(),
      }),
    });

    if (!response.ok) {
      throw new Error("추천 반응 저장에 실패했습니다.");
    }
  }

  async function finalizeMovieSelection() {
    if (!confirmMovie || selectedMovieId || selectingMovie) {
      return;
    }

    setSelectingMovie(true);
    setError("");
    const {
      result,
      rank,
      roundId: selectedRoundId,
      modelVersion,
    } = confirmMovie;

    try {
      await sendEvent(
        "SELECT",
        result.movie.internal_id,
        rank,
        modelVersion,
        selectedRoundId,
        { locked: true, title: result.movie.title },
      );
      setSelectedMovieId(result.movie.internal_id);
      setConfirmMovie(null);
      setDetailMovie(null);
      setSelectionSuccess(result);

      const confirmationText = `✅ 최종 영화가 「${result.movie.title}」로 확정되었습니다. 확정 후에는 다른 영화로 변경할 수 없습니다.`;
      setMessages((current) => [
        ...current,
        { message_id: Date.now(), user_id: "AI", text: confirmationText },
      ]);

      try {
        await apiFetch("/chat/messages", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            room_id: roomId,
            user_id: "AI",
            text: confirmationText,
          }),
        });
      } catch (saveError) {
        console.warn("확정 안내 메시지 저장 실패:", saveError);
      }
    } catch (exception) {
      setError(
        exception instanceof Error
          ? exception.message
          : "영화 확정에 실패했습니다.",
      );
    } finally {
      setSelectingMovie(false);
    }
  }

  async function resetChat() {
    setError("");

    try {
      const response = await apiFetch(`/chat/rooms/${roomId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("대화 초기화에 실패했습니다.");
      }

      setMessages([]);
      setMembers([emptyMember("A"), emptyMember("B")]);
      setAnalyses([]);
      setResults([]);
      setExcludedMovieIds([]);
      setRoundId("");
      setAnalysisPage(0);
      setPreferenceStateVersion(0);
      setRecentPreferenceDeltas([]);
      setReplyTo(null);
      setSelectedMovieId(null);
      setDetailMovie(null);
      setConfirmMovie(null);
      setSelectionSuccess(null);
      setRecommendationMeta(null);
      setShowResetConfirm(false);
    } catch (exception) {
      setError(
        exception instanceof Error ? exception.message : "대화 초기화 실패",
      );
    }
  }

  return (
    <main>
      <header>
        <div>
          <span className="eyebrow">MEETUPLOG AI RECOMMENDATION</span>

          <h1>
            A와 B의 대화로
            <br />
            맞춤 영화를 추천해요
          </h1>

          <p>
            자음/모음 오타 교정, 장르/소재/브랜드 선호도, 개봉 연도(2020년
            이후/최신/고전)까지 대화에서 자동으로 분석합니다.
          </p>
        </div>

        <div
          style={{
            display: "flex",
            gap: "8px",
            flexDirection: "column",
            alignItems: "flex-end",
          }}
        >
          <button
            onClick={recommend}
            disabled={loading || Boolean(selectedMovieId)}
          >
            {loading
              ? "계산 중…"
              : results.length
                ? "다른 영화 다시 추천"
                : "AI 영화 추천"}
          </button>

          <button
            type="button"
            style={{
              background: "#f0f4f9",
              color: "#1a73e8",
              border: "1px solid #dadce0",
              borderRadius: "8px",
              padding: "6px 12px",
              cursor: "pointer",
              fontSize: "13px",
              fontWeight: 600,
            }}
            onClick={() => setShowEvalModal(true)}
          >
            📊 TMDB 모델 성능 평가
          </button>
        </div>
      </header>

      {error && <p className="error">{error}</p>}

      <section className="workspace">
        <div className="chat-panel">
          <div className="panel-title">
            <h2>테스트 채팅</h2>

            <div className="chat-tools">
              <span className="msg-badge">{messages.length}개 대화</span>

              <button
                type="button"
                className="reset-chat-btn"
                onClick={() => setShowResetConfirm(true)}
                title="대화 및 성향 초기화"
              >
                🧹 대화 초기화
              </button>
            </div>
          </div>

          <div className="messages" ref={chatMessagesRef}>
            {messages.length === 0 ? (
              <div className="empty-chat-guide">
                <p className="empty">
                  A 또는 B를 선택하고 영화 취향을 자유롭게 말해보세요!
                </p>

                <div className="quick-suggestions">
                  <span>💡 추천 예시 대화 (클릭하여 입력):</span>

                  <div className="chip-list">
                    <button
                      type="button"
                      onClick={() =>
                        setInput("나 넷플 가입함 넷플릭스 영화 추천해줘")
                      }
                    >
                      "나 넷플 가입함 넷플릭스 영화 추천해줘"
                    </button>

                    <button
                      type="button"
                      onClick={() => setInput("티빙에 뭐 볼만한 영화 없나?")}
                    >
                      "티빙에 뭐 볼만한 영화 없나?"
                    </button>

                    <button
                      type="button"
                      onClick={() =>
                        setInput("2020년 이후 최신 SF 영화 추천해줘")
                      }
                    >
                      "2020년 이후 최신 SF 영화 추천해줘"
                    </button>

                    <button
                      type="button"
                      onClick={() =>
                        setInput("인터스텔라 같은 SF 스릴러가 좋아")
                      }
                    >
                      "인터스텔라 같은 SF 스릴러가 좋아"
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              messages.map((message, index) => {
                if (message.user_id === "AI" || message.is_recommendation) {
                  return (
                    <div
                      className="bubble AI"
                      key={message.message_id ?? `${message.roundId}-${index}`}
                    >
                      <b className="chat-avatar AI">🤖</b>

                      <div className="ai-chat-content">
                        <p className="ai-intro-text">{message.text}</p>

                        {message.recommendations &&
                          message.recommendations.length > 0 && (
                            <div className="inline-recommendations">
                              <div className="recommendations-header-card">
                                <div className="recommendations-banner">
                                  <div className="banner-title">
                                    <span className="sparkle">✨</span> AI 맞춤
                                    영화 TOP {message.recommendations.length}
                                  </div>

                                  <span className="banner-badge">
                                    TMDB AI 매칭 엔진
                                  </span>
                                </div>

                                {message.recommendationMeta && (
                                  <RecommendationEvidence
                                    meta={message.recommendationMeta}
                                  />
                                )}
                              </div>

                              {message.recommendations.map(
                                (item, recommendationIndex) => (
                                  <div
                                    className="inline-card"
                                    key={item.movie.internal_id}
                                  >
                                    <div className="card-top-row">
                                      <div className="inline-poster-container">
                                        <MoviePoster
                                          posterPath={item.movie.poster_path}
                                          title={item.movie.title}
                                          releaseDate={item.movie.release_date}
                                        />

                                        <div className="rank-ribbon">
                                          #{recommendationIndex + 1}
                                        </div>
                                      </div>

                                      <div className="inline-movie-info">
                                        <div className="badge-row">
                                          <span className="match-score-badge">
                                            🎯{" "}
                                            {Math.round(item.group_score * 100)}
                                            % 매칭
                                          </span>

                                          <EvidenceBadge
                                            level={item.evidence_level}
                                          />

                                          {item.movie.certification && (
                                            <span className="cert-badge">
                                              {item.movie.certification}
                                            </span>
                                          )}
                                        </div>

                                        <h4 className="movie-title-heading">
                                          {item.movie.title}
                                        </h4>

                                        <div className="genres-list">
                                          {item.movie.genres.map((genre) => (
                                            <span
                                              key={genre}
                                              className="genre-chip"
                                            >
                                              {genre}
                                            </span>
                                          ))}
                                        </div>

                                        <div className="meta-info-row">
                                          <span>
                                            📅{" "}
                                            {item.movie.release_date?.slice(
                                              0,
                                              4,
                                            ) ?? "연도 미상"}
                                            년
                                          </span>

                                          <span>
                                            ⏱️ {item.movie.runtime ?? "—"}분
                                          </span>

                                          <span className="rating">
                                            ⭐{" "}
                                            {item.movie.vote_average.toFixed(1)}
                                          </span>
                                        </div>
                                      </div>
                                    </div>

                                    <div className="card-overview-box">
                                      <p className="inline-overview">
                                        {item.movie.overview}
                                      </p>
                                    </div>

                                    <div className="card-section reasons-section">
                                      <div className="section-header-title">
                                        💡 추천 근거
                                      </div>

                                      <div className="reasons-chips-grid">
                                        {item.reasons.map((reason) => (
                                          <span
                                            className="reason-pill"
                                            key={reason}
                                          >
                                            <span className="bullet">✓</span>{" "}
                                            {reason}
                                          </span>
                                        ))}
                                      </div>
                                    </div>

                                    <div className="card-section member-fit-section">
                                      <div className="section-header-title">
                                        👥 구성원 적합도 분석
                                      </div>

                                      <div className="member-fit-grid">
                                        {item.member_scores.map(
                                          (memberScore) => (
                                            <div
                                              className="member-fit-card"
                                              key={memberScore.user_id}
                                            >
                                              <div className="member-fit-head">
                                                <span
                                                  className={`user-badge user-${memberScore.user_id}`}
                                                >
                                                  {memberScore.user_id}
                                                </span>

                                                <span className="score-percent">
                                                  {Math.round(
                                                    memberScore.score * 100,
                                                  )}
                                                  %
                                                </span>
                                              </div>

                                              <div className="bar-track">
                                                <div
                                                  className={`bar-fill fill-${memberScore.user_id}`}
                                                  style={{
                                                    width: `${Math.max(
                                                      6,
                                                      memberScore.score * 100,
                                                    )}%`,
                                                  }}
                                                />
                                              </div>

                                              {(memberScore.matched.length >
                                                0 ||
                                                memberScore.penalties.length >
                                                  0) && (
                                                <div className="member-evidence-chips">
                                                  {memberScore.matched.map(
                                                    (matched) => (
                                                      <span
                                                        key={matched}
                                                        className="evidence-chip match"
                                                      >
                                                        +{matched}
                                                      </span>
                                                    ),
                                                  )}

                                                  {memberScore.penalties.map(
                                                    (penalty) => (
                                                      <span
                                                        key={penalty}
                                                        className="evidence-chip penalty"
                                                      >
                                                        -{penalty}
                                                      </span>
                                                    ),
                                                  )}
                                                </div>
                                              )}
                                            </div>
                                          ),
                                        )}
                                      </div>
                                    </div>

                                    <div className="card-section provider-section">
                                      <div className="section-header-title">
                                        📺 어디서 볼 수 있나요?
                                      </div>

                                      {item.movie.is_now_playing ? (
                                        <div className="provider-links-row">
                                          <span className="ott-badge">
                                            현재 상영 중
                                          </span>

                                          {item.movie.cinema_sources?.map(
                                            (source) => (
                                              <a
                                                key={`${item.movie.internal_id}-${source.cinema}`}
                                                className="ott-badge"
                                                href={
                                                  source.source_url || undefined
                                                }
                                                target="_blank"
                                                rel="noreferrer"
                                              >
                                                {source.cinema === "MEGABOX"
                                                  ? "메가박스"
                                                  : source.cinema ===
                                                      "LOTTE_CINEMA"
                                                    ? "롯데시네마"
                                                    : source.cinema}
                                              </a>
                                            ),
                                          )}
                                        </div>
                                      ) : item.movie.providers.length > 0 ? (
                                        <div className="provider-links-row">
                                          {item.movie.providers.map(
                                            (provider) => (
                                              <span
                                                key={`${provider.provider_id}-${provider.type}`}
                                                className={`ott-badge ott-${provider.name
                                                  .toLowerCase()
                                                  .replace(/[\s+]/g, "")}`}
                                              >
                                                {provider.name}{" "}
                                                <small>
                                                  (
                                                  {labels[provider.type] ??
                                                    provider.type}
                                                  )
                                                </small>
                                              </span>
                                            ),
                                          )}
                                        </div>
                                      ) : (
                                        <div className="unknown-provider">
                                          시청 정보 미확인
                                        </div>
                                      )}
                                    </div>

                                    <div className="recommendation-card-actions">
                                      <button
                                        type="button"
                                        className="movie-detail-btn"
                                        onClick={() => setDetailMovie(item)}
                                      >
                                        상세보기
                                      </button>
                                      <button
                                        type="button"
                                        className="movie-confirm-btn"
                                        disabled={Boolean(selectedMovieId)}
                                        onClick={() =>
                                          setConfirmMovie({
                                            result: item,
                                            rank: recommendationIndex + 1,
                                            roundId: message.roundId ?? roundId,
                                            modelVersion:
                                              message.recommendationMeta
                                                ?.modelVersion,
                                          })
                                        }
                                      >
                                        {selectedMovieId ===
                                        item.movie.internal_id
                                          ? "확정 완료"
                                          : selectedMovieId
                                            ? "선택 불가"
                                            : "이 영화 확정"}
                                      </button>
                                    </div>
                                  </div>
                                ),
                              )}

                              <div className="inline-reroll-action">
                                <button
                                  type="button"
                                  onClick={recommend}
                                  disabled={loading || Boolean(selectedMovieId)}
                                  className="reroll-btn"
                                >
                                  {selectedMovieId
                                    ? "🔒 영화 확정 완료 - 변경 불가"
                                    : "🔄 조건 맞춰서 다른 영화 추천받기"}
                                </button>
                              </div>
                            </div>
                          )}
                      </div>
                    </div>
                  );
                }

                return (
                  <div
                    className={`bubble ${message.user_id}`}
                    key={message.message_id ?? index}
                  >
                    <b className={`chat-avatar ${message.user_id}`}>
                      {message.user_id}
                    </b>

                    <span className="user-msg-text">
                      {message.text}

                      <button
                        className="reply-button"
                        type="button"
                        onClick={() => setReplyTo(message)}
                      >
                        답장
                      </button>
                    </span>
                  </div>
                );
              })
            )}
          </div>

          {replyTo && (
            <div className="reply-preview">
              <span>
                {replyTo.user_id}에게 답장: {replyTo.text}
              </span>

              <button type="button" onClick={() => setReplyTo(null)}>
                취소
              </button>
            </div>
          )}

          <form onSubmit={sendMessage}>
            <div className="speaker">
              <button
                type="button"
                className={speaker === "A" ? "active" : ""}
                onClick={() => setSpeaker("A")}
              >
                A
              </button>

              <button
                type="button"
                className={speaker === "B" ? "active" : ""}
                onClick={() => setSpeaker("B")}
              >
                B
              </button>
            </div>

            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={`${speaker}의 메시지를 입력하세요`}
            />

            <button type="submit">전송</button>
          </form>
        </div>

        <div className="profiles">
          <div className="analysis-sync-card">
            <div className="analysis-sync-icon" aria-hidden="true">
              ✦
            </div>

            <div>
              <strong>
                {preferenceStateVersion > 0
                  ? "ML 성향 분석 · 추천 반영 완료"
                  : "ML 성향 분석 대기"}
              </strong>
              <span>
                {preferenceStateVersion > 0
                  ? `상태 버전 v${preferenceStateVersion} · 강화 모델 0.6.0`
                  : "채팅을 입력하면 사용자별 성향을 분석합니다."}
              </span>
            </div>
          </div>

          {recentPreferenceDeltas.length > 0 && (
            <div className="recent-delta-card">
              <b>방금 추천 점수에 반영된 성향</b>
              <div>
                {recentPreferenceDeltas.slice(0, 6).map((delta, index) => (
                  <span
                    className={
                      typeof delta.score === "number" && delta.score < 0
                        ? "delta-negative"
                        : "delta-positive"
                    }
                    key={`${delta.user_id}-${delta.target_type}-${delta.target_value}-${index}`}
                  >
                    {delta.user_id} · {delta.target_value}
                    {typeof delta.score === "number"
                      ? ` ${formatSignedScore(delta.score)}`
                      : ""}
                  </span>
                ))}
              </div>
            </div>
          )}

          {members.map((member) => {
            const topMemberScore = results[0]?.member_scores.find(
              (score) => score.user_id === member.user_id,
            );

            return (
              <div
                className={`profile profile-${member.user_id}`}
                key={member.user_id}
              >
                <div className="profile-heading-row">
                  <h2>
                    <span>{member.user_id}</span> 분석된 성향
                  </h2>

                  {topMemberScore && (
                    <div className="profile-score-badge">
                      <small>TOP 1 개인 적합도</small>
                      <strong>{Math.round(topMemberScore.score * 100)}%</strong>
                    </div>
                  )}
                </div>

                <PreferenceRows member={member} movieTitles={movieTitles} />

                {topMemberScore && (
                  <div className="profile-score-track" aria-hidden="true">
                    <i
                      style={{
                        width: `${Math.max(5, topMemberScore.score * 100)}%`,
                      }}
                    />
                  </div>
                )}
              </div>
            );
          })}

          {analyses.length > 0 && (
            <div className="latest">
              <h3>전체 문장 분석 · {analyses.length}개</h3>

              {[...analyses]
                .reverse()
                .slice(analysisPage * 6, analysisPage * 6 + 6)
                .map((analysis, index) => (
                  <div
                    className="analysis-row"
                    key={`${analysis.text}-${index}`}
                  >
                    <b>
                      {analysis.user_id} · {analysis.target ?? "대상 미확인"}
                    </b>

                    <span>
                      {attitudeLabels[analysis.attitude] ?? analysis.attitude} ·{" "}
                      {analysis.preference_score > 0 ? "+" : ""}
                      {analysis.preference_score} · 신뢰도{" "}
                      {Math.round(analysis.confidence * 100)}%
                    </span>

                    {analysis.corrected_from && (
                      <small>
                        유사도 매칭: “{analysis.corrected_from}” → “
                        {analysis.target}”
                      </small>
                    )}

                    <small>{analysis.note}</small>
                  </div>
                ))}

              <div className="analysis-pages">
                <button
                  type="button"
                  disabled={analysisPage === 0}
                  onClick={() => setAnalysisPage((previous) => previous - 1)}
                >
                  최신
                </button>

                <span>
                  {analysisPage + 1} / {Math.ceil(analyses.length / 6)}
                </span>

                <button
                  type="button"
                  disabled={(analysisPage + 1) * 6 >= analyses.length}
                  onClick={() => setAnalysisPage((previous) => previous + 1)}
                >
                  이전
                </button>
              </div>
            </div>
          )}
        </div>
      </section>

      {detailMovie && (
        <div
          className="movie-modal-overlay"
          onClick={() => setDetailMovie(null)}
        >
          <article
            className="movie-detail-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="movie-detail-title"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              className="movie-modal-close"
              aria-label="상세보기 닫기"
              onClick={() => setDetailMovie(null)}
            >
              ✕
            </button>
            <div className="movie-detail-layout">
              <div className="movie-detail-poster">
                <MoviePoster
                  posterPath={detailMovie.movie.poster_path}
                  title={detailMovie.movie.title}
                  releaseDate={detailMovie.movie.release_date}
                />
              </div>
              <div className="movie-detail-copy">
                <span className="movie-detail-kicker">AI 추천 영화</span>
                <h2 id="movie-detail-title">{detailMovie.movie.title}</h2>
                <div className="movie-detail-meta">
                  <span>
                    {detailMovie.movie.release_date?.slice(0, 4) ?? "연도 미상"}
                  </span>
                  <span>{detailMovie.movie.runtime ?? "—"}분</span>
                  <span>⭐ {detailMovie.movie.vote_average.toFixed(1)}</span>
                </div>
                <div className="genres-list">
                  {detailMovie.movie.genres.map((genre) => (
                    <span className="genre-chip" key={genre}>
                      {genre}
                    </span>
                  ))}
                </div>
                <dl className="movie-detail-facts">
                  <div>
                    <dt>감독</dt>
                    <dd>
                      {detailMovie.movie.directors?.join(", ") || "정보 없음"}
                    </dd>
                  </div>
                  <div>
                    <dt>출연</dt>
                    <dd>
                      {detailMovie.movie.cast?.slice(0, 5).join(", ") ||
                        "정보 없음"}
                    </dd>
                  </div>
                </dl>
                <section className="movie-detail-overview">
                  <h3>줄거리</h3>
                  <p>
                    {detailMovie.movie.overview || "줄거리 정보가 없습니다."}
                  </p>
                </section>
                <section className="movie-detail-reasons">
                  <h3>AI 추천 이유</h3>
                  <div className="reasons-chips-grid">
                    {detailMovie.reasons.map((reason) => (
                      <span className="reason-pill" key={reason}>
                        ✓ {reason}
                      </span>
                    ))}
                  </div>
                </section>
                <section className="movie-detail-providers">
                  <h3>볼 수 있는 OTT</h3>
                  <div className="provider-links-row">
                    {detailMovie.movie.providers.length > 0 ? (
                      detailMovie.movie.providers.map((provider) => (
                        <span
                          className="ott-badge"
                          key={`${provider.provider_id}-${provider.type}`}
                        >
                          {provider.name} (
                          {labels[provider.type] ?? provider.type})
                        </span>
                      ))
                    ) : (
                      <span className="unknown-provider">시청 정보 미확인</span>
                    )}
                  </div>
                </section>
                <div className="movie-detail-actions">
                  <button
                    type="button"
                    className="movie-detail-cancel"
                    onClick={() => setDetailMovie(null)}
                  >
                    닫기
                  </button>
                  <button
                    type="button"
                    className="movie-confirm-btn"
                    disabled={Boolean(selectedMovieId)}
                    onClick={() => {
                      const rank = results.findIndex(
                        (item) =>
                          item.movie.internal_id ===
                          detailMovie.movie.internal_id,
                      );
                      setConfirmMovie({
                        result: detailMovie,
                        rank: rank >= 0 ? rank + 1 : 1,
                        roundId,
                      });
                    }}
                  >
                    {selectedMovieId
                      ? "이미 영화가 확정됨"
                      : "이 영화 확정하기"}
                  </button>
                </div>
              </div>
            </div>
          </article>
        </div>
      )}

      {confirmMovie && (
        <div
          className="movie-modal-overlay"
          onClick={() => !selectingMovie && setConfirmMovie(null)}
        >
          <article
            className="movie-confirm-modal"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="movie-confirm-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="confirm-icon">⚠️</div>
            <span className="movie-detail-kicker">최종 선택</span>
            <h2 id="movie-confirm-title">정말 이 영화로 확정할까요?</h2>
            <p className="confirm-movie-title">
              {confirmMovie.result.movie.title}
            </p>
            <p className="confirm-warning">
              한 번 확정하면 다른 영화로 변경할 수 없습니다.
              <br />
              선택한 영화가 맞는지 다시 확인해 주세요.
            </p>
            <div className="movie-confirm-actions">
              <button
                type="button"
                className="movie-detail-cancel"
                disabled={selectingMovie}
                onClick={() => setConfirmMovie(null)}
              >
                취소
              </button>
              <button
                type="button"
                className="movie-confirm-btn"
                disabled={selectingMovie}
                onClick={finalizeMovieSelection}
              >
                {selectingMovie ? "확정 중..." : "확정하기"}
              </button>
            </div>
          </article>
        </div>
      )}

      {selectionSuccess && (
        <div className="movie-modal-overlay">
          <article
            className="movie-success-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="movie-success-title"
          >
            <div className="success-check">✓</div>
            <h2 id="movie-success-title">영화가 확정되었습니다!</h2>
            <p className="success-subtitle">즐거운 영화 시간 되세요 🎉</p>
            <div className="success-movie-summary">
              <div className="success-poster">
                <MoviePoster
                  posterPath={selectionSuccess.movie.poster_path}
                  title={selectionSuccess.movie.title}
                  releaseDate={selectionSuccess.movie.release_date}
                />
              </div>
              <div>
                <h3>{selectionSuccess.movie.title}</h3>
                <div className="genres-list">
                  {selectionSuccess.movie.genres.map((genre) => (
                    <span className="genre-chip" key={genre}>
                      {genre}
                    </span>
                  ))}
                </div>
                <ul className="success-facts">
                  <li>
                    개봉{" "}
                    {selectionSuccess.movie.release_date?.slice(0, 4) ??
                      "정보 없음"}
                  </li>
                  <li>러닝타임 {selectionSuccess.movie.runtime ?? "—"}분</li>
                  <li>
                    평점 ⭐ {selectionSuccess.movie.vote_average.toFixed(1)}
                  </li>
                  <li>
                    OTT{" "}
                    {selectionSuccess.movie.providers
                      .map((provider) => provider.name)
                      .join(", ") || "정보 미확인"}
                  </li>
                </ul>
              </div>
            </div>
            <div className="success-actions">
              {selectionSuccess.movie.provider_link && (
                <a
                  href={selectionSuccess.movie.provider_link}
                  target="_blank"
                  rel="noreferrer"
                  className="watch-now-btn"
                >
                  ▶ 지금 시청하기
                </a>
              )}
              <button
                type="button"
                className="movie-detail-btn"
                onClick={() => {
                  setDetailMovie(selectionSuccess);
                  setSelectionSuccess(null);
                }}
              >
                영화 정보 상세 보기
              </button>
              <button
                type="button"
                className="movie-detail-cancel"
                onClick={() => setSelectionSuccess(null)}
              >
                닫기
              </button>
            </div>
          </article>
        </div>
      )}

      {showEvalModal && (
        <div
          className="eval-modal-overlay"
          onClick={() => setShowEvalModal(false)}
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.6)",
            zIndex: 1000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "16px",
          }}
        >
          <div
            className="eval-modal"
            onClick={(event) => event.stopPropagation()}
            style={{
              background: "#fff",
              borderRadius: "16px",
              maxWidth: "600px",
              width: "100%",
              maxHeight: "90vh",
              overflowY: "auto",
              padding: "24px",
              boxShadow: "0 20px 25px -5px rgba(0,0,0,0.2)",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "16px",
              }}
            >
              <h2
                style={{
                  fontSize: "18px",
                  fontWeight: 700,
                  margin: 0,
                  color: "#0f172a",
                }}
              >
                📊 TMDB 추천 모델 성능 평가 상세
              </h2>

              <button
                onClick={() => setShowEvalModal(false)}
                style={{
                  background: "none",
                  border: "none",
                  fontSize: "20px",
                  cursor: "pointer",
                  color: "#64748b",
                }}
              >
                ✕
              </button>
            </div>

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "16px",
                fontSize: "14px",
                color: "#334155",
              }}
            >
              <div
                style={{
                  background: "#f8fafc",
                  padding: "12px 16px",
                  borderRadius: "8px",
                  borderLeft: "4px solid #2563eb",
                }}
              >
                <strong>모델 버전:</strong>{" "}
                {evalMetrics?.model_name || "역할별 인물 추천·문맥 계승 검증"}
                <br />
                <strong>데이터 원천:</strong>{" "}
                {evalMetrics?.data_source || "동결 TMDB 실제 크레딧 카탈로그"} (
                {evalMetrics?.catalog_movie_count ??
                  evalMetrics?.dataset_stats?.eligible_movies ??
                  "측정 전"}
                개 추천 대상)
                <br />
                <strong>검증 상태:</strong>{" "}
                {evalMetrics?.production_ready === true
                  ? "운영 검증 기준 통과"
                  : evalMetrics?.passed === true &&
                      evalMetrics?.person_id_data_ready === false
                    ? "동작 검증 통과 · TMDB 인물 ID 데이터 보강 필요"
                    : evalMetrics?.status === "NOT_EVALUATED"
                      ? "아직 평가하지 않음"
                      : "검증 결과 확인 필요"}
              </div>

              <div>
                <h3
                  style={{
                    fontSize: "15px",
                    fontWeight: 600,
                    color: "#0f172a",
                    marginBottom: "8px",
                  }}
                >
                  1. 오프라인 평가 지표
                </h3>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(2, 1fr)",
                    gap: "10px",
                  }}
                >
                  <MetricCard
                    label="배우 선호 Hit@3"
                    value={formatRate(
                      evalMetrics?.actor?.preference_hit_rate_at_3,
                    )}
                    description={`${evalMetrics?.actor?.scenario_count ?? 0}개 ID 기반 시나리오`}
                    valueColor="#2563eb"
                  />

                  <MetricCard
                    label="배우 비선호 회피@3"
                    value={formatRate(
                      evalMetrics?.actor?.dislike_avoidance_rate_at_3,
                    )}
                    description="비선호 배우 영화의 TOP 3 제외율"
                    valueColor="#2563eb"
                  />

                  <MetricCard
                    label="감독 선호 Hit@3"
                    value={formatRate(
                      evalMetrics?.director?.preference_hit_rate_at_3,
                    )}
                    description={`${evalMetrics?.director?.scenario_count ?? 0}개 ID 기반 시나리오`}
                    valueColor="#16a34a"
                  />

                  <MetricCard
                    label="정확히 3편 출력"
                    value={formatRate(
                      evalMetrics?.actor?.exact_three_rate !== undefined &&
                        evalMetrics?.director?.exact_three_rate !== undefined
                        ? Math.min(
                            evalMetrics.actor.exact_three_rate,
                            evalMetrics.director.exact_three_rate,
                          )
                        : undefined,
                    )}
                    description="중복 없는 3개 추천 카드 구성률"
                    valueColor="#16a34a"
                  />
                </div>
              </div>

              <div>
                <h3
                  style={{
                    fontSize: "15px",
                    fontWeight: 600,
                    color: "#0f172a",
                    marginBottom: "8px",
                  }}
                >
                  2. 자연어 대화 분석 및 오타 교정
                </h3>

                <ul
                  style={{
                    paddingLeft: "20px",
                    margin: 0,
                    lineHeight: 1.6,
                  }}
                >
                  <li>
                    <strong>동의·인정·찬성 및 부정 변형 문맥 계승:</strong>{" "}
                    {formatRate(evalMetrics?.context_inheritance?.accuracy)} (
                    {evalMetrics?.context_inheritance?.passed ?? 0}/
                    {evalMetrics?.context_inheritance?.case_count ?? 0}건)
                  </li>

                  <li>
                    <strong>배우 선호 평균 점수 상승:</strong>{" "}
                    {evalMetrics?.actor?.mean_preference_score_lift?.toFixed(
                      3,
                    ) ?? "측정 전"}
                  </li>

                  <li>
                    <strong>감독 비선호 평균 점수 하락:</strong>{" "}
                    {evalMetrics?.director?.mean_dislike_score_drop?.toFixed(
                      3,
                    ) ?? "측정 전"}
                  </li>

                  <li>
                    <strong>평가 범위:</strong> 카탈로그 기반 구성요소 검증이며,
                    실제 사용자 수용률로 해석하지 않음
                  </li>
                </ul>
              </div>

              <div>
                <h3
                  style={{
                    fontSize: "15px",
                    fontWeight: 600,
                    color: "#0f172a",
                    marginBottom: "8px",
                  }}
                >
                  3. 그룹 공정성 및 피드백 반영
                </h3>

                <ul
                  style={{
                    paddingLeft: "20px",
                    margin: 0,
                    lineHeight: 1.6,
                  }}
                >
                  <li>
                    <strong>최소 개인 만족도 고려:</strong> Least Misery 방식
                    적용
                  </li>

                  <li>
                    <strong>온라인 반응 반영:</strong> 찬성·반대·보류·확정
                    이벤트 지원
                  </li>
                </ul>
              </div>
            </div>

            <div
              style={{
                marginTop: "20px",
                textAlign: "right",
              }}
            >
              <button
                onClick={() => setShowEvalModal(false)}
                style={{
                  background: "#0f172a",
                  color: "#fff",
                  border: "none",
                  borderRadius: "8px",
                  padding: "8px 16px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}

      {showResetConfirm && (
        <div
          className="eval-modal-overlay"
          onClick={() => setShowResetConfirm(false)}
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.6)",
            zIndex: 1000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "16px",
          }}
        >
          <div
            className="eval-modal"
            onClick={(event) => event.stopPropagation()}
            style={{
              background: "#fff",
              borderRadius: "16px",
              maxWidth: "440px",
              width: "100%",
              padding: "24px",
              boxShadow: "0 20px 25px -5px rgba(0,0,0,0.2)",
            }}
          >
            <h3
              style={{
                fontSize: "18px",
                fontWeight: 700,
                margin: "0 0 12px",
                color: "#0f172a",
              }}
            >
              🧹 대화 및 성향 초기화
            </h3>

            <p
              style={{
                fontSize: "14px",
                color: "#475569",
                lineHeight: 1.5,
                margin: "0 0 20px",
              }}
            >
              현재 주고받은 모든 대화, 분석된 성향, 추천 영화 및 이력이 서버
              DB와 앱에서 삭제됩니다. 초기화하시겠습니까?
            </p>

            <div
              style={{
                display: "flex",
                gap: "10px",
                justifyContent: "flex-end",
              }}
            >
              <button
                type="button"
                style={{
                  background: "#f1f5f9",
                  color: "#475569",
                  border: "1px solid #cbd5e1",
                  padding: "10px 18px",
                  borderRadius: "10px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
                onClick={() => setShowResetConfirm(false)}
              >
                취소
              </button>

              <button
                type="button"
                style={{
                  background: "#dc2626",
                  color: "#ffffff",
                  border: "1px solid #b91c1c",
                  padding: "10px 18px",
                  borderRadius: "10px",
                  fontWeight: 700,
                  cursor: "pointer",
                }}
                onClick={resetChat}
              >
                초기화 실행
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function MetricCard({
  label,
  value,
  description,
  valueColor,
}: {
  label: string;
  value: string;
  description: string;
  valueColor: string;
}) {
  return (
    <div
      style={{
        background: "#f1f5f9",
        padding: "12px",
        borderRadius: "8px",
      }}
    >
      <div
        style={{
          fontSize: "12px",
          color: "#64748b",
        }}
      >
        {label}
      </div>

      <div
        style={{
          fontSize: "20px",
          fontWeight: 700,
          color: valueColor,
        }}
      >
        {value}
      </div>

      <small
        style={{
          fontSize: "11px",
          color: "#64748b",
        }}
      >
        {description}
      </small>
    </div>
  );
}

const evidenceLabels = {
  HIGH: "근거 높음",
  MEDIUM: "근거 보통",
  LOW: "근거 부족",
};

function EvidenceBadge({ level }: { level: "LOW" | "MEDIUM" | "HIGH" }) {
  return (
    <span className={`evidence-badge ${level.toLowerCase()}`}>
      {evidenceLabels[level]}
    </span>
  );
}

function RecommendationEvidence({ meta }: { meta: RecommendationMeta }) {
  const summaries = meta.reflectedMembers.flatMap((member) =>
    preferenceSummary(member).map((value) => `${member.user_id} · ${value}`),
  );

  const lowEvidence = meta.mode === "LOW_EVIDENCE";

  return (
    <div className="recommendation-evidence-box">
      <div className="evidence-status-line">
        <span className={`mode-dot ${lowEvidence ? "low" : "preference"}`} />

        <span>
          {lowEvidence
            ? "취향 정보가 적어 평점과 인기도를 통합 계산했습니다."
            : "대화에서 수집된 그룹 취향 데이터를 기반으로 계산했습니다."}
        </span>
      </div>

      {summaries.length > 0 ? (
        <div className="evidence-chips-wrap">
          {summaries.map((value) => (
            <span className="evidence-tag" key={value}>
              {value}
            </span>
          ))}
        </div>
      ) : (
        <p
          className="empty"
          style={{
            margin: 0,
            fontSize: "12px",
            color: "#94a3b8",
          }}
        >
          확실하게 확인된 취향 조건이 없습니다.
        </p>
      )}
    </div>
  );
}

function getMovieTitle(
  idOrTitle: string,
  movieTitles: Record<string, string> = {},
): string {
  if (movieTitles[idOrTitle]) {
    return movieTitles[idOrTitle];
  }
  const found = MOVIES.find(
    (movie) =>
      movie.internal_id === idOrTitle ||
      movie.title === idOrTitle ||
      movie.title_ko === idOrTitle,
  );

  return found ? found.title : idOrTitle;
}

function preferenceSummary(member: Preference): string[] {
  return [
    ...Object.entries(member.liked_genres).map(
      ([genre, value]) => `${genre} 선호 +${value}`,
    ),

    ...Object.entries(member.disliked_genres).map(
      ([genre, value]) => `${genre} 비선호 -${value}`,
    ),

    ...Object.entries(member.liked_topics).map(
      ([topic, value]) => `${topic} 소재 +${value}`,
    ),

    ...Object.entries(member.disliked_topics).map(
      ([topic, value]) => `${topic} 소재 -${value}`,
    ),

    ...Object.entries(member.liked_brands).map(
      ([brand, value]) => `${brand} 선호 +${value}`,
    ),

    ...Object.entries(member.disliked_brands).map(
      ([brand, value]) => `${brand} 비선호 -${value}`,
    ),

    ...(member.disliked_movies?.map(
      (movie) => `🎬 ${getMovieTitle(movie)} 비선호`,
    ) ?? []),

    ...member.seen_movies.map(
      (movieId) => `👁️ ${getMovieTitle(movieId)} 관람함`,
    ),

    ...member.liked_movies.map(
      (movieId) => `❤️ ${getMovieTitle(movieId)} 선호`,
    ),

    ...member.direct_movies.map(
      (movieId) => `🎯 ${getMovieTitle(movieId)} 직접 지정`,
    ),

    ...(member.ott_platforms?.length
      ? [
          `📺 ${member.ott_platforms.join(", ")} 구독${
            member.ott_strict ? " (전용)" : ""
          }`,
        ]
      : []),

    ...(member.prefers_theater ? ["🎬 영화관 관람 선호"] : []),

    ...(member.liked_actors ?? []).map((person) => `배우 ${person.name} 선호`),

    ...(member.liked_directors ?? []).map(
      (person) => `감독 ${person.name} 선호`,
    ),

    ...(member.disliked_actors ?? []).map(
      (person) => `배우 ${person.name} 비선호`,
    ),

    ...(member.disliked_directors ?? []).map(
      (person) => `감독 ${person.name} 비선호`,
    ),

    ...(member.min_year ? [`${member.min_year}년 이후 개봉`] : []),

    ...(member.max_year ? [`${member.max_year}년 이전 개봉`] : []),

    ...(member.max_runtime ? [`${member.max_runtime}분 이하`] : []),

    ...(member.min_runtime ? [`${member.min_runtime}분 이상`] : []),

    ...member.countries.map((country) =>
      country === "KR" ? "한국 영화만" : `${country} 제작 영화`,
    ),

    ...member.hard_exclusions.map((exclusion) => `${exclusion} 제외`),
  ];
}

function PreferenceRows({
  member,
  movieTitles,
}: {
  member: Preference;
  movieTitles: Record<string, string>;
}) {
  const yearCondition = [
    member.min_year ? `${member.min_year}년 이후` : "",
    member.max_year ? `${member.max_year}년 이전` : "",
  ]
    .filter(Boolean)
    .join(", ");

  const runtimeCondition = [
    member.min_runtime ? `${member.min_runtime}분 이상` : "",
    member.max_runtime ? `${member.max_runtime}분 이하` : "",
  ]
    .filter(Boolean)
    .join(", ");

  const legacyLikedPeople =
    (member.liked_actors?.length ?? 0) +
      (member.liked_directors?.length ?? 0) ===
    0
      ? (member.liked_people ?? []).join(", ")
      : "";
  const legacyDislikedPeople =
    (member.disliked_actors?.length ?? 0) +
      (member.disliked_directors?.length ?? 0) ===
    0
      ? (member.disliked_people ?? []).join(", ")
      : "";

  const rows: [string, string][] = [
    [
      "구독 OTT",
      member.ott_platforms?.length
        ? `${member.ott_platforms.join(", ")}${
            member.ott_strict ? " (해당 OTT만)" : ""
          }`
        : "",
    ],

    ["관람 방식", member.prefers_theater ? "영화관 관람 선호" : ""],

    [
      "선호 장르",
      Object.entries(member.liked_genres)
        .map(([genre, value]) => `${genre} +${value}`)
        .join(", "),
    ],

    [
      "비선호 장르",
      Object.entries(member.disliked_genres)
        .map(([genre, value]) => `${genre} -${value}`)
        .join(", "),
    ],

    [
      "선호 소재",
      Object.entries(member.liked_topics)
        .map(([topic, value]) => `${topic} +${value}`)
        .join(", "),
    ],

    [
      "비선호 소재",
      Object.entries(member.disliked_topics)
        .map(([topic, value]) => `${topic} -${value}`)
        .join(", "),
    ],

    [
      "선호 브랜드",
      Object.entries(member.liked_brands)
        .map(([brand, value]) => `${brand} +${value}`)
        .join(", "),
    ],

    [
      "비선호 브랜드",
      Object.entries(member.disliked_brands)
        .map(([brand, value]) => `${brand} -${value}`)
        .join(", "),
    ],

    [
      "비선호 영화",
      (member.disliked_movies ?? [])
        .map((movie) => getMovieTitle(movie, movieTitles))
        .join(", "),
    ],

    [
      "관람한 영화",
      member.seen_movies
        .map((movie) => getMovieTitle(movie, movieTitles))
        .join(", "),
    ],

    [
      "선호 영화",
      member.liked_movies
        .map((movie) => getMovieTitle(movie, movieTitles))
        .join(", "),
    ],

    [
      "직접 후보",
      member.direct_movies
        .map((movie) => getMovieTitle(movie, movieTitles))
        .join(", "),
    ],

    [
      "재관람 허용",
      member.rewatch_allowed_movies
        .map((movie) => getMovieTitle(movie, movieTitles))
        .join(", "),
    ],

    [
      "선호 배우",
      personPreferenceText(member.liked_actors) || legacyLikedPeople,
    ],

    ["선호 감독", personPreferenceText(member.liked_directors)],

    [
      "비선호 배우",
      personPreferenceText(member.disliked_actors, true) ||
        legacyDislikedPeople,
    ],

    ["비선호 감독", personPreferenceText(member.disliked_directors, true)],

    ["개봉 연도", yearCondition],

    [
      "제작 국가",
      member.countries
        .map((country) => (country === "KR" ? "한국만" : country))
        .join(", "),
    ],

    ["상영시간", runtimeCondition],

    ["강제 제외", member.hard_exclusions.join(", ")],
  ].filter(([, value]) => Boolean(value)) as [string, string][];

  if (rows.length === 0) {
    return <p className="empty">아직 분석된 성향이 없습니다.</p>;
  }

  return (
    <>
      {rows.map(([label, value]) => (
        <div className="pref-row" key={label}>
          <b>{label}</b>
          <span>{value}</span>
        </div>
      ))}
    </>
  );
}

export default App;
