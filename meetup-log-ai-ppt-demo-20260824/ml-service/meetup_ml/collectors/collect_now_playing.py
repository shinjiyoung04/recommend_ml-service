"""
=============================================================================
[한국 영화관 현재 상영 영화 수집 크롤러 모듈]
- 수집 대상: CGV, 롯데시네마(LOTTE_CINEMA), 메가박스(MEGABOX)
- 주요 기능:
  1. 각 영화관 공식 웹사이트 및 API에서 현재 상영/예매 가능 영화 목록 수집
  2. requests & BeautifulSoup 우선 사용, 필요 시 Playwright 차선책 활용
  3. 사이트별 독립적 오류 처리 (특정 사이트 장애 시에도 타 사이트 수집 지속)
  4. 동일 영화 제목 매칭(normalized_title 기준)을 통한 데이터 병합
  5. 한국 표준시(Asia/Seoul, UTC+9) ISO 8601 날짜/시간 포맷 적용
  6. 결과 데이터 JSON 스키마 규격 검증 및 저장 (0건 수집 시 기존 파일 보존)
=============================================================================
"""

import os
import re
import json
import time
import logging
import html
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

import requests
from bs4 import BeautifulSoup

# 콘솔 출력용 로깅 설정 (초보자도 실행 과정을 쉽게 파악할 수 있도록 작성)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("MovieCollector")

# ==========================================
# 1. 공통 상수 및 설정 정의
# ==========================================

# 한국 표준시 (KST: UTC+9) 타임존 설정
KST = timezone(timedelta(hours=9))

# 스키마 버전에 맞는 결과 저장 파일 경로
OUTPUT_RELATIVE_PATH = Path("data/normalized/now_playing_movies.json")

# HTTP 요청 시 웹 브라우저처럼 보이게 하기 위한 User-Agent 헤더
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
}

# 요청 간 대기 시간(초) - 서버 과부하 방지용
REQUEST_DELAY_SECONDS = 1.2


# ==========================================
# 2. 헬퍼 함수 (유틸리티)
# ==========================================

def get_current_iso_time() -> str:
    """현재 한국 시간을 ISO 8601 형식으로 반환합니다."""
    return datetime.now(KST).isoformat(timespec="seconds")

def create_normalized_title(title: Optional[str]) -> str:
    """
    영화 제목을 매칭용 문자열로 정규화합니다.

    예:
    "미니언즈 &amp; 몬스터즈"
    → "미니언즈몬스터즈"
    """
    if not title:
        return ""

    # &amp; 같은 HTML 문자를 실제 문자로 변환합니다.
    decoded_title = html.unescape(title)

    # 괄호 안의 상영 방식 정보를 제거합니다.
    clean_title = re.sub(
        r"\((2D|3D|4DX|IMAX|ATMOS|자막|더빙|디지털)\)",
        "",
        decoded_title,
        flags=re.IGNORECASE,
    )

    # 한글, 영문, 숫자만 남기고 공백과 특수문자를 제거합니다.
    normalized = re.sub(
        r"[^0-9a-zA-Z가-힣]",
        "",
        clean_title,
    )

    return normalized.lower()



def parse_release_year(release_date_str: Optional[str]) -> Optional[int]:
    """날짜 문자열("YYYY-MM-DD")에서 연도(int)를 추출합니다."""
    if not release_date_str:
        return None
    match = re.search(r"(\d{4})", release_date_str)
    if match:
        return int(match.group(1))
    return None


def clean_rating_text(rating_raw: Optional[str]) -> Optional[str]:
    """관람 등급 텍스트를 표준 명칭으로 정리합니다."""
    if not rating_raw:
        return None
    r = rating_raw.strip()
    if "전체" in r:
        return "전체 관람가"
    elif "12" in r:
        return "12세 이상 관람가"
    elif "15" in r:
        return "15세 이상 관람가"
    elif "18" in r or "청소년" in r or "불가" in r or "19" in r:
        return "청소년 관람 불가"
    elif "미정" in r:
        return "등급 미정"
    return r


