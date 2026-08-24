import re
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import MultiLabelBinarizer, StandardScaler
from .schemas import Movie


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().casefold())


class FeatureBuilder:
    def fit_transform(self, movies: list[Movie]) -> dict[str, sparse.csr_matrix]:
        self.genre = MultiLabelBinarizer().fit([m.genres for m in movies])
        genre = sparse.csr_matrix(
            self.genre.transform([m.genres for m in movies]),
            dtype=np.float32,
        )
        overview_text = [normalize_text(" ".join(dict.fromkeys(filter(None, [m.overview_ko, m.overview_en, m.overview])))) for m in movies]
        self.overview = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=12000).fit(overview_text)
        overview = self.overview.transform(overview_text).astype(np.float32)
        self.keyword = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b", max_features=4000).fit([" ".join(m.keywords) or "unknown" for m in movies])
        keyword = self.keyword.transform([" ".join(m.keywords) or "unknown" for m in movies]).astype(np.float32)
        self.people = TfidfVectorizer(token_pattern=r"(?u)[^|]+", max_features=4000).fit([" | ".join(m.directors + m.cast[:5]) or "unknown" for m in movies])
        people = self.people.transform([" | ".join(m.directors + m.cast[:5]) or "unknown" for m in movies]).astype(np.float32)
        numeric_raw = [[m.runtime or 0, int((m.release_date or "0")[:4] or 0), m.vote_average, np.log1p(m.vote_count), np.log1p(m.popularity)] for m in movies]
        self.numeric = StandardScaler()
        numeric = sparse.csr_matrix(
            self.numeric.fit_transform(numeric_raw),
            dtype=np.float32,
        )
        return {"genre": genre, "overview": overview, "keyword": keyword, "people": people, "numeric": numeric}

    @staticmethod
    def combine(
        parts: dict[str, sparse.csr_matrix],
        weights: dict[str, float] | None = None,
    ) -> sparse.csr_matrix:
        weights = weights or {"genre": .24, "overview": .34, "keyword": .2, "people": .12, "numeric": .1}
        # Keep high-dimensional text features sparse. The model bundle reduces
        # this matrix before fitting the ranker, avoiding multi-GB dense arrays.
        return sparse.hstack(
            [parts[key] * weights[key] for key in weights],
            format="csr",
            dtype=np.float32,
        )
