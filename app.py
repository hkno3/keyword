import os
import re
import json
import time
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from groq import Groq

import naver_api
import claude_service
import gemini_service
import news_fetcher
import wp_service
import sitemap_service

load_dotenv()

CRAWLED_FILE = os.path.join(os.path.dirname(__file__), "crawled_links.txt")
_CRAWLED_FILE_OLD = os.path.join(os.path.dirname(__file__), "crawled_links.json")
KEYWORDS_HISTORY_FILE = os.path.join(os.path.dirname(__file__), "keywords_history.json")
KEYWORDS_BLACKLIST_FILE = os.path.join(os.path.dirname(__file__), "keywords_blacklist.json")
MEMO_FILE = os.path.join(os.path.dirname(__file__), "memo.txt")
PAGE_VIEWS_FILE = os.path.join(os.path.dirname(__file__), "page_views.json")
PAGE_VIEWS_DETAIL_FILE = os.path.join(os.path.dirname(__file__), "page_views_detail.json")
PAGE_VIEWS_SNAPSHOTS_DIR = os.path.join(os.path.dirname(__file__), "snapshots")
GROQ_USAGE_FILE = os.path.join(os.path.dirname(__file__), "groq_usage.json")
GEMINI_USAGE_FILE = os.path.join(os.path.dirname(__file__), "gemini_usage.json")
WP_SITES_FILE = os.path.join(os.path.dirname(__file__), "wp_sites.json")
SITEMAP_SOURCES_FILE = os.path.join(os.path.dirname(__file__), "sitemap_sources.json")

