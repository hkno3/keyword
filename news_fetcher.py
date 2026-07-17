import os
import re
import email.utils
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
MAX_SCRAPE_CHARS = 3000

CATEGORY_QUERIES = {
    "건강": [
        "건강 관리", "다이어트", "식단", "운동", "영양제",
        "피부 관리", "수면", "면역력", "건강식품", "체중 감량",
    ],
    "부동산": [
        "아파트", "부동산", "전세", "월세", "청약",
        "분양", "재개발", "재건축", "부동산 시장",
    ],
    "사업": [
        "창업", "사업", "스타트업", "프랜차이즈", "부업",
        "온라인 쇼핑몰", "사업 아이템", "소자본 창업",
    ],
    "투자": [
        "주식", "ETF", "재테크", "코인", "펀드",
        "부동산 투자", "절세", "연금", "배당주",
    ],
    "정부지원금": [
        "정부지원금", "청년지원금", "복지급여", "국가보조금", "긴급복지",
        "근로장려금", "자녀장려금", "에너지바우처", "주거급여", "의료급여",
    ],
    "보험": [
        "생명보험", "실손보험", "자동차보험", "암보험", "치아보험",
        "어린이보험", "보험 비교", "보험 추천", "보험료 절약",
    ],
    "대출": [
        "신용대출", "주택담보대출", "전세대출", "대출 금리", "대출 조건",
        "저금리대출", "직장인대출", "햇살론", "사잇돌대출",
    ],
    "법률": [
        "이혼", "상속", "형사", "민사소송", "고소",
        "합의금", "변호사 비용", "법률 상담", "위자료",
    ],
    "세금": [
        "종합소득세", "부가세", "절세", "연말정산", "세금 환급",
        "양도소득세", "상속세", "증여세", "부동산 세금",
    ],
    "육아출산": [
        "임신", "출산", "육아용품", "어린이집", "유아식",
        "출산 준비", "육아휴직", "산후조리원", "아기 발달",
    ],
    "여행": [
        "국내여행", "제주도여행", "숙소 추천", "맛집", "펜션",
        "캠핑", "해외여행", "여행 준비", "가족여행",
    ],
    "반려동물": [
        "강아지", "고양이", "동물병원", "강아지 사료", "고양이 사료",
        "반려동물 보험", "강아지 훈련", "펫시터", "반려동물 용품",
    ],
    "생활정보": [
        "쿠팡 환불", "쿠팡 고객센터", "쿠팡 취소",
        "배민 환불", "배달의민족 고객센터", "배민 취소",
        "네이버 고객센터", "카카오 고객센터", "카카오톡 오류",
        "다이소 환불", "이마트 환불", "올리브영 환불",
        "에어컨 전기세", "전기세 절약", "가스비 절약", "관리비 절약",
        "에어컨 청소", "보일러 고장", "변기 막힘", "수도 누수",
        "택배 분실", "택배 반품", "직구 관세", "해외직구 방법",
        "운전면허 갱신", "주민등록증 재발급", "여권 갱신", "주차위반 과태료",
        "건강보험 환급", "실업급여 신청", "국민연금 조회",
        "스마트폰 초기화", "아이폰 수리비", "삼성 AS", "노트북 느려짐",
        "유튜브 광고 차단", "넷플릭스 해지", "구독 해지 방법",
        "영수증 없이 환불", "중고나라 사기", "당근마켓 사기",
    ],
}

