"""
블로그 썸네일 자동 생성기 (ComfyUI FLUX + Pillow)
- ComfyUI FLUX.1-schnell로 배경 이미지 생성
- Pillow로 한글 텍스트 합성
- JPEG 저장

사용법: python make_thumbnail_comfy.py
"""

import json
import time
import uuid
import os
import sys
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# ── 설정 ──────────────────────────────────────────────────────────────
COMFYUI_URL = "http://127.0.0.1:8188"
OUTPUT_PATH  = r"D:\keyword\thumbnail_output.jpg"
JPEG_QUALITY = 92
IMG_W, IMG_H = 1280, 720

# ── 썸네일 텍스트 (줄별 세그먼트 + 색상) ──────────────────────────────
# 수정 포인트: LINES와 IMAGE_PROMPT만 바꾸면 다른 글 썸네일도 생성 가능
LINES = [
    [("이 약국", (255, 255, 255))],
    [("30%", (255, 230, 0)), (" 싸다고?", (255, 255, 255))],
    [("직접", (255, 60, 60)),  (" 갔다!", (255, 255, 255))],
]

# FLUX 이미지 생성 프롬프트 (배경만, 텍스트·사람 없이)
IMAGE_PROMPT = (
    "A bright modern Korean pharmacy interior, colorful medicine shelves, "
    "clean organized display of health products, warm lighting, "
    "wide angle perspective, no text, no people, no signs"
)

# ── 폰트 설정 ─────────────────────────────────────────────────────────
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\NanumGothicBold.ttf",
    r"C:\Windows\Fonts\NanumGothicExtraBold.ttf",
    r"C:\Windows\Fonts\malgunbd.ttf",   # 맑은 고딕 Bold
    r"C:\Windows\Fonts\gulim.ttc",
]
FONT_SIZES  = [170, 140, 130]  # 줄별 크기
OUTLINE_W   = 9
LINE_GAP    = 25

# ── FLUX ComfyUI 워크플로우 ────────────────────────────────────────────
def build_flux_workflow(prompt: str, seed: int = -1) -> dict:
    if seed < 0:
        import random
        seed = random.randint(0, 2**31)

    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "flux1-schnell.safetensors",
                "weight_dtype": "default"
            }
        },
        "2": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": "t5xxl_fp16.safetensors",
                "clip_name2": "clip_l.safetensors",
                "type": "flux"
            }
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": "ae.safetensors"
            }
        },
        "4": {
            "class_type": "CLIPTextEncodeFlux",
            "inputs": {
                "clip": ["2", 0],
                "clip_l": prompt,
                "t5xxl": prompt,
                "guidance": 3.5
            }
        },
        "5": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {
                "width": IMG_W,
                "height": IMG_H,
                "batch_size": 1
            }
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model":        ["1", 0],
                "positive":     ["4", 0],
                "negative":     ["7", 0],
                "latent_image": ["5", 0],
                "seed":         seed,
                "steps":        4,
                "cfg":          1.0,
                "sampler_name": "euler",
                "scheduler":    "simple",
                "denoise":      1.0
            }
        },
        "7": {
            "class_type": "CLIPTextEncodeFlux",
            "inputs": {
                "clip":    ["2", 0],
                "clip_l":  "",
                "t5xxl":   "text, watermark, signature, people, person, face",
                "guidance": 3.5
            }
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["6", 0],
                "vae":     ["3", 0]
            }
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "images":          ["8", 0],
                "filename_prefix": "thumb_bg"
            }
        }
    }

