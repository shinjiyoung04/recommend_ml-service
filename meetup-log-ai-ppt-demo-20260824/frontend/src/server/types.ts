export interface Preference {
  user_id: string;
  liked_genres: Record<string, number>;
  disliked_genres: Record<string, number>;
  liked_topics: Record<string, number>;
  disliked_topics: Record<string, number>;
  liked_brands: Record<string, number>;
  disliked_brands: Record<string, number>;
  liked_movies: string[];
  direct_movies: string[];
  seen_movies: string[];
  rewatch_allowed_movies: string[];
  disliked_movies?: string[];
  liked_people?: string[];
  countries: string[];
  languages?: string[];
  certifications?: string[];
  ott_platforms?: string[];
  ott_strict?: boolean;
  allowed_providers?: number[];
  allowed_provider_types?: string[];
  max_runtime?: number;
  min_runtime?: number;
  min_year?: number;
  max_year?: number;
  hard_exclusions: string[];
  confidence?: number;
}

export interface ChatMessage {
  message_id?: number;
  user_id: string;
  text: string;
  reply_to_message_id?: number;
  is_recommendation?: boolean;
  recommendations?: any[];
  recommendationMeta?: any;
  roundId?: string;
}

export interface MessageAnalysis {
  user_id: string;
  text: string;
  target?: string;
  target_type?: string;
  attitude: string;
  preference_score: number;
  confidence: number;
  corrected_from?: string;
  note: string;
}

export interface RecommendationEvent {
  id: string;
  event_id: string;
  room_id: string;
  round_id: string;
  user_id: string;
  movie_id?: string;
  rank_no?: number;
  event_type: string;
  model_version: string;
  payload: Record<string, any>;
  occurred_at: string;
}

export interface MemberScore {
  user_id: string;
  score: number;
  matched: string[];
  penalties: string[];
}

export interface Recommendation {
  movie: any;
  group_score: number;
  member_scores: MemberScore[];
  reasons: string[];
  evidence_level: 'LOW' | 'MEDIUM' | 'HIGH';
  watch_path_status: string;
}

export interface GroupRecommendRequest {
  roomId: string;
  roundId: string;
  members: Preference[];
  allowedProviders?: number[];
  allowedProviderTypes?: string[];
  limit?: number;
  includeUnknownWatchPath?: boolean;
  excludedMovieIds?: string[];
}
