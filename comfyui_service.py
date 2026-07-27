"""
ComfyUI API 연동 서비스
- 키워드 기반 블로그 썸네일 자동 생성
- 한글 텍스트 오버레이
- WebP 변환
- WordPress 대표이미지 업로드
"""
import json
import time
import random
import io
import os
import requests
from requests.auth import HTTPBasicAuth

COMFYUI_URL = "http://127.0.0.1:8188"

# ★ 다운받은 파일명으로 변경 (예: juggernautXL_v9Rdphoto2Lightning.safetensors)
CHECKPOINT_NAME = "juggernautXL_ragnarok.safetensors"

# 네거티브 프롬프트 (SDXL에서 핵심)
NEGATIVE_PROMPT = (
    "text, watermark, signature, logo, words, letters, writing, label, "
    "title, caption, font, typography, korean text, japanese text, chinese text, "
    "people, person, human, face, crowd, "
    "blurry, low quality, ugly, bad anatomy, deformed, pixelated, oversaturated"
)

# 워크플로 템플릿 (Juggernaut XL / SDXL 기반)
WORKFLOW_TEMPLATE = {
    "4": {
        "inputs": {"ckpt_name": CHECKPOINT_NAME},
        "class_type": "CheckpointLoaderSimple",
        "_meta": {"title": "Load Checkpoint"}
    },
    "6": {
        "inputs": {
            "text": "",   # 포지티브 프롬프트 삽입 위치
            "clip": ["4", 1]
        },
        "class_type": "CLIPTextEncode",
        "_meta": {"title": "Positive Prompt"}
    },
    "7": {
        "inputs": {
            "text": NEGATIVE_PROMPT,
            "clip": ["4", 1]
        },
        "class_type": "CLIPTextEncode",
        "_meta": {"title": "Negative Prompt"}
    },
    "3": {
        "inputs": {
            "seed": 42,
            "steps": 30,
            "cfg": 7.0,
            "sampler_name": "dpmpp_2m",
            "scheduler": "karras",
            "denoise": 1.0,
            "model":         ["4", 0],
            "positive":      ["6", 0],
            "negative":      ["7", 0],
            "latent_image":  ["5", 0]
        },
        "class_type": "KSampler",
        "_meta": {"title": "KSampler"}
    },
    "5": {
        "inputs": {
            "width": 1280,
            "height": 720,
            "batch_size": 1
        },
        "class_type": "EmptyLatentImage",
        "_meta": {"title": "Empty Latent Image"}
    },
    "8": {
        "inputs": {
            "samples": ["3", 0],
            "vae":     ["4", 2]
        },
        "class_type": "VAEDecode",
        "_meta": {"title": "VAE Decode"}
    },
    "9": {
        "inputs": {
            "filename_prefix": "blog_thumb",
            "images": ["8", 0]
        },
        "class_type": "SaveImage",
        "_meta": {"title": "Save Image"}
    }
}


NO_TEXT_SUFFIX = (
    ", no text, no letters, no words, no watermark, no signs, no labels, "
    "no people, no faces, clean background only, high quality, 16:9 aspect ratio"
)


def _keyword_to_prompt(keyword: str) -> str:
    """키워드를 영문 이미지 프롬프트로 변환"""
    # 주제별 프롬프트 매핑
    mapping = {
        "카드": "credit cards arranged on clean white surface, modern minimal design, blue and gold tones",
        "은행": "modern financial building exterior, glass and steel architecture, professional clean style",
        "금융": "abstract financial concept, golden coins and graphs floating, dark blue gradient background",
        "대출": "house and coins balance scale, financial planning concept, warm professional tones",
        "보험": "protective shield glowing around house and family silhouette, warm blue tones",
        "세금": "stack of documents and calculator on clean desk, professional minimal design",
        "절세": "piggy bank with golden coins, green plants growing from coins, bright optimistic tones",
        "복지": "warm glowing hands cupping small house, caring social support concept",
        "건강": "fresh colorful vegetables and fruits arranged beautifully, bright vibrant lifestyle",
        "식품": "fresh organic ingredients on wooden table, colorful natural food styling",
        "뷰티": "elegant skincare products on marble surface, soft pastel tones, minimal design",
        "여행": "scenic landscape with mountains and blue sky, adventurous travel concept",
        "부동산": "modern residential house with garden, bright sunny day, clean architecture",
        "창업": "abstract business growth arrows on gradient background, modern entrepreneurship",
        "약국": "clean modern pharmacy interior with organized medicine shelves, bright lighting",
        "병원": "clean modern hospital corridor, bright professional medical environment",
        "운동": "gym equipment and weights arranged neatly, energetic fitness concept",
        "다이어트": "healthy meal prep bowls with colorful vegetables, clean nutrition concept",
    }

    for kw, prompt in mapping.items():
        if kw in keyword:
            return prompt + NO_TEXT_SUFFIX

    # 기본 프롬프트 (키워드 포함하지 않음 - FLUX가 한글 텍스트 생성 방지)
    return (
        "abstract modern background with soft gradient colors, "
        "professional clean design, bokeh effect, studio lighting"
        + NO_TEXT_SUFFIX
    )