# ── ComfyUI API 호출 ──────────────────────────────────────────────────
def generate_image(prompt: str) -> Image.Image:
    workflow = build_flux_workflow(prompt)
    client_id = str(uuid.uuid4())

    print("▶ ComfyUI에 이미지 생성 요청...")
    resp = requests.post(
        f"{COMFYUI_URL}/prompt",
        json={"prompt": workflow, "client_id": client_id},
        timeout=30
    )
    resp.raise_for_status()
    prompt_id = resp.json()["prompt_id"]
    print(f"  prompt_id: {prompt_id}")

    # 완료 대기 (최대 5분)
    for i in range(300):
        time.sleep(1)
        hist = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10).json()
        if prompt_id in hist:
            outputs = hist[prompt_id].get("outputs", {})
            for node_id, node_out in outputs.items():
                if "images" in node_out:
                    img_info = node_out["images"][0]
                    filename  = img_info["filename"]
                    subfolder = img_info.get("subfolder", "")
                    img_type  = img_info.get("type", "output")
                    print(f"  생성 완료: {filename}")

                    # 이미지 다운로드
                    params = {"filename": filename, "type": img_type}
                    if subfolder:
                        params["subfolder"] = subfolder
                    r = requests.get(f"{COMFYUI_URL}/view", params=params, timeout=30)
                    r.raise_for_status()
                    return Image.open(BytesIO(r.content)).convert("RGB")
        if (i + 1) % 10 == 0:
            print(f"  대기 중... {i+1}초")

    raise TimeoutError("이미지 생성 시간 초과 (5분)")

# ── 폰트 로드 ─────────────────────────────────────────────────────────
def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    print("⚠ 한글 폰트 없음 - 기본 폰트 사용")
    return ImageFont.load_default()

# ── 외곽선 텍스트 ─────────────────────────────────────────────────────
def draw_outlined_text(draw, x, y, text, font, fill, outline=(0, 0, 0), thickness=OUTLINE_W):
    for dx in range(-thickness, thickness + 1):
        for dy in range(-thickness, thickness + 1):
            if dx * dx + dy * dy <= thickness * thickness:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)

# ── 텍스트 합성 ───────────────────────────────────────────────────────
def composite_text(bg: Image.Image) -> Image.Image:
    # 배경을 정확한 크기로
    img = bg.resize((IMG_W, IMG_H), Image.LANCZOS)

    # 반투명 어두운 오버레이 (텍스트 가독성)
    overlay = Image.new("RGBA", (IMG_W, IMG_H), (0, 0, 0, 100))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # 폰트 & 줄 높이 계산
    fonts = [load_font(sz) for sz in FONT_SIZES]
    line_heights = []
    for i, line in enumerate(LINES):
        h_max = 0
        for seg, _ in line:
            bb = draw.textbbox((0, 0), seg, font=fonts[i])
            h_max = max(h_max, bb[3] - bb[1])
        line_heights.append(h_max)

    total_h = sum(line_heights) + LINE_GAP * (len(LINES) - 1)
    cur_y   = (IMG_H - total_h) // 2

    for i, line in enumerate(LINES):
        font = fonts[i]
        seg_widths = []
        total_w = 0
        for seg, _ in line:
            bb = draw.textbbox((0, 0), seg, font=font)
            sw = bb[2] - bb[0]
            seg_widths.append(sw)
            total_w += sw

        cur_x = (IMG_W - total_w) // 2
        for j, (seg, color) in enumerate(line):
            draw_outlined_text(draw, cur_x, cur_y, seg, font, color)
            cur_x += seg_widths[j]

        cur_y += line_heights[i] + LINE_GAP

    return img

# ── 메인 ─────────────────────────────────────────────────────────────
def main():
    # ComfyUI 연결 확인
    try:
        r = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        r.raise_for_status()
        print("✅ ComfyUI 연결 확인")
    except Exception as e:
        print(f"❌ ComfyUI 연결 실패: {e}")
        print("   ComfyUI를 먼저 실행해주세요 (http://127.0.0.1:8188)")
        sys.exit(1)

    # 1. FLUX로 배경 생성
    bg_image = generate_image(IMAGE_PROMPT)

    # 2. 텍스트 합성
    print("▶ 텍스트 합성 중...")
    final = composite_text(bg_image)

    # 3. JPEG 저장
    final.save(OUTPUT_PATH, "JPEG", quality=JPEG_QUALITY)
    print(f"\n✅ 완료: {OUTPUT_PATH}")
    print(f"   크기: {final.size}, 용량: {os.path.getsize(OUTPUT_PATH) // 1024}KB")

if __name__ == "__main__":
    main()