CATEGORY_FILTERS = {
    "건강": [
        "건강", "질병", "병원", "수술", "치료", "투병", "면역", "영양", "비타민",
        "당뇨", "고혈압", "암", "디스크", "관절", "수면", "피로", "스트레스",
        "다이어트", "식단", "체중", "감량", "살", "몸매", "비만", "칼로리",
        "피부", "스킨케어", "피부관리", "피부과", "보톡스", "여드름", "주름",
        "운동", "헬스", "트레이닝", "근육", "근력", "유산소", "요가", "필라테스",
        "약", "처방", "진료", "증상", "통증", "두통", "복통", "소화", "변비",
        "혈당", "혈압", "콜레스테롤", "갑상선", "간", "신장", "폐", "심장",
        "탈모", "다크서클", "붓기", "부종", "냉증", "생리통", "갱년기",
        "단백질", "오메가", "유산균", "콜라겐", "마그네슘", "철분", "아연",
        "절식", "간헐적단식", "저탄고지", "채식", "글루텐",
    ],
    "부동산": [
        "부동산", "아파트", "집", "빌라", "주택", "오피스텔", "상가", "건물",
        "매입", "매매", "전세", "월세", "임대", "분양", "저택", "펜트하우스",
        "청약", "재개발", "재건축", "갭투자", "경매", "공시가", "실거래가",
        "입주", "계약", "등기", "중개", "공인중개사", "부동산세", "취득세",
        "역세권", "신축", "구축", "빌딩", "토지", "땅", "지방", "수도권",
        "임장", "호가", "매물", "시세", "평형", "평당", "관리비",
    ],
    "사업": [
        "사업", "창업", "회사", "브랜드", "론칭", "대표", "CEO", "설립",
        "카페", "식당", "레스토랑", "매장", "프랜차이즈", "매출", "수익",
        "스타트업", "부업", "온라인쇼핑몰", "스마트스토어", "위탁판매",
        "사업자등록", "법인", "개인사업자", "세금계산서", "비용처리",
        "마케팅", "SNS마케팅", "광고비", "고객", "유통", "납품",
        "아이템", "틈새시장", "수익모델", "손익분기", "투자유치",
    ],
    "투자": [
        "투자", "재테크", "주식", "코인", "펀드", "ETF", "자산", "배당",
        "연금", "적금", "예금", "부업", "수입", "연봉",
        "비트코인", "이더리움", "알트코인", "NFT", "가상화폐",
        "해외주식", "미국주식", "나스닥", "S&P", "배당금", "배당률",
        "IRP", "ISA", "퇴직연금", "국민연금", "개인연금",
        "금", "달러", "환율", "채권", "리츠", "원자재",
        "손절", "익절", "분할매수", "장기투자", "단타", "스윙",
    ],
    "정부지원금": [
        "지원금", "보조금", "급여", "바우처", "장려금", "수당", "혜택", "복지",
        "신청", "자격", "대상", "조건", "기간", "방법",
        "정부", "국가", "지자체", "시청", "구청", "주민센터",
        "청년", "노인", "장애인", "저소득", "한부모", "다자녀",
        "에너지", "난방", "교육비", "취업", "창업지원", "소상공인",
        "복지로", "정부24", "신청방법", "서류", "온라인신청",
    ],
    "보험": [
        "보험", "보장", "보험료", "가입", "특약", "갱신", "실손", "생명",
        "암보험", "치아", "자동차보험", "보험금", "청구", "해지",
        "비교", "추천", "설계", "보험사", "손해보험", "상해보험",
        "사망보험금", "입원비", "수술비", "진단금", "후유장해",
        "무해지", "순수보장", "만기환급", "변액", "종신",
        "운전자보험", "화재보험", "여행자보험", "펫보험",
    ],
    "대출": [
        "대출", "금리", "한도", "금융", "신용", "담보", "전세", "상환",
        "이자", "대환", "햇살론", "사잇돌", "저금리",
        "DSR", "LTV", "DTI", "원리금", "거치", "분할상환",
        "카드론", "마이너스통장", "비상금대출", "소액대출",
        "1금융", "2금융", "저축은행", "캐피탈", "인터넷은행",
        "카카오뱅크", "토스뱅크", "케이뱅크", "신용점수", "신용등급",
    ],
    "법률": [
        "이혼", "상속", "소송", "변호사", "법률", "고소", "합의", "위자료",
        "형사", "민사", "재판", "판결", "법원",
        "고발", "내용증명", "지급명령", "손해배상", "가압류",
        "양육권", "양육비", "재산분할", "협의이혼", "조정",
        "유언장", "유류분", "상속포기", "한정승인",
        "명예훼손", "사기", "횡령", "배임", "폭행",
        "노동", "해고", "퇴직금", "임금체불", "직장내괴롭힘",
    ],
    "세금": [
        "세금", "소득세", "부가세", "절세", "환급", "공제", "신고", "납부",
        "연말정산", "양도세", "증여세", "상속세", "세무",
        "종합소득세", "사업소득", "근로소득", "기타소득", "배당소득",
        "취득세", "재산세", "종부세", "지방세",
        "세금계산서", "현금영수증", "경비처리", "비용공제",
        "홈택스", "세무서", "세무사", "기장", "신고기간",
        "환급금", "가산세", "체납", "분납",
    ],
    "육아출산": [
        "임신", "출산", "육아", "아기", "신생아", "어린이집", "유아", "산후",
        "모유", "분유", "이유식", "육아휴직", "태교",
        "출산준비물", "산후조리원", "조리원", "입덧", "태동",
        "예방접종", "소아과", "아기발달", "언어발달", "성장",
        "유모차", "카시트", "아기띠", "젖병", "기저귀",
        "어린이집비용", "유치원", "돌봄", "아이돌봄서비스",
        "출산지원금", "육아수당", "부모급여", "아동수당",
    ],
    "여행": [
        "여행", "숙소", "맛집", "펜션", "호텔", "캠핑", "제주도", "관광",
        "명소", "코스", "일정", "여행지", "가볼만한",
        "국내여행", "해외여행", "패키지", "자유여행", "배낭여행",
        "항공권", "비행기", "렌터카", "기차여행", "버스투어",
        "가족여행", "커플여행", "혼자여행", "당일치기", "1박2일",
        "글램핑", "오토캠핑", "워케이션", "리조트", "풀빌라",
        "여행경비", "여행준비", "여행필수품", "여행앱", "환전",
    ],
    "반려동물": [
        "강아지", "고양이", "반려동물", "펫", "동물병원", "사료", "간식",
        "훈련", "예방접종", "중성화", "분양", "입양",
        "강아지훈련", "배변패드", "켄넬", "목줄", "하네스",
        "고양이모래", "캣타워", "캣닙", "습식사료", "건식사료",
        "동물등록", "마이크로칩", "펫보험", "병원비",
        "슬개골", "심장사상충", "켄넬코프", "피부병", "구내염",
        "펫시터", "호텔링", "미용", "목욕", "발톱",
    ],
    "생활정보": [
        "환불", "고객센터", "취소", "반품", "교환", "AS", "수리",
        "쿠팡", "배민", "배달의민족", "네이버", "카카오", "다이소",
        "이마트", "홈플러스", "올리브영", "무신사", "지그재그",
        "전기세", "가스비", "관리비", "수도요금", "절약", "요금",
        "에어컨", "보일러", "냉장고", "세탁기", "청소기", "전자레인지",
        "택배", "반품", "배송", "분실", "파손", "지연",
        "직구", "관세", "해외배송", "아마존", "이베이", "알리익스프레스",
        "면허", "갱신", "재발급", "여권", "주민등록", "인감",
        "과태료", "벌금", "범칙금", "주차", "교통위반",
        "건강보험", "실업급여", "국민연금", "4대보험",
        "스마트폰", "초기화", "데이터복구", "배터리", "액정",
        "넷플릭스", "유튜브", "구독", "해지", "결제",
        "중고나라", "당근마켓", "번개장터", "사기", "피해",
        "방법", "절차", "신청", "조회", "확인",
    ],
}