def generate_image(keyword: str, image_prompt: str = None, timeout: int = 120) -> bytes | None:
    """
    ComfyUI API로 이미지 생성 후 PNG bytes 반환.
    ComfyUI가 꺼져있으면 None 반환.
    """
    # ComfyUI 연결 확인
    try:
        r = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        if not r.ok:
            print("  ⚠️  ComfyUI 연결 실패 (이미지 생성 건너뜀)")
            return None
    except Exception:
        print("  ⚠️  ComfyUI 오프라인 (이미지 생성 건너뜀)")
        return None

    # 워크플로 복사 및 설정
    workflow = json.loads(json.dumps(WORKFLOW_TEMPLATE))
    if image_prompt:
        # 사용자 제공 프롬프트도 no-text suffix 강제 추가
        prompt_text = image_prompt + NO_TEXT_SUFFIX
    else:
        prompt_text = _keyword_to_prompt(keyword)
    workflow["6"]["inputs"]["text"] = prompt_text
    workflow["3"]["inputs"]["seed"] = random.randint(1, 999999999)
    workflow["9"]["inputs"]["filename_prefix"] = f"blog_{keyword[:20]}"

    # 큐에 추가
    payload = {"prompt": workflow}
    r = requests.post(f"{COMFYUI_URL}/prompt", json=payload, timeout=10)
    if not r.ok:
        print(f"  ❌ ComfyUI 큐 추가 실패: {r.status_code}")
        return None

    prompt_id = r.json()["prompt_id"]
    print(f"  🎨 이미지 생성 중... (prompt_id: {prompt_id[:8]}...)")

    # 완료 대기
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(2)
        hist = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
        if not hist.ok:
            continue
        data = hist.json().get(prompt_id, {})
        if not data:
            continue
        outputs = data.get("outputs", {})
        # 이미지 찾기
        for node_id, node_out in outputs.items():
            images = node_out.get("images", [])
            if images:
                img_info = images[0]
                img_url = (
                    f"{COMFYUI_URL}/view"
                    f"?filename={img_info['filename']}"
                    f"&subfolder={img_info.get('subfolder', '')}"
                    f"&type={img_info.get('type', 'output')}"
                )
                img_r = requests.get(img_url, timeout=30)
                if img_r.ok:
                    elapsed = time.time() - start
                    print(f"  ✅ 이미지 생성 완료 ({elapsed:.1f}초)")
                    return img_r.content

        status = data.get("status", {})
        if status.get("status_str") == "error":
            print("  ❌ ComfyUI 생성 오류")
            return None

    print(f"  ⏱️  타임아웃 ({timeout}초) — 이미지 생성 건너뜀")
    return None


