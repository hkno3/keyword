"""
링크 캐시 업데이트 스크립트 (증분 방식 v2)
- 캐시가 있으면: 최신 글부터 가져오다가 이미 캐시에 있는 URL 발견 시 즉시 중단
  → 날짜 무관하게 새로 발행된 글만 정확히 추가
- 캐시가 없으면: 전체 수집 (최초 1회)

사용법: python update_links_cache.py
"""
import json
import os
import time
from datetime import datetime
import requests
from requests.auth import HTTPBasicAuth

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SITES_FILE = os.path.join(SCRIPT_DIR, 'wp_sites.json')
CACHE_FILE = os.path.join(SCRIPT_DIR, 'links_cache.json')

SITES = ['bizachieve', 'bodyandwell']   # cointrail 제외


def fetch_incremental(site: dict, existing_urls: set) -> list:
    """
    최신 글부터 수집. existing_urls에 있는 URL을 만나면 즉시 중단.
    → 날짜 기준 없이 실제로 새로 올라온 글만 가져옴.
    """
    base   = site['url'].rstrip('/')
    auth   = HTTPBasicAuth(site['username'], site['app_password'])
    url    = f"{base}/wp-json/wp/v2/posts"
    params = {
        'per_page': 100,
        'status':   'publish',
        '_fields':  'title,link',
        'orderby':  'date',
        'order':    'desc',
        'page':     1,
    }

    new_posts = []

    while True:
        try:
            r = requests.get(url, params=params, auth=auth, timeout=30)
            if r.status_code == 400:
                break
            if not r.ok:
                print(f"  ❌ {site['name']} 페이지 {params['page']} 오류: {r.status_code}")
                break

            batch = r.json()
            if not batch:
                break

            total_pages = int(r.headers.get('X-WP-TotalPages', 1))
            hit_existing = False

            for p in batch:
                title = p.get('title', {}).get('rendered', '').strip()
                link  = p.get('link', '').strip()
                if not title or not link:
                    continue
                if link in existing_urls:
                    hit_existing = True  # 이미 캐시에 있는 글 발견 → 여기서 멈춤
                    break
                new_posts.append({'t': title, 'u': link})

            print(f"  페이지 {params['page']}/{total_pages} — {len(batch)}개 수신"
                  f" / 신규 누적 {len(new_posts)}개"
                  + (" → 기존 글 발견, 중단" if hit_existing else ""))

            if hit_existing or params['page'] >= total_pages:
                break

            params['page'] += 1
            time.sleep(0.3)

        except Exception as e:
            print(f"  ❌ {site['name']} 수집 오류: {e}")
            break

    return new_posts


def fetch_all(site: dict) -> list:
    """전체 글 수집 (캐시 없을 때 최초 1회)"""
    base   = site['url'].rstrip('/')
    auth   = HTTPBasicAuth(site['username'], site['app_password'])
    url    = f"{base}/wp-json/wp/v2/posts"
    params = {
        'per_page': 100,
        'status':   'publish',
        '_fields':  'title,link',
        'orderby':  'date',
        'order':    'desc',
        'page':     1,
    }

    posts = []
    while True:
        try:
            r = requests.get(url, params=params, auth=auth, timeout=30)
            if r.status_code == 400:
                break
            if not r.ok:
                print(f"  ❌ 페이지 {params['page']} 오류: {r.status_code}")
                break

            batch = r.json()
            if not batch:
                break

            total_pages = int(r.headers.get('X-WP-TotalPages', 1))
            for p in batch:
                title = p.get('title', {}).get('rendered', '').strip()
                link  = p.get('link', '').strip()
                if title and link:
                    posts.append({'t': title, 'u': link})

            print(f"  페이지 {params['page']}/{total_pages} — {len(batch)}개 ({len(posts)}개 누적)")

            if params['page'] >= total_pages:
                break
            params['page'] += 1
            time.sleep(0.3)

        except Exception as e:
            print(f"  ❌ 수집 오류: {e}")
            break

    return posts


def main():
    with open(SITES_FILE, encoding='utf-8') as f:
        sites_list = json.load(f)
    sites = {s['name']: s for s in sites_list}

    # 기존 캐시 로드
    cache     = {}
    full_mode = True

    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding='utf-8') as f:
            cache = json.load(f)
        existing_total = sum(len(cache.get(n, [])) for n in SITES)
        if existing_total > 0:
            full_mode = False
            print(f"▶ 증분 업데이트 모드 (현재 캐시: {existing_total}개)")
        else:
            cache = {}
            print("▶ 전체 수집 모드 (캐시 비어있음)")
    else:
        print("▶ 전체 수집 모드 (최초 실행)")

    today       = datetime.now().strftime('%Y-%m-%d')
    added_total = 0

    for name in SITES:
        if name not in sites:
            print(f"⚠ {name} 설정 없음, 건너뜀")
            continue

        print(f"\n▶ {name} ({'전체' if full_mode else '증분'}) 수집 중...")

        if full_mode:
            new_posts   = fetch_all(sites[name])
            cache[name] = new_posts
            added_total += len(new_posts)
            print(f"  ✅ {name}: 총 {len(new_posts)}개")
        else:
            existing_urls = {p['u'] for p in cache.get(name, [])}
            new_posts     = fetch_incremental(sites[name], existing_urls)
            if new_posts:
                # 혹시 모를 중복 한 번 더 제거
                deduped     = [p for p in new_posts if p['u'] not in existing_urls]
                cache[name] = deduped + cache.get(name, [])
                added_total += len(deduped)
                print(f"  ✅ {name}: 신규 {len(deduped)}개 추가 → 누적 {len(cache[name])}개")
            else:
                print(f"  ✅ {name}: 신규 없음 → 누적 {len(cache.get(name, []))}개 유지")

    cache['updated_at'] = today

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, separators=(',', ':'))

    total   = sum(len(cache.get(n, [])) for n in SITES)
    size_kb = os.path.getsize(CACHE_FILE) // 1024
    mode_str = f"전체 {added_total}개" if full_mode else f"신규 {added_total}개 추가"
    print(f"\n✅ 완료 ({mode_str}) — 누적 총 {total}개 / {size_kb}KB")


if __name__ == '__main__':
    main()
