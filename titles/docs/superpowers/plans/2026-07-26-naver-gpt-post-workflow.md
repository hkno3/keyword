# Naver GPT Post Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Process `호카 본디9 와이드.txt` through three web GPTs and save a verified article, one thumbnail, and all requested body images as WebP files.

**Architecture:** A small Python helper owns deterministic local work: title parsing, image-directive parsing, output paths, WebP conversion, and final verification. The browser worker owns only ChatGPT UI interactions and downloads; it passes the selected title and article text between the three GPTs. The source TXT moves to `n완료` only after the helper verifies every required output.

**Tech Stack:** Python 3.14, Pillow 12.1.1, pytest, logged-in ChatGPT web UI, Codex in-app browser control.

## Global Constraints

- Test only `D:\keyword\titles\호카 본디9 와이드.txt`.
- Select the title referenced by `🥈 2등 추천: N번`.
- Send the selected title to the article GPT.
- Send both the selected title and completed article to the thumbnail GPT.
- Send each three-line image directive block to the body-image GPT without modification or summarization.
- Save all generated images as genuine WebP files.
- Save results under `D:\keyword\titles\네이버 포스팅\호카 본디9 와이드\`.
- Move the source TXT to `D:\keyword\titles\n완료\` only after every verification succeeds.
- Do not publish anything to Naver Blog.

---

### Task 1: Parse the ranked title

**Files:**
- Create: `workflow/naver_post_workflow.py`
- Create: `tests/test_naver_post_workflow.py`

**Interfaces:**
- Consumes: UTF-8 TXT content containing numbered titles and a `🥈 2등 추천` line.
- Produces: `extract_second_ranked_title(text: str) -> str`.

- [ ] **Step 1: Write the failing title-parser tests**

```python
from pathlib import Path

import pytest

from workflow.naver_post_workflow import extract_second_ranked_title


def test_extracts_title_referenced_by_second_rank():
    text = """📝 블로그 제목
1. 첫 번째 제목
2. 두 번째 제목
5. 호카 본디9 와이드 신기 전 이것 모르면 5만원 손해
🏆 추천 순위
🥈 2등 추천: 5번 / 추천 이유: 클릭충동 최고
"""
    assert extract_second_ranked_title(text) == (
        "호카 본디9 와이드 신기 전 이것 모르면 5만원 손해"
    )


def test_rejects_missing_second_rank():
    with pytest.raises(ValueError, match="2등 추천"):
        extract_second_ranked_title("1. 제목만 있음")
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `python -m pytest tests/test_naver_post_workflow.py -v`

Expected: FAIL because `workflow.naver_post_workflow` does not exist.

- [ ] **Step 3: Implement the minimal title parser**

```python
import re


def extract_second_ranked_title(text: str) -> str:
    rank = re.search(r"🥈\s*2등 추천:\s*(\d+)번", text)
    if not rank:
        raise ValueError("2등 추천 번호를 찾을 수 없습니다.")
    number = rank.group(1)
    title = re.search(rf"(?m)^\s*{re.escape(number)}\.\s+(.+?)\s*$", text)
    if not title:
        raise ValueError(f"{number}번 제목을 찾을 수 없습니다.")
    return title.group(1).strip()
```

- [ ] **Step 4: Run the title-parser tests**

Run: `python -m pytest tests/test_naver_post_workflow.py -v`

Expected: 2 tests PASS.

- [ ] **Step 5: Verify the real test file**

Run:

```powershell
python -c "from pathlib import Path; from workflow.naver_post_workflow import extract_second_ranked_title; print(extract_second_ranked_title(Path('호카 본디9 와이드.txt').read_text(encoding='utf-8-sig')))"
```

Expected: `호카 본디9 와이드 신기 전 이것 모르면 5만원 손해`

- [ ] **Step 6: Commit**

```powershell
git add titles/workflow/naver_post_workflow.py titles/tests/test_naver_post_workflow.py
git commit -m "feat: parse second-ranked blog title"
```

### Task 2: Parse body-image directive blocks

**Files:**
- Modify: `workflow/naver_post_workflow.py`
- Modify: `tests/test_naver_post_workflow.py`

**Interfaces:**
- Consumes: Completed article text.
- Produces: `extract_image_directives(article: str) -> list[str]`, preserving each three-line block exactly.

- [ ] **Step 1: Add failing directive-parser tests**

