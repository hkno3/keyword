"""
자식 키워드 중 별 5개 미만인 항목을 히스토리에서 삭제하는 일회성 스크립트.
실행: python cleanup_child_keywords.py
"""
import json
import os

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "keywords_history.json")

with open(HISTORY_FILE, "r", encoding="utf-8") as f:
    history = json.load(f)

before = len(history)
to_delete = [
    kw for kw, entry in history.items()
    if "parent_keyword" in entry and entry.get("star_count", 0) < 5
]

for kw in to_delete:
    del history[kw]

with open(HISTORY_FILE, "w", encoding="utf-8") as f:
    json.dump(history, f, ensure_ascii=False, indent=2)

print(f"삭제: {len(to_delete)}개 / 남은 키워드: {len(history)}개 (전체 {before}개)")
