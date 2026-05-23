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


def find_related(keyword: str, urls: list[str], n: int = 6) -> list[str]:
    """키워드와 관련 높은 URL n개 반환 (슬러그 매칭)"""
    if not urls:
        return []

    # 키워드에서 2자 이상 단어 추출
    kw_words = set()
    for word in re.split(r'\s+', keyword):
        if len(word) >= 2:
            kw_words.add(word)
        if len(word) >= 4:
            kw_words.add(word[:2])

    scored = []
    for url in urls:
        slug = urllib.parse.unquote(url)
        score = sum(1 for w in kw_words if w in slug)
        if score > 0:
            scored.append((score, url))

    scored.sort(key=lambda x: -x[0])
    return [url for _, url in scored[:n]]