_MONTHS = {
    "Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06",
    "Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12",
}


def _parse_date(date_str: str) -> str:
    if not date_str:
        return ""
    if re.match(r"^\d{8}$", date_str):
        return f"{date_str[:4]}.{date_str[4:6]}.{date_str[6:]}"
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        return dt.strftime("%Y.%m.%d")
    except Exception:
        pass
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", date_str)
    if m:
        day, mon, year = m.group(1), m.group(2)[:3].capitalize(), m.group(3)
        return f"{year}.{_MONTHS.get(mon, '00')}.{day.zfill(2)}"
    return ""


def _date_sortkey(date_str: str) -> str:
    if not date_str:
        return "00000000"
    if re.match(r"^\d{8}$", date_str):
        return date_str
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        return dt.strftime("%Y%m%d%H%M%S")
    except Exception:
        pass
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", date_str)
    if m:
        day, mon, year = m.group(1), m.group(2)[:3].capitalize(), m.group(3)
        return f"{year}{_MONTHS.get(mon,'00')}{day.zfill(2)}"
    return "00000000"


def _naver_headers() -> dict:
    return {
        "X-Naver-Client-Id": os.getenv("NAVER_CLIENT_ID", ""),
        "X-Naver-Client-Secret": os.getenv("NAVER_CLIENT_SECRET", ""),
    }


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&[a-z#\d]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _passes_filter(title: str, category: str) -> bool:
    words = CATEGORY_FILTERS.get(category, [])
    return any(w in title for w in words) if words else True


def _search_news(query: str, display: int = 100) -> list[dict]:
    try:
        resp = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            headers=_naver_headers(),
            params={"query": query, "display": display, "sort": "date"},
            timeout=8,
        )
        resp.raise_for_status()
        return [
            {
                "title": _strip_html(item.get("title", "")),
                "link": item.get("originallink") or item.get("link", ""),
                "pubDate": _parse_date(item.get("pubDate", "")),
                "type": "뉴스",
            }
            for item in resp.json().get("items", [])
        ]
    except Exception:
        return []


def fetch_category_news(category: str, max_total: int = 1000) -> list[dict]:
    queries = CATEGORY_QUERIES.get(category, [])
    seen = set()
    results = []

    for query in queries:
        for item in _search_news(query):
            t = item["title"]
            if t and t not in seen and _passes_filter(t, category):
                seen.add(t)
                results.append(item)

    results.sort(key=lambda x: _date_sortkey(x.get("pubDate", "")), reverse=True)
    return results[:max_total]


