import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from .matching import match_movies
from .schemas import Movie
from .storage import JsonStore


def load_kobis_details(store: JsonStore) -> list[dict]:
    path = store.raw / "kobis" / "details.jsonl"
    if not path.exists():
        raise RuntimeError("KOBIS 원본 데이터가 없습니다. 먼저 `collect kobis`를 실행하세요.")
    by_code: dict[str, dict] = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            info = row.get("movieInfoResult", {}).get("movieInfo", row)
            if info.get("movieCd"):
                by_code[info["movieCd"]] = info
    return list(by_code.values())


def _names(rows: list[dict], field: str = "peopleNm") -> list[str]:
    return list(dict.fromkeys(x.get(field, "").strip() for x in rows if x.get(field, "").strip()))


def _kobis_movie(info: dict) -> Movie:
    code = info["movieCd"]
    release = info.get("openDt") or ""
    release_date = f"{release[:4]}-{release[4:6]}-{release[6:]}" if len(release) == 8 else None
    genres = [x.get("genreNm", "") for x in info.get("genres", []) if x.get("genreNm")]
    directors = _names(info.get("directors", []))
    cast = _names(info.get("actors", []))[:20]
    score = (30 if genres else 0) + (15 if directors else 0) + (15 if cast else 0)
    audits = info.get("audits", [])
    return Movie(
        internal_id="mov_" + hashlib.sha1(f"kobis|{code}".encode()).hexdigest()[:12],
        kobis_code=code,
        title=info.get("movieNm") or info.get("movieNmEn") or "제목 없음",
        title_ko=info.get("movieNm"), title_en=info.get("movieNmEn"), original_title=info.get("movieNmEn"),
        genres=genres, directors=directors, cast=cast,
        countries=[x.get("nationNm", "") for x in info.get("nations", []) if x.get("nationNm")],
        release_date=release_date,
        runtime=int(info["showTm"]) if str(info.get("showTm", "")).isdigit() else None,
        certification=audits[0].get("watchGradeNm") if audits else None,
        data_sources=["KOBIS"], completeness_score=score, recommendation_eligible=False,
    )


def integrate_kobis(store: JsonStore, threshold: float = .78) -> dict:
    movies = store.load_movies()
    tmdb_count = sum(movie.tmdb_id is not None for movie in movies)
    kobis = load_kobis_details(store)
    tmdb_movies = [movie for movie in movies if movie.tmdb_id is not None]
    mappings = match_movies([m.model_dump() for m in tmdb_movies], kobis, threshold)
    kobis_by_code = {row["movieCd"]: row for row in kobis}
    mapping_by_movie = {
        row["internal_id"]: row
        for row in mappings
        if (
            row.get("kobis_code")
            and row.get("match_status") == "AUTO_ACCEPT"
        )
    }
    integrated: list[Movie] = []
    for movie in movies:
        mapping = mapping_by_movie.get(movie.internal_id)
        if not mapping:
            integrated.append(movie)
            continue
        info = kobis_by_code[mapping["kobis_code"]]
        movie.kobis_code = info["movieCd"]
        movie.data_sources = list(dict.fromkeys(movie.data_sources + ["TMDB", "KOBIS"]))
        movie.directors = list(dict.fromkeys(movie.directors + _names(info.get("directors", []))))
        movie.cast = list(dict.fromkeys(movie.cast + _names(info.get("actors", []))))[:20]
        movie.genres = list(dict.fromkeys(movie.genres + [x.get("genreNm", "") for x in info.get("genres", []) if x.get("genreNm")]))
        movie.countries = list(dict.fromkeys(movie.countries + [x.get("nationNm", "") for x in info.get("nations", []) if x.get("nationNm")]))
        if not movie.runtime and str(info.get("showTm", "")).isdigit():
            movie.runtime = int(info["showTm"])
        audits = info.get("audits", [])
        if not movie.certification and audits:
            movie.certification = audits[0].get("watchGradeNm")
        if not movie.release_date and info.get("openDt") and len(info["openDt"]) == 8:
            value = info["openDt"]
            movie.release_date = f"{value[:4]}-{value[4:6]}-{value[6:]}"
        integrated.append(movie)
    matched_codes = {row["kobis_code"] for row in mappings if row.get("kobis_code")}
    existing_kobis_codes = {movie.kobis_code for movie in integrated if movie.kobis_code}
    kobis_only = [_kobis_movie(info) for info in kobis if info["movieCd"] not in matched_codes and info["movieCd"] not in existing_kobis_codes]
    integrated.extend(kobis_only)
    store.save_movies(integrated)
    report_dir = store.normalized / "matching"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "tmdb_kobis_mappings.json").write_text(json.dumps(mappings, ensure_ascii=False, indent=2), encoding="utf-8")
    review = [
        row
        for row in mappings
        if row.get("match_status") == "REVIEW"
    ]
    (report_dir / "review_required.json").write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    matched = len(mapping_by_movie)
    report = {"tmdb_movies": tmdb_count, "kobis_movies": len(kobis), "matched": matched,
              "kobis_only_movies": len(kobis_only), "unified_movies": len(integrated),
              "recommendation_eligible": sum(movie.recommendation_eligible for movie in integrated),
              "match_rate_tmdb": round(matched / tmdb_count, 4) if tmdb_count else 0,
              "review_required": len(review), "integrated_at": datetime.now(timezone.utc).isoformat()}
    (report_dir / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
