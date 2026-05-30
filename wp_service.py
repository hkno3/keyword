import re
import requests
from requests.auth import HTTPBasicAuth


def test_connection(site: dict) -> tuple[bool, str]:
    try:
        url = site["url"].rstrip("/") + "/wp-json/wp/v2/users/me"
        r = requests.get(url, auth=HTTPBasicAuth(site["username"], site["app_password"]), timeout=10)
        if r.status_code == 200:
            return True, r.json().get("name", "연결 성공")
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


def _get_or_create_tag(site: dict, name: str, auth: HTTPBasicAuth) -> int | None:
    base = site["url"].rstrip("/") + "/wp-json/wp/v2/tags"
    r = requests.get(base, params={"search": name, "per_page": 5}, auth=auth, timeout=10)
    for tag in r.json() if r.ok else []:
        if tag["name"] == name:
            return tag["id"]
    r = requests.post(base, json={"name": name}, auth=auth, timeout=10)
    return r.json().get("id") if r.status_code == 201 else None


def publish_post(site: dict, post_data: dict, pub_status: str = "draft", scheduled_date: str = "") -> dict:
    """WordPress REST API로 포스트 발행.
    pub_status: 'draft' | 'publish' | 'future'
    scheduled_date: ISO 8601 형식 (예: '2026-05-24T09:00:00'), pub_status='future'일 때 필수
    """
    auth = HTTPBasicAuth(site["username"], site["app_password"])
    base = site["url"].rstrip("/")

    tag_ids = [
        tid for t in post_data.get("tags", [])
        if (tid := _get_or_create_tag(site, t, auth)) is not None
    ]

    payload = {
        "title": post_data["title"],
        "content": post_data["content"],
        "status": pub_status,
        "tags": tag_ids,
        "meta": {
            "_yoast_wpseo_metadesc": post_data.get("meta_description", ""),
            "_yoast_wpseo_focuskw": post_data.get("focus_keyword", ""),
            "rank_math_focus_keyword": post_data.get("focus_keyword", ""),
            "rank_math_description": post_data.get("meta_description", ""),
        },
    }

    if scheduled_date:
        payload["date"] = scheduled_date
        payload["status"] = "future"

    r = requests.post(f"{base}/wp-json/wp/v2/posts", json=payload, auth=auth, timeout=30)
    r.raise_for_status()
    return r.json()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def fetch_post_views(site: dict, site_key: str, hist_kws: list) -> dict:
    """워드프레스 전체 포스트 조회수를 키워드와 매칭해서 반환.
    반환: {keyword: count}
    """
    auth = HTTPBasicAuth(site["username"], site["app_password"])
    base = site["url"].rstrip("/") + "/wp-json/wp/v2/posts"
    result = {}
    page = 1
    norm_kws = {_normalize(kw): kw for kw in hist_kws}

    while True:
        try:
            r = requests.get(base, params={
                "per_page": 100,
                "page": page,
                "_fields": "id,title,meta",
                "status": "publish",
            }, auth=auth, timeout=30)
        except Exception:
            break

        if not r.ok:
            break

        posts = r.json()
        if not posts:
            break

        for post in posts:
            title = post.get("title", {}).get("rendered", "")
            title = re.sub(r"<[^>]+>", "", title).strip()
            count = int(post.get("meta", {}).get("_post_views_count", 0) or 0)
            if count == 0:
                continue

            norm_title = _normalize(title)
            matched = None
            best_len = 0
            for norm_kw, orig_kw in norm_kws.items():
                if len(norm_kw) >= 2 and norm_kw in norm_title:
                    if len(norm_kw) > best_len:
                        matched = orig_kw
                        best_len = len(norm_kw)

            if matched:
                result[matched] = result.get(matched, 0) + count

        total_pages = int(r.headers.get("X-WP-TotalPages", 1))
        if page >= total_pages:
            break
        page += 1

    return result
