"""
조회수 트래킹 서버 — 워드프레스 JS에서 호출
실행: python tracker.py
기본 포트: 8502
"""
import json
import os
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from datetime import datetime

TRACKER_FILE = os.path.join(os.path.dirname(__file__), "page_views.json")

SITE_MAP = {
    "baw": "bodyandwell",
    "biz": "bizachieve",
}

def _load_views() -> dict:
    try:
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_views(data: dict):
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()

def _match_keyword(title: str, keywords: list) -> str | None:
    norm_title = _normalize(title)
    best = None
    for kw in keywords:
        norm_kw = _normalize(kw)
        if len(norm_kw) >= 2 and norm_kw in norm_title:
            if best is None or len(norm_kw) > len(_normalize(best)):
                best = kw
    return best

def record_view(title: str, site: str):
    from app import _load_keywords_history
    hist = _load_keywords_history()
    keywords = [k for k in hist.keys() if k != "__meta__"]
    matched = _match_keyword(title, keywords)

    views = _load_views()
    key = matched if matched else title
    if key not in views:
        views[key] = {"baw": 0, "biz": 0, "last_seen": ""}
    site_key = site if site in ("baw", "biz") else "baw"
    views[key][site_key] = views[key].get(site_key, 0) + 1
    views[key]["last_seen"] = datetime.now().strftime("%Y-%m-%d")
    _save_views(views)


class TrackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/track":
            self.send_response(404)
            self.end_headers()
            return

        params = parse_qs(parsed.query)
        title = params.get("title", [""])[0].strip()
        site = params.get("site", ["baw"])[0].strip()

        if title:
            try:
                record_view(title, site)
            except Exception as e:
                print(f"[tracker] error: {e}")

        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass  # 로그 출력 끄기


if __name__ == "__main__":
    port = int(os.getenv("TRACKER_PORT", 8502))
    server = HTTPServer(("0.0.0.0", port), TrackHandler)
    print(f"[tracker] 조회수 트래킹 서버 시작 — 포트 {port}")
    server.serve_forever()
