import json
import re
from groq import Groq

MODEL = "qwen/qwen3.6-27b"


def extract_seed_keywords(article: str, client: Groq) -> tuple[list[str], int]:
    """기사에서 단일 씨드 키워드 10개 추출. (keywords, total_tokens) 반환"""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=400,
        reasoning_effort="none",
        messages=[{
            "role": "user",
            "content": f"""한국 블로그 SEO 전문가입니다.
아래 기사의 핵심 주제에 딱 맞는 단일 키워드를 추출하세요. (최대 10개, 관련 있는 것만 — 억지로 채우지 말 것)

엄격한 조건:
- 기사의 핵심 소재(사람·음식·성분·질병·장소·제품 등)와 직접 관련된 단어만
- "효율", "안정성", "유통", "경쟁력", "산업", "기업", "정책", "시장", "전략" 같은 범용 비즈니스 단어 절대 금지
- 반드시 한국어 단일 단어 (예: 유산균, 김치, 혈당, 오메가3, 치매)
- 일반인이 네이버에서 직접 검색할 법한 구체적인 단어
- 기사에서 반복 언급되거나 핵심 소재인 단어 우선

나쁜 예 (기사 주제가 김치라면): 산업, 효율, 유통, 경쟁력, 안정성
좋은 예 (기사 주제가 김치라면): 김치, 유산균, 발효, 젖산균, 배추

기사:
{article[:500]}

JSON 배열로만 반환: ["키워드1", "키워드2", ...]""",
        }],
    )
    tokens = response.usage.total_tokens if response.usage else 0
    text = response.choices[0].message.content.strip()
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group()), tokens
        except json.JSONDecodeError:
            pass
    return [], tokens


def generate_title_single(keyword: str, client: Groq, summary: str = "") -> tuple[str, int]:
    """키워드로 블로그 제목 1개 생성. (title, total_tokens) 반환"""
    context = f"\n\n## 키워드 관련 실제 정보 (반드시 이 정보 기반으로 제목 작성)\n{summary}" if summary else ""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=200,
        reasoning_effort="none",
        messages=[{
            "role": "user",
            "content": f"""당신은 네이버 블로그 SEO 전문가입니다.

키워드: "{keyword}"{context}

## 제목 생성 규칙
1. 키워드를 제목 맨 앞 15자 이내 배치 — 키워드의 띄어쓰기·글자 완전히 동일하게
2. 공백 포함 24~30자
3. 숫자 반드시 1개 이상 포함 (개수/기간/연도/금액 등) — 위 실제 정보의 수치 우선 사용
4. 특수기호 사용 금지
5. 홍보성 단어 금지 (이벤트·강추·무료·공짜·할인·1위 등)
6. 제목 마무리는 명사형 (~방법, ~총정리, ~조건, ~기준, ~이유 등)
7. 반드시 한국어(한글)로만 작성 — 일본어 절대 금지
8. 추측·날조 금지 — 위 실제 정보에 없는 수치나 사실 사용 금지

독자의 검색 의도에 맞는 제목 1개만 반환 (제목 텍스트만, 따옴표·설명 없이):""",
        }],
    )
    tokens = response.usage.total_tokens if response.usage else 0
    title = response.choices[0].message.content.strip().strip('"\'')

    def _valid(t: str) -> bool:
        return bool(t) and not _has_japanese(t) and keyword[:4] in t[:20]

    if not _valid(title):
        # 키워드가 제목 앞에 없으면 1회 재시도 (summary 없이)
        r2 = client.chat.completions.create(
            model=MODEL, max_tokens=200, reasoning_effort="none",
            messages=[{"role": "user", "content":
                f'키워드 "{keyword}"로 시작하는 한국어 블로그 제목 1개만 반환 (24~30자, 숫자 포함, 따옴표 없이):'}],
        )
        tokens += r2.usage.total_tokens if r2.usage else 0
        title = r2.choices[0].message.content.strip().strip('"\'')

    if not _valid(title):
        title = f"{keyword} 완벽 정리 3가지 핵심 방법"
    return title, tokens