```python
from workflow.naver_post_workflow import extract_image_directives


def test_extracts_image_directives_verbatim_and_in_order():
    first = (
        "[이미지 추천: 첫 번째 장면]\n"
        "[이미지 삽입 문구: 첫 번째 문구]\n"
        "[이미지 Alt text: 첫 번째 대체 문구]"
    )
    second = (
        "[이미지 추천: 두 번째 장면]\n"
        "[이미지 삽입 문구: 두 번째 문구]\n"
        "[이미지 Alt text: 두 번째 대체 문구]"
    )
    article = f"도입부\n{first}\n설명\n{second}\n마무리"
    assert extract_image_directives(article) == [first, second]


def test_rejects_partial_directive_block():
    article = "[이미지 추천: 장면]\n[이미지 삽입 문구: 문구]"
    with pytest.raises(ValueError, match="완전하지 않은"):
        extract_image_directives(article)
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run: `python -m pytest tests/test_naver_post_workflow.py -v`

Expected: FAIL because `extract_image_directives` is undefined.

- [ ] **Step 3: Implement exact three-line extraction**

```python
IMAGE_BLOCK = re.compile(
    r"(?m)^(\[이미지 추천:[^\r\n]*\]\r?\n"
    r"\[이미지 삽입 문구:[^\r\n]*\]\r?\n"
    r"\[이미지 Alt text:[^\r\n]*\])$"
)


def extract_image_directives(article: str) -> list[str]:
    image_line_count = len(re.findall(r"(?m)^\[이미지 (?:추천|삽입 문구|Alt text):", article))
    blocks = [match.group(1).replace("\r\n", "\n") for match in IMAGE_BLOCK.finditer(article)]
    if image_line_count != len(blocks) * 3:
        raise ValueError("완전하지 않은 본문 이미지 지시 묶음이 있습니다.")
    return blocks
```

- [ ] **Step 4: Run all parser tests**

Run: `python -m pytest tests/test_naver_post_workflow.py -v`

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add titles/workflow/naver_post_workflow.py titles/tests/test_naver_post_workflow.py
git commit -m "feat: parse body image directives"
```

### Task 3: Convert and verify generated images

**Files:**
- Modify: `workflow/naver_post_workflow.py`
- Modify: `tests/test_naver_post_workflow.py`

**Interfaces:**
- Consumes: Downloaded PNG, JPEG, or WebP paths.
- Produces: `convert_to_webp(source: Path, destination: Path) -> Path`.
- Produces: `verify_webp(path: Path) -> None`.

- [ ] **Step 1: Add failing WebP tests**

```python
from PIL import Image

from workflow.naver_post_workflow import convert_to_webp, verify_webp


def test_converts_png_to_real_webp(tmp_path):
    source = tmp_path / "source.png"
    destination = tmp_path / "output.webp"
    Image.new("RGB", (32, 24), "red").save(source)
    assert convert_to_webp(source, destination) == destination
    verify_webp(destination)
    with Image.open(destination) as image:
        assert image.format == "WEBP"
        assert image.size == (32, 24)


def test_verify_webp_rejects_renamed_png(tmp_path):
    fake = tmp_path / "fake.webp"
    Image.new("RGB", (8, 8), "blue").save(fake, format="PNG")
    with pytest.raises(ValueError, match="WebP"):
        verify_webp(fake)
```

- [ ] **Step 2: Run the WebP tests and verify they fail**

Run: `python -m pytest tests/test_naver_post_workflow.py -v`

Expected: FAIL because the WebP functions are undefined.

- [ ] **Step 3: Implement conversion and format verification**

```python
from pathlib import Path

from PIL import Image


def convert_to_webp(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        converted = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        converted.save(destination, format="WEBP", quality=92, method=6)
    verify_webp(destination)
    return destination


def verify_webp(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"이미지 파일이 없습니다: {path}")
    with Image.open(path) as image:
        if image.format != "WEBP":
            raise ValueError(f"실제 WebP 형식이 아닙니다: {path}")
        image.verify()
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/test_naver_post_workflow.py -v`

Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add titles/workflow/naver_post_workflow.py titles/tests/test_naver_post_workflow.py
git commit -m "feat: convert generated images to webp"
```

### Task 4: Add output verification and safe completion

**Files:**
- Modify: `workflow/naver_post_workflow.py`
- Modify: `tests/test_naver_post_workflow.py`

**Interfaces:**
- Consumes: Source path, result directory, article text, and expected body-image count.
- Produces: `verify_outputs(result_dir: Path, stem: str, article: str, body_count: int) -> None`.
- Produces: `complete_source(source: Path, completed_dir: Path) -> Path`.

- [ ] **Step 1: Add failing completion tests**

```python
from workflow.naver_post_workflow import complete_source, verify_outputs


def test_verifies_complete_result_and_moves_source(tmp_path):
    result = tmp_path / "네이버 포스팅" / "키워드"
    result.mkdir(parents=True)
    article = (
        "본문\n[이미지 추천: 장면]\n[이미지 삽입 문구: 문구]\n"
        "[이미지 Alt text: 대체 문구]"
    )
    (result / "본문.txt").write_text(article, encoding="utf-8")
    for name in ("키워드 thumbnail.webp", "body-01.webp"):
        Image.new("RGB", (8, 8), "green").save(result / name, format="WEBP")
    verify_outputs(result, "키워드", article, body_count=1)

    source = tmp_path / "키워드.txt"
    source.write_text("원본", encoding="utf-8")
    moved = complete_source(source, tmp_path / "n완료")
    assert moved == tmp_path / "n완료" / "키워드.txt"
    assert moved.exists()
    assert not source.exists()


