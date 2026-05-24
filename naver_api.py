import hmac
import hashlib
import base64
import json
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
                        "pc_click": _parse_count(item.get("monthlyAvePcClkCnt", 0)),
                        "mobile_click": _parse_count(item.get("monthlyAveMobileClkCnt", 0)),
                        "pc_ctr": item.get("monthlyAvePcCtr", 0),
                        "mobile_ctr": item.get("monthlyAveMobileCtr", 0),
                        "comp_idx": item.get("compIdx", "N/A"),
                    }
        except Exception as e:
            print(f"[SearchAD] '{seed}' 오류: {e}")

    return all_keywords


def get_autocomplete(keyword: str, max_results: int = 10) -> List[str]:
    """네이버 자동완성 키워드 수집 (JSONP 파싱)"""
    try:
        resp = requests.get(
            "https://ac.search.naver.com/nx/ac",
            params={
                "q": keyword, "con": "1", "frm": "nx", "ans": "2",
                "r_format": "json", "r_enc": "UTF-8", "r_unicode": "0",
                "t_koreng": "1", "run": "2", "rev": "4", "q_enc": "UTF-8",
                "st": "100", "ackey": "yuxrhu1i", "_callback": "_jsonp_2",
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36",
                "Referer": "https://search.naver.com/",
                "Accept": "*/*",
            },
            timeout=5,
        )
        resp.raise_for_status()
        # JSONP 응답에서 JSON 추출: _jsonp_2({...}) → {...}
        text = resp.text.strip()
        match = re.search(r'_jsonp_\d+\((.+)\)\s*;?\s*$', text, re.DOTALL)
        if not match:
            return []
        data = json.loads(match.group(1))
        items = data.get("items", [])
        if not items:
            return []
        first = items[0]
        suggestions = first if (isinstance(first, list) and first and isinstance(first[0], list)) else items
        return [s[0] for s in suggestions[:max_results] if s and s[0]]
    except Exception as e:
        print(f"[자동완성] '{keyword}' 오류: {e}")
        return []


def get_search_volumes_batch(keywords: List[str], customer_id: str, api_key: str, secret_key: str) -> Dict[str, Dict]:
    """자동완성 키워드 검색량 조회 - 입력한 키워드만 결과로 반환"""
    results: Dict[str, Dict] = {}
    uri = "/keywordstool"
    # sanitized → original 매핑 (필터링용)
    sanitized_map = {_sanitize_keyword(kw): kw for kw in keywords if _sanitize_keyword(kw)}

    for original_kw, sanitized in [(kw, _sanitize_keyword(kw)) for kw in keywords]:
        if not sanitized:
            continue
        headers = _ad_headers("GET", uri, customer_id, api_key, secret_key)
        encoded = urllib.parse.quote_plus(sanitized)
        url = f"{SEARCH_AD_BASE_URL}{uri}?hintKeywords={encoded}&showDetail=1"
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            for item in resp.json().get("keywordList", []):
                rel_kw = item.get("relKeyword", "")
                rel_sanitized = _sanitize_keyword(rel_kw)
                # 입력한 키워드와 매칭되는 것만 저장
                if rel_sanitized not in sanitized_map:
                    continue
                matched_kw = sanitized_map[rel_sanitized]
                pc = _parse_count(item.get("monthlyPcQcCnt", 0))
                mobile = _parse_count(item.get("monthlyMobileQcCnt", 0))
                total = pc + mobile
                if matched_kw not in results or total > results[matched_kw]["total_search"]:
                    results[matched_kw] = {
                        "pc_search": pc,
                        "mobile_search": mobile,
                        "total_search": total,
                        "pc_click": _parse_count(item.get("monthlyAvePcClkCnt", 0)),
                        "mobile_click": _parse_count(item.get("monthlyAveMobileClkCnt", 0)),
                        "pc_ctr": item.get("monthlyAvePcCtr", 0),
                        "mobile_ctr": item.get("monthlyAveMobileCtr", 0),
                        "comp_idx": item.get("compIdx", "N/A"),
                    }
        except Exception as e:
            print(f"[SearchAD] '{original_kw}' 오류: {e}")

    return results


def get_blog_doc_count(keyword: str, client_id: str, client_secret: str) -> int:
    for attempt in range(4):
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
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json().get("total", 0)
        except requests.HTTPError:
            raise
        except Exception:
            return 0
    return 0


def get_doc_counts_parallel(keywords: List[str], client_id: str, client_secret: str, max_workers: int = 3) -> Dict[str, int]:
    """블로그 문서수 병렬 조회 (Rate Limit 방지: 동시 3개)"""
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
            "pc_search": data.get("pc_search", 0),
            "mobile_search": data.get("mobile_search", 0),
            "total_search": total,
            "pc_click": data.get("pc_click", 0),
            "mobile_click": data.get("mobile_click", 0),
            "pc_ctr": data.get("pc_ctr", 0),
            "mobile_ctr": data.get("mobile_ctr", 0),
            "comp_idx": data.get("comp_idx", "N/A"),
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


def _naver_search(query: str, search_type: str, client_id: str, client_secret: str, display: int = 5) -> list[dict]:
    """네이버 검색 API 공통 함수. search_type: news | blog | webkr"""
    url = f"{SEARCH_API_BASE_URL}/v1/search/{search_type}"
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    params = {"query": query, "display": display, "sort": "sim"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("items", [])
    except Exception:
        return []


def search_news(keyword: str, client_id: str, client_secret: str, display: int = 5) -> list[str]:
    """네이버 뉴스 검색 → URL 목록 반환"""
    items = _naver_search(keyword, "news", client_id, client_secret, display)
    return [item["link"] for item in items if item.get("link")]


def search_blog(keyword: str, client_id: str, client_secret: str, display: int = 5) -> list[str]:
    """네이버 블로그 검색 → URL 목록 반환"""
    items = _naver_search(keyword, "blog", client_id, client_secret, display)
    return [item["link"] for item in items if item.get("link")]


def get_keyword_summary(keyword: str, client_id: str, client_secret: str) -> str:
    """키워드로 웹/블로그 검색해 상위 스니펫 요약 반환 (제목 생성 컨텍스트용)"""
    snippets = []
    for search_type in ("webkr", "blog"):
        items = _naver_search(keyword, search_type, client_id, client_secret, display=3)
        for item in items:
            title = re.sub(r"<[^>]+>", "", item.get("title", "")).strip()
            desc = re.sub(r"<[^>]+>", "", item.get("description", "")).strip()
            if title:
                snippets.append(title)
            if desc:
                snippets.append(desc)
    return " / ".join(snippets[:8]) if snippets else ""
