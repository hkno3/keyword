"""
Google Docs MCP 리프레시 토큰 갱신 스크립트
실행: python refresh_google_token.py
"""
import json
import os
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.request
import urllib.parse

CLIENT_ID = ""
CLIENT_SECRET = ""
REDIRECT_URI = "http://localhost:8765"
TOKEN_PATH = os.path.expanduser(r"C:\Users\Administrator\.config\google-docs-mcp\token.json")
CONFIG_PATH = os.path.expanduser(r"C:\Users\Administrator\AppData\Roaming\Claude\claude_desktop_config.json")

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]

auth_code = None

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>인증 완료! 이 창을 닫으세요.</h2>".encode("utf-8"))
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # 로그 숨김


def get_auth_url():
    params = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    })
    return f"https://accounts.google.com/o/oauth2/v2/auth?{params}"


def exchange_code(code):
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def save_token(token_data):
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        json.dump(token_data, f, indent=2)
    print(f"✅ 토큰 저장: {TOKEN_PATH}")


def update_config(refresh_token):
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["mcpServers"]["google-docs-mcp"]["env"]["GOOGLE_REFRESH_TOKEN"] = refresh_token
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"✅ 설정 파일 업데이트: {CONFIG_PATH}")


if __name__ == "__main__":
    print("🔑 Google 인증 시작...")
    url = get_auth_url()
    print(f"\n브라우저가 열립니다. Google 계정으로 로그인 후 허용을 눌러주세요.")
    webbrowser.open(url)

    print("\n⏳ 인증 대기 중...")
    server = HTTPServer(("localhost", 8765), CallbackHandler)
    server.handle_request()

    if auth_code:
        print("✅ 인증 코드 수신, 토큰 교환 중...")
        token_data = exchange_code(auth_code)

        if "refresh_token" in token_data:
            save_token(token_data)
            update_config(token_data["refresh_token"])
            print("\n🎉 완료! Claude 앱을 재시작하면 Google Sheets 사용 가능합니다.")
        else:
            print("❌ 리프레시 토큰이 없습니다. 다시 시도해주세요.")
            print(token_data)
    else:
        print("❌ 인증 실패")
