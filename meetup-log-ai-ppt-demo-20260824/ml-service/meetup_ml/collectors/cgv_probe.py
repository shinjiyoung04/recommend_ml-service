from pathlib import Path

import requests


# CGV 무비차트 페이지
CGV_URL = "https://cgv.co.kr/cnm/cgvChart/movieChart?tabParam=75"

# 웹사이트가 일반 브라우저 요청처럼 인식하도록 User-Agent를 지정합니다.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


def main() -> None:
    print("[1] CGV 페이지 요청 시작")
    print(f"[2] 요청 주소: {CGV_URL}")

    try:
        response = requests.get(
            CGV_URL,
            headers=HEADERS,
            timeout=20,
        )

        response.encoding = "utf-8"

        print(f"[3] 응답 상태 코드: {response.status_code}")
        print(f"[4] 응답 문자 수: {len(response.text):,}")

        # 잘못된 응답이면 예외를 발생시킵니다.
        response.raise_for_status()

    except requests.RequestException as error:
        print("[오류] CGV 페이지 요청에 실패했습니다.")
        print(error)
        return

    # 받아온 HTML을 파일로 저장합니다.
    output_path = Path("data") / "raw" / "cgv_movie_chart.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        response.text,
        encoding="utf-8",
    )

    print(f"[5] HTML 저장 완료: {output_path.resolve()}")

    # HTML 안에 영화와 관련된 문자열이 존재하는지 간단히 검사합니다.
    check_keywords = [
        "무비차트",
        "예매율",
        "개봉",
        "영화",
    ]

    print("\n[6] HTML 문자열 검사")

    for keyword in check_keywords:
        found = keyword in response.text
        print(f"- {keyword}: {'발견' if found else '없음'}")

    print("\n[완료] 먼저 저장된 HTML을 확인해야 합니다.")


if __name__ == "__main__":
    main()