import hmac
import hashlib
import base64
import time
import requests
from typing import List, Dict

SEARCH_AD_BASE_URL = "https://api.naver.com"
SEARCH_API_BASE_URL = "https://openapi.naver.com"


def _generate_signature(timestamp: str, method: str, uri: str, secret_key: str) -> str:
    message = f"{timestamp}.{method}.{uri}"
    h = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        digestmod=hashlib.sha256,
    )
    return base64.b64encode(h.digest()).decode("utf-8")


def _ad_headers(method: str, uri: str, customer_id: str, api_key: str, secret_key: str) -> Dict:
    timestamp = str(int(time.time() * 1000))
    return {
        "X-Timestamp": timestamp,
        "X-API-KEY": api_key,
        "X-Customer": str(customer_id),
        "X-Signature": _generate_signature(timestamp, method, uri, secret_key),
        "Content-Type": "application/json; charset=UTF-8",
    }


def _parse_count(value) -> int:
    """'< 10' 같은 문자열도 숫자로 변환"""
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


def get_keyword_stats(
    keywords: List[str],
    customer_id: str,
    api_key: str,
    secret_key: str,
) -> Dict[str, Dict]:
    """네이버 검색광고 API로 키워드별 월 검색량 조회 (5개씩 배치)"""
    results: Dict[str, Dict] = {}

    for i in range(0, len(keywords), 5):
        batch = keywords[i : i + 5]
        uri = "/keywordstool"
        headers = _ad_headers("GET", uri, customer_id, api_key, secret_key)
        params = {"hintKeywords": ",".join(batch), "showDetail": "1"}

        try:
            resp = requests.get(
                f"{SEARCH_AD_BASE_URL}{uri}",
                headers=headers,
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            for item in resp.json().get("keywordList", []):
                kw = item.get("relKeyword", "")
                results[kw] = {
                    "pc_search": _parse_count(item.get("monthlyPcQcCnt", 0)),
                    "mobile_search": _parse_count(item.get("monthlyMobileQcCnt", 0)),
                    "comp_idx": item.get("compIdx", "N/A"),
                }
        except Exception as e:
            print(f"[SearchAD API 오류] {e}")

    return results


def get_blog_doc_count(keyword: str, client_id: str, client_secret: str) -> int:
    """네이버 블로그 검색 API로 총 문서 수 조회"""
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
    except Exception as e:
        print(f"[Search API 오류] {e}")
        return 0


def competition_level(search_volume: int, doc_count: int):
    """
    경쟁 강도 = 문서량 / 검색량
    낮을수록 공략하기 좋은 키워드
    """
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
