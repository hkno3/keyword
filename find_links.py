"""
링크 캐시에서 관련 링크 검색
- links_cache.json에서 키워드 매칭으로 상위 N개 반환
- Claude가 bash로 호출 → 결과만 받아서 사용

사용법:
  python find_links.py "키워드" "bizachieve" 5       # 내부링크 (같은 사이트)
  python find_links.py "키워드" "bodyandwell" 1      # 외부링크 (다른 사이트)
  python find_links.py "키워드" "bizachieve" 5 exclude="https://exclude-url.com/"
"""
import json
import os
import sys
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(SCRIPT_DIR, 'links_cache.json')


def tokenize(text: str) -> set:
    """한글/영문 단어 토큰화 (조사 포함 단어 단위)"""
    # 숫자+단위 패턴 보존, 나머지는 공백/특수문자로 분리
    tokens = re.findall(r'[가-힣a-zA-Z0-9]+', text.lower())
    return set(tokens)


def score(query_tokens: set, title: str) -> float:
    """제목과 쿼리 토큰 매칭 점수 (0.0 ~ 1.0)"""
    title_tokens = tokenize(title)
    if not title_tokens or not query_tokens:
        return 0.0

    overlap = query_tokens & title_tokens
    # Jaccard 유사도 기반 + 쿼리 커버리지 가중
    jaccard    = len(overlap) / len(query_tokens | title_tokens)
    coverage   = len(overlap) / len(query_tokens)
    return jaccard * 0.4 + coverage * 0.6


def find_links(keyword: str, site: str, count: int = 5, exclude_urls: set = None) -> list:
    if not os.path.exists(CACHE_FILE):
        print(f"ERROR: {CACHE_FILE} 없음. update_links_cache.py 먼저 실행하세요.", file=sys.stderr)
        return []

    with open(CACHE_FILE, encoding='utf-8') as f:
        cache = json.load(f)

    posts = cache.get(site, [])
    if not posts:
        print(f"ERROR: '{site}' 데이터 없음.", file=sys.stderr)
        return []

    query_tokens = tokenize(keyword)
    exclude_urls = exclude_urls or set()

    scored = []
    for p in posts:
        url = p['u']
        if url in exclude_urls:
            continue
        s = score(query_tokens, p['t'])
        if s > 0:
            scored.append((s, p['t'], url))

    scored.sort(key=lambda x: -x[0])
    top = scored[:count]

    return [{'title': t, 'url': u, 'score': round(s, 3)} for s, t, u in top]


def main():
    if len(sys.argv) < 3:
        print("사용법: python find_links.py <키워드> <사이트> [개수]")
        sys.exit(1)

    keyword = sys.argv[1]
    site    = sys.argv[2]
    count   = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    # exclude= 파라미터 파싱
    exclude_urls = set()
    for arg in sys.argv[4:]:
        if arg.startswith('exclude='):
            exclude_urls.add(arg[8:])

    # 캐시 날짜 확인
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding='utf-8') as f:
            meta = json.load(f)
        updated = meta.get('updated_at', '')
        from datetime import date
        today = date.today().strftime('%Y-%m-%d')
        if updated != today:
            print(f"⚠ 캐시가 오래됨 ({updated}). 링크캐시업데이트.bat 실행 권장.", file=sys.stderr)

    results = find_links(keyword, site, count, exclude_urls)

    if not results:
        print("관련 링크 없음")
        return

    print(f"\n▶ '{keyword}' 관련 링크 ({site}, 상위 {len(results)}개)")
    print("─" * 60)
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}")
        print(f"   {r['url']}  [유사도: {r['score']}]")
    print("─" * 60)


if __name__ == '__main__':
    main()