def add_text_overlay(image_bytes: bytes, keyword: str, thumbnail_lines: list = None) -> bytes:
    """
    이미지에 한글 텍스트 오버레이 추가 (3줄 컬러 스타일)
    thumbnail_lines: [[[텍스트, 색상코드], ...], ...] 형식
      색상코드: "white"|(255,255,255), "yellow"|(255,230,0), "red"|(255,60,60)
    """
    COLOR_MAP = {
        "white":  (255, 255, 255),
        "yellow": (255, 230, 0),
        "red":    (255, 60, 60),
    }
    OUTLINE_W  = 9
    LINE_GAP   = 18
    FONT_SIZES = [150, 120, 110]
    SHEAR      = 0.12   # 기울기 강도 (0=없음, 0.15=약간 기울임)
    SHADOW_OFF = 6      # 드롭 섀도우 오프셋(px)

    try:
        from PIL import Image, ImageDraw, ImageFont, ImageTransform
        import io as _io

        img = Image.open(_io.BytesIO(image_bytes)).convert("RGBA")
        W, H = img.size

        # 반투명 어두운 오버레이 (가독성)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 110))
        img = Image.alpha_composite(img, overlay)

        # 폰트 경로 (Black Han Sans 우선)
        font_candidates = [
            "C:/Windows/Fonts/BlackHanSans-Regular.ttf",
            "C:/Windows/Fonts/NanumGothicExtraBold.ttf",
            "C:/Windows/Fonts/NanumGothicBold.ttf",
            "C:/Windows/Fonts/malgunbd.ttf",
            "C:/Windows/Fonts/gulim.ttc",
        ]

        def load_font(size):
            for fp in font_candidates:
                if os.path.exists(fp):
                    try:
                        return ImageFont.truetype(fp, size)
                    except Exception:
                        continue
            return ImageFont.load_default()

        def render_text_layer(text, font, fill, W, H, x, y):
            """텍스트를 투명 레이어에 그린 뒤 shear 변환 적용해 반환"""
            # 여유 공간을 충분히 줘서 기울어도 잘리지 않도록
            pad = int(H * SHEAR) + 60
            layer = Image.new("RGBA", (W + pad * 2, H + pad * 2), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)

            lx = x + pad
            ly = y + pad

            # 1) 드롭 섀도우 (반투명 검정)
            shadow_color = (0, 0, 0, 180)
            for dx in range(-OUTLINE_W, OUTLINE_W + 1):
                for dy in range(-OUTLINE_W, OUTLINE_W + 1):
                    if dx*dx + dy*dy <= OUTLINE_W*OUTLINE_W:
                        d.text((lx+dx, ly+dy), text, font=font, fill=(0, 0, 0, 255))
            d.text((lx + SHADOW_OFF, ly + SHADOW_OFF), text, font=font, fill=shadow_color)

            # 2) 본문 텍스트
            d.text((lx, ly), text, font=font, fill=fill + (255,) if len(fill) == 3 else fill)

            # 3) Shear(기울기) 변환
            # affine transform: (a,b,c,d,e,f) → x'=ax+by+c, y'=dx+ey+f
            # shear x축: x' = x + shear*y
            shear_matrix = (1, SHEAR, -SHEAR * ly, 0, 1, 0)
            layer = layer.transform(
                layer.size,
                Image.AFFINE,
                shear_matrix,
                resample=Image.BICUBIC
            )

            # 원래 크기로 크롭
            layer = layer.crop((pad, pad, pad + W, pad + H))
            return layer

        # thumbnail_lines 없으면 제목에서 자동 생성
        if not thumbnail_lines:
            thumbnail_lines = _auto_split_title(keyword)

        fonts = [load_font(sz) for sz in FONT_SIZES[:len(thumbnail_lines)]]

        # 줄 높이 계산 (더미 draw 사용)
        dummy = ImageDraw.Draw(img)
        line_heights = []
        for i, line in enumerate(thumbnail_lines):
            font = fonts[i] if i < len(fonts) else fonts[-1]
            h_max = 0
            for seg in line:
                bb = dummy.textbbox((0, 0), seg[0], font=font)
                h_max = max(h_max, bb[3] - bb[1])
            line_heights.append(h_max)

        total_h = sum(line_heights) + LINE_GAP * (len(thumbnail_lines) - 1)
        cur_y = (H - total_h) // 2

        for i, line in enumerate(thumbnail_lines):
            font = fonts[i] if i < len(fonts) else fonts[-1]
            seg_widths = []
            total_w = 0
            for seg in line:
                bb = dummy.textbbox((0, 0), seg[0], font=font)
                sw = bb[2] - bb[0]
                seg_widths.append(sw)
                total_w += sw

            cur_x = (W - total_w) // 2
            for j, seg in enumerate(line):
                text = seg[0]
                color_key = seg[1] if len(seg) > 1 else "white"
                color = COLOR_MAP.get(color_key, (255, 255, 255)) if isinstance(color_key, str) else tuple(color_key)
                text_layer = render_text_layer(text, font, color, W, H, cur_x, cur_y)
                img = Image.alpha_composite(img, text_layer)
                cur_x += seg_widths[j]

            cur_y += line_heights[i] + LINE_GAP

        out = _io.BytesIO()
        img.convert("RGB").save(out, format="PNG")
        return out.getvalue()

    except ImportError:
        print("  ⚠️  Pillow 미설치 — 텍스트 오버레이 건너뜀")
        return image_bytes
    except Exception as e:
        print(f"  ⚠️  텍스트 오버레이 실패: {e}")
        return image_bytes


