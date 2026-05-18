import os
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from groq import Groq

import naver_api
import claude_service

load_dotenv()

# ── 페이지 설정 ──────────────────────────────────────────
st.set_page_config(page_title="수익형 키워드 분석기", page_icon="🔍", layout="wide")
st.title("🔍 수익형 키워드 분석기")
st.caption("뉴스 기사를 붙여넣으면 수익성 높은 블로그 키워드를 자동 추출합니다")

# ── 사이드바: API 키 설정 ─────────────────────────────────
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
        st.error("❌ 네이버 API 키 없음 (.env 확인)")

    st.divider()
    st.markdown(
        "**경쟁 강도 기준** (문서량 ÷ 검색량)\n"
        "- ⭐⭐⭐⭐⭐ 매우 낮음 `< 0.5`\n"
        "- ⭐⭐⭐⭐ 낮음 `0.5~1`\n"
        "- ⭐⭐⭐ 보통 `1~3`\n"
        "- ⭐⭐ 높음 `3~10`\n"
        "- ⭐ 매우 높음 `> 10`"
    )

# ── 메인: 기사 입력 ───────────────────────────────────────
article_text = st.text_area(
    "뉴스 기사 붙여넣기",
    height=300,
    placeholder=(
        "뉴스 기사 전체를 복사해서 붙여넣으세요.\n"
        "기자명, SNS 버튼 등 UI 잔재가 포함돼도 자동으로 걸러냅니다."
    ),
)

run = st.button("🚀 키워드 분석 시작", type="primary", use_container_width=True)

if run:
    # ── 입력값 검증 ──────────────────────────────────────
    if not article_text.strip():
        st.error("기사를 입력해주세요.")
        st.stop()
    if not groq_key:
        st.error("Groq API 키를 입력해주세요.")
        st.stop()
    if not naver_ok:
        st.error(".env 파일에 네이버 API 키를 설정해주세요.")
        st.stop()

    # ── 환경변수 로드 ─────────────────────────────────────
    customer_id = os.getenv("NAVER_AD_CUSTOMER_ID", "")
    ad_api_key = os.getenv("NAVER_AD_API_KEY", "")
    ad_secret = os.getenv("NAVER_AD_SECRET_KEY", "")
    naver_client_id = os.getenv("NAVER_CLIENT_ID", "")
    naver_client_secret = os.getenv("NAVER_CLIENT_SECRET", "")

    claude_client = Groq(api_key=groq_key)
    results = []

    with st.status("분석 중...", expanded=True) as status:

        # STEP 1: 키워드 추출
        st.write("📝 AI가 키워드 추출 중...")
        keywords = claude_service.extract_keywords(article_text, claude_client)
        if not keywords:
            st.error("키워드 추출에 실패했습니다. 기사 내용을 확인해주세요.")
            st.stop()
        st.write(f"✅ {len(keywords)}개 키워드 추출 완료")

        # STEP 2: 네이버 검색광고 API → 월 검색량
        st.write("📊 네이버 검색광고 API 호출 중...")
        stats_map = naver_api.get_keyword_stats(keywords, customer_id, ad_api_key, ad_secret)

        # STEP 3: 네이버 블로그 검색 API → 문서량 + 경쟁 강도 계산
        st.write("🔎 블로그 문서량 확인 및 경쟁 강도 계산 중...")
        candidates = []

        for kw in keywords:
            stat = stats_map.get(kw, {"pc_search": 0, "mobile_search": 0})
            total_search = stat["pc_search"] + stat["mobile_search"]
            doc_count = naver_api.get_blog_doc_count(kw, naver_client_id, naver_client_secret)
            level, stars, ratio = naver_api.competition_level(total_search, doc_count)

            candidates.append(
                {
                    "keyword": kw,
                    "total_search": total_search,
                    "doc_count": doc_count,
                    "level": level,
                    "stars": stars,
                    "ratio": ratio,
                }
            )

        # STEP 4: ⭐⭐⭐⭐⭐ 필터 → 검색량 높은 순 TOP 5
        top5 = sorted(
            [c for c in candidates if c["stars"] == "⭐⭐⭐⭐⭐"],
            key=lambda x: x["total_search"],
            reverse=True,
        )[:5]

        fallback = False
        if not top5:
            fallback = True
            top5 = sorted(candidates, key=lambda x: (len(x["stars"]), x["total_search"]), reverse=True)[:5]

        # STEP 5: Groq → 블로그 제목 생성
        st.write("✍️ 블로그 제목 생성 중...")
        for item in top5:
            titles = claude_service.generate_titles(item["keyword"], claude_client)
            item["titles"] = titles
            item["best_title"] = titles[0] if titles else f"{item['keyword']} 활용법 3가지"
            results.append(item)

        status.update(label="✅ 분석 완료!", state="complete")

    # ── 결과 출력 ─────────────────────────────────────────
    if fallback:
        st.warning("⭐⭐⭐⭐⭐ 키워드가 없어 상위 5개를 대신 표시합니다.")

    st.subheader("📊 추천 키워드 TOP 5")

    table_rows = []
    for r in results:
        table_rows.append(
            {
                "포커스 키워드": r["keyword"],
                "블로그 제목": r["best_title"],
                "월검색 / 문서수": f"{r['total_search']:,} / {r['doc_count']:,}",
                "경쟁 강도": r["level"],
                "추천도": r["stars"],
            }
        )

    st.dataframe(pd.DataFrame(table_rows), width="stretch", hide_index=True)

    # ── 상세 보기 (대안 제목 포함) ────────────────────────
    with st.expander("📋 대안 제목 전체 보기"):
        for r in results:
            st.markdown(f"### {r['keyword']}")
            st.caption(f"월 검색량 {r['total_search']:,}회 · 블로그 문서 {r['doc_count']:,}건 · 경쟁비율 {r['ratio']:.2f}")
            for i, title in enumerate(r.get("titles", []), 1):
                v = claude_service.validate_title(title, r["keyword"])
                length_color = "green" if v["length_ok"] else "red"
                pos_color = "green" if v["keyword_pos_ok"] else "orange"
                st.markdown(
                    f"{i}. **{title}**  "
                    f":{length_color}[{v['length']}자] "
                    f":{pos_color}[키워드 {v['keyword_pos']+1}번째 글자부터]"
                )
            st.divider()