def test_does_not_move_when_body_image_is_missing(tmp_path):
    result = tmp_path / "결과"
    result.mkdir()
    (result / "본문.txt").write_text("본문", encoding="utf-8")
    Image.new("RGB", (8, 8), "green").save(
        result / "키워드 thumbnail.webp", format="WEBP"
    )
    with pytest.raises(ValueError, match="body-01"):
        verify_outputs(result, "키워드", "본문", body_count=1)
```

- [ ] **Step 2: Run the completion tests and verify they fail**

Run: `python -m pytest tests/test_naver_post_workflow.py -v`

Expected: FAIL because completion functions are undefined.

- [ ] **Step 3: Implement strict output verification and collision-safe move**

```python
import shutil


def verify_outputs(
    result_dir: Path, stem: str, article: str, body_count: int
) -> None:
    article_path = result_dir / "본문.txt"
    if not article.strip() or not article_path.is_file():
        raise ValueError("본문.txt가 없거나 비어 있습니다.")
    if article_path.read_text(encoding="utf-8") != article:
        raise ValueError("저장된 본문이 생성된 본문과 다릅니다.")
    verify_webp(result_dir / f"{stem} thumbnail.webp")
    for index in range(1, body_count + 1):
        path = result_dir / f"body-{index:02d}.webp"
        if not path.is_file():
            raise ValueError(f"{path.name} 파일이 없습니다.")
        verify_webp(path)


def complete_source(source: Path, completed_dir: Path) -> Path:
    completed_dir.mkdir(parents=True, exist_ok=True)
    destination = completed_dir / source.name
    if destination.exists():
        raise FileExistsError(f"완료 폴더에 같은 파일이 있습니다: {destination}")
    return Path(shutil.move(str(source), str(destination)))
```

- [ ] **Step 4: Run the complete test suite**

Run: `python -m pytest tests/test_naver_post_workflow.py -v`

Expected: 8 tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add titles/workflow/naver_post_workflow.py titles/tests/test_naver_post_workflow.py
git commit -m "feat: verify outputs before completing source"
```

### Task 5: Execute the one-file browser test

**Files:**
- Create: `네이버 포스팅/호카 본디9 와이드/본문.txt`
- Create: `네이버 포스팅/호카 본디9 와이드/호카 본디9 와이드 thumbnail.webp`
- Create: `네이버 포스팅/호카 본디9 와이드/body-01.webp` and subsequent numbered images
- Move after verification: `호카 본디9 와이드.txt` to `n완료/호카 본디9 와이드.txt`

**Interfaces:**
- Consumes: Parser and verification functions from Tasks 1–4 plus the three GPT URLs.
- Produces: The complete verified local post package.

- [ ] **Step 1: Extract and record the selected title**

Run:

```powershell
python -c "from pathlib import Path; from workflow.naver_post_workflow import extract_second_ranked_title; print(extract_second_ranked_title(Path('호카 본디9 와이드.txt').read_text(encoding='utf-8-sig')))"
```

Expected: `호카 본디9 와이드 신기 전 이것 모르면 5만원 손해`

- [ ] **Step 2: Generate the article in the article GPT**

Open the article GPT URL, start a new chat, enter the exact selected title, submit once, and wait until generation finishes. Copy the complete response without editing it.

- [ ] **Step 3: Save the article**

Create `네이버 포스팅/호카 본디9 와이드/본문.txt` as UTF-8 and store the complete article response.

- [ ] **Step 4: Extract the body-image directive blocks**

Run the helper against `본문.txt` and record the returned block count. Confirm every returned string contains the exact three original lines and that their order matches the article.

- [ ] **Step 5: Generate and save the thumbnail**

Open the thumbnail GPT URL in a new chat. Submit the exact selected title followed by the complete article text. Download the single generated image, convert it with `convert_to_webp`, and save it as `호카 본디9 와이드 thumbnail.webp`.

- [ ] **Step 6: Generate and save each body image**

For each directive returned in Step 4, start a new body-image GPT chat, submit the three-line block unchanged, download the generated image, convert it with `convert_to_webp`, and save it as `body-01.webp`, `body-02.webp`, and so on in article order.

- [ ] **Step 7: Verify all outputs**

Call `verify_outputs` with the saved article and the directive count. Open the resulting WebP files with Pillow to confirm they decode successfully.

- [ ] **Step 8: Move the source only after successful verification**

Call `complete_source(Path("호카 본디9 와이드.txt"), Path("n완료"))`.

- [ ] **Step 9: Report the test result**

Report the selected title, article path, thumbnail path, body-image count, and final source path. If any step fails, preserve the source in place and report the failed stage.