def _auto_split_title(title: str) -> list:
    """
    블로그 제목을 3줄로 자동 분할, 숫자→yellow / 첫 동작어→red
    반환: [[[텍스트, 색상], ...], ...]
    """
    import re
    words = title.split()
    # 약 3등분
    n = len(words)
    s1 = n // 3
    s2 = n // 3 * 2
    groups = [
        " ".join(words[:s1]),
        " ".join(words[s1:s2]),
        " ".join(words[s2:]),
    ]
    groups = [g for g in groups if g]

    action_words = ["직접", "확인", "후기", "방법", "정리", "총정리", "가이드", "알아보기"]
    result = []
    action_used = False
    for g in groups:
        # 숫자 포함 여부 확인
        has_num = bool(re.search(r'\d', g))
        # 동작어 포함 여부
        has_action = any(w in g for w in action_words) and not action_used

        if has_num:
            # 숫자 부분 yellow, 나머지 white
            parts = re.split(r'(\d[\d,%.]+)', g)
            segs = []
            for p in parts:
                if p:
                    color = "yellow" if re.match(r'\d[\d,%.]*', p) else "white"
                    segs.append([p, color])
            result.append(segs)
        elif has_action:
            # 첫 동작어 red
            for w in action_words:
                if w in g:
                    idx = g.index(w)
                    segs = []
                    if idx > 0:
                        segs.append([g[:idx], "white"])
                    segs.append([w, "red"])
                    rest = g[idx+len(w):]
                    if rest:
                        segs.append([rest, "white"])
                    result.append(segs)
                    action_used = True
                    break
        else:
            result.append([[g, "white"]])

    return result


def to_webp(image_bytes: bytes, quality: int = 85) -> bytes:
    """PNG → JPEG 변환 (WebP 차단 호스팅 대응)"""
    try:
        from PIL import Image
        import io as _io

        img = Image.open(_io.BytesIO(image_bytes)).convert("RGB")
        out = _io.BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except Exception as e:
        print(f"  ⚠️  JPEG 변환 실패: {e} — PNG 그대로 사용")
        return image_bytes


def upload_featured_image(site: dict, image_bytes: bytes, keyword: str, post_id: int, title_en: str = "", alt_text: str = "") -> bool:
    """
    WordPress에 이미지 업로드 후 대표이미지로 설정.
    반환: 성공 여부
    """
    auth = HTTPBasicAuth(site["username"], site["app_password"])
    base = site["url"].rstrip("/")

    ext = "jpg"
    mime = "image/jpeg"
    filename = f"{title_en}_thumb.jpg" if title_en else f"blog_thumb_{post_id}.jpg"

    # 미디어 업로드
    try:
        r = requests.post(
            f"{base}/wp-json/wp/v2/media",
            auth=auth,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": mime,
            },
            data=image_bytes,
            timeout=60,
        )
        if not r.ok:
            print(f"  ❌ 이미지 업로드 실패: {r.status_code} {r.text[:200]}")
            return False

        media_id = r.json().get("id")
        if not media_id:
            print("  ❌ 미디어 ID 없음")
            return False

        print(f"  🖼️  미디어 업로드 성공 (ID: {media_id})")

        # alt text 설정
        if alt_text:
            requests.post(
                f"{base}/wp-json/wp/v2/media/{media_id}",
                auth=auth,
                json={"alt_text": alt_text},
                timeout=15,
            )
            print(f"  📝 alt text 설정: {alt_text}")

        # 포스트에 대표이미지 설정
        r2 = requests.post(
            f"{base}/wp-json/wp/v2/posts/{post_id}",
            auth=auth,
            json={"featured_media": media_id},
            timeout=15,
        )
        if r2.ok:
            print(f"  ✅ 대표이미지 설정 완료")
            return True
        else:
            print(f"  ⚠️  대표이미지 설정 실패: {r2.status_code}")
            return False

    except Exception as e:
        print(f"  ❌ 이미지 처리 오류: {e}")
        return False


def generate_and_upload(site: dict, keyword: str, post_id: int,
                        title_en: str = "", image_prompt: str = None,
                        thumbnail_lines: list = None, alt_text: str = "") -> bool:
    """
    키워드 → 이미지 생성 → 텍스트 오버레이 → JPEG → WordPress 대표이미지 업로드
    전체 파이프라인. 실패해도 예외 없이 False 반환.
    ComfyUI가 꺼져있으면 건너뜀 (글 발행은 정상 진행).
    """
    try:
        img_bytes = generate_image(keyword, image_prompt=image_prompt)
        if img_bytes is None:
            return False

        img_bytes = add_text_overlay(img_bytes, keyword, thumbnail_lines=thumbnail_lines)
        img_bytes = to_webp(img_bytes)
        return upload_featured_image(site, img_bytes, keyword, post_id, title_en=title_en, alt_text=alt_text)
    except Exception as e:
        print(f"  ❌ 이미지 파이프라인 오류: {e}")
        return False
