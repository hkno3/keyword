import os
import json
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from dotenv import load_dotenv
from groq import Groq

import naver_api
import claude_service
import news_fetcher

load_dotenv()

CRAWLED_FILE = os.path.join(os.path.dirname(__file__), "crawled_links.json")

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
        "Groq API Key",
        value=os.getenv("GROQ_API_KEY", ""),
        type="password",
        help="https://console.groq.com 에서 발급 (무료)",
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

# ── 자동 키워드 찾기 ─────────────────────────────────────
st.subheader("🤖 자동 키워드 찾기")

for key in ["auto_keywords", "auto_crawled", "auto_running"]:
    if key not in st.session_state:
        st.session_state[key] = [] if key != "auto_running" else False

crawled_file_links = _load_crawled_links()

col_cat, col_num, col_btn1, col_btn2 = st.columns([2, 1, 1, 1])
with col_cat:
    auto_category = st.selectbox("카테고리", [
        "건강", "부동산", "사업", "투자", "정부지원금",
        "보험", "대출", "법률", "세금", "육아출산", "여행", "반려동물",
    ], label_visibility="collapsed")
with col_num:
    auto_target = st.number_input("찾을 키워드 수", min_value=1, value=10, step=1, label_visibility="collapsed")
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
        groq_client = Groq(api_key=groq_key)
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

            status_box.info(f"🔍 [{article['pubDate']}] {article['title'][:50]}...")

            # 크롤링
            text = news_fetcher.scrape_article(article["link"])
            _save_crawled_link(article["link"])
            crawled_links.add(article["link"])
            st.session_state.auto_crawled.append({"link": article["link"], "pubDate": article["pubDate"], "title": article["title"]})

            if not text:
                continue

            # AI 씨드 추출
            try:
                seeds = claude_service.extract_seed_keywords(text, groq_client)
                seeds = [s for s in seeds if len(s.strip()) >= 2]
            except Exception:
                continue

            if not seeds:
                continue

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
            to_lookup = {k: v for k, v in related.items() if v["total_search"] >= 2000}

            if not to_lookup:
                continue

            # 문서수 조회
            doc_counts = naver_api.get_doc_counts_parallel(list(to_lookup.keys()), naver_id, naver_secret)
            table = naver_api.build_keyword_table(to_lookup, doc_counts)

            # 별 3개 이상 + 클릭률 1% 이상 + 중복 제거
            for r in table:
                if len(collected) >= auto_target:
                    break
                if r["stars"] in ("⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐") and \
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
            seeds = claude_service.extract_seed_keywords(article, groq_client)
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
    col1, col2 = st.columns(2)
    with col1:
        min_search = st.number_input("최소 월 검색량", min_value=0, value=default_min, step=100)
    with col2:
        max_doc = st.number_input("최대 문서수 (0=제한없음)", min_value=0, value=0, step=1000)

    filtered = [
        r for r in table
        if r["total_search"] >= min_search
        and (max_doc == 0 or r["doc_count"] <= max_doc)
        and (r["pc_ctr"] >= 1 or r["mobile_ctr"] >= 1)
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
                    titles = claude_service.generate_titles(selected, groq_client)
                kw_data = next(r for r in filtered if r["keyword"] == selected)
                st.session_state.titles = {
                    "keyword": selected,
                    "titles": titles,
                    "data": kw_data,
                }

# ── PHASE 4: 결과 테이블 (복사/다운로드) ─────────────────
if st.session_state.titles:
    t = st.session_state.titles
    d = t["data"]

    st.divider()
    st.subheader("📋 생성된 제목")

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