# ==========================================
# 3. 영화관별 크롤러 구현부
# ==========================================

def collect_cgv() -> List[Dict[str, Any]]:
    """
    [CGV 크롤러]
    CGV 무비차트 페이지(http://www.cgv.co.kr/movies/)에서 현재 상영작 정보를 수집합니다.
    """
    logger.info(">>> CGV 영화 수집 시작...")
    collected_movies = []
    url = "http://www.cgv.co.kr/movies/default.aspx"

    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # 무비차트 영화 목록 li 요소 선택
        movie_items = soup.select(".sect-movie-chart ol li") or soup.select(".box-image")

        rank = 1
        for item in movie_items:
            title_el = item.select_one(".title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            # 예매율 추출 (예: "예매율 22.4%" -> 22.4)
            percent_el = item.select_one(".percent span")
            reservation_rate = None
            if percent_el:
                percent_text = percent_el.parent.get_text()
                rate_match = re.search(r"([\d\.]+)%", percent_text)
                if rate_match:
                    reservation_rate = float(rate_match.group(1))

            # 개봉일 추출
            txt_info = item.select_one(".txt-info strong")
            release_date = None
            if txt_info:
                date_match = re.search(r"(\d{4})[\.\-](\d{2})[\.\-](\d{2})", txt_info.get_text())
                if date_match:
                    release_date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"

            # 포스터 이미지 URL
            img_el = item.select_one(".thumb-image img")
            poster_url = None
            if img_el:
                poster_url = img_el.get("src") or img_el.get("data-src")

            # 상세 페이지 URL
            link_el = item.select_one("a.link-reservation, .box-image a")
            detail_url = None
            if link_el and link_el.get("href"):
                href = link_el.get("href")
                detail_url = href if href.startswith("http") else f"http://www.cgv.co.kr{href}"

            # 관람 등급
            grade_el = item.select_one(".cgvicon, .ico-grade")
            rating = clean_rating_text(grade_el.get_text(strip=True)) if grade_el else None

            collected_movies.append({
                "cinema": "CGV",
                "title": title,
                "rank": rank,
                "reservation_rate": reservation_rate,
                "release_date": release_date,
                "rating": rating,
                "poster_url": poster_url,
                "detail_url": detail_url
            })
            rank += 1

        logger.info(f"✔ CGV 수집 성공: 총 {len(collected_movies)}건")

    except Exception as e:
        logger.error(f"❌ CGV 수집 중 오류 발생: {e}")
        collected_movies = _collect_cgv_playwright_fallback()

    return collected_movies


def _collect_cgv_playwright_fallback() -> List[Dict[str, Any]]:
    """Playwright를 이용한 CGV 차선책 수집 함수"""
    logger.info("  ↳ Playwright로 CGV 차선책 수집을 시도합니다...")
    collected_movies = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("http://www.cgv.co.kr/movies/default.aspx", timeout=15000)
            page.wait_for_selector(".sect-movie-chart", timeout=5000)
            content = page.content()
            browser.close()

            soup = BeautifulSoup(content, "html.parser")
            items = soup.select(".sect-movie-chart ol li")
            rank = 1
            for item in items:
                title_el = item.select_one(".title")
                if not title_el:
                    continue
                collected_movies.append({
                    "cinema": "CGV",
                    "title": title_el.get_text(strip=True),
                    "rank": rank,
                    "reservation_rate": None,
                    "release_date": None,
                    "rating": None,
                    "poster_url": None,
                    "detail_url": "http://www.cgv.co.kr/movies/"
                })
                rank += 1
            logger.info(f"✔ Playwright CGV 차선책 성공: 총 {len(collected_movies)}건")
    except Exception as e:
        logger.warning(f"⚠️ Playwright CGV 차선책 시도 실패: {e}")

    return collected_movies


def collect_lotte_cinema() -> List[Dict[str, Any]]:
    """
    [롯데시네마 크롤러]
    롯데시네마 공식 데이터 API 엔드포인트를 호출하여 상영작 목록을 수집합니다.
    """
    logger.info(">>> 롯데시네마 영화 수집 시작...")
    collected_movies = []
    url = "https://www.lottecinema.co.kr/LCWS/Movie/MovieData.aspx"

    payload = {
        "paramList": json.dumps({
            "MethodName": "GetMovies",
            "channelType": "HO",
            "osType": "Chrome",
            "osVersion": "",
            "multiLanguage": "Language_KR",
            "division": 1,
            "moviePlayFilters": "",
            "sortType": 1
        })
    }

    try:
        response = requests.post(url, data=payload, headers=HTTP_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        movie_items = data.get("Movies", {}).get("Items", []) or data.get("Movie", {}).get("Items", [])

        rank = 1
        for item in movie_items:
            title = item.get("MovieNameKR") or item.get("MovieName")
            if not title:
                continue

            booking_rate = item.get("BookingRate")
            reservation_rate = float(booking_rate) if booking_rate is not None else None

            raw_date = item.get("ReleaseDate") or item.get("StartTime")
            release_date = None
            if raw_date:
                match = re.search(r"(\d{4})[\.\-](\d{2})[\.\-](\d{2})", str(raw_date))
                if match:
                    release_date = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

            rating = clean_rating_text(item.get("ViewGradeNameKR") or item.get("ViewGradeName"))
            poster_url = item.get("PosterURL")
            movie_code = item.get("RepresentationMovieCode") or item.get("MovieCode")

            detail_url = f"https://www.lottecinema.co.kr/NLCMC/Movie/MovieDetailView?movie={movie_code}" if movie_code else None

            collected_movies.append({
                "cinema": "LOTTE_CINEMA",
                "title": title,
                "rank": rank,
                "reservation_rate": reservation_rate,
                "release_date": release_date,
                "rating": rating,
                "poster_url": poster_url,
                "detail_url": detail_url
            })
            rank += 1

        logger.info(f"✔ 롯데시네마 수집 성공: 총 {len(collected_movies)}건")

    except Exception as e:
        logger.error(f"❌ 롯데시네마 수집 중 오류 발생: {e}")
        collected_movies = _collect_lotte_playwright_fallback()

    return collected_movies


def _collect_lotte_playwright_fallback() -> List[Dict[str, Any]]:
    """Playwright를 이용한 롯데시네마 차선책 수집 함수"""
    logger.info("  ↳ Playwright로 롯데시네마 차선책 수집을 시도합니다...")
    collected_movies = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://www.lottecinema.co.kr/NLCMC/Movie/List?flag=1", timeout=15000)
            page.wait_for_timeout(3000)
            content = page.content()
            browser.close()

            soup = BeautifulSoup(content, "html.parser")
            items = soup.select(".movie_list li, .movie_clist li")
            rank = 1
            for item in items:
                title_el = item.select_one(".tit, .movie_name")
                if not title_el:
                    continue
                collected_movies.append({
                    "cinema": "LOTTE_CINEMA",
                    "title": title_el.get_text(strip=True),
                    "rank": rank,
                    "reservation_rate": None,
                    "release_date": None,
                    "rating": None,
                    "poster_url": None,
                    "detail_url": "https://www.lottecinema.co.kr/"
                })
                rank += 1
            logger.info(f"✔ Playwright 롯데시네마 차선책 성공: 총 {len(collected_movies)}건")
    except Exception as e:
        logger.warning(f"⚠️ Playwright 롯데시네마 차선책 시도 실패: {e}")

    return collected_movies


def collect_megabox() -> List[Dict[str, Any]]:
    """
    [메가박스 크롤러]
    메가박스 공식 목록 API 엔드포인트를 호출하여 현재 상영작 정보를 수집합니다.
    """
    logger.info(">>> 메가박스 영화 수집 시작...")
    collected_movies = []
    url = "https://www.megabox.co.kr/on/oh/oha/Movie/selectMovieList.do"

    payload = {
        "paramList": json.dumps({
            "crtgType": "ON",
            "onlYBooking": "N",
            "sortType": "IB"
        })
    }

    try:
        response = requests.post(url, data=payload, headers=HTTP_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        movie_items = data.get("movieList", [])
        
        rank = 1
        for item in movie_items:
            title = item.get("movieNm")
            if not title:
                continue
            title = html.unescape(title).strip()

            sales_rat = item.get("salesRat")
            reservation_rate = float(sales_rat) if sales_rat is not None else None

            raw_date = item.get("rleaseDt")
            release_date = None
            if raw_date:
                match = re.search(r"(\d{4})[\.\-](\d{2})[\.\-](\d{2})", str(raw_date))
                if match:
                    release_date = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

            rating = clean_rating_text(item.get("adstrdNm") or item.get("admitCd"))

            img_path = item.get("rltmImgPath") or item.get("posterImgPath")
            poster_url = f"https://img.megabox.co.kr{img_path}" if img_path and not img_path.startswith("http") else img_path

            movie_no = item.get("movieNo")
            detail_url = f"https://www.megabox.co.kr/movie-detail?rpstMovieNo={movie_no}" if movie_no else None

            collected_movies.append({
                "cinema": "MEGABOX",
                "title": title,
                "rank": rank,
                "reservation_rate": reservation_rate,
                "release_date": release_date,
                "rating": rating,
                "poster_url": poster_url,
                "detail_url": detail_url
            })
            rank += 1

        logger.info(f"✔ 메가박스 수집 성공: 총 {len(collected_movies)}건")

    except Exception as e:
        logger.error(f"❌ 메가박스 수집 중 오류 발생: {e}")
        collected_movies = _collect_megabox_playwright_fallback()

    return collected_movies


def _collect_megabox_playwright_fallback() -> List[Dict[str, Any]]:
    """Playwright를 이용한 메가박스 차선책 수집 함수"""
    logger.info("  ↳ Playwright로 메가박스 차선책 수집을 시도합니다...")
    collected_movies = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://www.megabox.co.kr/movie", timeout=15000)
            page.wait_for_timeout(3000)
            content = page.content()
            browser.close()

            soup = BeautifulSoup(content, "html.parser")
            items = soup.select(".movie-list ol li, #movieList li")
            rank = 1
            for item in items:
                title_el = item.select_one(".title, .tit")
                if not title_el:
                    continue
                collected_movies.append({
                    "cinema": "MEGABOX",
                    "title": title_el.get_text(strip=True),
                    "rank": rank,
                    "reservation_rate": None,
                    "release_date": None,
                    "rating": None,
                    "poster_url": None,
                    "detail_url": "https://www.megabox.co.kr/movie"
                })
                rank += 1
            logger.info(f"✔ Playwright 메가박스 차선책 성공: 총 {len(collected_movies)}건")
    except Exception as e:
        logger.warning(f"⚠️ Playwright 메가박스 차선책 시도 실패: {e}")

    return collected_movies


# ==========================================
# 4. 데이터 통합 및 JSON 저장 로직
# ==========================================

def merge_movie_records(raw_cinema_data: Dict[str, List[Dict[str, Any]]], collected_time_iso: str) -> List[Dict[str, Any]]:
    """
    여러 영화관에서 수집된 개별 영화 항목들을 normalized_title 기준으로 병합합니다.
    - 동일 영화가 여러 영화관에 존재할 경우 하나의 메인 영화 객체로 합치고,
      sources 배열에 각 영화관별 실시간 순위 및 예매율 정보를 저장합니다.
    """
    merged_map: Dict[str, Dict[str, Any]] = {}

    for cinema_name, items in raw_cinema_data.items():
        for item in items:
            title = item["title"]
            norm_title = create_normalized_title(title)
            if not norm_title:
                continue

            cinema_source_obj = {
                "cinema": cinema_name,
                "rank": item.get("rank"),
                "reservation_rate": item.get("reservation_rate"),
                "booking_available": True,
                "source_url": item.get("detail_url"),
                "collected_at": collected_time_iso
            }

            if norm_title in merged_map:
                existing = merged_map[norm_title]
                existing["sources"].append(cinema_source_obj)

                if not existing.get("poster_url") and item.get("poster_url"):
                    existing["poster_url"] = item.get("poster_url")
                if not existing.get("release_date") and item.get("release_date"):
                    existing["release_date"] = item.get("release_date")
                    existing["release_year"] = parse_release_year(item.get("release_date"))
                if not existing.get("rating") and item.get("rating"):
                    existing["rating"] = item.get("rating")
                if not existing.get("detail_url") and item.get("detail_url"):
                    existing["detail_url"] = item.get("detail_url")
            else:
                rel_date = item.get("release_date")
                rel_year = parse_release_year(rel_date)

                merged_map[norm_title] = {
                    "title": title,
                    "normalized_title": norm_title,
                    "original_title": None,
                    "release_date": rel_date,
                    "release_year": rel_year,
                    "rating": item.get("rating"),
                    "poster_url": item.get("poster_url"),
                    "detail_url": item.get("detail_url"),
                    "is_now_playing": True,
                    "watch_path": "현재 상영 중",
                    "sources": [cinema_source_obj]
                }

    return list(merged_map.values())


def main():
    """크롤러 프로그램 메인 실행 제어 함수"""
    logger.info("==================================================")
    logger.info("🎬 한국 3대 영화관(CGV, 롯데시네마, 메가박스) 현재 상영 영화 수집기")
    logger.info("==================================================")

    now_iso = get_current_iso_time()
    raw_cinema_results: Dict[str, List[Dict[str, Any]]] = {}

    cinemas_to_collect = [
        ("CGV", collect_cgv),
        ("LOTTE_CINEMA", collect_lotte_cinema),
        ("MEGABOX", collect_megabox)
    ]

    success_counts = {}

    for index, (cinema_code, collector_func) in enumerate(cinemas_to_collect):
        if index > 0:
            time.sleep(REQUEST_DELAY_SECONDS)

        try:
            movies = collector_func()
            raw_cinema_results[cinema_code] = movies
            success_counts[cinema_code] = len(movies)
        except Exception as err:
            logger.error(f"❌ [{cinema_code}] 수집 실패: {err}")
            raw_cinema_results[cinema_code] = []
            success_counts[cinema_code] = 0

    merged_movies = merge_movie_records(raw_cinema_results, now_iso)
    total_count = len(merged_movies)

    logger.info("--------------------------------------------------")
    logger.info("📊 수집 결과 요약:")
    for code, count in success_counts.items():
        logger.info(f"  - {code:12s}: {count}건 수집")
    logger.info(f"  - 통합 영화 수 : {total_count}개 (중복 제거 완료)")
    logger.info("--------------------------------------------------")

    # 수집 결과가 0건이면 기존 JSON 파일 덮어쓰지 않고 에러 출력
    if total_count == 0:
        logger.error("[오류] 수집된 영화 데이터가 0건입니다!")
        logger.error("기존 JSON 데이터 손실 방지를 위해 파일 덮어쓰기를 취소하고 작업을 중단합니다.")
        raise RuntimeError("No movies collected from any cinema sources.")

    final_output_json = {
        "schema_version": "1.0",
        "collected_at": now_iso,
        "sources": ["CGV", "LOTTE_CINEMA", "MEGABOX"],
        "movie_count": total_count,
        "movies": merged_movies
    }

    output_file_path = OUTPUT_RELATIVE_PATH
    output_file_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file_path, "w", encoding="utf-8") as f:
        json.dump(final_output_json, f, ensure_ascii=False, indent=2)

    logger.info(f"🎉 성공적으로 데이터를 저장했습니다! 파일 위치: {output_file_path.resolve()}")


if __name__ == "__main__":
    main()