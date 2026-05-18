import json
import re
from groq import Groq

MODEL = "llama-3.3-70b-versatile"


def extract_keywords(article: str, client: Groq) -> list[str]:
    """기사 텍스트에서 SEO 키워드 15개 추출"""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=800,
        messages=[
            {
                "role": "user",
                "content": f"""당신은 한국 블로그 SEO 전문가입니다.
아래 뉴스 기사에서 네이버 블로그 글쓰기에 적합한 키워드 15개를 추출하세요.

조건:
- 반드시 한국어(한글)로만 작성 (영어 혼용 금지, 러시아어·특수문자 절대 금지)
- 네이버에서 실제로 검색할 법한 구체적인 키워드
- 단일 단어보다 복합어(2~4단어) 우선
- 기사 핵심 주제 + 관련 부주제 포함
- 기자명, SNS 버튼, 광고 문구 같은 UI 잔재는 무시
- 중복 없이 다양하게
- 각 키워드는 40자 이내

기사:
{article[:3000]}

JSON 배열로만 반환하세요 (설명 없이): ["키워드1", "키워드2", ...]""",
            }
        ],
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
    """키워드에 대한 블로그 제목 5개 생성 (규칙 엄수)"""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=600,
        messages=[
            {
                "role": "user",
                "content": f"""한국 블로그 제목 전문가로서 키워드 "{keyword}"에 대한 제목 5개를 만드세요.

필수 규칙 (모두 지킬 것):
1. 공백 포함 24~30자
2. "{keyword}" 키워드를 제목 맨 앞 15자 이내에 배치
3. 키워드 글자와 띄어쓰기 100% 동일하게 유지 (변형 금지)
4. 심리 자극 요소: 이득 / 손실 / 비교 / 효율 / 안전 중 하나 선택
5. 단순 나열 금지, 문맥적으로 자연스럽게 연결
6. 동사 위주 능동형 표현
7. 숫자 포함 권장
8. 특수문자(!?~…), 홍보성 단어(최고·완벽·강추 등) 금지

JSON 배열로만 반환 (설명 없이): ["제목1", "제목2", "제목3", "제목4", "제목5"]""",
            }
        ],
    )

    text = response.choices[0].message.content.strip()
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return [f"{keyword} 제대로 알고 활용하는 3가지 방법"]


def validate_title(title: str, keyword: str) -> dict:
    """제목 규칙 검증 결과 반환"""
    length = len(title)
    pos = title.find(keyword)
    return {
        "length_ok": 24 <= length <= 30,
        "keyword_pos_ok": 0 <= pos <= 14,
        "length": length,
        "keyword_pos": pos,
    }
