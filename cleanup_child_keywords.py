"""
히스토리 정리 스크립트 (한 번만 실행)
1. 자식 키워드 중 별 5개 미만 삭제
2. 자식이 없는 부모 키워드 삭제
실행: python cleanup_child_keywords.py
"""
import json
import os

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "keywords_history.json")

with open(HISTORY_FILE, "r", encoding="utf-8") as f:
    history = json.load(f)

before = len(history)

# 1단계: 자식 키워드 중 별 5개 미만 삭제
child_deleted = [
    kw for kw, entry in history.items()
    if "parent_keyword" in entry and entry.get("star_count", 0) < 5
]
for kw in child_deleted:
    del history[kw]

# 2단계: 자식이 없는 부모 키워드 삭제
children_parents = {entry["parent_keyword"] for entry in history.values() if "parent_keyword" in entry}
parent_deleted = [
    kw for kw, entry in history.items()
    if entry.get("is_parent") and kw not in children_parents
]
for kw in parent_deleted:
    del history[kw]

with open(HISTORY_FILE, "w", encoding="utf-8") as f:
    json.dump(history, f, ensure_ascii=False, indent=2)

print(f"별 5개 미만 자식 삭제: {len(child_deleted)}개")
print(f"자식 없는 부모 삭제: {len(parent_deleted)}개")
print(f"남은 키워드: {len(history)}개 (전체 {before}개)")
