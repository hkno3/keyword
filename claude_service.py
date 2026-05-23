import json
import re
from groq import Groq

MODEL = "llama-3.3-70b-versatile"


def extract_seed_keywords(article: str, client: Groq) -> tuple[list[str], int]:
    """기사에서 단일 씨드 키워드 10개 추출. (keywords, total_tokens) 반환"""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=400,
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


def generate_titles(keyword: str, client: Groq) -> tuple[list[str], str, int]:
    """키워드로 블로그 제목 3개 생성 + 추천 1개 반환"""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=1200,
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
