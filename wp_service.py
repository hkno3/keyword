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
