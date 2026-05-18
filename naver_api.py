import hmac
import hashlib
import base64
import re
import time
import urllib.parse
import requests
from typing import List, Dict

SEARCH_AD_BASE_URL = "https://api.searchad.naver.com"
SEARCH_API_BASE_URL = "https://openapi.naver.com"


def _generate_signature(timestamp: str, method: str, uri: str, secret_key: str) -> str:
    message = f"{timestamp}.{method}.{uri}"
    h = hmac.new(secret_key.encode("utf-8"), message.encode("utf-8"), digestmod=hashlib.sha256)
    return base64.b64encode(h.digest()).decode("utf-8")


def _ad_headers(method: str, uri: str, customer_id: str, api_key: str, secret_key: str) -> Dict:
    timestamp = str(int(time.time() * 1000))
    # GET 요청에는 Content-Type 헤더 제외
    return {
        "X-Timestamp": timestamp,
        "X-API-KEY": api_key,
        "X-Customer": str(customer_id),
        "X-Signature": _generate_signature(timestamp, method, uri, secret_key),
    }


def _is_valid_keyword(keyword: str) -> bool:
    """한국어, 영어, 숫자, 공백만 허용 / 40자 이내"""
    return (
        bool(re.match(r'^[가-힣a-zA-Z0-9\s]+$', keyword.strip()))
        and 1 <= len(keyword.strip()) <= 40
    )


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

    # 유효하지 않은 키워드 사전 필터링
    valid_keywords = [kw for kw in keywords if _is_valid_keyword(kw)]
    print(f"[SearchAD] 유효 키워드 {len(valid_keywords)}/{len(keywords)}개")

    for i in range(0, len(valid_keywords), 5):
        batch = valid_keywords[i : i + 5]
        uri = "/keywordstool"
        headers = _ad_headers("GET", uri, customer_id, api_key, secret_key)
        params = {"hintKeywords": ",".join(batch), "showDetail": "1"}

        try:
            # 콤마를 인코딩하지 않고 URL 직접 구성 (requests의 %2C 변환 방지)
            encoded = urllib.parse.quote(",".join(batch), safe=",")
            url = f"{SEARCH_AD_BASE_URL}{uri}?hintKeywords={encoded}&showDetail=1"
            resp = requests.get(url, headers=headers, timeout=10)
            print(f"[SearchAD] 상태코드: {resp.status_code}")
            print(f"[SearchAD] 응답내용: {resp.text[:300]}")
            resp.raise_for_status()
            keyword_list = resp.json().get("keywordList", [])

            # API가 반환한 전체 키워드를 저장
            returned: Dict[str, Dict] = {}
            for item in keyword_list:
                kw = item.get("relKeyword", "")
                returned[kw] = {
                    "pc_search": _parse_count(item.get("monthlyPcQcCnt", 0)),
                    "mobile_search": _parse_count(item.get("monthlyMobileQcCnt", 0)),
                    "comp_idx": item.get("compIdx", "N/A"),
                }

            # 각 힌트 키워드를 반환 결과와 매칭 (공백·대소문자 무시)
            for hint in batch:
                hint_norm = hint.lower().replace(" ", "")
                if hint in returned:
                    results[hint] = returned[hint]
                else:
                    matched = next(
                        (data for kw, data in returned.items()
                         if kw.lower().replace(" ", "") == hint_norm),
                        None,
                    )
                    # 매칭 실패 시 API 첫 번째 결과로 대체
                    results[hint] = matched if matched else (
                        list(returned.values())[0] if returned else
                        {"pc_search": 0, "mobile_search": 0, "comp_idx": "N/A"}
                    )

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
