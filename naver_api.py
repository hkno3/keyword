import hmac
import hashlib
import base64
import re
import time
import urllib.parse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

SEARCH_AD_BASE_URL = "https://api.searchad.naver.com"
SEARCH_API_BASE_URL = "https://openapi.naver.com"


def _generate_signature(timestamp: str, method: str, uri: str, secret_key: str) -> str:
    message = f"{timestamp}.{method}.{uri}"
    h = hmac.new(secret_key.encode("utf-8"), message.encode("utf-8"), digestmod=hashlib.sha256)
    return base64.b64encode(h.digest()).decode("utf-8")


def _ad_headers(method: str, uri: str, customer_id: str, api_key: str, secret_key: str) -> Dict:
    timestamp = str(int(time.time() * 1000))
    return {
        "X-Timestamp": timestamp,
        "X-API-KEY": api_key,
        "X-Customer": str(customer_id),
        "X-Signature": _generate_signature(timestamp, method, uri, secret_key),
    }


def _sanitize_keyword(keyword: str) -> str:
    kw = re.sub(r'\s+', '', keyword.strip())
    kw = re.sub(r'[^가-힣a-zA-Z0-9]', '', kw)
    return kw[:40]


def _parse_count(value) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("<"):
            return 5
        try:
            return int(s.replace(",", ""))
        except ValueError:
            return 0
    return 0


def get_related_keywords(seed_keywords: List[str], customer_id: str, api_key: str, secret_key: str) -> Dict[str, Dict]:
    """씨드 키워드(단일)로 연관키워드 전체 수집 — 중복 시 검색량 높은 것 유지"""
    all_keywords: Dict[str, Dict] = {}

    for seed in seed_keywords:
        sanitized = _sanitize_keyword(seed)
        if not sanitized:
            continue

        uri = "/keywordstool"
        headers = _ad_headers("GET", uri, customer_id, api_key, secret_key)
        encoded = urllib.parse.quote_plus(sanitized)
        url = f"{SEARCH_AD_BASE_URL}{uri}?hintKeywords={encoded}&showDetail=1"

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()

            for item in resp.json().get("keywordList", []):
                kw = item.get("relKeyword", "")
                pc = _parse_count(item.get("monthlyPcQcCnt", 0))
                mobile = _parse_count(item.get("monthlyMobileQcCnt", 0))
                total = pc + mobile

                if kw not in all_keywords or total > all_keywords[kw]["total_search"]:
                    all_keywords[kw] = {
                        "pc_search": pc,
                        "mobile_search": mobile,
                        "total_search": total,
                        "comp_idx": item.get("compIdx", "N/A"),
                    }
        except Exception as e:
            print(f"[SearchAD] '{seed}' 오류: {e}")

    return all_keywords


def get_blog_doc_count(keyword: str, client_id: str, client_secret: str) -> int:
    try:
        resp = requests.get(
            f"{SEARCH_API_BASE_URL}/v1/search/blog.json",
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
            },
            params={"query": keyword, "display": 1},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("total", 0)
    except Exception:
        return 0


def get_doc_counts_parallel(keywords: List[str], client_id: str, client_secret: str, max_workers: int = 10) -> Dict[str, int]:
    """블로그 문서수 병렬 조회로 속도 향상"""
    results: Dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(get_blog_doc_count, kw, client_id, client_secret): kw
            for kw in keywords
        }
        for future in as_completed(futures):
            kw = futures[future]
            try:
                results[kw] = future.result()
            except Exception:
                results[kw] = 0
    return results


def build_keyword_table(related: Dict[str, Dict], doc_counts: Dict[str, int]) -> List[Dict]:
    """검색량 + 문서수 + 경쟁강도 통합 테이블 생성 (경쟁 낮은 순 정렬)"""
    rows = []
    for kw, data in related.items():
        total = data["total_search"]
        doc = doc_counts.get(kw, 0)
        level, stars, ratio = competition_level(total, doc)
        rows.append({
            "keyword": kw,
            "total_search": total,
            "doc_count": doc,
            "level": level,
            "stars": stars,
            "ratio": ratio,
        })
    return sorted(rows, key=lambda x: x["ratio"])


def competition_level(search_volume: int, doc_count: int):
    if search_volume == 0:
        return "매우 높음", "⭐", 999.0
    ratio = doc_count / search_volume
    if ratio < 0.5:
        return "매우 낮음", "⭐⭐⭐⭐⭐", ratio
    elif ratio < 1.0:
        return "낮음", "⭐⭐⭐⭐", ratio
    elif ratio < 3.0:
        return "보통", "⭐⭐⭐", ratio
    elif ratio < 10.0:
        return "높음", "⭐⭐", ratio
    else:
        return "매우 높음", "⭐", ratio
