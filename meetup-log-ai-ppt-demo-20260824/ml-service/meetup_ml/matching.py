import re
import unicodedata
from difflib import SequenceMatcher

DISTRIBUTOR_ALIASES = {
    "cj enm": "cjenm",
    "씨제이이엔엠": "cjenm",
    "cj엔터테인먼트": "cjenm",
    "씨제이엔터테인먼트": "cjenm",

    "lotte entertainment": "lotte",
    "롯데엔터테인먼트": "lotte",
    "롯데컬처웍스": "lotte",

    "new": "new",
    "넥스트엔터테인먼트월드": "new",

    "showbox": "showbox",
    "쇼박스": "showbox",
}


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"[^0-9a-z가-힣]", "", value)

def normalize_company(value: str) -> str:
    raw = (value or "").strip().casefold()

    if raw in DISTRIBUTOR_ALIASES:
        return DISTRIBUTOR_ALIASES[raw]

    normalized = normalize_title(value)

    for alias, canonical in DISTRIBUTOR_ALIASES.items():
        if normalize_title(alias) == normalized:
            return canonical

    return normalized


def _company_similarity(left_companies: list[str], right_companies: list[str]) -> float:
    if not left_companies or not right_companies:
        return 0.0

    best = 0.0

    for left in left_companies:
        for right in right_companies:
            a = normalize_company(left)
            b = normalize_company(right)

            if not a or not b:
                continue

            if a == b:
                return 1.0

            best = max(
                best,
                SequenceMatcher(None, a, b).ratio(),
            )

    return best


def _similarity(left: str, right: str) -> float:
    a, b = normalize_title(left), normalize_title(right)
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _person_names(rows: list[dict]) -> set[str]:
    return {normalize_title(row.get("peopleNm", "")) for row in rows if normalize_title(row.get("peopleNm", ""))}


def match_movies(tmdb: list[dict], kobis: list[dict], threshold: float = 0.78) -> list[dict]:
    results = []
    for left in tmdb:
        best = (0.0, None, [])
        for right in kobis:
            left_titles = [left.get("title"), left.get("title_ko"), left.get("title_en"), left.get("original_title")]
            right_titles = [right.get("movieNm"), right.get("movieNmEn")]
            title_score = max((_similarity(a or "", b or "") for a in left_titles for b in right_titles), default=0)
            signals = ["title"] if title_score >= .8 else []
            score = title_score * .65
            ly = (left.get("release_date") or "")[:4]
            ry = str(right.get("prdtYear") or "")[:4]
            if ly and ry and abs(int(ly) - int(ry)) <= 1:
                score += .15; signals.append("year")
            ld = {normalize_title(x) for x in left.get("directors", [])}; rd = _person_names(right.get("directors", []))
            if ld & rd:
                score += .15; signals.append("director")
            lc = {normalize_title(x) for x in left.get("cast", [])}
            rc = _person_names(right.get("actors", []))
            if lc & rc:
                score += .05
                signals.append("cast")

            if score > best[0]:
                best = (score, right, signals)
        score, right, signals = best
        if right and score >= 0.90:
            status = "AUTO_ACCEPT"
            kobis_code = right.get("movieCd")
        elif right and score >= threshold:
            status = "REVIEW"
            kobis_code = right.get("movieCd")
        else:
            status = "UNMATCHED"
            kobis_code = None

        results.append(
            {
                "internal_id": left["internal_id"],
                "tmdb_id": left.get("tmdb_id"),
                "kobis_code": kobis_code,
                "method": "+".join(signals) or "unmatched",
                "confidence": round(score, 4),
                "match_status": status,
                "needs_review": status == "REVIEW",
            }
        )
    return results
