"""Semantic preference-to-movie scoring with an offline-safe fallback."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.pipeline import FeatureUnion

from .schemas import Movie, Preference


def movie_document(movie: Movie) -> str:
    actor_names = list(movie.cast[:5])
    director_names = list(movie.directors)
    for credit in movie.cast_people[:5]:
        actor_names.extend(value for value in (credit.name, credit.original_name) if value)
    for credit in movie.director_people:
        director_names.extend(value for value in (credit.name, credit.original_name) if value)
    fields = [
        f"제목 {movie.title}",
        f"한국어 제목 {movie.title_ko}" if movie.title_ko else "",
        f"원제 {movie.original_title}" if movie.original_title else "",
        "장르 " + " ".join(movie.genres),
        "키워드 " + " ".join(movie.keywords),
        "배우 " + " ".join(dict.fromkeys(actor_names)),
        "감독 " + " ".join(dict.fromkeys(director_names)),
        "줄거리 " + " ".join(dict.fromkeys(filter(None, [movie.overview_ko, movie.overview, movie.overview_en]))),
    ]
    return ". ".join(field for field in fields if field.strip())


def preference_document(preference: Preference) -> str:
    fields: list[str] = []
    fields.extend(f"{name} 장르 선호" for name, value in preference.liked_genres.items() if value > 0)
    fields.extend(f"{name} 소재 분위기 선호" for name, value in preference.liked_topics.items() if value > 0)
    fields.extend(f"{name} 시리즈 브랜드 선호" for name, value in preference.liked_brands.items() if value > 0)
    structured_names = {
        person.original_name or person.name
        for person in [*preference.liked_actors, *preference.liked_directors]
    }
    fields.extend(
        f"{person.original_name or person.name} 배우 선호"
        for person in preference.liked_actors
    )
    fields.extend(
        f"{person.original_name or person.name} 감독 선호"
        for person in preference.liked_directors
    )
    fields.extend(
        f"{name} 배우 감독 선호"
        for name in preference.liked_people
        if name not in structured_names
    )
    if preference.countries:
        fields.append(" ".join(preference.countries) + " 제작 영화 선호")
    if preference.min_year:
        fields.append(f"{preference.min_year}년 이후 최신 영화 선호")
    if preference.max_year:
        fields.append(f"{preference.max_year}년 이전 고전 영화 선호")
    if preference.max_runtime:
        fields.append(f"상영시간 {preference.max_runtime}분 이하 선호")
    return ". ".join(fields)


@dataclass
class SemanticScoreResult:
    scores: dict[str, list[float]]
    backend: str
    model_name: str


class SemanticPreferenceEngine:
    """Scores structured user preferences against movie documents.

    SentenceTransformer is lazy and optional. The lexical fallback deliberately
    mixes Korean word n-grams with character n-grams so spacing and light typos
    do not turn the whole recommendation service into a hard failure.
    """

    def __init__(
        self,
        model_name: str,
        use_embedding: bool = True,
        cache_dir: Path | None = None,
        precomputed_dir: Path | None = None,
    ):
        self.model_name = model_name
        self.use_embedding = use_embedding
        self.cache_dir = cache_dir
        self.precomputed_dir = precomputed_dir
        self._encoder = None
        self._catalog_key = ""
        self._movie_documents: list[str] = []
        self._movie_vectors = None
        self._fallback = None
        self.backend = "tfidf-word-char"

    @staticmethod
    def _key(movies: list[Movie]) -> str:
        ids = [m.internal_id for m in movies]
        payload = json.dumps(ids, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _load_encoder(self):
        if not self.use_embedding:
            return None
        if self._encoder is not None:
            return self._encoder
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            return None
        self._encoder = SentenceTransformer(
            self.model_name,
            device="cpu",
            local_files_only=True,
        )
        return self._encoder

    def fit_catalog(self, movies: list[Movie]) -> None:
        key = self._key(movies)
        if key == self._catalog_key:
            return
        self._catalog_key = key
        self._movie_documents = [movie_document(movie) for movie in movies]
        # 배포 ZIP에 동봉된 SBERT 행렬을 우선 사용한다. 인코더 패키지가
        # 없어도 영화 벡터는 사용할 수 있으며, 질의 인코딩에만 로컬 모델이
        # 필요하다. ID 순서와 파일 해시가 하나라도 다르면 안전하게 거부한다.
        encoder = None
        try:
            encoder = self._load_encoder()
        except (OSError, RuntimeError):
            # API 요청 중 Hub 접속을 재시도하지 않는다. 모델이 로컬에
            # 없으면 즉시 재현 가능한 lexical fallback으로 전환한다.
            encoder = None
        if encoder is not None and self.precomputed_dir:
            vector_path = self.precomputed_dir / "movie_embeddings.npy"
            metadata_path = self.precomputed_dir / "movie_embeddings_meta.json"
            manifest_path = self.precomputed_dir / "catalog_manifest.json"
            if vector_path.exists() and metadata_path.exists() and manifest_path.exists():
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    ordered_ids = [movie.internal_id for movie in movies]
                    manifest_ids = manifest.get("ordered_movie_ids", [])
                    file_hash = hashlib.sha256(vector_path.read_bytes()).hexdigest()
                    valid = (
                        len(manifest_ids) == len(set(manifest_ids))
                        and set(manifest_ids).issubset(set(ordered_ids))
                        and metadata.get("catalog_sha256") == manifest.get("catalog_sha256")
                        and metadata.get("model_name") == self.model_name
                        and metadata.get("movie_count") == len(manifest_ids)
                        and metadata.get("embeddings_sha256") == file_hash
                    )
                    if valid:
                        vectors = np.load(vector_path, mmap_mode="r")
                        if vectors.shape == (
                            len(manifest_ids),
                            int(metadata.get("embedding_dimension", -1)),
                        ):
                            by_id = {movie_id: index for index, movie_id in enumerate(manifest_ids)}
                            missing = [i for i, movie_id in enumerate(ordered_ids) if movie_id not in by_id]
                            if not missing and manifest_ids == ordered_ids:
                                self._movie_vectors = vectors
                            else:
                                # Catalog additions do not invalidate the frozen 5k rows.
                                # Encode only new rows and restore current catalog order.
                                extra = encoder.encode(
                                    [self._movie_documents[i] for i in missing],
                                    normalize_embeddings=True,
                                    show_progress_bar=False,
                                ) if missing else np.empty((0, vectors.shape[1]), dtype=np.float32)
                                extra_by_index = {movie_index: row for row, movie_index in enumerate(missing)}
                                self._movie_vectors = np.asarray([
                                    vectors[by_id[movie_id]] if movie_id in by_id else extra[extra_by_index[i]]
                                    for i, movie_id in enumerate(ordered_ids)
                                ], dtype=np.float32)
                            self._fallback = None
                            self.backend = "sentence-transformers-precomputed"
                            return
                except (OSError, ValueError, json.JSONDecodeError, TypeError):
                    pass
        if encoder is not None:
            vector_path = self.cache_dir / "movie_vectors.npy" if self.cache_dir else None
            metadata_path = self.cache_dir / "movie_vectors.json" if self.cache_dir else None
            cached = False
            if vector_path and metadata_path and vector_path.exists() and metadata_path.exists():
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    if (
                        metadata.get("catalog_sha256") == key
                        and metadata.get("model_name") == self.model_name
                        and metadata.get("movie_count") == len(movies)
                    ):
                        self._movie_vectors = np.load(vector_path, mmap_mode="r")
                        cached = len(self._movie_vectors) == len(movies)
                except (OSError, ValueError, json.JSONDecodeError):
                    cached = False
            if not cached:
                self._movie_vectors = encoder.encode(
                    self._movie_documents,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    batch_size=32,
                ).astype(np.float32, copy=False)
                if vector_path and metadata_path:
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    np.save(vector_path, self._movie_vectors)
                    metadata_path.write_text(
                        json.dumps({
                            "catalog_sha256": key,
                            "model_name": self.model_name,
                            "movie_count": len(movies),
                            "embedding_dimension": int(self._movie_vectors.shape[1]),
                        }, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
            self._fallback = None
            self.backend = "sentence-transformers-cache" if cached else "sentence-transformers"
            return
        self._fallback = FeatureUnion([
            (
                "word",
                TfidfVectorizer(
                    ngram_range=(1, 2),
                    min_df=2,
                    max_features=12_000,
                    sublinear_tf=True,
                ),
            ),
            (
                "char",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(2, 5),
                    min_df=2,
                    max_features=12_000,
                    sublinear_tf=True,
                ),
            ),
        ])
        self._movie_vectors = self._fallback.fit_transform(self._movie_documents)
        self.backend = "tfidf-word-char"

    def score(self, movies: list[Movie], members: list[Preference]) -> SemanticScoreResult:
        self.fit_catalog(movies)
        documents = [preference_document(member) for member in members]
        result: dict[str, list[float]] = {}
        active = [(i, text) for i, text in enumerate(documents) if text]
        if not active:
            return SemanticScoreResult(result, self.backend, self.model_name)
        indices, texts = zip(*active)
        if self.backend.startswith("sentence-transformers"):
            vectors = self._encoder.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
            similarities = np.asarray(vectors) @ np.asarray(self._movie_vectors).T
        else:
            vectors = self._fallback.transform(list(texts))
            similarities = cosine_similarity(vectors, self._movie_vectors)
        similarities = np.clip(similarities, 0.0, 1.0)
        for row, member_index in enumerate(indices):
            result[members[member_index].user_id] = similarities[row].astype(float).tolist()
        return SemanticScoreResult(result, self.backend, self.model_name)
