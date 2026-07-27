"""
블로그 썸네일 생성기
- Canva에서 export한 배경 이미지 URL을 받아
- 중앙에 한글 텍스트(외곽선)를 합성해 저장

사용법: python make_thumbnail.py
"""

import sys
import urllib.request
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os

# ── 설정 ──────────────────────────────────────────────────────────
CANVA_IMAGE_URL = (
    "https://export-download.canva.com/Qa7AU/DAHQNaQa7AU/-1/0/"
    "0001-9167587448084038724.png"
    "?X-Amz-Algorithm=AWS4-HMAC-SHA256"
    "&X-Amz-Credential=AKIAQYCGKMUH5AO7UJ26%2F20260722%2Fus-east-1%2Fs3%2Faws4_request"
    "&X-Amz-Date=20260722T202414Z"
    "&X-Amz-Expires=70527"
    "&X-Amz-Signature=48fa1322a6514259e7fcbe80f3fc99b4d9a8b6e54f0dd749d296c6c947232a22"
    "&X-Amz-SignedHeaders=host%3Bx-amz-expected-bucket-owner"
    "&response-expires=Thu%2C%2023%20Jul%202026%2015%3A59%3A41%20GMT"
)

OUTPUT_PATH = r"D:\keyword\thumbnail_인천창고형약국_v2.png"

# Windows NanumGothic 또는 Noto 폰트 경로 시도
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\NanumGothicBold.ttf",
    r"C:\Windows\Fonts\malgunbd.ttf",    # 맑은 고딕 Bold
    r"C:\Windows\Fonts\gulim.ttc",
]

# ── 텍스트 정의 (세그먼트별 색상) ────────────────────────────────
# 각 줄: [(텍스트, 색상), ...]
LINES = [
    [("이 약국", (255, 255, 255))],
    [("30%", (255, 230, 0)), (" 싸다고?", (255, 255, 255))],
    [("직접", (255, 60, 60)),  (" 갔다!", (255, 255, 255))],
]

W, H = 1280, 720
FONT_SIZES = [160, 130, 120]   # 줄별 폰트 크기
OUTLINE_W  = 8                 # 외곽선 두께
LINE_GAP   = 30                # 줄 간격

# ── 폰트 로드 ─────────────────────────────────────────────────────
def load_font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    print("⚠️  한글 폰트를 찾지 못했습니다. 기본 폰트 사용.")
    return ImageFont.load_default()

# ── 외곽선 텍스트 그리기 ──────────────────────────────────────────
def draw_outlined_text(draw, x, y, text, font, fill, outline=(0,0,0), thickness=OUTLINE_W):
    for dx in range(-thickness, thickness+1):
        for dy in range(-thickness, thickness+1):
            if dx*dx + dy*dy <= thickness*thickness:
                draw.text((x+dx, y+dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)

# ── 메인 ─────────────────────────────────────────────────────────
def main():
    # 1. 배경 이미지 다운로드
    print("배경 다운로드 중...")
    try:
        req = urllib.request.Request(CANVA_IMAGE_URL,
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            bg = Image.open(BytesIO(resp.read())).convert("RGB")
        bg = bg.resize((W, H), Image.LANCZOS)
        print(f"  배경 크기: {bg.size}")
    except Exception as e:
        print(f"  다운로드 실패: {e}")
        print("  → 노란 배경으로 대체합니다.")
        bg = Image.new("RGB", (W, H), (255, 215, 0))

    # 2. 반투명 어두운 오버레이 (텍스트 가독성↑)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 110))
    bg_rgba = bg.convert("RGBA")
    bg_rgba = Image.alpha_composite(bg_rgba, overlay)
    img = bg_rgba.convert("RGB")
    draw = ImageDraw.Draw(img)

    # 3. 텍스트 세로 전체 높이 계산
    fonts = [load_font(sz) for sz in FONT_SIZES]
    line_heights = []
    for i, line in enumerate(LINES):
        font = fonts[i]
        h_max = 0
        for seg, _ in line:
            bb = draw.textbbox((0, 0), seg, font=font)
            h_max = max(h_max, bb[3] - bb[1])
        line_heights.append(h_max)

    total_h = sum(line_heights) + LINE_GAP * (len(LINES) - 1)
    start_y = (H - total_h) // 2   # 수직 중앙

    # 4. 각 줄 가로 너비 계산 → 수평 중앙
    cur_y = start_y
    for i, line in enumerate(LINES):
        font = fonts[i]
        total_w = 0
        seg_widths = []
        for seg, _ in line:
            bb = draw.textbbox((0, 0), seg, font=font)
            sw = bb[2] - bb[0]
            seg_widths.append(sw)
            total_w += sw

        cur_x = (W - total_w) // 2   # 수평 중앙
        for j, (seg, color) in enumerate(line):
            draw_outlined_text(draw, cur_x, cur_y, seg, font, color)
            cur_x += seg_widths[j]

        cur_y += line_heights[i] + LINE_GAP

    # 5. 저장
    img.save(OUTPUT_PATH, "PNG")
    print(f"\n✅ 저장 완료: {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
