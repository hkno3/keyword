"""
대기 중인 블로그 포스트 일괄 발행 스크립트
사용법: python publish_all.py

- pending_posts.json 에서 status="pending" 인 글 전부 발행
- 발행 성공 시 keywords_history.json 자동 업데이트
- 발행 완료 항목은 status="published" 로 변경
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from wp_service import publish_post
from comfyui_service import generate_and_upload

PENDING_FILE  = os.path.join(script_dir, 'pending_posts.json')
HISTORY_FILE  = os.path.join(script_dir, 'keywords_history.json')
SITES_FILE    = os.path.join(script_dir, 'wp_sites.json')
CAT_MAP_FILE  = os.path.join(script_dir, 'category_map.json')

# 사이트 설정 로드
with open(SITES_FILE, encoding='utf-8') as f:
    sites_list = json.load(f)
sites = {s['name']: s for s in sites_list}

# 카테고리 맵 로드
with open(CAT_MAP_FILE, encoding='utf-8') as f:
    cat_map = json.load(f)

# 대기 목록 로드
with open(PENDING_FILE, encoding='utf-8') as f:
    posts = json.load(f)

# keywords_history 로드
with open(HISTORY_FILE, encoding='utf-8') as f:
    history = json.load(f)

pending = [p for p in posts if p.get('status') == 'pending']
print(f"발행 대기 중인 포스트: {len(pending)}개\n")


if not pending:
    print("발행할 포스트가 없습니다.")
    sys.exit(0)

for i, post in enumerate(pending, 1):
    keyword = post['keyword']
    site_name = post['site']
    title = post['title']

    print(f"[{i}/{len(pending)}] '{title}' → {site_name}.com 발행 중...")

    if site_name not in sites:
        print(f"  ❌ 알 수 없는 사이트: {site_name}, 건너뜀\n")
        continue

    site = sites[site_name]

    # 카테고리 ID 조회
    cat_name = post.get('category', '')
    cat_id = cat_map.get(site_name, {}).get(cat_name)
    if cat_id:
        print(f"  📂 카테고리: {cat_name} (ID: {cat_id})")
    else:
        print(f"  ⚠️  카테고리 '{cat_name}' 미매핑 → 미분류로 발행")

    # 글 작성 시점 사용 (created_at 없으면 현재 시간)
    post_date_str = post.get('created_at', datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))
    # KST(+09:00) 오프셋 명시 — 없으면 WordPress가 사이트 기본 timezone으로 해석해 9시간 오차 발생
    if 'T' in post_date_str and '+' not in post_date_str and not post_date_str.endswith('Z'):
        post_date_str += '+09:00'

    post_data = {
        'title': title,
        'content': post['content'],
        'meta_description': post.get('meta_description', ''),
        'focus_keyword': post.get('focus_keyword', keyword),
        'category_id': cat_id,
        'post_date': post_date_str,
    }

    try:
        result = publish_post(site, post_data, pub_status='draft')
    except Exception as e:
        print(f"  ❌ 발행 오류: {e}\n")
        continue

    if result and result.get('id'):
        post_id = result['id']
        post_url = result.get('link', f"https://{site_name}.com/?p={post_id}")
        print(f"  ✅ 성공! ID: {post_id} / URL: {post_url}")

        # 대표이미지 생성 (ComfyUI 실행 중일 때만 동작, 꺼져있으면 자동 건너뜀)
        generate_and_upload(
            site, keyword, post_id,
            title_en=post.get('title_en', ''),
            image_prompt=post.get('image_prompt'),
            thumbnail_lines=post.get('thumbnail_lines'),
            alt_text=post.get('title', keyword),
        )

        # pending_posts.json 상태 업데이트
        post['status'] = 'published'
        post['wp_post_id'] = post_id
        post['wp_url'] = post_url

        # keywords_history.json 업데이트
        if keyword in history:
            history[keyword]['published'] = True
            history[keyword].pop('queued', None)  # queued 플래그 제거
            history[keyword]['wp_post_id'] = post_id
            history[keyword]['wp_url'] = post_url
            print(f"  ✅ keywords_history.json 업데이트 완료")
        else:
            print(f"  ⚠️  '{keyword}' 키워드가 history에 없음 (수동 확인 필요)")
    else:
        print(f"  ❌ 발행 실패: {result}")

    print()
    if i < len(pending):
        time.sleep(2)  # 연속 발행 시 서버 부하 방지

# 파일 저장
with open(PENDING_FILE, 'w', encoding='utf-8') as f:
    json.dump(posts, f, ensure_ascii=False, indent=2)

with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
    json.dump(history, f, ensure_ascii=False, indent=2)

published_count = sum(1 for p in posts if p.get('status') == 'published' and p in pending)
print(f"=== 완료: {len([p for p in pending if p.get('wp_post_id')])}개 발행 성공 ===")