def _load_sitemap_sources() -> list:
    try:
        with open(SITEMAP_SOURCES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_sitemap_sources(sources: list):
    with open(SITEMAP_SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(sources, f, ensure_ascii=False, indent=2)

def _load_wp_sites() -> list:
    try:
        with open(WP_SITES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_wp_sites(sites: list):
    with open(WP_SITES_FILE, "w", encoding="utf-8") as f:
        json.dump(sites, f, ensure_ascii=False, indent=2)

def _load_groq_usage() -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    empty = {"date": today, "key1_tokens": 0, "key2_tokens": 0}
    try:
        with open(GROQ_USAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") != today:
            return empty
        # 구버전 마이그레이션
        if "tokens" in data and "key1_tokens" not in data:
            return {"date": today, "key1_tokens": data["tokens"], "key2_tokens": 0}
        return data
    except Exception:
        return empty

def _save_groq_usage(key1: int, key2: int):
    today = datetime.now().strftime("%Y-%m-%d")
    with open(GROQ_USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump({"date": today, "key1_tokens": key1, "key2_tokens": key2}, f)

def _add_groq_tokens(n: int):
    key_idx = st.session_state.get("groq_key_idx", 0)
    k1 = st.session_state.get("groq_key1_tokens", 0)
    k2 = st.session_state.get("groq_key2_tokens", 0)
    if key_idx == 0:
        k1 += n
        st.session_state.groq_key1_tokens = k1
    else:
        k2 += n
        st.session_state.groq_key2_tokens = k2
    st.session_state.groq_tokens = k1 + k2
    _save_groq_usage(k1, k2)

def _load_gemini_usage() -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(GEMINI_USAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") != today:
            return {"date": today, "calls": 0}
        return data
    except Exception:
        return {"date": today, "calls": 0}

def _add_gemini_call():
    today = datetime.now().strftime("%Y-%m-%d")
    st.session_state.gemini_calls = st.session_state.get("gemini_calls", 0) + 1
    with open(GEMINI_USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump({"date": today, "calls": st.session_state.gemini_calls}, f)

def _load_blacklist() -> dict:
    try:
        with open(KEYWORDS_BLACKLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_blacklist(bl: dict):
    with open(KEYWORDS_BLACKLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(bl, f, ensure_ascii=False, indent=2)

def _load_page_views() -> dict:
    try:
        with open(PAGE_VIEWS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _load_page_views_detail() -> dict:
    try:
        with open(PAGE_VIEWS_DETAIL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _load_snapshots() -> dict:
    """반환: {keyword: {date: {"baw": N, "biz": N}}}"""
    import csv
    result = {}
    if not os.path.exists(PAGE_VIEWS_SNAPSHOTS_DIR):
        return result
    for fname in sorted(os.listdir(PAGE_VIEWS_SNAPSHOTS_DIR)):
        if not fname.endswith(".csv"):
            continue
        date = fname[:-4]
        try:
            with open(os.path.join(PAGE_VIEWS_SNAPSHOTS_DIR, fname), "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    kw = row.get("키워드", "")
                    if not kw:
                        continue
                    result.setdefault(kw, {})[date] = {
                        "baw": int(row.get("baw", 0) or 0),
                        "biz": int(row.get("biz", 0) or 0),
                    }
        except Exception:
            pass
    return result

@st.dialog("📊 조회수 상세")
def _show_view_detail(kw: str, children: list, detail: dict):
    all_kws = [kw] + list(children)
    has_any = False
    for target_kw in all_kws:
        data = detail.get(target_kw, {})
        if not data:
            continue
        has_any = True
        st.markdown(f"**{target_kw}**")
        for sk, posts in data.items():
            site_name = {"baw": "bodyandwell", "biz": "bizachieve"}.get(sk, sk)
            st.caption(site_name)
            for p in sorted(posts, key=lambda x: x["count"], reverse=True):
                st.markdown(f"- {p['title']} — **{p['count']}회**")
    if not has_any:
        st.info("매칭된 포스트 없음")

def _get_view_str(kw: str, views: dict) -> str:
    v = views.get(kw)
    if not v:
        return ""
    baw = v.get("baw", 0)
    biz = v.get("biz", 0)
    parts = []
    if baw:
        parts.append(f"baw:{baw}")
    if biz:
        parts.append(f"biz:{biz}")
    return " ".join(parts)

def _load_keywords_history() -> dict:
    try:
        with open(KEYWORDS_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_keywords_history(history: dict):
    with open(KEYWORDS_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def _mark_keyword_published(kw: str):
    history = _load_keywords_history()
    if kw in history:
        history[kw]["published"] = True
        _save_keywords_history(history)

def _save_keywords_to_history(rows: list):
    history = _load_keywords_history()
    today = datetime.now().strftime("%Y-%m-%d")
    added = 0
    seen = set(history.keys())
    for row in rows:
        kw = row["keyword"] if isinstance(row, dict) else row
        if kw and kw not in seen:
            entry = {"first_found": today}
            if isinstance(row, dict):
                if "total_search" in row:
                    entry["total_search"] = row["total_search"]
                if "doc_count" in row:
                    entry["doc_count"] = row["doc_count"]
                if "mobile_ctr" in row:
                    entry["mobile_ctr"] = row["mobile_ctr"]
                if "stars" in row:
                    entry["star_count"] = len(row["stars"])
                if "comp_idx" in row:
                    entry["comp_idx"] = row["comp_idx"]
                if row.get("is_parent"):
                    entry["is_parent"] = True
                if row.get("parent_keyword"):
                    entry["parent_keyword"] = row["parent_keyword"]
            history[kw] = entry
            seen.add(kw)
            added += 1
    _save_keywords_history(history)
    st.session_state.keywords_history = history
    return added

def _load_crawled_links() -> set:
    result = set()
    # 구형 JSON 파일 자동 마이그레이션
    if os.path.exists(_CRAWLED_FILE_OLD):
        try:
            with open(_CRAWLED_FILE_OLD, "r", encoding="utf-8") as f:
                result = set(json.load(f))
            with open(CRAWLED_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(result))
            os.remove(_CRAWLED_FILE_OLD)
        except Exception:
            pass
        return result
    try:
        with open(CRAWLED_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    except Exception:
        return set()

def _save_crawled_link(link: str):
    with open(CRAWLED_FILE, "a", encoding="utf-8") as f:
        f.write(link + "\n")

st.set_page_config(page_title="수익형 키워드 분석기", page_icon="🔍", layout="wide")
st.title("🔍 수익형 키워드 분석기")
st.caption("뉴스 기사를 붙여넣으면 경쟁 낮은 블로그 키워드를 자동으로 찾아줍니다")

# ── 사이드바 ─────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ API 설정")
    groq_key = st.text_input(
        "Groq API Key 1",
        value=os.getenv("GROQ_API_KEY", ""),
        type="password",
        help="https://console.groq.com 에서 발급 (무료)",
    )
    groq_key2 = st.text_input(
        "Groq API Key 2 (한도 초과 시 자동 전환)",
        value=os.getenv("GROQ_API_KEY2", ""),
        type="password",
    )
    st.divider()
    gemini_key1 = st.text_input(
        "Gemini API Key 1",
        value=os.getenv("GEMINI_API_KEY_1", ""),
        type="password",
        help="Google AI Studio에서 발급 (무료)",
    )
    gemini_key2 = st.text_input(
        "Gemini API Key 2 (한도 초과 시 자동 전환)",
        value=os.getenv("GEMINI_API_KEY_2", ""),
        type="password",
    )
    st.divider()
    naver_ok = bool(os.getenv("NAVER_AD_API_KEY")) and bool(os.getenv("NAVER_CLIENT_ID"))
    if naver_ok:
        st.success("✅ 네이버 API 연결됨")
    else:
        st.error("❌ 네이버 API 키 없음")
    st.divider()
    crawled_count = len(_load_crawled_links())
    st.caption(f"크롤링 기록: {crawled_count}개 기사")
    if st.button("🗑️ 크롤링 기록 초기화"):
        for _f in [CRAWLED_FILE, _CRAWLED_FILE_OLD]:
            if os.path.exists(_f):
                os.remove(_f)
        st.session_state.auto_crawled = []
        st.rerun()
    st.divider()
    st.markdown(f"**🤖 Groq 사용량 (오늘 {datetime.now().strftime('%m/%d')})**")
    used_key = st.session_state.get("groq_key_idx", 0) + 1
    cur_tokens = st.session_state.get(f"groq_key{used_key}_tokens", 0)
    groq_pct = min(cur_tokens / 100000, 1.0)
    st.progress(groq_pct)
    st.caption(f"Key {used_key}: {cur_tokens:,} / 100,000 토큰 ({groq_pct*100:.1f}%)")
    k1 = st.session_state.get("groq_key1_tokens", 0)
    k2 = st.session_state.get("groq_key2_tokens", 0)
    if k2 > 0:
        st.caption(f"Key1: {k1:,} / Key2: {k2:,}")
    st.markdown(f"**✨ Gemini 사용량 (오늘 {datetime.now().strftime('%m/%d')})**")
    gemini_calls = st.session_state.get("gemini_calls", 0)
    gemini_pct = min(gemini_calls / 20, 1.0)
    st.progress(gemini_pct)
    st.caption(f"{gemini_calls} / 20회 ({gemini_pct*100:.0f}%)")
    gemini_key_used = st.session_state.get("gemini_key_used", "1")
    st.caption(f"현재 Key {gemini_key_used} 사용 중")
    st.markdown("**🔍 네이버 API 호출 (이번 세션)**")
    st.caption(f"검색광고: {st.session_state.get('naver_ad_calls', 0):,}회")
    st.caption(f"검색(문서수): {st.session_state.get('naver_search_calls', 0):,}회")
    st.divider()
    st.markdown("**📝 메모장**")
    try:
        with open(MEMO_FILE, "r", encoding="utf-8") as _mf:
            _memo_saved = _mf.read()
    except Exception:
        _memo_saved = ""
    _memo = st.text_area("메모", value=_memo_saved, height=450, label_visibility="collapsed", key="sidebar_memo", placeholder="여기에 메모하세요...")
    if _memo != _memo_saved:
        with open(MEMO_FILE, "w", encoding="utf-8") as _mf:
            _mf.write(_memo)
    st.divider()
    history = _load_keywords_history()
    st.caption(f"키워드 히스토리: {len(history)}개 키워드")
    st.download_button(
        "💾 히스토리 저장",
        data=json.dumps(history, ensure_ascii=False, indent=2),
        file_name=f"keywords_history_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
        mime="application/json",
        use_container_width=True,
    )
    uploaded = st.file_uploader("📂 히스토리 불러오기", type="json", key="hist_upload",
                                label_visibility="collapsed")
    if uploaded:
        try:
            imported = json.load(uploaded)
            merged = _load_keywords_history()
            added = 0
            for kw, val in imported.items():
                if kw not in merged:
                    merged[kw] = val
                    added += 1
            _save_keywords_history(merged)
            st.session_state.keywords_history = merged
            st.success(f"✅ {added}개 키워드 불러옴")
            st.rerun()
        except Exception as e:
            st.error(f"❌ {e}")
    if st.button("🗑️ 키워드 히스토리 초기화"):
        if os.path.exists(KEYWORDS_HISTORY_FILE):
            os.remove(KEYWORDS_HISTORY_FILE)
        st.session_state.keywords_history = {}
        st.rerun()
    if st.button("⬛ 발행됨 → 블랙리스트로 보내기", use_container_width=True):
        _bl = _load_blacklist()
        _h = _load_keywords_history()
        _moved = 0
        for kw, val in list(_h.items()):
            if kw == "__meta__":
                continue
            if val.get("published"):
                _bl[kw] = {"moved_at": datetime.now().strftime("%Y-%m-%d")}
                del _h[kw]
                _moved += 1
        _save_blacklist(_bl)
        _save_keywords_history(_h)
        st.session_state.keywords_history = _h
        st.success(f"✅ {_moved}개 블랙리스트로 이동")
        st.rerun()
    st.divider()
    st.markdown("**🗺️ 사이트맵**")
    sm_sources = _load_sitemap_sources()
    cached_urls = sitemap_service.load_cache()
    st.caption(f"캐시: {len(cached_urls)}개 URL | 소스: {len(sm_sources)}개")
    for i, src in enumerate(sm_sources):
        c1, c2, c3 = st.columns([4, 1, 1])
        with c1:
            st.markdown(f"**{src['name']}**")
            st.caption(src["url"][:40] + "..." if len(src["url"]) > 40 else src["url"])
        with c2:
            if st.button("🔄", key=f"sm_reload_{i}", help="이 시트만 업데이트"):
                with st.spinner("불러오는 중..."):
                    urls, err = sitemap_service.load_from_sheets(src["url"])
                if err:
                    st.error(f"❌ {err}")
                else:
                    # 기존 캐시에 병합
                    existing = sitemap_service.load_cache()
                    merged = list(dict.fromkeys(existing + urls))
                    sitemap_service.save_cache(merged)
                    st.success(f"✅ {len(urls)}개")
                    st.rerun()
        with c3:
            if st.button("🗑️", key=f"sm_del_{i}"):
                sm_sources.pop(i)
                _save_sitemap_sources(sm_sources)
                st.rerun()
    if sm_sources:
        if st.button("🔄 전체 업데이트", use_container_width=True, key="sm_reload_all"):
            all_urls = []
            for src in sm_sources:
                with st.spinner(f"{src['name']} 불러오는 중..."):
                    urls, err = sitemap_service.load_from_sheets(src["url"])
                if not err:
                    all_urls.extend(urls)
            merged = list(dict.fromkeys(all_urls))
            sitemap_service.save_cache(merged)
            st.success(f"✅ 총 {len(merged)}개 URL 저장됨")
            st.rerun()
    with st.expander("➕ 사이트맵 추가"):
        with st.form("sm_add_form"):
            sm_name = st.text_input("사이트명", placeholder="예: bodyandwell")
            sm_url = st.text_input("Google Sheets URL", placeholder="https://docs.google.com/spreadsheets/d/...")
            if st.form_submit_button("저장", use_container_width=True):
                if sm_name and sm_url:
                    sm_sources = _load_sitemap_sources()
                    sm_sources.append({"name": sm_name, "url": sm_url.strip()})
                    _save_sitemap_sources(sm_sources)
                    st.success(f"✅ {sm_name} 추가됨")
                    st.rerun()
                else:
                    st.error("모든 항목을 입력해주세요.")
    st.divider()
    st.markdown("**🌐 WordPress 사이트**")
    wp_sites = _load_wp_sites()
    if wp_sites:
        for i, site in enumerate(wp_sites):
            col_name, col_test, col_del = st.columns([4, 1, 1])
            with col_name:
                st.caption(f"**{site['name']}**  \n{site['url']}")
            with col_test:
                if st.button("🔌", key=f"wp_test_{i}", help="연결 테스트"):
                    with st.spinner("테스트 중..."):
                        ok, msg = wp_service.test_connection(site)
                    if ok:
                        st.success(f"✅ {msg}")
                    else:
                        st.error(f"❌ {msg}")
            with col_del:
                if st.button("🗑️", key=f"wp_del_{i}", help="삭제"):
                    wp_sites.pop(i)
                    _save_wp_sites(wp_sites)
                    st.rerun()
    else:
        st.caption("등록된 사이트 없음")
    with st.expander("➕ 사이트 추가"):
        with st.form("wp_add_form"):
            wp_name = st.text_input("사이트명", placeholder="예: bodyandwell")
            wp_url = st.text_input("URL", placeholder="https://bodyandwell.com")
            wp_user = st.text_input("아이디(이메일)")
            wp_pass = st.text_input("앱 비밀번호", type="password",
                                    help="WordPress 관리자 > 프로필 > 애플리케이션 비밀번호에서 생성")
            if st.form_submit_button("저장", use_container_width=True):
                if wp_name and wp_url and wp_user and wp_pass:
                    sites = _load_wp_sites()
                    sites.append({
                        "name": wp_name,
                        "url": wp_url.rstrip("/"),
                        "username": wp_user,
                        "app_password": wp_pass,
                    })
                    _save_wp_sites(sites)
                    st.success(f"✅ {wp_name} 저장됨")
                    st.rerun()
                else:
                    st.error("모든 항목을 입력해주세요.")
    st.divider()
    st.markdown(
        "**경쟁 강도 기준** (문서수 ÷ 검색량)\n"
        "- ⭐⭐⭐⭐⭐ 매우 낮음 `< 0.5`\n"
        "- ⭐⭐⭐⭐ 낮음 `0.5~1`\n"
        "- ⭐⭐⭐ 보통 `1~3`\n"
        "- ⭐⭐ 높음 `3~10`\n"
        "- ⭐ 매우 높음 `> 10`"
    )

# ── 뉴스 탭 ──────────────────────────────────────────────
st.subheader("📰 카테고리별 최신 뉴스")
탭건강, 탭부동산, 탭사업, 탭투자, 탭지원금, 탭보험, 탭대출, 탭법률, 탭세금, 탭육아, 탭여행, 탭반려, 탭생활 = st.tabs([
    "💊 건강", "🏠 부동산", "💼 사업", "📈 투자", "🏛️ 정부지원금",
    "🛡️ 보험", "💳 대출", "⚖️ 법률", "💰 세금", "👶 육아출산", "✈️ 여행", "🐾 반려동물", "🏪 생활정보",
])

for tab, category in [
    (탭건강, "건강"), (탭부동산, "부동산"), (탭사업, "사업"), (탭투자, "투자"), (탭지원금, "정부지원금"),
    (탭보험, "보험"), (탭대출, "대출"), (탭법률, "법률"), (탭세금, "세금"),
    (탭육아, "육아출산"), (탭여행, "여행"), (탭반려, "반려동물"), (탭생활, "생활정보"),
]:
    with tab:
        if st.button(f"{category} 뉴스 불러오기", key=f"load_{category}"):
            with st.spinner("뉴스 수집 중..."):
                st.session_state[f"news_{category}"] = news_fetcher.fetch_category_news(category, max_total=1000)
                st.session_state[f"news_{category}_show"] = 100

        articles = st.session_state.get(f"news_{category}", [])
        if articles:
            show_count = st.session_state.get(f"news_{category}_show", 100)
            visible = articles[:show_count]
            st.caption(f"{show_count}개 표시 중 / 총 {len(articles)}개")
            with st.container(height=600):
                for i, a in enumerate(visible):
                    col1, col2 = st.columns([8, 2])
                    with col1:
                        st.markdown(f"[{a['pubDate']}] [{a['title']}]({a['link']})")
                    with col2:
                        if st.button("이 기사 분석", key=f"analyze_{category}_{i}"):
                            with st.spinner("기사 본문 가져오는 중..."):
                                text = news_fetcher.scrape_article(a["link"])
                            if text:
                                st.session_state.article_text = text
                                st.rerun()
                            else:
                                st.warning("본문을 가져올 수 없어요. 직접 붙여넣기 해주세요.")
            if show_count < len(articles):
                if st.button(f"더 보기 (+50개)", key=f"more_{category}"):
                    st.session_state[f"news_{category}_show"] = show_count + 50
                    st.rerun()

st.divider()

# ── 함수 정의 ─────────────────────────────────────────────
CATEGORY_KEYWORDS = {
    "건강":     ["건강", "영양", "비타민", "운동", "질병", "식품", "효능", "증상", "치료", "약", "의료", "다이어트", "피부", "혈당", "혈압", "암", "당뇨", "관절", "면역", "장"],
    "부동산":   ["부동산", "아파트", "청약", "전세", "월세", "매매", "집값", "분양", "재건축", "임대", "토지", "상가"],
    "사업":     ["사업", "창업", "프랜차이즈", "소상공인", "자영업", "매출", "폐업", "법인", "스타트업"],
    "투자":     ["투자", "주식", "코인", "펀드", "ETF", "배당", "수익", "자산", "금리", "재테크"],
    "정부지원금": ["지원금", "보조금", "정부", "복지", "혜택", "신청", "지원", "수당", "바우처", "장려금"],
    "보험":     ["보험", "실손", "생명", "자동차보험", "화재", "암보험", "연금", "보장", "보험료"],
    "대출":     ["대출", "금리", "이자", "신용", "담보", "전세대출", "주택담보", "저금리", "대환"],
    "법률":     ["법률", "소송", "계약", "위자료", "손해배상", "이혼", "상속", "고소", "변호사", "판결"],
    "세금":     ["세금", "세율", "절세", "환급", "연말정산", "종합소득세", "부가세", "양도세", "증여세"],
    "육아출산": ["육아", "출산", "아기", "임신", "산후", "육아휴직", "어린이집", "유아", "태교", "신생아"],
    "여행":     ["여행", "호텔", "항공", "숙박", "관광", "투어", "패키지", "비자", "해외여행", "국내여행"],
    "반려동물": ["반려견", "반려묘", "강아지", "고양이", "펫", "동물병원", "사료", "훈련", "분양"],
    "생활정보": ["환불", "고객센터", "취소", "반품", "절약", "전기세", "가스비", "택배", "직구", "과태료", "재발급", "갱신", "해지", "신청", "방법", "수리", "AS", "사기"],
}

def _is_relevant_article(title: str, category: str) -> bool:
    kws = CATEGORY_KEYWORDS.get(category, [])
    if not kws:
        return True
    title_lower = title.lower()
    return any(kw in title_lower for kw in kws)

def _run_longtail(seed_keywords: list):
    customer_id = os.getenv("NAVER_AD_CUSTOMER_ID", "")
    ad_key = os.getenv("NAVER_AD_API_KEY", "")
    ad_secret = os.getenv("NAVER_AD_SECRET_KEY", "")
    naver_id = os.getenv("NAVER_CLIENT_ID", "")
    naver_secret = os.getenv("NAVER_CLIENT_SECRET", "")

    with st.spinner("자동완성 수집 중..."):
        ac_parent_map = {}  # {자식키워드: 부모키워드}
        for kw in seed_keywords:
            ac = naver_api.get_autocomplete(kw)
            for child in ac:
                if child not in ac_parent_map:
                    ac_parent_map[child] = kw
        ac_all = list(ac_parent_map.keys())

    if not ac_all:
        st.warning("자동완성 키워드를 찾을 수 없어요.")
        return

    with st.spinner(f"검색량 조회 중... ({len(ac_all)}개)"):
        related = naver_api.get_search_volumes_batch(ac_all, customer_id, ad_key, ad_secret)

    with st.spinner(f"문서수 조회 중... ({len(related)}개)"):
        doc_counts = naver_api.get_doc_counts_parallel(list(related.keys()), naver_id, naver_secret)

    table = naver_api.build_keyword_table(related, doc_counts)
    st.session_state.longtail_table = table
    st.session_state.longtail_parent_map = ac_parent_map

# ── 자동 키워드 찾기 ─────────────────────────────────────
st.subheader("🤖 자동 키워드 찾기")

for key in ["auto_keywords", "auto_crawled", "auto_running"]:
    if key not in st.session_state:
        st.session_state[key] = [] if key != "auto_running" else False
if "keywords_history" not in st.session_state:
    st.session_state.keywords_history = _load_keywords_history()
if "groq_tokens" not in st.session_state:
    _gu = _load_groq_usage()
    st.session_state.groq_key1_tokens = _gu["key1_tokens"]
    st.session_state.groq_key2_tokens = _gu["key2_tokens"]
    st.session_state.groq_tokens = _gu["key1_tokens"] + _gu["key2_tokens"]
if "gemini_calls" not in st.session_state:
    st.session_state.gemini_calls = _load_gemini_usage()["calls"]
if "gemini_key_used" not in st.session_state:
    st.session_state.gemini_key_used = "1"
for key in ["naver_ad_calls", "naver_search_calls"]:
    if key not in st.session_state:
        st.session_state[key] = 0
if "bulk_items" not in st.session_state:
    st.session_state.bulk_items = []
if "bulk_title_versions" not in st.session_state:
    st.session_state.bulk_title_versions = {}

crawled_file_links = _load_crawled_links()
groq_keys = [k for k in [groq_key, groq_key2] if k.strip()]

col_cat, col_source, col_num, col_search, col_stars, col_btn1, col_btn2 = st.columns([2, 1, 1, 1, 1, 1, 1])
with col_cat:
    auto_category = st.selectbox("카테고리", [
        "건강", "부동산", "사업", "투자", "정부지원금",
        "보험", "대출", "법률", "세금", "육아출산", "여행", "반려동물", "생활정보",
    ], label_visibility="collapsed")
with col_source:
    auto_source = st.selectbox("소스", ["블로그", "뉴스", "지식인", "카페", "웹문서"], label_visibility="collapsed")
with col_num:
    auto_target = st.number_input("찾을 키워드 수", min_value=1, value=5, step=1)
with col_search:
    auto_min_search = st.number_input("최소 검색량", min_value=0, value=1000, step=100,
                                       help="이 검색량 이상인 키워드만 문서수를 조회합니다 (API 절약)")
with col_stars:
    auto_min_stars = st.number_input("최소 별 개수", min_value=1, max_value=5, value=5, step=1)
with col_btn1:
    start_btn = st.button("🤖 자동 찾기", type="primary", use_container_width=True)
with col_btn2:
    stop_btn = st.button("⏹ 스탑", use_container_width=True)

if stop_btn:
    st.session_state.auto_running = False

# 분석한 기사 기록 표시
if st.session_state.auto_crawled:
    last = st.session_state.auto_crawled[-1]
    _last_pd = f"[{last['pubDate']}] " if last.get("pubDate") else ""
    st.caption(f"마지막 분석 기사: {_last_pd}{last['title']}")

auto_table_box = st.empty()

def _render_auto_table(keywords):
    if not keywords:
        return
    auto_df = pd.DataFrame([{
        "키워드": r["keyword"],
        "검색": f"https://search.naver.com/search.naver?query={r['keyword']}",
        "검색_PC": f"{r['pc_search']:,}",
        "검색_모바일": f"{r['mobile_search']:,}",
        "월검색(합계)": f"{r['total_search']:,}",
        "클릭_PC": f"{r['pc_click']:,}",
        "클릭_모바일": f"{r['mobile_click']:,}",
        "클릭률_PC": f"{r['pc_ctr']}%",
        "클릭률_모바일": f"{r['mobile_ctr']}%",
        "경쟁정도(AD)": r.get("comp_idx", "N/A"),
        "문서수": f"{r['doc_count']:,}",
        "경쟁 강도": r["level"],
        "추천도": r["stars"],
    } for r in keywords])
    with auto_table_box.container():
        st.success(f"✅ {len(keywords)}개 키워드 수집됨")
        st.dataframe(auto_df, hide_index=True, use_container_width=True,
                     column_config={"검색": st.column_config.LinkColumn("검색", display_text="🔍 네이버")})
        tsv = auto_df.to_csv(sep="\t", index=False).replace("`", "'").replace("\\", "\\\\")
        components.html(f"""
<button onclick="navigator.clipboard.writeText(`{tsv}`).then(()=>{{this.textContent='✅ 복사됨!';setTimeout(()=>this.textContent='📋 표 복사 (엑셀 붙여넣기용)',2000)}}).catch(()=>alert('복사 실패'))">📋 표 복사 (엑셀 붙여넣기용)</button>
<style>button{{padding:8px 20px;background:#ff4b4b;color:white;border:none;border-radius:6px;cursor:pointer;font-size:14px;font-family:sans-serif}}</style>
""", height=50)

_render_auto_table(st.session_state.auto_keywords)

if start_btn:
    if not groq_key:
        st.error("Groq API 키를 입력해주세요.")
    else:
        st.session_state.auto_running = True
        st.session_state.auto_keywords = []  # 매번 새로 시작
        groq_key_idx = 0
        groq_client = Groq(api_key=groq_keys[0])
        customer_id = os.getenv("NAVER_AD_CUSTOMER_ID", "")
        ad_key = os.getenv("NAVER_AD_API_KEY", "")
        ad_secret = os.getenv("NAVER_AD_SECRET_KEY", "")
        naver_id = os.getenv("NAVER_CLIENT_ID", "")
        naver_secret = os.getenv("NAVER_CLIENT_SECRET", "")

        # 기사 목록 (없으면 수집)
        _cache_key = f"{auto_source}_{auto_category}"
        if not st.session_state.get(_cache_key):
            with st.spinner(f"{auto_category} {auto_source} 수집 중..."):
                _fetch_map = {
                    "뉴스": news_fetcher.fetch_category_news,
                    "지식인": news_fetcher.fetch_category_kin,
                    "블로그": news_fetcher.fetch_category_blog,
                    "카페": news_fetcher.fetch_category_cafe,
                    "웹문서": news_fetcher.fetch_category_web,
                }
                st.session_state[_cache_key] = _fetch_map[auto_source](auto_category, max_total=1000)

        articles = st.session_state[_cache_key]
        crawled_links = _load_crawled_links()
        collected = list(st.session_state.auto_keywords)
        _existing_kws = set(_load_keywords_history().keys()) | set(_load_blacklist().keys())
        collected_kws = {r["keyword"] for r in collected} | _existing_kws

        status_box = st.empty()
        progress = st.progress(0)

        for article in articles:
            if not st.session_state.auto_running:
                break
            if len(collected) >= auto_target:
                break
            if article["link"] in crawled_links:
                continue

            # 제목 관련성 체크 (API 호출 없이)
            if not _is_relevant_article(article["title"], auto_category):
                continue

            status_box.info(f"🔍 [{article['pubDate']}] {article['title'][:50]}...")

            # 본문 확보 (뉴스: 크롤링, 나머지: API title+description 사용)
            if auto_source == "뉴스":
                text = news_fetcher.scrape_article(article["link"])
            else:
                text = f"{article['title']}\n{article.get('description', '')}".strip()
            _save_crawled_link(article["link"])
            crawled_links.add(article["link"])
            st.session_state.auto_crawled.append({"link": article["link"], "pubDate": article["pubDate"], "title": article["title"]})

            if not text:
                status_box.warning("⚠️ 본문 없음 → 다음 기사")
                continue

            # AI 씨드 추출
            try:
                seeds, tokens = claude_service.extract_seed_keywords(text, groq_client)
                _add_groq_tokens(tokens)
                st.session_state.groq_key_idx = groq_key_idx
                seeds = [s for s in seeds if len(s.strip()) >= 2]
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate_limit" in err_str.lower():
                    groq_key_idx += 1
                    if groq_key_idx < len(groq_keys):
                        groq_client = Groq(api_key=groq_keys[groq_key_idx])
                        st.session_state.groq_key_idx = groq_key_idx
                        status_box.warning(f"⚠️ Key {groq_key_idx} 한도 초과 → Key {groq_key_idx + 1}로 전환")
                        try:
                            seeds, tokens = claude_service.extract_seed_keywords(text, groq_client)
                            _add_groq_tokens(tokens)
                            seeds = [s for s in seeds if len(s.strip()) >= 2]
                        except Exception:
                            continue
                    else:
                        status_box.error("🚫 모든 Groq API 키 한도 초과. 내일 다시 시도하세요.")
                        st.session_state.auto_running = False
                        break
                else:
                    status_box.warning(f"⚠️ 씨드 추출 실패: {e}")
                    continue

            if not seeds:
                status_box.warning("⚠️ 씨드 키워드 없음 → 다음 기사")
                continue

            status_box.info(f"🌱 씨드: {', '.join(seeds[:5])}")

            # 자동완성
            autocomplete_kws = []
            for seed in seeds:
                ac = naver_api.get_autocomplete(seed)
                autocomplete_kws.extend(ac)
            autocomplete_kws = list(dict.fromkeys(autocomplete_kws))

            if not autocomplete_kws:
                autocomplete_kws = seeds

            # 검색량 조회
            related = naver_api.get_search_volumes_batch(autocomplete_kws, customer_id, ad_key, ad_secret)
            st.session_state.naver_ad_calls += len(autocomplete_kws)
            to_lookup = {k: v for k, v in related.items() if v["total_search"] >= auto_min_search}

            if not to_lookup:
                status_box.warning(f"⚠️ 검색량 {auto_min_search:,} 이상 키워드 없음 ({len(related)}개 조회) → 다음 기사")
                continue

            # 문서수 조회
            doc_counts = naver_api.get_doc_counts_parallel(list(to_lookup.keys()), naver_id, naver_secret)
            st.session_state.naver_search_calls += len(to_lookup)
            table = naver_api.build_keyword_table(to_lookup, doc_counts)

            # 최소 별 개수 + 클릭률 1% 이상 + 중복 제거
            all_stars = ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]
            valid_stars = set(all_stars[auto_min_stars - 1:])
            for r in table:
                if len(collected) >= auto_target:
                    break
                if r["stars"] in valid_stars and \
                   (r["pc_ctr"] >= 1 or r["mobile_ctr"] >= 1) and \
                   r["keyword"] not in collected_kws:
                    r["source_title"] = article["title"]
                    r["source_article"] = text[:2000]
                    collected.append(r)
                    collected_kws.add(r["keyword"])

            st.session_state.auto_keywords = collected
            progress.progress(min(len(collected) / auto_target, 1.0))
            _render_auto_table(collected)

        st.session_state.auto_running = False
        status_box.empty()
        progress.empty()
        if len(collected) >= auto_target:
            st.success(f"🎉 키워드 {len(collected)}개 수집 완료!")
        else:
            st.warning(f"기사를 다 돌았어요. {len(collected)}개 수집됨.")

        if collected:
            _run_longtail([r["keyword"] for r in collected])
            _parent_map = st.session_state.get("longtail_parent_map", {})
            child_rows = []
            if st.session_state.get("longtail_table"):
                for r in st.session_state.longtail_table:
                    if r.get("mobile_ctr", 0) >= 2 and r.get("stars", "") == "⭐⭐⭐⭐⭐":
                        child_row = dict(r)
                        parent_kw = _parent_map.get(r["keyword"])
                        if parent_kw:
                            child_row["parent_keyword"] = parent_kw
                        child_rows.append(child_row)

            # 자식이 있는 부모만 히스토리 저장
            parents_with_children = {r["parent_keyword"] for r in child_rows if "parent_keyword" in r}
            parents_to_save = [{**r, "is_parent": True} for r in collected if r["keyword"] in parents_with_children]
            if parents_to_save:
                _save_keywords_to_history(parents_to_save)
            if child_rows:
                added = _save_keywords_to_history(child_rows)
                st.success(f"✅ 모바일 클릭률 2% 이상 별 5개 키워드 {added}개 히스토리에 저장됐습니다.")
        st.rerun()

# ── 2차 검색: 황금 롱테일 키워드 ─────────────────────────
st.divider()
st.subheader("🔎 황금 롱테일 키워드 (2차 검색)")

if "longtail_table" not in st.session_state:
    st.session_state.longtail_table = []

col_lt1, col_lt2 = st.columns([3, 1])
with col_lt1:
    direct_lt_input = st.text_input("직접 키워드 입력 (쉼표로 구분)", placeholder="예: 근로장려금, 직장인대출", label_visibility="collapsed")
with col_lt2:
    direct_lt_btn = st.button("🔎 롱테일 찾기", use_container_width=True)

auto_lt_btn = st.button("⭐ 황금 키워드로 롱테일 찾기", use_container_width=True,
                         disabled=len(st.session_state.auto_keywords) == 0)

if auto_lt_btn:
    seed_kws = [r["keyword"] for r in st.session_state.auto_keywords]
    _run_longtail(seed_kws)
    st.rerun()

if direct_lt_btn:
    if direct_lt_input.strip():
        seed_kws = [k.strip() for k in direct_lt_input.split(",") if k.strip()]
        _run_longtail(seed_kws)
        st.rerun()
    else:
        st.warning("키워드를 입력해주세요.")

if st.session_state.longtail_table:
    lt_df = pd.DataFrame([{
        "키워드": r["keyword"],
        "검색": f"https://search.naver.com/search.naver?query={r['keyword']}",
        "검색_PC": f"{r['pc_search']:,}",
        "검색_모바일": f"{r['mobile_search']:,}",
        "월검색(합계)": f"{r['total_search']:,}",
        "클릭_PC": f"{r['pc_click']:,}",
        "클릭_모바일": f"{r['mobile_click']:,}",
        "클릭률_PC": f"{r['pc_ctr']}%",
        "클릭률_모바일": f"{r['mobile_ctr']}%",
        "경쟁정도(AD)": r.get("comp_idx", "N/A"),
        "문서수": f"{r['doc_count']:,}",
        "경쟁 강도": r["level"],
        "추천도": r["stars"],
    } for r in st.session_state.longtail_table])
    st.caption(f"총 {len(lt_df)}개 롱테일 키워드 | 경쟁 낮은 순 정렬")
    st.dataframe(lt_df, hide_index=True, use_container_width=True,
                 column_config={"검색": st.column_config.LinkColumn("검색", display_text="🔍 네이버")})
    tsv_lt = lt_df.to_csv(sep="\t", index=False).replace("`", "'").replace("\\", "\\\\")
    components.html(f"""
<button onclick="navigator.clipboard.writeText(`{tsv_lt}`).then(()=>{{this.textContent='✅ 복사됨!';setTimeout(()=>this.textContent='📋 표 복사 (엑셀 붙여넣기용)',2000)}}).catch(()=>alert('복사 실패'))">📋 표 복사 (엑셀 붙여넣기용)</button>
<style>button{{padding:8px 20px;background:#ff4b4b;color:white;border:none;border-radius:6px;cursor:pointer;font-size:14px;font-family:sans-serif}}</style>
""", height=50)

    if st.button("📥 히스토리에 저장", use_container_width=True):
        kws = [r for r in st.session_state.longtail_table if r.get("mobile_ctr", 0) >= 2]
        added = _save_keywords_to_history(kws)
        filtered_out = len(st.session_state.longtail_table) - len(kws)
        msg = f"✅ {added}개 저장됨 (모바일 클릭률 2% 이상)"
        if filtered_out:
            msg += f" | {filtered_out}개 제외됨 (클릭률 미달)"
        st.success(msg)
        st.rerun()

def _build_parent_groups(hist_kws: list, hist: dict):
    kw_set = set(hist_kws)
    direct_parent = {}

    # stored parent_keyword 우선
    for kw in hist_kws:
        p = hist[kw].get("parent_keyword", "")
        if p and p in kw_set:
            direct_parent[kw] = p

    # 자동 감지 (stored 없는 키워드만, 4글자 이상 후보)
    for child in hist_kws:
        if child in direct_parent:
            continue
        best = None
        for cand in hist_kws:
            if cand != child and len(cand) >= 2 and child.startswith(cand):
                if best is None or len(cand) > len(best):
                    best = cand
        if best:
            direct_parent[child] = best

    # 체인 따라 최상위 부모(root) 찾기
    def find_root(kw, depth=0):
        if depth > 20:
            return kw
        p = direct_parent.get(kw)
        if p is None:
            return kw
        return find_root(p, depth + 1)

    # 최상위 부모 기준으로 모두 귀속, 고아도 빈 자식으로 부모 그리드에 포함
    groups = {}
    for kw in hist_kws:
        root = find_root(kw)
        if root != kw:
            groups.setdefault(root, []).append(kw)
        else:
            groups.setdefault(kw, [])
    return groups


# ── 키워드 히스토리 ───────────────────────────────────────
st.divider()
st.subheader("📋 키워드 히스토리")

_hist = _load_keywords_history()
_blacklist = _load_blacklist()
_page_views = _load_page_views()
_pv_detail = _load_page_views_detail()
_hist_kws = sorted([kw for kw, v in _hist.items() if kw != "__meta__" and not v.get("excluded", False)])

if not _hist_kws:
    st.caption("키워드 히스토리가 없습니다. 위에서 황금 롱테일 키워드를 찾아주세요.")
else:
    st.caption(f"총 {len(_hist_kws)}개 황금 롱테일 키워드 (모바일 클릭률 2% 이상)")

    # ── 별 3,4개 부모 키워드 + 자식 키워드 일괄 삭제 (히스토리에서 완전 제거 → 추후 재등장 가능) ──
    _groups_for_del34 = _build_parent_groups(_hist_kws, _hist)
    _del34_pks = [pk for pk in _groups_for_del34 if _hist.get(pk, {}).get("star_count") in (3, 4)]
    if _del34_pks:
        _del34_total = sum(1 + len(_groups_for_del34[pk]) for pk in _del34_pks)
        if st.button(f"🗑️ 별 3,4개 부모 키워드 일괄 삭제 (부모 {len(_del34_pks)}개 + 자식 포함 총 {_del34_total}개)", key="hist_del34_btn"):
            for _pk34 in _del34_pks:
                for _kw34 in [_pk34] + _groups_for_del34[_pk34]:
                    _hist.pop(_kw34, None)
            _save_keywords_history(_hist)
            st.toast(f"✅ {_del34_total}개 키워드 히스토리에서 삭제 완료! (다음 자동 찾기에서 다시 발견되면 재등장)")
            st.rerun()

    # ── 누적 조회수 TOP 50 / 오늘 조회수 TOP 50 ──────────────────────────────────────
    def _build_top_data(kws, views, baw_key, biz_key):
        data = []
        for kw in kws:
            v = views.get(kw, {})
            baw = v.get(baw_key, 0)
            biz = v.get(biz_key, 0)
            total = baw + biz
            if total == 0:
                continue
            vs = " ".join(p for p in [f"baw:{baw}" if baw else "", f"biz:{biz}" if biz else ""] if p)
            ts = _hist[kw].get("total_search", "")
            dc = _hist[kw].get("doc_count", "")
            ctr = _hist[kw].get("mobile_ctr", "")
            sc = _hist[kw].get("star_count", "")
            ci = _hist[kw].get("comp_idx", "")
            stat = "|".join(s for s in [str(ts), str(dc), f"{ctr:.2f}" if ctr != "" else "", f"⭐{sc}" if sc != "" else "", ci] if s)
            data.append((kw, total, stat, vs))
        data.sort(key=lambda x: x[1], reverse=True)
        return data

    def _render_top50(data, key_prefix, pv_detail, children_map):
        top50 = data[:50]
        c1, c2, c3 = st.columns(3)
        per = 17
        for col, offset in zip([c1, c2, c3], [0, 17, 34]):
            with col:
                for i, (kw, total, stat, vs) in enumerate(top50[offset:offset+per]):
                    tm1, tm2 = st.columns([5, 1])
                    with tm1:
                        st.markdown(f'<p style="margin:2px 0;font-size:0.82em;"><b>{offset+i+1}. {kw}</b>&nbsp;<span style="color:#888;">{stat}</span>&nbsp;<span style="color:#4fc3f7;">{vs}</span></p>', unsafe_allow_html=True)
                    with tm2:
                        if st.button("📊", key=f"{key_prefix}_{offset+i}", help="매칭 포스트 보기"):
                            _show_view_detail(kw, children_map.get(kw, []), pv_detail)

    _cum_data = _build_top_data(_hist_kws, _page_views, "baw", "biz")
    _today_data = _build_top_data(_hist_kws, _page_views, "today_baw", "today_biz")

    if _cum_data:
        _cum_baw = sum(_page_views.get(k, {}).get("baw", 0) for k, _, _, _ in _cum_data[:50])
        _cum_biz = sum(_page_views.get(k, {}).get("biz", 0) for k, _, _, _ in _cum_data[:50])
        _first_dates = [_page_views.get(k, {}).get("first_tracked", "") for k, _, _, _ in _cum_data[:50]]
        _first_dates = [d for d in _first_dates if d]
        _since_str = f"  |  {min(_first_dates)}~" if _first_dates else ""
        with st.expander(f"👁 누적 조회수 TOP 50  |  baw:{_cum_baw}  biz:{_cum_biz}{_since_str}", expanded=False):
            _render_top50(_cum_data, "cum_vd", _pv_detail, {})

    if _today_data:
        _today_baw = sum(_page_views.get(k, {}).get("today_baw", 0) for k, _, _, _ in _today_data[:50])
        _today_biz = sum(_page_views.get(k, {}).get("today_biz", 0) for k, _, _, _ in _today_data[:50])
        with st.expander(f"🌅 오늘 조회수 TOP 50  |  baw:{_today_baw}  biz:{_today_biz}", expanded=False):
            _render_top50(_today_data, "today_vd", _pv_detail, {})
    _snapshots = _load_snapshots()
    if _snapshots:
        with st.expander("📈 스냅샷 분석", expanded=False):
            import pandas as pd
            _snap_kws = sorted(_snapshots.keys(), key=lambda k: sum(v["baw"] + v["biz"] for v in _snapshots[k].values()), reverse=True)
            _snap_mode = st.radio("보기", ["TOP 30", "전부보기"], horizontal=True, label_visibility="collapsed", key="snap_mode")
            _snap_kws_show = _snap_kws[:30] if _snap_mode == "TOP 30" else _snap_kws
            _sel_kw = st.selectbox("키워드 선택", _snap_kws_show, key="snap_sel_kw")
            if _sel_kw:
                _kw_data = _snapshots[_sel_kw]
                _dates = sorted(_kw_data.keys())
                _df = pd.DataFrame([{"날짜": d, "baw": _kw_data[d]["baw"], "biz": _kw_data[d]["biz"]} for d in _dates]).set_index("날짜")
                st.line_chart(_df)

    # ── 현재 페이지 키워드 미리 계산 (버튼에서 사용) ──────────────────────────────────────
    _groups_pre = _build_parent_groups(_hist_kws, _hist)
    _sort_pre = st.session_state.get("hist_sort", "별점 높은 순")
    if _sort_pre == "검색량 높은 순":
        _pk_list_pre = sorted(_groups_pre.keys(), key=lambda k: _hist[k].get("total_search", 0), reverse=True)
    elif _sort_pre == "문서수 낮은 순":
        _pk_list_pre = sorted(_groups_pre.keys(), key=lambda k: _hist[k].get("doc_count", 9999999))
    elif _sort_pre == "모바일 클릭률 높은 순":
        _pk_list_pre = sorted(_groups_pre.keys(), key=lambda k: _hist[k].get("mobile_ctr", 0), reverse=True)
    elif _sort_pre == "별점 높은 순":
        _pk_list_pre = sorted(_groups_pre.keys(), key=lambda k: _hist[k].get("star_count", 0), reverse=True)
    elif _sort_pre == "매우높음+검색량 높은 순":
        _comp_rank = {"매우높음": 5, "높음": 4, "보통": 3, "낮음": 2, "매우낮음": 1}
        _pk_list_pre = sorted(_groups_pre.keys(), key=lambda k: (
            _comp_rank.get(_hist[k].get("comp_idx", ""), 0),
            _hist[k].get("total_search", 0)
        ), reverse=True)
    else:
        _pk_list_pre = sorted(_groups_pre.keys())
    _PAGE_SIZE_PRE = 100
    _cur_page_pre = st.session_state.get("hist_page", 0)
    _pk_page_pre = _pk_list_pre[_cur_page_pre * _PAGE_SIZE_PRE : (_cur_page_pre + 1) * _PAGE_SIZE_PRE]
    _page_all_kws = []
    for _ppk in _pk_page_pre:
        _page_all_kws.append(_ppk)
        _page_all_kws.extend(_groups_pre.get(_ppk, []))

    col_selall, col_desel, col_stat, col_stat_reset, col_views, col_snap, col_sort, col_expand = st.columns([2, 2, 3, 1, 3, 2, 4, 2])
    with col_selall:
        if st.button("전체 선택", use_container_width=True):
            for kw in _hist_kws:
                st.session_state[f"hist_chk_{kw}"] = True
            st.rerun()
    with col_desel:
        if st.button("선택 해제", use_container_width=True):
            for kw in _hist_kws:
                st.session_state[f"hist_chk_{kw}"] = False
            st.rerun()
    with col_stat:
        _last_stat_update = _hist.get("__meta__", {}).get(f"last_stat_update_p{_cur_page_pre}")
        _stat_days_left = 0
        if _last_stat_update:
            _stat_elapsed = (datetime.now() - datetime.strptime(_last_stat_update, "%Y-%m-%d")).days
            _stat_days_left = max(0, 30 - _stat_elapsed)
        _stat_btn_disabled = _stat_days_left > 0
        _stat_btn_label = f"📊 통계 갱신 ({_stat_days_left}일 후)" if _stat_days_left else f"📊 통계 갱신 ({len(_page_all_kws)}개)"
        if st.button(_stat_btn_label, use_container_width=True, disabled=_stat_btn_disabled):
            _naver_cid = os.getenv("NAVER_AD_CUSTOMER_ID", "")
            _naver_akey = os.getenv("NAVER_AD_API_KEY", "")
            _naver_skey = os.getenv("NAVER_AD_SECRET_KEY", "")
            _naver_client_id = os.getenv("NAVER_CLIENT_ID", "")
            _naver_client_secret = os.getenv("NAVER_CLIENT_SECRET", "")
            _update_targets = _page_all_kws
            with st.spinner(f"통계 조회 중... ({len(_update_targets)}개)"):
                _vol_data = naver_api.get_search_volumes_batch(_update_targets, _naver_cid, _naver_akey, _naver_skey)
                _doc_data = naver_api.get_doc_counts_parallel(_update_targets, _naver_client_id, _naver_client_secret)
            _updated = 0
            for kw in _update_targets:
                vol = _vol_data.get(kw, {})
                doc = _doc_data.get(kw, 0)
                if vol:
                    _hist[kw]["total_search"] = vol.get("total_search", 0)
                    _hist[kw]["doc_count"] = doc
                    _hist[kw]["mobile_ctr"] = vol.get("mobile_ctr", 0)
                    _, stars, _ = naver_api.competition_level(vol.get("total_search", 0), doc)
                    _hist[kw]["star_count"] = len(stars)
                    if vol.get("comp_idx"):
                        _hist[kw]["comp_idx"] = vol["comp_idx"]
                    _updated += 1
            if "__meta__" not in _hist:
                _hist["__meta__"] = {}
            _hist["__meta__"][f"last_stat_update_p{_cur_page_pre}"] = datetime.now().strftime("%Y-%m-%d")
            _save_keywords_history(_hist)
            st.session_state.keywords_history = _hist
            st.success(f"✅ {_updated}개 키워드 통계 업데이트 완료!")
            st.rerun()
    with col_stat_reset:
        if st.button("🔄", use_container_width=True, help="통계 갱신 타이머 초기화"):
            if "__meta__" in _hist:
                _hist["__meta__"].pop(f"last_stat_update_p{_cur_page_pre}", None)
            _save_keywords_history(_hist)
            st.session_state.keywords_history = _hist
            st.rerun()
    with col_views:
        if st.button("👁 조회수 가져오기", use_container_width=True):
            _wp_sites = _load_wp_sites()
            _site_keys = {"bodyandwell": "baw", "bizachieve": "biz"}
            _views = _load_page_views()
            _updated = 0
            _processed_sks = []
            for _ws in _wp_sites:
                _sk = next((v for k, v in _site_keys.items() if k in _ws.get("url", "").lower() or k in _ws.get("name", "").lower()), None)
                if not _sk:
                    continue
                with st.spinner(f"{_ws.get('name','사이트')} 조회수 가져오는 중..."):
                    _fetched, _fetched_today, _fetched_detail = wp_service.fetch_post_views(_ws, _sk, _hist_kws)
                # 오늘 조회수 먼저 전체 0으로 초기화
                for _kw in _views:
                    _views[_kw][f"today_{_sk}"] = 0
                for _kw, _cnt in _fetched.items():
                    _is_new = _kw not in _views
                    if _is_new:
                        _views[_kw] = {"baw": 0, "biz": 0, "today_baw": 0, "today_biz": 0, "last_updated": "", "first_tracked": datetime.now().strftime("%Y-%m-%d")}
                    elif "first_tracked" not in _views[_kw]:
                        _views[_kw]["first_tracked"] = datetime.now().strftime("%Y-%m-%d")
                    _views[_kw][_sk] = _cnt
                    _views[_kw]["last_updated"] = datetime.now().strftime("%Y-%m-%d")
                    _updated += 1
                for _kw, _cnt in _fetched_today.items():
                    if _kw not in _views:
                        _views[_kw] = {"baw": 0, "biz": 0, "today_baw": 0, "today_biz": 0, "last_updated": ""}
                    _views[_kw][f"today_{_sk}"] = _cnt
                _detail_all = _load_page_views_detail()
                for _kw, _posts in _fetched_detail.items():
                    if _kw not in _detail_all:
                        _detail_all[_kw] = {}
                    _detail_all[_kw][_sk] = _posts
                with open(PAGE_VIEWS_DETAIL_FILE, "w", encoding="utf-8") as _pvdf:
                    json.dump(_detail_all, _pvdf, ensure_ascii=False, indent=2)
            with open(PAGE_VIEWS_FILE, "w", encoding="utf-8") as _pvf:
                json.dump(_views, _pvf, ensure_ascii=False, indent=2)
            st.toast(f"✅ {_updated}개 키워드 조회수 업데이트!")
            st.rerun()
    with col_snap:
        import csv, os as _os
        _today = datetime.now().strftime("%Y-%m-%d")
        _os.makedirs(PAGE_VIEWS_SNAPSHOTS_DIR, exist_ok=True)
        _snap_file = _os.path.join(PAGE_VIEWS_SNAPSHOTS_DIR, f"{_today}.csv")
        _snap_already = _os.path.exists(_snap_file)
        _snap_label = "📸 저장완료" if _snap_already else "📸 스냅샷"
        if st.button(_snap_label, use_container_width=True, disabled=_snap_already, help="하루 1회 저장 가능"):
            _snap_views = _load_page_views()
            with open(_snap_file, "w", newline="", encoding="utf-8-sig") as _cf:
                _w = csv.writer(_cf)
                _w.writerow(["날짜", "키워드", "baw", "biz"])
                for _kw, _v in sorted(_snap_views.items()):
                    _w.writerow([_today, _kw, _v.get("baw", 0), _v.get("biz", 0)])
            st.toast(f"✅ {len(_snap_views)}개 키워드 스냅샷 저장 완료!")
    with col_sort:
        _sort_options = ["가나다순", "검색량 높은 순", "문서수 낮은 순", "모바일 클릭률 높은 순", "별점 높은 순", "매우높음+검색량 높은 순"]
        if "hist_sort" not in st.session_state:
            st.session_state["hist_sort"] = "매우높음+검색량 높은 순"
        _prev_sort = st.session_state.get("hist_sort_prev", "별점 높은 순")
        _sort_by = st.selectbox("정렬", _sort_options, label_visibility="collapsed", key="hist_sort")
        if _sort_by != _prev_sort:
            st.session_state["hist_sort_prev"] = _sort_by
            st.session_state["hist_page"] = 0
    with col_expand:
        _all_exp = st.session_state.get("hist_all_expand", False)
        if st.button("📂 모두 접기" if _all_exp else "📂 모두 펼치기", use_container_width=True):
            _new_exp = not _all_exp
            st.session_state["hist_all_expand"] = _new_exp
            if not _new_exp:
                for _k in list(st.session_state.keys()):
                    if _k.startswith("hist_grp_exp_"):
                        del st.session_state[_k]
            st.rerun()

    if _sort_by == "검색량 높은 순":
        _hist_kws = sorted(_hist_kws, key=lambda k: _hist[k].get("total_search", 0), reverse=True)
    elif _sort_by == "문서수 낮은 순":
        _hist_kws = sorted(_hist_kws, key=lambda k: _hist[k].get("doc_count", 9999999))
    elif _sort_by == "모바일 클릭률 높은 순":
        _hist_kws = sorted(_hist_kws, key=lambda k: _hist[k].get("mobile_ctr", 0), reverse=True)
    elif _sort_by == "별점 높은 순":
        _hist_kws = sorted(_hist_kws, key=lambda k: _hist[k].get("star_count", 0), reverse=True)

    st.markdown("""<style>
div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stHorizontalBlock"] {
    margin-bottom: -18px;
    align-items: center;
}
div[data-testid="stVerticalBlockBorderWrapper"] .stCheckbox {
    margin-top: 6px;
}
div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="element-container"] p {
    margin: 0; line-height: 1.3;
}
div[data-testid="stVerticalBlockBorderWrapper"] .stButton > button {
    padding: 1px 7px; min-height: 0; height: 22px;
    font-size: 11px; line-height: 1;
}
</style>""", unsafe_allow_html=True)
    _groups = _build_parent_groups(_hist_kws, _hist)

    with st.container(height=600):
        # 부모 그룹 — 정렬 적용 후 3열 그리드
        if _sort_by == "검색량 높은 순":
            _pk_list = sorted(_groups.keys(), key=lambda k: _hist[k].get("total_search", 0), reverse=True)
        elif _sort_by == "문서수 낮은 순":
            _pk_list = sorted(_groups.keys(), key=lambda k: _hist[k].get("doc_count", 9999999))
        elif _sort_by == "모바일 클릭률 높은 순":
            _pk_list = sorted(_groups.keys(), key=lambda k: _hist[k].get("mobile_ctr", 0), reverse=True)
        elif _sort_by == "별점 높은 순":
            _pk_list = sorted(_groups.keys(), key=lambda k: _hist[k].get("star_count", 0), reverse=True)
        else:
            _pk_list = sorted(_groups.keys())

        _PAGE_SIZE = 30 if _all_exp else 100
        _total_pks = len(_pk_list)
        _total_pages = max(1, (_total_pks + _PAGE_SIZE - 1) // _PAGE_SIZE)
        _cur_page = st.session_state.get("hist_page", 0)
        if _cur_page >= _total_pages:
            _cur_page = 0
            st.session_state["hist_page"] = 0
        _pk_list_page = _pk_list[_cur_page * _PAGE_SIZE : (_cur_page + 1) * _PAGE_SIZE]

        for _row_s in range(0, len(_pk_list_page), 3):
            _row_pks = _pk_list_page[_row_s:_row_s + 3]
            _grid = st.columns(3)
            for _j in range(3):
                with _grid[_j]:
                    if _j >= len(_row_pks):
                        break
                    _pk = _row_pks[_j]
                    _pk_ch = sorted(_groups[_pk])
                    _pk_pub = _hist[_pk].get("published", False)
                    _pk_ts = _hist[_pk].get("total_search", "")
                    _pk_dc = _hist[_pk].get("doc_count", "")
                    _pk_ctr = _hist[_pk].get("mobile_ctr", "")
                    _pk_ctr_s = f"{_pk_ctr:.2f}" if _pk_ctr != "" else ""
                    _pk_sc = _hist[_pk].get("star_count", "")
                    _pk_star_s = f"⭐{_pk_sc}" if _pk_sc != "" else ""
                    _pk_vs = _get_view_str(_pk, _page_views)
                    _pk_ci = _hist[_pk].get("comp_idx", "")
                    _pk_stat = "|".join(s for s in [str(_pk_ts), str(_pk_dc), _pk_ctr_s, _pk_star_s, _pk_ci] if s) if _pk_ts != "" else ""
                    if _pk_vs:
                        _pk_stat = (_pk_stat + "|" if _pk_stat else "") + _pk_vs
                    _pk_exp = st.session_state.get(f"hist_grp_exp_{_pk}", _all_exp)
                    pc1, pc2, pc3, pc4, pc5 = st.columns([1, 5, 1, 1, 1])
                    with pc1:
                        st.checkbox("", key=f"hist_chk_{_pk}", label_visibility="collapsed")
                    with pc2:
                        _pk_in_bl = _pk in _blacklist
                        if _pk_pub:
                            st.markdown(f'<p style="color:#999;margin:0;font-size:0.80em;">✅ {_pk}&nbsp;<span style="color:#4caf50;">발행됨</span>' + (f'&nbsp;<span style="color:#bbb;">{_pk_stat}</span>' if _pk_stat else "") + f'&nbsp;<span style="color:#555;font-size:0.80em;">({len(_pk_ch)})</span></p>', unsafe_allow_html=True)
                        elif _pk_in_bl:
                            st.markdown(f'<p style="color:#f44336;margin:0;font-size:0.84em;"><b>📁 {_pk}</b>' + (f'&nbsp;<span style="color:#ef9a9a;">{_pk_stat}</span>' if _pk_stat else "") + f'&nbsp;<span style="color:#e57373;font-size:0.80em;">({len(_pk_ch)}) ⚠️중복</span></p>', unsafe_allow_html=True)
                        else:
                            st.markdown(f'<p style="margin:0;font-size:0.84em;"><b>📁 {_pk}</b>' + (f'&nbsp;<span style="color:#888;">{_pk_stat}</span>' if _pk_stat else "") + f'&nbsp;<span style="color:#666;font-size:0.80em;">({len(_pk_ch)})</span></p>', unsafe_allow_html=True)
                    with pc3:
                        if st.button("▼" if _pk_exp else "↓", key=f"hist_btn_{_pk}"):
                            st.session_state[f"hist_grp_exp_{_pk}"] = not _pk_exp
                            st.rerun()
                    with pc4:
                        _pk_pub_t = st.checkbox("", key=f"hist_pub_{_pk}", value=_pk_pub, label_visibility="collapsed", help="수동 발행")
                        if _pk_pub_t != _pk_pub:
                            _hist[_pk]["published"] = _pk_pub_t
                            _save_keywords_history(_hist)
                            st.rerun()
                    with pc5:
                        if st.button("✕", key=f"hist_del_{_pk}"):
                            today = datetime.now().strftime("%Y-%m-%d")
                            _hist[_pk]["excluded"] = True
                            _hist[_pk]["excluded_at"] = today
                            _hist[_pk]["exclude_reason"] = "published" if _hist[_pk].get("published") else "deleted"
                            _save_keywords_history(_hist)
                            st.rerun()
                    if _pk_exp:
                        for _ck in _pk_ch:
                            if _ck not in _hist:
                                continue
                            _ck_pub = _hist[_ck].get("published", False)
                            _ck_ts = _hist[_ck].get("total_search", "")
                            _ck_dc = _hist[_ck].get("doc_count", "")
                            _ck_ctr = _hist[_ck].get("mobile_ctr", "")
                            _ck_ctr_s = f"{_ck_ctr:.2f}" if _ck_ctr != "" else ""
                            _ck_sc = _hist[_ck].get("star_count", "")
                            _ck_star_s = f"⭐{_ck_sc}" if _ck_sc != "" else ""
                            _ck_vs = _get_view_str(_ck, _page_views)
                            _ck_ci = _hist[_ck].get("comp_idx", "")
                            _ck_stat = "|".join(s for s in [str(_ck_ts), str(_ck_dc), _ck_ctr_s, _ck_star_s, _ck_ci] if s) if _ck_ts != "" else ""
                            if _ck_vs:
                                _ck_stat = (_ck_stat + "|" if _ck_stat else "") + _ck_vs
                            cc1, cc2, cc3 = st.columns([1, 7, 1])
                            with cc1:
                                st.checkbox("", key=f"hist_chk_{_ck}", label_visibility="collapsed")
                            with cc2:
                                _ck_in_bl = _ck in _blacklist
                                if _ck_pub:
                                    st.markdown(f'<p style="margin:0 0 0 10px;font-size:0.76em;color:#999;">└ ✅ {_ck}' + (f'&nbsp;<span style="color:#bbb;">{_ck_stat}</span>' if _ck_stat else "") + '</p>', unsafe_allow_html=True)
                                elif _ck_in_bl:
                                    st.markdown(f'<p style="margin:0 0 0 10px;font-size:0.76em;color:#f44336;">└ <b>{_ck}</b>' + (f'&nbsp;<span style="color:#ef9a9a;">{_ck_stat}</span>' if _ck_stat else "") + ' ⚠️중복</p>', unsafe_allow_html=True)
                                else:
                                    st.markdown(f'<p style="margin:0 0 0 10px;font-size:0.76em;">└ <b>{_ck}</b>' + (f'&nbsp;<span style="color:#888;">{_ck_stat}</span>' if _ck_stat else "") + '</p>', unsafe_allow_html=True)
                            with cc3:
                                _ck_pub_t = st.checkbox("", key=f"hist_pub_{_ck}", value=_ck_pub, label_visibility="collapsed", help="수동 발행")
                                if _ck_pub_t != _ck_pub:
                                    _hist[_ck]["published"] = _ck_pub_t
                                    _save_keywords_history(_hist)
                                    st.rerun()
    _pp1, _pp2, _pp3 = st.columns([1, 3, 1])
    with _pp1:
        if _cur_page > 0 and st.button("◀ 이전", use_container_width=True):
            st.session_state["hist_page"] = _cur_page - 1
            st.rerun()
    with _pp2:
        _page_child_cnt = sum(len(_groups.get(pk, [])) for pk in _pk_list_page)
        st.caption(f"페이지 {_cur_page + 1} / {_total_pages}  (부모 {_cur_page * _PAGE_SIZE + 1}~{min((_cur_page + 1) * _PAGE_SIZE, _total_pks)} / {_total_pks}개  |  자식 {_page_child_cnt}개  |  합계 {len(_pk_list_page) + _page_child_cnt}개)")
    with _pp3:
        if _cur_page < _total_pages - 1 and st.button("다음 ▶", use_container_width=True):
            st.session_state["hist_page"] = _cur_page + 1
            st.rerun()

    if _pk_list_page:
        _page_total_del = len(_pk_list_page) + _page_child_cnt
        if st.button(f"🗑️ 현재 페이지 키워드 일괄 삭제 (부모 {len(_pk_list_page)}개 + 자식 {_page_child_cnt}개 = {_page_total_del}개)", key="hist_del_page_btn"):
            for _pk_d in _pk_list_page:
                for _kw_d in [_pk_d] + _groups.get(_pk_d, []):
                    _hist.pop(_kw_d, None)
            _save_keywords_history(_hist)
            st.toast(f"✅ 현재 페이지 {_page_total_del}개 키워드 히스토리에서 삭제 완료!")
            st.rerun()

    _excluded_kws = sorted([kw for kw, v in _hist.items() if v.get("excluded", False)])
    if _excluded_kws:
        with st.expander(f"🚫 제외 목록 ({len(_excluded_kws)}개)"):
            for exc_kw in _excluded_kws:
                exc_data = _hist[exc_kw]
                reason = "✅ 발행됨" if exc_data.get("published") else "삭제"
                ec1, ec2, ec3 = st.columns([5, 2, 1])
                with ec1:
                    st.caption(exc_kw)
                with ec2:
                    st.caption(reason)
                with ec3:
                    if st.button("↩", key=f"exc_restore_{exc_kw}", help="히스토리로 복원"):
                        _hist[exc_kw].pop("excluded", None)
                        _hist[exc_kw].pop("excluded_at", None)
                        _hist[exc_kw].pop("exclude_reason", None)
                        _save_keywords_history(_hist)
                        st.rerun()

    selected_kws_for_gen = [kw for kw in _hist_kws if st.session_state.get(f"hist_chk_{kw}")]
    n_sel = len(selected_kws_for_gen)

    if st.button(f"📝 제목 만들기 ({n_sel}개)", type="primary",
                 use_container_width=True, disabled=n_sel == 0):
        existing_kws = {item["keyword"] for item in st.session_state.bulk_items}
        new_kws = [kw for kw in selected_kws_for_gen if kw not in existing_kws]
        skip_cnt = len(selected_kws_for_gen) - len(new_kws)

        if not new_kws:
            st.info("선택한 키워드가 이미 발행 준비 목록에 있습니다.")
        else:
            wp_sites_default = _load_wp_sites()
            default_site = wp_sites_default[0]["name"] if wp_sites_default else ""
            for kw in new_kws:
                new_idx = len(st.session_state.bulk_items)
                st.session_state.bulk_title_versions[new_idx] = 0
                st.session_state.bulk_items.append({
                    "keyword": kw,
                    "title": "",
                    "post_data": {},
                    "site_name": default_site,
                })
            if skip_cnt:
                st.info(f"{skip_cnt}개는 이미 있어서 건너뜁니다.")
            st.rerun()

# ── 블랙리스트 섹션 ──────────────────────────────────────
_bl_kws = sorted(_blacklist.keys())
with st.expander(f"⬛ 블랙리스트 ({len(_bl_kws)}개) — 이미 발행한 키워드"):
    bl_dl_col, bl_up_col, bl_empty = st.columns([2, 3, 5])
    with bl_dl_col:
        st.download_button(
            "💾 JSON 저장",
            data=json.dumps(_blacklist, ensure_ascii=False, indent=2),
            file_name=f"keywords_blacklist_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True,
        )
    with bl_up_col:
        _bl_upload = st.file_uploader("📂 JSON 불러오기", type="json", key="bl_uploader", label_visibility="visible")
        if _bl_upload:
            try:
                _uploaded_bl = json.load(_bl_upload)
                _blacklist.update(_uploaded_bl)
                _save_blacklist(_blacklist)
                st.rerun()
            except Exception as e:
                st.error(f"❌ {e}")
    if _bl_kws:
        st.markdown("---")
        for _row_s in range(0, len(_bl_kws), 3):
            _bl_row = _bl_kws[_row_s:_row_s + 3]
            _bl_grid = st.columns(3)
            for _j in range(3):
                with _bl_grid[_j]:
                    if _j >= len(_bl_row):
                        break
                    _bk = _bl_row[_j]
                    _bk_date = _blacklist[_bk].get("moved_at", "")
                    bc1, bc2 = st.columns([5, 1])
                    with bc1:
                        st.markdown(f'<p style="margin:0;font-size:0.80em;">⬛ <b>{_bk}</b>' + (f'&nbsp;<span style="color:#666;font-size:0.76em;">{_bk_date}</span>' if _bk_date else "") + '</p>', unsafe_allow_html=True)
                    with bc2:
                        if st.button("✕", key=f"bl_del_{_bk}"):
                            del _blacklist[_bk]
                            _save_blacklist(_blacklist)
                            st.rerun()

# ── 발행 테이블 ───────────────────────────────────────────
if st.session_state.bulk_items:
    _bulk_items = st.session_state.bulk_items
    wp_sites_pub = _load_wp_sites()
    site_names = [s["name"] for s in wp_sites_pub]

    st.divider()
    st.subheader("🗓️ 발행 준비")

    # 예약 시간 자동 계산
    with st.container(border=True):
        st.caption("예약 시간 자동 계산")
        _now2 = datetime.now()
        col_sd, col_sh, col_sm, col_intv, col_calc = st.columns([2, 1, 1, 1, 2])
        with col_sd:
            bulk_start_date = st.date_input("시작 날짜", value=_now2.date(), key="bulk_start_date")
        with col_sh:
            bulk_start_hour = st.number_input("시", 0, 23, value=_now2.hour, key="bulk_start_hour")
        with col_sm:
            bulk_start_min = st.number_input("분", 0, 59, value=_now2.minute, step=10, key="bulk_start_min")
        with col_intv:
            bulk_interval = st.number_input("간격(시간)", min_value=1, value=1, key="bulk_interval")
        with col_calc:
            st.write("")
            if st.button("⚡ 자동 계산", use_container_width=True):
                start_dt = datetime(
                    bulk_start_date.year, bulk_start_date.month, bulk_start_date.day,
                    bulk_start_hour, bulk_start_min
                )
                for i in range(len(_bulk_items)):
                    dt = start_dt + timedelta(hours=i * bulk_interval)
                    st.session_state[f"bulk_sched_input_{i}"] = dt.strftime("%Y-%m-%d %H:%M")
                st.rerun()

    def _do_generate_post(item: dict, edited_title: str,
                          internal_links=None, related_posts=None) -> dict:
        kw = item["keyword"]
        if internal_links is None and related_posts is None:
            cached_u = sitemap_service.load_cache()
            rel_u = sitemap_service.find_related(kw, cached_u, n=6)
            internal_links = rel_u[:3] or None
            related_posts = rel_u[3:6] or None
        post_data, used_k = gemini_service.generate_blog_post(
            keyword=kw, title=edited_title,
            api_key1=gemini_key1, api_key2=gemini_key2,
            internal_links=internal_links or None,
            related_posts=related_posts or None,
        )
        st.session_state.gemini_key_used = used_k
        _add_gemini_call()
        return post_data

    def _do_publish(site_obj: dict, post_data: dict, title: str, sched: str):
        pub_data = dict(post_data)
        pub_data["title"] = title
        if sched:
            sched_iso = sched.replace(" ", "T") + ":00" if len(sched) == 16 else sched
            wp_service.publish_post(site_obj, pub_data, scheduled_date=sched_iso)
        else:
            wp_service.publish_post(site_obj, pub_data, pub_status="publish")

    # 테이블 헤더
    hc = st.columns([0.5, 1.5, 2.8, 0.6, 0.8, 0.7, 0.6, 1.8, 2.2, 1.2])
    for col, label in zip(hc, ["#", "키워드", "제목", "새제목", "글생성", "미리보기", "🔗", "사이트", "예약시간", "발행"]):
        col.markdown(f"**{label}**")
    st.divider()

    _t_naver_id = os.getenv("NAVER_CLIENT_ID", "")
    _t_naver_secret = os.getenv("NAVER_CLIENT_SECRET", "")

    for i, item in enumerate(_bulk_items):
        cols = st.columns([0.5, 1.5, 2.8, 0.6, 0.8, 0.7, 0.6, 1.8, 2.2, 1.2])
        with cols[0]:
            st.caption(str(i + 1))
        with cols[1]:
            st.caption(item["keyword"])
        with cols[2]:
            _ver = st.session_state.bulk_title_versions.get(i, 0)
            cur_title = st.text_input("", value=item["title"],
                                      key=f"bulk_title_{i}_v{_ver}", label_visibility="collapsed")
        with cols[3]:
            if st.button("🔄", key=f"bulk_retitle_{i}", use_container_width=True, help="제목 새로 만들기"):
                if not groq_keys:
                    st.error("Groq 키 필요")
                else:
                    with st.spinner(""):
                        try:
                            kw_t = item["keyword"]
                            smry = naver_api.get_keyword_summary(kw_t, _t_naver_id, _t_naver_secret) if _t_naver_id else ""
                            key_idx_r = st.session_state.get("groq_key_idx", 0)
                            gc = Groq(api_key=groq_keys[key_idx_r])
                            try:
                                new_title, tokens = claude_service.generate_title_single(kw_t, gc, summary=smry)
                            except Exception as e:
                                err_s = str(e)
                                if ("429" in err_s or "rate_limit" in err_s.lower()) and key_idx_r + 1 < len(groq_keys):
                                    key_idx_r += 1
                                    st.session_state.groq_key_idx = key_idx_r
                                    gc = Groq(api_key=groq_keys[key_idx_r])
                                    new_title, tokens = claude_service.generate_title_single(kw_t, gc, summary=smry)
                                else:
                                    raise
                            _add_groq_tokens(tokens)
                            updated = list(st.session_state.bulk_items)
                            updated[i] = {**updated[i], "title": new_title}
                            st.session_state.bulk_items = updated
                            st.session_state.bulk_title_versions[i] = _ver + 1
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ {e}")
        with cols[4]:
            has_post = bool(item.get("post_data"))
            _title_empty = not cur_title.strip()
            if st.button("✍️" if not has_post else "↺", key=f"bulk_gen_{i}",
                         use_container_width=True,
                         disabled=_title_empty,
                         help="제목을 먼저 입력해주세요" if _title_empty else "Gemini로 글 생성"):
                if not gemini_key1:
                    st.error("Gemini 키 필요")
                else:
                    try:
                        gen_title = cur_title
                        _il = st.session_state.get(f"bulk_internal_links_{i}") if st.session_state.get(f"bulk_links_init_{i}") else None
                        _rp = st.session_state.get(f"bulk_related_posts_{i}") if st.session_state.get(f"bulk_links_init_{i}") else None
                        pd = _do_generate_post(item, gen_title, internal_links=_il, related_posts=_rp)
                        st.session_state.bulk_items[i]["post_data"] = pd
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")
        with cols[5]:
            has_post = bool(item.get("post_data"))
            if st.button("👁️", key=f"bulk_prev_btn_{i}", disabled=not has_post):
                st.session_state[f"bulk_prev_{i}"] = not st.session_state.get(f"bulk_prev_{i}", False)
                st.rerun()
        with cols[6]:
            if st.button("🔗", key=f"bulk_links_btn_{i}", help="내부링크 / 함께보면 좋은 글 확인"):
                st.session_state[f"bulk_links_{i}"] = not st.session_state.get(f"bulk_links_{i}", False)
                st.rerun()
        with cols[7]:
            cur_site = st.selectbox("", site_names,
                                    index=site_names.index(item["site_name"]) if item["site_name"] in site_names else 0,
                                    key=f"bulk_site_{i}", label_visibility="collapsed")
        with cols[8]:
            cur_sched = st.text_input("", placeholder="2026-05-24 09:00",
                                      key=f"bulk_sched_input_{i}", label_visibility="collapsed")
        with cols[9]:
            has_post_pub = bool(item.get("post_data"))
            if st.button("발행", key=f"bulk_pub_{i}", use_container_width=True,
                         disabled=not has_post_pub, help="글 생성 후 발행 가능"):
                site_obj = next((s for s in wp_sites_pub if s["name"] == cur_site), None)
                if not site_obj:
                    st.error("사이트 없음")
                else:
                    try:
                        _do_publish(site_obj, item["post_data"], cur_title, cur_sched.strip())
                        _mark_keyword_published(item["keyword"])
                        st.success("✅ 완료")
                    except Exception as e:
                        st.error(f"❌ {e}")

        if st.session_state.get(f"bulk_links_{i}"):
            # 첫 오픈 시 자동 매칭 초기화 (키워드만 사용)
            if not st.session_state.get(f"bulk_links_init_{i}"):
                _cu = sitemap_service.load_cache()
                _ru = sitemap_service.find_related(item["keyword"], _cu, n=6)
                st.session_state[f"bulk_internal_links_{i}"] = _ru[:3]
                st.session_state[f"bulk_related_posts_{i}"] = _ru[3:6]
                st.session_state[f"bulk_links_init_{i}"] = True

            _int_links = list(st.session_state.get(f"bulk_internal_links_{i}", []))
            _rel_posts = list(st.session_state.get(f"bulk_related_posts_{i}", []))

            with st.container(border=True):
                lc1, lc2 = st.columns(2)
                with lc1:
                    st.caption("**📎 내부링크**")
                    for j, u in enumerate(_int_links):
                        uc1, uc2 = st.columns([9, 1])
                        with uc1:
                            st.caption(u)
                        with uc2:
                            if st.button("✕", key=f"del_int_{i}_{j}"):
                                _int_links.pop(j)
                                st.session_state[f"bulk_internal_links_{i}"] = _int_links
                                st.rerun()
                    if not _int_links:
                        st.caption("없음")
                with lc2:
                    st.caption("**📖 함께보면 좋은 글**")
                    for j, u in enumerate(_rel_posts):
                        uc1, uc2 = st.columns([9, 1])
                        with uc1:
                            st.caption(u)
                        with uc2:
                            if st.button("✕", key=f"del_rel_{i}_{j}"):
                                _rel_posts.pop(j)
                                st.session_state[f"bulk_related_posts_{i}"] = _rel_posts
                                st.rerun()
                    if not _rel_posts:
                        st.caption("없음")

                st.caption("**🔍 링크 직접 검색**")
                sq1, sq2 = st.columns([4, 1])
                with sq1:
                    _sq = st.text_input("", placeholder="검색어 입력",
                                        key=f"bulk_lq_{i}", label_visibility="collapsed")
                with sq2:
                    if st.button("검색", key=f"bulk_lsearch_{i}", use_container_width=True):
                        if _sq.strip():
                            _cu2 = sitemap_service.load_cache()
                            st.session_state[f"bulk_lresults_{i}"] = sitemap_service.find_related(_sq.strip(), _cu2, n=10)
                            st.rerun()

                _sr_list = st.session_state.get(f"bulk_lresults_{i}", [])
                if _sr_list:
                    st.caption(f"검색 결과 {len(_sr_list)}개 — 체크 후 추가")
                    for j, u in enumerate(_sr_list):
                        st.checkbox(u, key=f"bulk_lchk_{i}_{j}")
                    _selected = [_sr_list[j] for j in range(len(_sr_list))
                                 if st.session_state.get(f"bulk_lchk_{i}_{j}", False)]
                    if _selected:
                        rc1, rc2 = st.columns(2)
                        with rc1:
                            if st.button("📎 내부링크로 추가", key=f"add_int_{i}", use_container_width=True):
                                cur = list(st.session_state.get(f"bulk_internal_links_{i}", []))
                                for u in _selected:
                                    if u not in cur:
                                        cur.append(u)
                                st.session_state[f"bulk_internal_links_{i}"] = cur
                                st.session_state.pop(f"bulk_lresults_{i}", None)
                                st.rerun()
                        with rc2:
                            if st.button("📖 함께보면 좋은 글로 추가", key=f"add_rel_{i}", use_container_width=True):
                                cur = list(st.session_state.get(f"bulk_related_posts_{i}", []))
                                for u in _selected:
                                    if u not in cur:
                                        cur.append(u)
                                st.session_state[f"bulk_related_posts_{i}"] = cur
                                st.session_state.pop(f"bulk_lresults_{i}", None)
                                st.rerun()

        if st.session_state.get(f"bulk_prev_{i}") and item.get("post_data"):
            with st.expander(f"👁️ {item['keyword']} 미리보기", expanded=True):
                _preview_html = item["post_data"].get("content", "")
                _preview_html = re.sub(r'<a ', '<a target="_blank" rel="noopener" ', _preview_html)
                st.html(_preview_html)

    st.divider()
    col_gen, col_pub, col_reset = st.columns([2, 2, 1])
    with col_reset:
        if st.button("🗑️ 초기화", use_container_width=True):
            st.session_state.bulk_items = []
            st.session_state.bulk_title_versions = {}
            for _k in [k for k in st.session_state if any(
                k.startswith(p) for p in [
                    "bulk_links_", "bulk_internal_links_", "bulk_related_posts_",
                    "bulk_lresults_", "bulk_lq_", "bulk_lchk_",
                ])]:
                del st.session_state[_k]
            st.rerun()
    with col_gen:
        if not gemini_key1:
            st.error("사이드바에서 Gemini API 키를 입력해주세요.")
        elif st.button("✍️ 일괄 글생성", type="primary", use_container_width=True):
            success_cnt, fail_cnt = 0, 0
            prog_b = st.progress(0)
            status_b = st.empty()
            n_b = len(_bulk_items)
            for i, item in enumerate(_bulk_items):
                kw_b = item["keyword"]
                _ver_b = st.session_state.bulk_title_versions.get(i, 0)
                title_b = st.session_state.get(f"bulk_title_{i}_v{_ver_b}", item["title"])
                if item.get("post_data"):
                    prog_b.progress((i + 1) / n_b)
                    continue
                try:
                    status_b.info(f"[{i+1}/{n_b}] {kw_b} — 글 생성 중...")
                    _il_b = st.session_state.get(f"bulk_internal_links_{i}") if st.session_state.get(f"bulk_links_init_{i}") else None
                    _rp_b = st.session_state.get(f"bulk_related_posts_{i}") if st.session_state.get(f"bulk_links_init_{i}") else None
                    post_data_b = _do_generate_post(item, title_b, internal_links=_il_b, related_posts=_rp_b)
                    st.session_state.bulk_items[i]["post_data"] = post_data_b
                    success_cnt += 1
                except Exception as e:
                    fail_cnt += 1
                    status_b.warning(f"❌ {kw_b}: {e}")
                prog_b.progress((i + 1) / n_b)
            prog_b.empty()
            status_b.empty()
            st.success(f"✅ 글생성 완료: {success_cnt}개 성공 / {fail_cnt}개 실패")
            st.rerun()
    with col_pub:
        if st.button("🚀 일괄 발행", use_container_width=True):
            success_cnt, fail_cnt = 0, 0
            prog_b = st.progress(0)
            status_b = st.empty()
            n_b = len(_bulk_items)
            for i, item in enumerate(_bulk_items):
                kw_b = item["keyword"]
                _ver_b = st.session_state.bulk_title_versions.get(i, 0)
                title_b = st.session_state.get(f"bulk_title_{i}_v{_ver_b}", item["title"])
                site_b = st.session_state.get(f"bulk_site_{i}", item["site_name"])
                sched_b = st.session_state.get(f"bulk_sched_input_{i}", "").strip()
                site_obj_b = next((s for s in wp_sites_pub if s["name"] == site_b), None)
                post_data_b = item.get("post_data")
                if not site_obj_b or not post_data_b:
                    fail_cnt += 1
                    prog_b.progress((i + 1) / n_b)
                    continue
                try:
                    status_b.info(f"[{i+1}/{n_b}] {kw_b} — 발행 중...")
                    _do_publish(site_obj_b, post_data_b, title_b, sched_b)
                    _mark_keyword_published(kw_b)
                    success_cnt += 1
                except Exception as e:
                    fail_cnt += 1
                    status_b.warning(f"❌ {kw_b}: {e}")
                prog_b.progress((i + 1) / n_b)
            prog_b.empty()
            status_b.empty()
            st.success(f"✅ 발행 완료: {success_cnt}개 성공 / {fail_cnt}개 실패")

# ── 세션 초기화 ───────────────────────────────────────────
for key in ["keyword_table", "selected_kw", "titles"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ── PHASE 1: 기사 입력 ────────────────────────────────────
if "article_text" not in st.session_state:
    st.session_state.article_text = ""

article = st.text_area(
    "뉴스 기사 붙여넣기",
    key="article_text",
    height=250,
    placeholder="뉴스 기사 전체를 복사해서 붙여넣으세요. 또는 위 뉴스에서 '이 기사 분석' 클릭",
)

manual_keywords = st.text_input(
    "직접 키워드 추가 (쉼표로 구분)",
    placeholder="예: 김치, 유산균, 발효",
)

col_a, col_b = st.columns(2)
with col_a:
    min_search_pre = st.number_input("문서수 조회 최소 검색량 (API 절약)", min_value=0, value=1000, step=100,
                                     help="이 검색량 이상인 키워드만 블로그 문서수를 조회합니다")
with col_b:
    min_stars_pre = st.number_input("최소 별 개수 (1~5)", min_value=1, max_value=5, value=5, step=1,
                                    help="이 별 개수 이상인 키워드만 결과에 표시합니다")

if st.button("🚀 키워드 분석 시작", type="primary", use_container_width=True):
    if not article.strip() and not manual_keywords.strip():
        st.error("기사를 입력하거나 직접 키워드를 입력해주세요.")
        st.stop()
    if not groq_key:
        st.error("Groq API 키를 입력해주세요.")
        st.stop()
    if not naver_ok:
        st.error(".env 파일에 네이버 API 키를 확인해주세요.")
        st.stop()

    groq_client = Groq(api_key=groq_key)
    customer_id = os.getenv("NAVER_AD_CUSTOMER_ID", "")
    ad_key = os.getenv("NAVER_AD_API_KEY", "")
    ad_secret = os.getenv("NAVER_AD_SECRET_KEY", "")
    naver_id = os.getenv("NAVER_CLIENT_ID", "")
    naver_secret = os.getenv("NAVER_CLIENT_SECRET", "")

    with st.status("분석 중...", expanded=True) as status:
        manual = [k.strip() for k in manual_keywords.split(",") if k.strip()] if manual_keywords.strip() else []

        if article.strip():
            st.write("📝 씨드 키워드 추출 중...")
            seeds, tokens = claude_service.extract_seed_keywords(article, groq_client)
            _add_groq_tokens(tokens)
        else:
            seeds = []

        seeds = list(dict.fromkeys(seeds + manual))  # 중복 제거, 순서 유지

        if not seeds:
            st.error("기사를 입력하거나 직접 키워드를 입력해주세요.")
            st.stop()
        st.write(f"✅ 씨드 키워드: {', '.join(seeds)}")

        st.write("🔍 네이버 자동완성 키워드 수집 중...")
        autocomplete_kws = []
        for seed in seeds:
            if len(seed.strip()) < 2:
                st.write(f"  · {seed} → 한 글자 스킵")
                continue
            ac = naver_api.get_autocomplete(seed)
            st.write(f"  · {seed} → {len(ac)}개: {', '.join(ac)}" if ac else f"  · {seed} → 자동완성 없음")
            autocomplete_kws.extend(ac)
        autocomplete_kws = list(dict.fromkeys(autocomplete_kws))

        if autocomplete_kws:
            st.write(f"✅ 자동완성 키워드 총 {len(autocomplete_kws)}개")
            st.write(f"📈 검색량 조회 중... ({len(autocomplete_kws)}개)")
            related = naver_api.get_search_volumes_batch(autocomplete_kws, customer_id, ad_key, ad_secret)
        else:
            st.warning("⚠️ 자동완성 수집 실패 → 연관키워드 방식으로 대체")
            related = naver_api.get_related_keywords(seeds, customer_id, ad_key, ad_secret)
        st.write(f"✅ 키워드 {len(related)}개 수집")

        to_lookup = {k: v for k, v in related.items() if v["total_search"] >= min_search_pre}
        st.write(f"📊 블로그 문서수 조회 중... ({len(to_lookup)}개, 검색량 {min_search_pre:,} 이상만)")
        doc_counts = naver_api.get_doc_counts_parallel(list(to_lookup.keys()), naver_id, naver_secret)

        table = naver_api.build_keyword_table(to_lookup, doc_counts)
        st.session_state.keyword_table = table
        st.session_state.min_search_pre = min_search_pre
        st.session_state.min_stars_pre = min_stars_pre
        st.session_state.selected_kw = None
        st.session_state.titles = None
        status.update(label=f"✅ 완료! 키워드 {len(table)}개 분석됨", state="complete")

# ── PHASE 2: 필터 슬라이더 + 테이블 ──────────────────────
if st.session_state.keyword_table:
    table = st.session_state.keyword_table

    if not table:
        st.warning("조건에 맞는 키워드가 없습니다.")
        st.stop()

    max_search = max(r["total_search"] for r in table)
    max_docs = max(r["doc_count"] for r in table)

    st.subheader("📊 키워드 목록")
    default_min = st.session_state.get("min_search_pre", 3000)
    col1, col2, col3 = st.columns(3)
    with col1:
        min_search = st.number_input("최소 월 검색량", min_value=0, value=default_min, step=100)
    with col2:
        max_doc = st.number_input("최대 문서수 (0=제한없음)", min_value=0, value=0, step=1000)
    with col3:
        min_stars = st.number_input("최소 별 개수 (1~5)", min_value=1, max_value=5, value=st.session_state.get("min_stars_pre", 5), step=1)

    all_stars = ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]
    valid_stars = set(all_stars[min_stars - 1:])
    filtered = [
        r for r in table
        if r["total_search"] >= min_search
        and (max_doc == 0 or r["doc_count"] <= max_doc)
        and (r["pc_ctr"] >= 1 or r["mobile_ctr"] >= 1)
        and r["stars"] in valid_stars
    ]

    if not filtered:
        st.warning("조건에 맞는 키워드가 없어요. 슬라이더를 조절해보세요.")
    else:
        df = pd.DataFrame([{
            "키워드": r["keyword"],
            "검색": f"https://search.naver.com/search.naver?query={r['keyword']}",
            "검색_PC": f"{r['pc_search']:,}",
            "검색_모바일": f"{r['mobile_search']:,}",
            "월검색(합계)": f"{r['total_search']:,}",
            "클릭_PC": f"{r['pc_click']:,}",
            "클릭_모바일": f"{r['mobile_click']:,}",
            "클릭률_PC": f"{r['pc_ctr']}%",
            "클릭률_모바일": f"{r['mobile_ctr']}%",
            "경쟁정도(AD)": r["comp_idx"],
            "문서수": f"{r['doc_count']:,}",
            "경쟁 강도": r["level"],
            "추천도": r["stars"],
        } for r in filtered])

        st.dataframe(df, hide_index=True, use_container_width=True,
                     column_config={"검색": st.column_config.LinkColumn("검색", display_text="🔍 네이버")})
        st.caption(f"총 {len(filtered)}개 키워드 | 경쟁 낮은 순 정렬")

        tsv = df.to_csv(sep="\t", index=False).replace("`", "'").replace("\\", "\\\\")
        components.html(f"""
<button onclick="navigator.clipboard.writeText(`{tsv}`).then(()=>{{this.textContent='✅ 복사됨!';setTimeout(()=>this.textContent='📋 표 복사 (엑셀 붙여넣기용)',2000)}}).catch(()=>alert('복사 실패: 브라우저 권한을 확인하세요'))">📋 표 복사 (엑셀 붙여넣기용)</button>
<style>button{{padding:8px 20px;background:#ff4b4b;color:white;border:none;border-radius:6px;cursor:pointer;font-size:14px;font-family:sans-serif}}</style>
""", height=50)

        # ── PHASE 3: 키워드 선택 → 제목 생성 ────────────────
        st.divider()
        st.subheader("✍️ 제목 생성")

        kw_list = [r["keyword"] for r in filtered]
        selected = st.selectbox("제목 생성할 키워드 선택", kw_list)

        if st.button("📝 제목 5개 생성", type="primary"):
            if not groq_key:
                st.error("Groq API 키를 입력해주세요.")
            else:
                groq_client = Groq(api_key=groq_key)
                with st.spinner("제목 생성 중..."):
                    titles, recommended, tokens = claude_service.generate_titles(selected, groq_client)
                    _add_groq_tokens(tokens)
                kw_data = next(r for r in filtered if r["keyword"] == selected)
                st.session_state.titles = {
                    "keyword": selected,
                    "titles": titles,
                    "recommended": recommended,
                    "data": kw_data,
                }

# ── PHASE 4: 결과 테이블 (복사/다운로드) ─────────────────
if st.session_state.titles:
    t = st.session_state.titles
    d = t["data"]

    st.divider()
    st.subheader("📋 생성된 제목")

    if t.get("recommended"):
        st.info(f"⭐ 추천 제목: **{t['recommended']}**")

    rows = []
    for title in t["titles"]:
        v = claude_service.validate_title(title, t["keyword"])
        length_str = f"{v['length']}자 {'✅' if v['length_ok'] else '❌'}"
        rows.append({
            "포커스 키워드": t["keyword"],
            "블로그 제목": title,
            "글자수": length_str,
            "검색_PC": f"{d.get('pc_search', 0):,}",
            "검색_모바일": f"{d.get('mobile_search', 0):,}",
            "월검색(합계)": f"{d['total_search']:,}",
            "클릭_PC": f"{d.get('pc_click', 0):,}",
            "클릭_모바일": f"{d.get('mobile_click', 0):,}",
            "클릭률_PC": f"{d.get('pc_ctr', 0)}%",
            "클릭률_모바일": f"{d.get('mobile_ctr', 0)}%",
            "경쟁정도(AD)": d.get("comp_idx", "N/A"),
            "문서수": f"{d['doc_count']:,}",
            "경쟁 강도": d["level"],
            "추천도": d["stars"],
        })

    result_df = pd.DataFrame(rows)
    st.dataframe(result_df, hide_index=True, width="stretch")

    # 엑셀 복사용 (글자수 컬럼 제외)
    export_df = pd.DataFrame([{
        "포커스 키워드": r["포커스 키워드"],
        "블로그 제목": r["블로그 제목"],
        "검색_PC": r["검색_PC"],
        "검색_모바일": r["검색_모바일"],
        "월검색(합계)": r["월검색(합계)"],
        "클릭_PC": r["클릭_PC"],
        "클릭_모바일": r["클릭_모바일"],
        "클릭률_PC": r["클릭률_PC"],
        "클릭률_모바일": r["클릭률_모바일"],
        "경쟁정도(AD)": r["경쟁정도(AD)"],
        "문서수": r["문서수"],
        "경쟁 강도": r["경쟁 강도"],
        "추천도": r["추천도"],
    } for r in rows])

    csv = export_df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "⬇️ 엑셀용 CSV 다운로드",
        data=csv,
        file_name=f"{t['keyword']}_제목.csv",
        mime="text/csv",
        use_container_width=True,
    )