def _search_kin(query: str, display: int = 100) -> list[dict]:
    try:
        resp = requests.get(
            "https://openapi.naver.com/v1/search/kin.json",
            headers=_naver_headers(),
            params={"query": query, "display": display, "sort": "date"},
            timeout=8,
        )
        resp.raise_for_status()
        return [
            {
                "title": _strip_html(item.get("title", "")),
                "link": item.get("link", ""),
                "description": _strip_html(item.get("description", "")),
                "pubDate": "",
                "type": "지식인",
            }
            for item in resp.json().get("items", [])
        ]
    except Exception:
        return []


def fetch_category_kin(category: str, max_total: int = 1000) -> list[dict]:
    queries = CATEGORY_QUERIES.get(category, [])
    seen = set()
    results = []

    for query in queries:
        for item in _search_kin(query):
            t = item["title"]
            if t and t not in seen and _passes_filter(t, category):
                seen.add(t)
                results.append(item)

    return results[:max_total]


def _search_api(query: str, search_type: str, label: str, display: int = 100) -> list[dict]:
    """blog / cafearticle / webkr 공통 검색 헬퍼"""
    try:
        resp = requests.get(
            f"https://openapi.naver.com/v1/search/{search_type}.json",
            headers=_naver_headers(),
            params={"query": query, "display": display, "sort": "date"},
            timeout=8,
        )
        resp.raise_for_status()
        return [
            {
                "title": _strip_html(item.get("title", "")),
                "link": item.get("link", ""),
                "description": _strip_html(item.get("description", "")),
                "pubDate": _parse_date(item.get("postdate", "") or item.get("pubDate", "")),
                "type": label,
            }
            for item in resp.json().get("items", [])
        ]
    except Exception:
        return []


def fetch_category_blog(category: str, max_total: int = 1000) -> list[dict]:
    queries = CATEGORY_QUERIES.get(category, [])
    seen, results = set(), []
    for query in queries:
        for item in _search_api(query, "blog", "블로그"):
            t = item["title"]
            if t and t not in seen and _passes_filter(t, category):
                seen.add(t); results.append(item)
    return results[:max_total]


def fetch_category_cafe(category: str, max_total: int = 1000) -> list[dict]:
    queries = CATEGORY_QUERIES.get(category, [])
    seen, results = set(), []
    for query in queries:
        for item in _search_api(query, "cafearticle", "카페"):
            t = item["title"]
            if t and t not in seen and _passes_filter(t, category):
                seen.add(t); results.append(item)
    return results[:max_total]


def fetch_category_web(category: str, max_total: int = 1000) -> list[dict]:
    queries = CATEGORY_QUERIES.get(category, [])
    seen, results = set(), []
    for query in queries:
        for item in _search_api(query, "webkr", "웹문서"):
            t = item["title"]
            if t and t not in seen and _passes_filter(t, category):
                seen.add(t); results.append(item)
    return results[:max_total]


def scrape_article(url: str) -> str:
    if not url or "naver.com/blog" in url:
        return ""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()
        body = (
            soup.find("article")
            or soup.find("main")
            or soup.find(id=re.compile(r"content|article|body", re.I))
            or soup.find(class_=re.compile(r"content|article|body|text", re.I))
            or soup.body
        )
        if not body:
            return ""
        text = body.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 20]
        return "\n".join(lines)[:MAX_SCRAPE_CHARS]
    except Exception:
        return ""


def fetch_summary_for_keyword(keyword: str, max_chars: int = 2000) -> str:
    """키워드로 뉴스→블로그→웹 순서로 스크래핑해서 summary 반환"""
    client_id = os.getenv("NAVER_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "")
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}

    def _get_urls(search_type: str) -> list[str]:
        try:
            r = requests.get(
                f"https://openapi.naver.com/v1/search/{search_type}",
                headers=headers,
                params={"query": keyword, "display": 5, "sort": "date"},
                timeout=10,
            )
            items = r.json().get("items", []) if r.ok else []
            return [item.get("link", "") for item in items if item.get("link")]
        except Exception:
            return []

    def _try_scrape(urls: list[str]) -> str:
        collected = []
        for url in urls:
            if sum(len(t) for t in collected) >= max_chars:
                break
            text = scrape_article(url)
            if text and len(text) > 100:
                collected.append(text[:600])
        return "\n\n".join(collected)[:max_chars]

    for search_type in ["news", "blog", "webkr"]:
        urls = _get_urls(search_type)
        if not urls:
            continue
        result = _try_scrape(urls)
        if result:
            return result

    return ""
