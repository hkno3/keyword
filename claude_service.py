import json
import re
from groq import Groq

MODEL = "llama-3.3-70b-versatile"


def extract_seed_keywords(article: str, client: Groq) -> list[str]:
    """기사에서 단일 씨드 키워드 10개 추출 (연관키워드 확장용)"""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": f"""한국 블로그 SEO 전문가입니다.
아래 기사의 핵심 주제에 딱 맞는 단일 키워드를 추출하세요. (최대 5개, 관련 있는 것만 — 억지로 채우지 말 것)

엄격한 조건:
- 기사의 핵심 소재(사람·음식·성분·질병·장소·제품 등)와 직접 관련된 단어만
- "효율", "안정성", "유통", "경쟁력", "산업", "기업", "정책", "시장", "전략" 같은 범용 비즈니스 단어 절대 금지
- 반드시 한국어 단일 단어 (예: 유산균, 김치, 혈당, 오메가3, 치매)
- 일반인이 네이버에서 직접 검색할 법한 구체적인 단어
- 기사에서 반복 언급되거나 핵심 소재인 단어 우선

나쁜 예 (기사 주제가 김치라면): 산업, 효율, 유통, 경쟁력, 안정성
좋은 예 (기사 주제가 김치라면): 김치, 유산균, 발효, 젖산균, 배추

기사:
{article[:2000]}

JSON 배열로만 반환: ["키워드1", "키워드2", ...]""",
        }],
    )
    text = response.choices[0].message.content.strip()
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return []


def generate_titles(keyword: str, client: Groq) -> list[str]:
    """키워드로 블로그 제목 5개 생성"""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": f"""한국 블로그 제목 전문가입니다. 키워드 "{keyword}"로 제목 5개를 만드세요.

필수 규칙:
1. 공백 포함 24~32자
2. "{keyword}"를 제목 맨 앞 15자 이내 배치
3. 키워드 글자·띄어쓰기 100% 동일하게 유지
4. 심리 자극: 이득·손실·비교·효율·안전 중 하나를 의미로 녹여내기 (단어 직접 쓰지 말 것)
5. 자연스러운 한국어 블로그 문체
6. 동사 위주 능동형
7. 특수문자·홍보성 단어 금지
8. 억지 숫자 금지 (자연스러울 때만 사용)

좋은 예: "{keyword} 먹기 전 꼭 알아야 할 부작용"
나쁜 예: "{keyword}로 90% 이상의 이득을 달성합니다"

JSON 배열로만 반환: ["제목1", "제목2", "제목3", "제목4", "제목5"]""",
        }],
    )
    text = response.choices[0].message.content.strip()
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return [f"{keyword} 제대로 알고 활용하는 방법"]


def validate_title(title: str, keyword: str) -> dict:
    length = len(title)
    pos = title.find(keyword)
    return {
        "length_ok": 24 <= length <= 32,
        "keyword_pos_ok": 0 <= pos <= 14,
        "length": length,
        "keyword_pos": pos,
    }