def generate_titles(keyword: str, client: Groq) -> tuple[list[str], str, int]:
    """키워드로 블로그 제목 3개 생성 + 추천 1개 반환"""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=1200,
        reasoning_effort="none",
        messages=[{
            "role": "user",
            "content": f"""당신은 네이버 블로그 SEO 전문가입니다.

키워드: "{keyword}"

## 처리 단계

STEP 1. 키워드에 띄어쓰기가 없으면 한국어 문법에 맞게 교정합니다.

STEP 2. 키워드 분석 (분야 / 주요 독자층 / 독자가 실제로 궁금한 것)

STEP 3. 아래 23가지 검색 심리 중 이 키워드에 해당하는 유형을 판별합니다:
실행·절차 / 입수·획득 / 준비·확인 / 자격·조건 / 일정·기한 / 비용·가격 / 비교·선택 /
결과·후기 검증 / 비교 전 탐색 / 문제 해결 / 전환·이동 / 재시도·복구 / 절약·최적화 /
탈출·중단 / 기한·놓침 대응 / 증빙·제출 / 공식 경로 탐색 / 타인 경험 검증 /
비교 후 최종 결정 / 선물·대리 구매 / 보안·개인정보 우려 / 초보·입문 진입 / 재구매·반복 사용

## 제목 생성 규칙 (5개 모두 적용)
1. 키워드를 제목 맨 앞 15자 이내 배치 — 키워드의 띄어쓰기·글자 완전히 동일하게
2. 공백 포함 24~30자
3. 숫자 반드시 1개 이상 포함 (개수/기간/연도/금액 등)
4. 특수기호 사용 금지
5. 홍보성 단어 금지 (이벤트·강추·무료·공짜·할인·1위 등)
6. 제목 마무리는 명사형 (~방법, ~총정리, ~조건, ~기준, ~이유 등)
7. 동사 위주 능동형 표현
8. 독자가 읽으면 무엇을 얻는지 제목에서 미리 보여줄 것
9. 반드시 한국어(한글)로만 작성 — 일본어(히라가나·가타카나)·한자 절대 사용 금지

좋은 예: "백김치 담그는 방법 한 번 따라하면 다시는 사 먹지 않는 이유"
나쁜 예: "백김치 담그는 방법 총정리"

STEP 3에서 판별한 심리 상태에 맞게 제목 3개를 생성하고,
공감성·결과 기대감·클릭 충동 기준으로 가장 좋은 제목 1개를 recommended로 선정합니다.

아래 JSON만 반환 (다른 텍스트 절대 없이):
{{"titles": ["제목1", "제목2", "제목3"], "recommended": "titles 중 하나와 정확히 동일한 추천 제목"}}""",
        }],
    )
    tokens = response.usage.total_tokens if response.usage else 0
    text = response.choices[0].message.content.strip()
    match = re.search(r'\{.*?"titles".*?\}', text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            titles = _filter_titles(data.get("titles", []))
            recommended = data.get("recommended", titles[0] if titles else "")
            if _has_japanese(recommended):
                recommended = titles[0] if titles else ""
            if titles:
                return titles, recommended, tokens
        except json.JSONDecodeError:
            pass
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if match:
        try:
            titles = _filter_titles(json.loads(match.group()))
            return titles, titles[0] if titles else "", tokens
        except json.JSONDecodeError:
            pass
    fallback = f"{keyword} 제대로 알고 활용하는 방법 3가지"
    return [fallback], fallback, tokens


def generate_blog_post(
    keyword: str,
    title: str,
    client: Groq,
    summary: str = "",
    internal_links: list[str] | None = None,
    related_posts: list[str] | None = None,
) -> tuple[dict, int]:
    """블로그 포스트 생성. (post_data, total_tokens) 반환"""
    inputs = [f"- focus_keyword: {keyword}", f"- title: {title}"]
    if summary:
        inputs.append(f"- summary: {summary}")
    if internal_links:
        inputs.append("- internal_links:\n" + "\n".join(f"  {u}" for u in internal_links))
    if related_posts:
        inputs.append("- related_posts:\n" + "\n".join(f"  {u}" for u in related_posts))

    prompt = f"""당신은 한국어 블로그 글을 작성하는 전문가입니다.
아래 입력값과 규칙에 따라 글을 생성하고, 반드시 JSON 형식으로만 출력하세요.
JSON 외 다른 텍스트는 절대 출력하지 마세요.

[입력값]
{chr(10).join(inputs)}

[출력 형식]
{{
  "title": "제목 (25자 이내, 특수문자 금지)",
  "focus_keyword": "포커스 키워드",
  "meta_description": "포커스 키워드 포함 150자 이내 요약문",
  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5"],
  "content": "HTML 본문 전체"
}}

[사실 날조 방지 — 최우선 규칙]
- summary에 명시된 수치·통계·연구 결과는 그대로 인용 가능
- summary에 없는 수치·퍼센트·연구 결과·통계는 생성 절대 금지
- "연구에 따르면", "~% 효과" 같은 표현은 summary 근거 없이 사용 금지
- summary가 있으면 그 내용 범위 안에서만 작성
- summary가 없으면 구체적 수치 없이 일반 정보 기반으로만 작성

[content HTML 작성 규칙]

▶ 글 길이
- HTML 태그 제외 순수 텍스트 기준 최소 800자

▶ 허용 태그
<h1> <h2> <h3> <p> <strong> <table> <tr> <th> <td> <ul> <li> <br>
- CSS 스타일 속성 금지 (인라인 style 포함)
- <a> 태그는 입력값(internal_links, related_posts)으로 제공된 URL에만 사용 가능
- 입력값에 없는 URL을 <a> 태그로 직접 생성 절대 금지
- HTML 속성값은 반드시 작은따옴표 사용: href='url' (쌍따옴표 href="url" 절대 금지)
- JSON 문자열 내 줄바꿈은 \n으로 표현

▶ 링크 처리 원칙
- 위키백과 링크 삽입 금지
- 내부링크: internal_links 입력값이 있을 때만 해당 URL 그대로 사용
- 함께 보면 좋은 글: related_posts 입력값이 있을 때만 해당 URL 그대로 사용
- 입력값 없으면 링크 섹션 자체 생략 (URL 추측·생성 절대 금지)

▶ 본문 구조 (순서 고정)
1. <h1>제목</h1>
2. <p>요약문 — 포커스 키워드 포함, 150자 이상 170자 이내</p>
3. H2 본문 섹션 — 제목에 숫자(N가지/N단계)가 있으면 정확히 그 숫자만큼 H2 작성, 각 H2 본문 150자 이상
4. <h2>자주 묻는 질문</h2> — Q&A 4개, 각 답변 80자 이상
5. <h2>글을 마치며</h2> — 200자 이상
6. <h2>함께 보면 좋은 글</h2> — related_posts 있을 때만 작성, URL 한 줄에 하나씩 단독 배치

▶ 포커스 키워드 배치 횟수
- 총 8~12회
- H1: 1회 / 요약문: 1회 / 각 H2: 1회 / FAQ 전체: 1회 / 글을 마치며: 1회

▶ 경험 사례 (2~3개 H2에만 삽입)
- 별도 섹션 금지, 본문 흐름 속에 자연스럽게 삽입
- 50~100자 이내, 3인칭 시점 (지인·친구·직장 동료 등)
- 수치나 구체적 효과 수치 포함 금지

▶ 문체 및 톤
- 친근하고 자연스러운 대화체
- 짧고 긴 문장 혼합
- 감정 표현 적극 사용

▶ 줄바꿈
- H2 끝, H3 끝, table 끝 뒤에 <br> 삽입

[제목 작성 원칙]
- 25자 이내, 특수문자 금지
- 핵심 키워드를 앞 15자 이내에 배치
- 숫자·후킹 요소 포함
- 광고성 키워드 금지 (최고·무료·추천·1위·최신 등)
- 제목의 숫자와 본문 H2 개수 반드시 일치"""

    def _do_request(p: str) -> tuple[str, int]:
        r = client.chat.completions.create(
            model=MODEL,
            max_tokens=4000,
            reasoning_effort="none",
            messages=[{"role": "user", "content": p}],
        )
        t = r.usage.total_tokens if r.usage else 0
        return r.choices[0].message.content.strip(), t

    def _parse(text: str) -> dict | None:
        # 마크다운 코드블록 제거
        text = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
        # 시도 1: 직접 파싱
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 시도 2: 첫 { ~ 마지막 }
        try:
            s = text.index("{")
            e = text.rindex("}") + 1
            return json.loads(text[s:e])
        except (ValueError, json.JSONDecodeError):
            pass
        return None

    text, tokens = _do_request(prompt)
    result = _parse(text)

    # 파싱 실패 시 1회 재시도 (더 명확한 지시 추가)
    if result is None:
        retry_prompt = prompt + "\n\n[중요] 반드시 유효한 JSON만 출력하세요. HTML 속성값은 작은따옴표(')만 사용하세요."
        text2, tokens2 = _do_request(retry_prompt)
        tokens += tokens2
        result = _parse(text2)

    return result or {}, tokens


def _has_japanese(text: str) -> bool:
    return any('぀' <= c <= 'ヿ' for c in text)

def _filter_titles(titles: list[str]) -> list[str]:
    return [t for t in titles if not _has_japanese(t)]

def validate_title(title: str, keyword: str) -> dict:
    length = len(title)
    pos = title.find(keyword)
    return {
        "length_ok": 24 <= length <= 32,
        "keyword_pos_ok": 0 <= pos <= 14,
        "length": length,
        "keyword_pos": pos,
    }
