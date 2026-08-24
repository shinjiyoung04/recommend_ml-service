from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


# 현재 파일 위치:
# ml-service/meetup_ml/integration/integrate_now_playing.py
ML_SERVICE_ROOT = Path(__file__).resolve().parents[2]

MOVIES_FILE = (
    ML_SERVICE_ROOT
    / "data"
    / "normalized"
    / "movies.json"
)

NOW_PLAYING_FILE = (
    ML_SERVICE_ROOT
    / "data"
    / "normalized"
    / "now_playing_movies.json"
)

OUTPUT_FILE = (
    ML_SERVICE_ROOT
    / "data"
    / "normalized"
    / "movies.runtime.json"
)

UNMATCHED_FILE = (
    ML_SERVICE_ROOT
    / "data"
    / "reports"
    / "now_playing_unmatched.json"
)


def load_json(path: Path) -> Any:
    """JSON 파일을 UTF-8로 읽습니다."""
    if not path.exists():
        raise FileNotFoundError(f"파일이 없습니다: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data: Any) -> None:
    """JSON 파일을 한글이 깨지지 않게 저장합니다."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def normalize_title(title: str | None) -> str:
    """
    영화 제목 비교를 위해 공백과 특수문자를 제거합니다.

    예:
    스파이더맨: 브랜드 뉴 데이
    → 스파이더맨브랜드뉴데이
    """
    if not title:
        return ""

    return re.sub(
        r"[^0-9a-zA-Z가-힣]",
        "",
        title,
    ).lower()


def main() -> None:
    print("[1] 기존 영화 데이터 불러오기")

    existing_movies = load_json(MOVIES_FILE)

    if not isinstance(existing_movies, list):
        raise ValueError(
            "movies.json은 영화 객체 배열이어야 합니다."
        )

    print(f"    기존 영화 수: {len(existing_movies):,}개")

    print("[2] 현재 상영작 데이터 불러오기")

    now_playing_data = load_json(NOW_PLAYING_FILE)
    now_playing_movies = now_playing_data.get("movies", [])

    if not isinstance(now_playing_movies, list):
        raise ValueError(
            "now_playing_movies.json의 movies가 배열이 아닙니다."
        )

    print(
        f"    현재 상영작 수: {len(now_playing_movies):,}개"
    )

    # 모든 영화에 기본값을 추가합니다.
    for movie in existing_movies:
        movie["is_now_playing"] = False
        movie["watch_path"] = None
        movie["cinema_sources"] = []

    # 기존 영화 5000개를 제목 기준으로 빠르게 찾기 위한 색인입니다.
    existing_by_title: dict[
        str,
        list[dict[str, Any]]
    ] = {}

    for movie in existing_movies:
        normalized = normalize_title(movie.get("title"))

        if not normalized:
            continue

        existing_by_title.setdefault(
            normalized,
            [],
        ).append(movie)

    matched_count = 0
    unmatched_movies: list[dict[str, Any]] = []

    print("[3] 현재 상영작과 기존 영화 데이터 매칭")

    for current_movie in now_playing_movies:
        title = current_movie.get("title")

        normalized = (
            current_movie.get("normalized_title")
            or normalize_title(title)
        )

        candidates = existing_by_title.get(
            normalized,
            [],
        )

        # 제목이 정확히 하나의 기존 영화와 일치해야 자동 매칭합니다.
        if len(candidates) != 1:
            unmatched_movies.append(
                {
                    "reason": (
                        "no_match"
                        if len(candidates) == 0
                        else "duplicate_title"
                    ),
                    "candidate_count": len(candidates),
                    "title": title,
                    "normalized_title": normalized,
                    "sources": current_movie.get(
                        "sources",
                        [],
                    ),
                }
            )
            continue

        matched_movie = candidates[0]

        matched_movie["is_now_playing"] = True
        matched_movie["watch_path"] = "현재 상영 중"
        matched_movie["cinema_sources"] = (
            current_movie.get("sources", [])
        )
        matched_movie["now_playing_updated_at"] = (
            now_playing_data.get("collected_at")
        )

        matched_count += 1

    print(f"    매칭 성공: {matched_count}개")
    print(
        f"    매칭 실패: {len(unmatched_movies)}개"
    )

    print("[4] 실행용 영화 데이터 저장")

    save_json(
        OUTPUT_FILE,
        existing_movies,
    )

    save_json(
        UNMATCHED_FILE,
        {
            "count": len(unmatched_movies),
            "movies": unmatched_movies,
        },
    )

    print(f"    저장 완료: {OUTPUT_FILE}")
    print(f"    미매칭 목록: {UNMATCHED_FILE}")


if __name__ == "__main__":
    main()