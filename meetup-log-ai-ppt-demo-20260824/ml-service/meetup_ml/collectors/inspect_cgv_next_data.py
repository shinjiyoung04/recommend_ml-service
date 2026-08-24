from pathlib import Path
import re


HTML_PATH = Path("data") / "raw" / "cgv_movie_chart.html"


def main() -> None:
    if not HTML_PATH.exists():
        print(f"[오류] HTML 파일이 없습니다: {HTML_PATH.resolve()}")
        return

    html = HTML_PATH.read_text(encoding="utf-8")

    print(f"[1] HTML 문자 수: {len(html):,}")
    print(f"[2] self.__next_f.push 개수: {html.count('self.__next_f.push')}")

    keywords = [
        "스파이더맨",
        "예매율",
        "개봉",
        "movieChart",
        "movieNm",
        "movieName",
        "movieTitle",
        "title",
        "bookingRate",
        "reservationRate",
    ]

    print("\n[3] 주요 문자열 검사")

    for keyword in keywords:
        count = html.lower().count(keyword.lower())
        print(f"- {keyword}: {count}개")

    print("\n[4] Next.js 데이터 일부 추출")

    matches = re.findall(
        r"self\.__next_f\.push\((.*?)\)</script>",
        html,
        flags=re.DOTALL,
    )

    print(f"- 추출된 push 블록: {len(matches)}개")

    output_path = Path("data") / "raw" / "cgv_next_data.txt"

    output_path.write_text(
        "\n\n".join(matches),
        encoding="utf-8",
    )

    print(f"- 저장 완료: {output_path.resolve()}")

    print("\n[5] 영화 관련 문자열 주변 문맥 출력")

    search_terms = [
        "movieChart",
        "movieNm",
        "movieName",
        "movieTitle",
        "bookingRate",
        "reservationRate",
    ]

    for term in search_terms:
        index = html.lower().find(term.lower())

        if index == -1:
            print(f"\n[{term}] 없음")
            continue

        start = max(0, index - 200)
        end = min(len(html), index + 500)

        print(f"\n[{term}] 발견 위치: {index}")
        print(html[start:end])


if __name__ == "__main__":
    main()