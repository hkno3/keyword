import json
import os
import re
import urllib.parse
import requests

SITEMAP_CACHE_FILE = os.path.join(os.path.dirname(__file__), "sitemap_cache.json")


def _sheets_to_csv_url(sheet_url: str) -> str:
    match = re.search(r'/spreadsheets/d/([^/]+)', sheet_url)
    if not match:
        return sheet_url
    sheet_id = match.group(1)
    gid = re.search(r'gid=(\d+)', sheet_url)
    gid = gid.group(1) if gid else '0'
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def load_from_sheets(sheet_url: str) -> tuple[list[str], str]:
    """Google Sheets에서 URL 목록 로드 후 캐시 저장. (urls, error) 반환"""
    try:
        csv_url = _sheets_to_csv_url(sheet_url)
        r = requests.get(csv_url, timeout=15)
        r.raise_for_status()

        urls = []
        for line in r.text.splitlines():
            for cell in line.split(','):
                cell = cell.strip().strip('"')
                if cell.startswith('http'):
                    decoded = urllib.parse.unquote(cell)
                    if decoded not in urls:
                        urls.append(decoded)

        save_cache(urls)
        return urls, ""
    except Exception as e:
        return [], str(e)


def load_cache() -> list[str]:
    try:
        with open(SITEMAP_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_cache(urls: list[str]):
    with open(SITEMAP_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(urls, f, ensure_ascii=False, indent=2)


_STOPWORDS = {
    # 행동/방식
    "추천", "방법", "비교", "정리", "분석", "총정리", "알아보기", "알아보자",
    "하는법", "하는방법", "가이드",
    # 평가/순위
    "순위", "랭킹", "후기", "리뷰", "솔직", "top", "best", "실패", "성공",
    # 특성 설명
    "종류", "효과", "이유", "원인", "특징", "장점", "단점", "차이",
    "뜻", "의미", "개념", "란", "이란",
    # 수식어
    "완벽", "핵심", "쉽게", "빠르게", "제대로", "기초", "입문", "초보",
    "꼭", "필수",
    # 숫자/단위
    "가지", "개", "편", "top3", "top5", "top10",
    # 기타
    "정보", "내용", "주의", "팁", "tip", "주의사항", "한눈에",
}


def find_related(keyword: str, urls: list[str], n: int = 6) -> list[str]:
    """키워드와 관련 높은 URL n개 반환 — 엄격(2단어 이상) → 느슨(1단어) 단계적 시도"""
    if not urls:
        return []

    kw_words = set()
    for word in re.split(r'\s+', keyword):
        if len(word) >= 2 and word.lower() not in _STOPWORDS:
            kw_words.add(word)

    if not kw_words:
        return []

    def _score(url, words):
        slug = urllib.parse.unquote(url)
        return sum(1 for w in words if w in slug)

    # 1단계: 2개 이상 단어 매칭 (엄격)
    scored = [(s, u) for u in urls if (s := _score(u, kw_words)) >= 2]
    scored.sort(key=lambda x: -x[0])
    result = [u for _, u in scored[:n]]

    if len(result) >= n:
        return result

    # 2단계: 1개 이상 단어 매칭으로 부족분 보완
    existing = set(result)
    scored2 = [(s, u) for u in urls if u not in existing and (s := _score(u, kw_words)) >= 1]
    scored2.sort(key=lambda x: -x[0])
    result += [u for _, u in scored2[:n - len(result)]]

    return result
