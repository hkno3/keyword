import json
import re
from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash"


def _make_client(api_key: str):
    return genai.Client(api_key=api_key)


def _parse_json(text: str) -> dict | None:
    text = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        s = text.index("{")
        e = text.rindex("}") + 1
        return json.loads(text[s:e])
    except (ValueError, json.JSONDecodeError):
        pass
    return None


def _build_prompt(keyword: str, title: str, internal_links: list[str] | None, related_posts: list[str] | None) -> str:
    inputs = [f"- focus_keyword: {keyword}", f"- title: {title}"]
    if internal_links:
        inputs.append("- internal_links:\n" + "\n".join(f"  {u}" for u in internal_links))
    if related_posts:
        inputs.append("- related_posts:\n" + "\n".join(f"  {u}" for u in related_posts))

    return f"""당신은 한국어 블로그 글을 작성하는 전문가입니다.
Google 검색을 통해 focus_keyword와 title에 관련된 최신 정보를 먼저 수집한 후,
아래 입력값과 규칙에 따라 글을 생성하고, 반드시 JSON 형식으로만 출력하세요.
JSON 외 다른 텍스트는 절대 출력하지 마세요. 인용 표시([1], [2] 등)는 절대 포함하지 마세요.

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

[content HTML 작성 규칙]

▶ 글 길이
- HTML 태그 제외 순수 텍스트 기준 최소 1000자

▶ 허용 태그
<h2> <h3> <h4> <p> <strong> <table> <tr> <th> <td> <ul> <ol> <li> <br> <a>
- <h1> 절대 사용 금지 (워드프레스 제목과 중복)
- CSS 스타일 속성 금지 (인라인 style 포함) — 단, 공공기관 버튼 <p style="..."> 에 한해 예외 허용
- <a> 태그는 입력값(internal_links, related_posts) 또는 공공기관 공식 URL에만 사용 가능
- 입력값에 없는 일반 URL을 <a> 태그로 직접 생성 절대 금지
- HTML 속성값은 반드시 작은따옴표 사용: href='url' (쌍따옴표 href="url" 절대 금지)
- JSON 문자열 내 줄바꿈은 \\n으로 표현

▶ 제목 계층 구조
- H2: 대주제 섹션 제목
- H3: H2 하위 소주제 (각 H2마다 2~3개)
- H4: H3 하위 세부 항목 (필요한 경우)
- 계층 순서 절대 건너뛰기 금지 (H2 다음 H4 금지)

▶ 링크 처리 원칙
- 위키백과 링크 삽입 금지
- 내부링크(internal_links): 관련 내용이 나오는 본문 중간에 자연스럽게 삽입
  예) <a href='url'>관련 글 보기</a> 형태로 문장 흐름 안에 배치
- 함께 보면 좋은 글(related_posts): 글 맨 끝 별도 섹션으로 배치
- 입력값 없으면 해당 링크 섹션 생략 (URL 추측·생성 절대 금지)

▶ 본문 구조 (순서 고정)
1. <p>요약문 — 포커스 키워드 포함, 150자 이상 170자 이내</p>
2. H2 본문 섹션 반복 (제목에 숫자 N이 있으면 정확히 N개):
   - <h2>섹션 제목</h2>
   - H3/H4로 세분화된 본문 (각 H3 본문 100자 이상)
   - 본문 내 관련 internal_link 자연스럽게 삽입
   - 섹션 끝에 요약 표 1개 (핵심 내용 3~5행)
   - <br>
3. <h2>자주 묻는 질문</h2> — Q&A 4개, 각 답변 80자 이상
4. <h2>글을 마치며</h2> — 200자 이상
5. <h2>함께 보면 좋은 글</h2> — related_posts 있을 때만, URL 한 줄에 하나씩

▶ 요약 표 형식 (각 H2 섹션 끝에 삽입)
<table>
<tr><th>항목</th><th>내용</th></tr>
<tr><td>핵심 포인트1</td><td>설명</td></tr>
</table>

▶ 문단 길이
- 한 <p> 태그 안에 3문장 이상이면 <br>로 줄바꿈
- 한 문장이 80자를 넘으면 자연스러운 위치에서 끊기

▶ 줄바꿈 규칙 (반드시 준수)
- 각 H2 섹션 끝 (요약 표 포함) 다음에 반드시 <br> 삽입
- 공공기관 버튼 (<p style=...>) 앞뒤로 반드시 <br> 삽입
- <h2>자주 묻는 질문</h2> 섹션 끝 다음에 반드시 <br> 삽입
- <h2>글을 마치며</h2> 섹션 끝 다음에 반드시 <br> 삽입

▶ 포커스 키워드 배치 횟수
- 총 8~12회
- 요약문: 1회 / 각 H2: 1회 / FAQ 전체: 1회 / 글을 마치며: 1회

▶ 경험 사례 (2~3개 H2에만 삽입)
- 별도 섹션 금지, 본문 흐름 속에 자연스럽게 삽입
- 50~100자 이내, 3인칭 시점 (지인·친구·직장 동료 등)
- 수치나 구체적 효과 수치 포함 금지

▶ 문체 및 톤
- 친근하고 자연스러운 대화체
- 짧고 긴 문장 혼합
- 감정 표현 적극 사용

▶ 공공기관 버튼 삽입 규칙
- Google 검색으로 문맥에 맞는 공공기관 공식 사이트를 찾아 본문 중간에 버튼 형태로 삽입
- 글 전체 기준 1~2개 삽입
- 독자가 실제로 행동해야 할 섹션에 우선 배치 (신청·조회·예약·신고 등)
- 단순 설명만 하는 문단에는 삽입하지 않음
- 각 섹션당 최대 1개

허용 도메인:
- .go.kr (정부기관) ✅
- .or.kr (공공기관) ✅
- .com, .co.kr 절대 금지 ❌

버튼 형식 (반드시 이 형식 그대로):
<p style='background:#FF6B35; color:white; padding:15px 25px; text-align:center; border-radius:8px; margin:20px auto; display:flex; align-items:center; justify-content:center;'>
  <a href='공공기관URL' style='color:white; text-decoration:none; font-weight:bold; font-size:22px;'>📌 기관명 - 구체적 행동</a>
</p>

버튼 텍스트 규칙:
- ✅ 좋은 예: 📌 국민건강보험공단 - 검진 예약하기
- ❌ 나쁜 예: 📌 국민건강보험공단 바로가기 (구체적 행동 없음)

URL 검증 절차:
1. 현재 문단 핵심 키워드 파악
2. "키워드 + 공공기관" 또는 "키워드 + 정부 사이트"로 검색
3. .go.kr, .or.kr 도메인만 선택
4. 검색으로 확인된 URL만 사용 — 불확실하면 버튼 삽입하지 않음
5. 억지로 관련 없는 기관 연결 금지

[제목 작성 원칙]
- 25자 이내, 특수문자 금지
- 핵심 키워드를 앞 15자 이내에 배치
- 숫자·후킹 요소 포함
- 광고성 키워드 금지 (최고·무료·추천·1위·최신 등)
- 제목의 숫자와 본문 H2 개수 반드시 일치"""


def _is_quota_error(e: Exception) -> bool:
    s = str(e).lower()
    return "429" in s or "quota" in s or "resource_exhausted" in s or "rate" in s


def generate_blog_post(
    keyword: str,
    title: str,
    api_key1: str,
    api_key2: str = "",
    internal_links: list[str] | None = None,
    related_posts: list[str] | None = None,
) -> tuple[dict, str]:
    """Gemini + Google Search 그라운딩으로 블로그 포스트 생성.
    Returns (post_data, used_key) — used_key: "1" or "2"
    """
    prompt = _build_prompt(keyword, title, internal_links, related_posts)

    def _call(key: str) -> dict | None:
        client = _make_client(key)
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.7,
            ),
        )
        return _parse_json(response.text)

    quota_exc = None
    try:
        result = _call(api_key1)
        if result:
            return result, "1"
    except Exception as e:
        if not _is_quota_error(e):
            raise
        quota_exc = e

    if api_key2:
        result = _call(api_key2)
        if result:
            return result, "2"

    if quota_exc:
        raise quota_exc
    return {}, "1"
