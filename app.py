import os
import json
import time
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from groq import Groq

import naver_api
import claude_service
import news_fetcher

load_dotenv()

CRAWLED_FILE = os.path.join(os.path.dirname(__file__), "crawled_links.json")
KEYWORDS_HISTORY_FILE = os.path.join(os.path.dirname(__file__), "keywords_history.json")
GROQ_USAGE_FILE = os.path.join(os.path.dirname(__file__), "groq_usage.json")

def _load_groq_usage() -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(GROQ_USAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") != today:
            return {"date": today, "tokens": 0}
        return data
    except Exception:
        return {"date": today, "tokens": 0}

def _save_groq_usage(tokens: int):
    today = datetime.now().strftime("%Y-%m-%d")
    with open(GROQ_USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump({"date": today, "tokens": tokens}, f)

def _add_groq_tokens(n: int):
    st.session_state.groq_tokens = st.session_state.get("groq_tokens", 0) + n
    _save_groq_usage(st.session_state.groq_tokens)

def _load_keywords_history() -> dict:
    try:
        with open(KEYWORDS_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_keywords_history(history: dict):
    with open(KEYWORDS_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def _mark_title_used(keyword: str, title: str):
    history = _load_keywords_history()
    if keyword in history:
        for t in history[keyword]["titles"]:
            if t["title"] == title:
                t["used"] = True
                break
    _save_keywords_history(history)
    st.session_state.keywords_history = history

def _unmark_title_used(keyword: str, title: str):
    history = _load_keywords_history()
    if keyword in history:
        for t in history[keyword]["titles"]:
            if t["title"] == title:
                t["used"] = False
                break
    _save_keywords_history(history)
    st.session_state.keywords_history = history
    if st.session_state.get("last_used_title", {}).get("title") == title:
        st.session_state.last_used_title = None

def _load_crawled_links() -> set:
    try:
        with open(CRAWLED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def _save_crawled_link(link: str):
    links = _load_crawled_links()
    links.add(link)
    with open(CRAWLED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(links), f, ensure_ascii=False)

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
    naver_ok = bool(os.getenv("NAVER_AD_API_KEY")) and bool(os.getenv("NAVER_CLIENT_ID"))
    if naver_ok:
        st.success("✅ 네이버 API 연결됨")
    else:
        st.error("❌ 네이버 API 키 없음")
    st.divider()
    crawled_count = len(_load_crawled_links())
    st.caption(f"크롤링 기록: {crawled_count}개 기사")
    if st.button("🗑️ 크롤링 기록 초기화"):
        if os.path.exists(CRAWLED_FILE):
            os.remove(CRAWLED_FILE)
        st.session_state.auto_crawled = []
        st.rerun()
    st.divider()
    st.markdown(f"**🤖 Groq 사용량 (오늘 {datetime.now().strftime('%m/%d')})**")
    groq_tokens = st.session_state.get("groq_tokens", 0)
    groq_pct = min(groq_tokens / 100000, 1.0)
    st.progress(groq_pct)
    st.caption(f"{groq_tokens:,} / 100,000 토큰 ({groq_pct*100:.1f}%)")
    used_key = st.session_state.get("groq_key_idx", 0) + 1
    st.caption(f"현재 Key {used_key} 사용 중")
    st.markdown("**🔍 네이버 API 호출 (이번 세션)**")
    st.caption(f"검색광고: {st.session_state.get('naver_ad_calls', 0):,}회")
    st.caption(f"검색(문서수): {st.session_state.get('naver_search_calls', 0):,}회")
    st.divider()
    history = _load_keywords_history()
    used_total = sum(1 for kw in history.values() for t in kw["titles"] if t["used"])
    unused_total = sum(1 for kw in history.values() for t in kw["titles"] if not t["used"])
    st.caption(f"키워드 히스토리: {len(history)}개 키워드 | 미사용 제목 {unused_total}개 | 사용됨 {used_total}개")
    if st.button("🗑️ 키워드 히스토리 초기화"):
        if os.path.exists(KEYWORDS_HISTORY_FILE):
            os.remove(KEYWORDS_HISTORY_FILE)
        st.session_state.keywords_history = {}
        st.rerun()
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
탭건강, 탭부동산, 탭사업, 탭투자, 탭지원금, 탭보험, 탭대출, 탭법률, 탭세금, 탭육아, 탭여행, 탭반려 = st.tabs([
    "💊 건강", "🏠 부동산", "💼 사업", "📈 투자", "🏛️ 정부지원금",
    "🛡️ 보험", "💳 대출", "⚖️ 법률", "💰 세금", "👶 육아출산", "✈️ 여행", "🐾 반려동물",
])

for tab, category in [
    (탭건강, "건강"), (탭부동산, "부동산"), (탭사업, "사업"), (탭투자, "투자"), (탭지원금, "정부지원금"),
    (탭보험, "보험"), (탭대출, "대출"), (탭법률, "법률"), (탭세금, "세금"),
    (탭육아, "육아출산"), (탭여행, "여행"), (탭반려, "반려동물"),
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
        ac_all = []
        for kw in seed_keywords:
            ac = naver_api.get_autocomplete(kw)
            ac_all.extend(ac)
        ac_all = list(dict.fromkeys(ac_all))

    if not ac_all:
        st.warning("자동완성 키워드를 찾을 수 없어요.")
        return

    with st.spinner(f"검색량 조회 중... ({len(ac_all)}개)"):
        related = naver_api.get_search_volumes_batch(ac_all, customer_id, ad_key, ad_secret)

    with st.spinner(f"문서수 조회 중... ({len(related)}개)"):
        doc_counts = naver_api.get_doc_counts_parallel(list(related.keys()), naver_id, naver_secret)

    table = naver_api.build_keyword_table(related, doc_counts)
    st.session_state.longtail_table = table

def _generate_and_save_titles(groq_client):
    history = _load_keywords_history()
    longtail = st.session_state.get("longtail_table", [])
    today = datetime.now().strftime("%Y-%m-%d")

    filtered = [r for r in longtail if r.get("mobile_ctr", 0) >= 2]
    to_generate = [r for r in filtered if r["keyword"] not in history]

    if not filtered:
        st.warning(f"⚠️ 모바일 클릭률 2% 이상 키워드가 없어요. 롱테일 전체: {len(longtail)}개")
        st.session_state.keywords_history = history
        return

    if not to_generate:
        st.info(f"📂 클릭률 2%↑ 키워드 {len(filtered)}개 모두 히스토리에 있어요. 제목 대기열을 확인하세요.")
        st.session_state.keywords_history = history
        return

    st.info(f"✍️ 클릭률 2%↑ 키워드 {len(filtered)}개 중 {len(to_generate)}개 제목 생성 시작")

    title_status = st.empty()
    title_progress = st.progress(0)
    errors = []

    for i, row in enumerate(to_generate):
        kw = row["keyword"]
        title_status.info(f"✍️ 제목 생성 중: {kw} ({i+1}/{len(to_generate)})")
        try:
            titles, recommended, tokens = claude_service.generate_titles(kw, groq_client)
            _add_groq_tokens(tokens)
            history[kw] = {
                "first_found": today,
                "titles": [
                    {"title": t, "used": False, "recommended": t == recommended}
                    for t in titles
                ],
            }
            _save_keywords_history(history)
        except Exception as e:
            errors.append(f"{kw}: {e}")
        title_progress.progress((i + 1) / len(to_generate))
        time.sleep(0.3)

    title_status.empty()
    title_progress.empty()

    if errors:
        st.warning(f"⚠️ 제목 생성 실패 {len(errors)}건:\n" + "\n".join(errors[:3]))

    st.session_state.keywords_history = history

# ── 자동 키워드 찾기 ─────────────────────────────────────
st.subheader("🤖 자동 키워드 찾기")

for key in ["auto_keywords", "auto_crawled", "auto_running"]:
    if key not in st.session_state:
        st.session_state[key] = [] if key != "auto_running" else False
if "keywords_history" not in st.session_state:
    st.session_state.keywords_history = _load_keywords_history()
if "groq_tokens" not in st.session_state:
    st.session_state.groq_tokens = _load_groq_usage()["tokens"]
for key in ["naver_ad_calls", "naver_search_calls"]:
    if key not in st.session_state:
        st.session_state[key] = 0

crawled_file_links = _load_crawled_links()

col_cat, col_num, col_stars, col_btn1, col_btn2 = st.columns([2, 1, 1, 1, 1])
with col_cat:
    auto_category = st.selectbox("카테고리", [
        "건강", "부동산", "사업", "투자", "정부지원금",
        "보험", "대출", "법률", "세금", "육아출산", "여행", "반려동물",
    ], label_visibility="collapsed")
with col_num:
    auto_target = st.number_input("찾을 키워드 수", min_value=1, value=10, step=1, label_visibility="collapsed")
with col_stars:
    auto_min_stars = st.number_input("최소 별 개수", min_value=1, max_value=5, value=3, step=1, label_visibility="collapsed")
with col_btn1:
    start_btn = st.button("🤖 자동 찾기", type="primary", use_container_width=True)
with col_btn2:
    stop_btn = st.button("⏹ 스탑", use_container_width=True)

if stop_btn:
    st.session_state.auto_running = False

# 분석한 기사 기록 표시
if st.session_state.auto_crawled:
    last = st.session_state.auto_crawled[-1]
    st.caption(f"마지막 분석 기사: [{last['pubDate']}] {last['title']}")

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
        groq_keys = [k for k in [groq_key, groq_key2] if k.strip()]
        groq_key_idx = 0
        groq_client = Groq(api_key=groq_keys[0])
        customer_id = os.getenv("NAVER_AD_CUSTOMER_ID", "")
        ad_key = os.getenv("NAVER_AD_API_KEY", "")
        ad_secret = os.getenv("NAVER_AD_SECRET_KEY", "")
        naver_id = os.getenv("NAVER_CLIENT_ID", "")
        naver_secret = os.getenv("NAVER_CLIENT_SECRET", "")

        # 기사 목록 (없으면 수집)
        if not st.session_state.get(f"news_{auto_category}"):
            with st.spinner(f"{auto_category} 기사 수집 중..."):
                st.session_state[f"news_{auto_category}"] = news_fetcher.fetch_category_news(auto_category, max_total=1000)

        articles = st.session_state[f"news_{auto_category}"]
        crawled_links = _load_crawled_links()
        collected = list(st.session_state.auto_keywords)
        collected_kws = {r["keyword"] for r in collected}

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

            # 크롤링
            text = news_fetcher.scrape_article(article["link"])
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
            to_lookup = {k: v for k, v in related.items() if v["total_search"] >= 2000}

            if not to_lookup:
                status_box.warning(f"⚠️ 검색량 2000 이상 키워드 없음 ({len(related)}개 조회) → 다음 기사")
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
            if st.session_state.get("longtail_table"):
                _generate_and_save_titles(groq_client)
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

if direct_lt_btn:
    if direct_lt_input.strip():
        seed_kws = [k.strip() for k in direct_lt_input.split(",") if k.strip()]
        _run_longtail(seed_kws)
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

# ── 제목 대기열 ──────────────────────────────────────────
st.divider()
st.subheader("✍️ 제목 대기열")

history = st.session_state.get("keywords_history", {})
longtail_kws = {r["keyword"] for r in st.session_state.get("longtail_table", [])}

# 사용됨 제목 전체 목록 (히스토리 파일 기반)
used_titles = [
    {"keyword": kw, "title": t["title"]}
    for kw, kw_data in history.items()
    for t in kw_data["titles"]
    if t["used"]
]

if used_titles:
    st.markdown("**📌 작성할 제목 목록**")
    for item in used_titles:
        col1, col2 = st.columns([8, 2])
        with col1:
            st.success(f"**{item['title']}**")
            st.caption(f"키워드: {item['keyword']}")
        with col2:
            st.write("")
            st.write("")
            if st.button("↩️ 취소", key=f"cancel_{item['keyword']}_{item['title'][:10]}"):
                _unmark_title_used(item["keyword"], item["title"])
                st.session_state.keywords_history = _load_keywords_history()
                st.rerun()

# 미사용 제목이 남은 키워드 목록
available_kws = [
    kw for kw in longtail_kws
    if kw in history and any(not t["used"] for t in history[kw]["titles"])
]
history_only_kws = [
    kw for kw in history
    if kw not in longtail_kws and any(not t["used"] for t in history[kw]["titles"])
]

all_pending = available_kws + history_only_kws

if not all_pending:
    st.caption("미사용 제목이 없습니다. 자동 찾기를 실행해보세요.")
else:
    st.caption(f"총 {len(all_pending)}개 키워드 대기 중")
    for kw in all_pending:
        kw_data = history[kw]
        unused_count = sum(1 for t in kw_data["titles"] if not t["used"])
        with st.expander(f"📝 {kw}  ({unused_count}개 남음)", expanded=True):
            for idx, t in enumerate(kw_data["titles"]):
                if not t["used"]:
                    star = "⭐ " if t.get("recommended") else ""
                    edited = st.text_input(
                        label=f"{star}제목 {idx+1}",
                        value=t["title"],
                        key=f"edit_{kw}_{idx}",
                        label_visibility="collapsed",
                    )
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        if edited != t["title"]:
                            if st.button("💾 저장", key=f"save_{kw}_{idx}"):
                                h = _load_keywords_history()
                                h[kw]["titles"][idx]["title"] = edited
                                _save_keywords_history(h)
                                st.session_state.keywords_history = h
                                st.rerun()
                    with col2:
                        if st.button("사용", key=f"use_{kw}_{idx}"):
                            title_to_use = st.session_state.get(f"edit_{kw}_{idx}", t["title"])
                            h = _load_keywords_history()
                            h[kw]["titles"][idx]["title"] = title_to_use
                            h[kw]["titles"][idx]["used"] = True
                            _save_keywords_history(h)
                            st.session_state.keywords_history = h
                            st.rerun()

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
    min_search_pre = st.number_input("문서수 조회 최소 검색량 (API 절약)", min_value=0, value=2000, step=100,
                                     help="이 검색량 이상인 키워드만 블로그 문서수를 조회합니다")
with col_b:
    min_stars_pre = st.number_input("최소 별 개수 (1~5)", min_value=1, max_value=5, value=3, step=1,
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
        min_stars = st.number_input("최소 별 개수 (1~5)", min_value=1, max_value=5, value=st.session_state.get("min_stars_pre", 3), step=1)

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
