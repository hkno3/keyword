"""
각 WordPress 사이트의 카테고리 목록 조회
사용법: python fetch_categories.py
"""
import json
import os
import requests
from requests.auth import HTTPBasicAuth

script_dir = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(script_dir, 'wp_sites.json'), encoding='utf-8') as f:
    sites_list = json.load(f)

for site in sites_list:
    name = site['name']
    url  = site['url'].rstrip('/')
    auth = HTTPBasicAuth(site['username'], site['app_password'])

    print(f"\n{'='*40}")
    print(f"사이트: {name} ({url})")
    print(f"{'='*40}")

    r = requests.get(
        f"{url}/wp-json/wp/v2/categories",
        params={"per_page": 100, "hide_empty": False},
        auth=auth, timeout=10
    )

    if not r.ok:
        print(f"  ❌ 조회 실패: {r.status_code}")
        continue

    cats = r.json()
    for c in sorted(cats, key=lambda x: x['id']):
        print(f"  ID: {c['id']:4d}  |  슬러그: {c['slug']:30s}  |  이름: {c['name']}")

print("\n완료. 위 내용을 Claude에게 알려주세요.")
