"""
US Residential Intelligence v2 — app.py
Streamlit 대시보드: 조회·필터 + 미분류 기사 분류 실행.
실행: streamlit run app.py
"""

import os
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from classifier import run_classifier

# ------------------------------------------------------------------
# 설정
# ------------------------------------------------------------------

ARTICLES_CSV = "articles.csv"

st.set_page_config(
    page_title="US Residential Intelligence v2",
    page_icon="🏠",
    layout="wide",
)

# ------------------------------------------------------------------
# 데이터 로드
# ------------------------------------------------------------------

@st.cache_data(ttl=60)
def load_data() -> pd.DataFrame:
    if not os.path.exists(ARTICLES_CSV):
        return pd.DataFrame()

    df = pd.read_csv(ARTICLES_CSV, dtype=str).fillna("")

    for col in ("collected_at", "published_at"):
        df[col] = pd.to_datetime(df[col], errors="coerce")

    df["classified"]    = df["classified"].str.lower() == "true"
    df["access_limited"] = df["access_limited"].str.lower() == "true"

    return df


def reload():
    st.cache_data.clear()
    st.rerun()


# ------------------------------------------------------------------
# 사이드바 — 필터 + 분류 버튼
# ------------------------------------------------------------------

def sidebar_filters(df: pd.DataFrame):
    st.sidebar.title("🔍 필터")

    def multiselect_filter(label: str, col: str) -> list:
        options = sorted(df[col].dropna().unique().tolist())
        options = [o for o in options if o != ""]
        return st.sidebar.multiselect(label, options, default=[])

    sel_category = multiselect_filter("카테고리", "category")
    sel_sector   = multiselect_filter("섹터",     "sector")

    st.sidebar.divider()

    st.sidebar.markdown("**게재일 범위**")
    today    = datetime.now().date()
    week_ago = today - timedelta(days=7)

    date_from = st.sidebar.date_input("From", value=week_ago)
    date_to   = st.sidebar.date_input("To",   value=today)

    filtered = df.copy()
    if sel_category: filtered = filtered[filtered["category"].isin(sel_category)]
    if sel_sector:   filtered = filtered[filtered["sector"].isin(sel_sector)]

    filtered = filtered[
        (filtered["published_at"].dt.date >= date_from) &
        (filtered["published_at"].dt.date <= date_to)
    ]

    st.sidebar.divider()

    hide_paywalled = st.sidebar.checkbox("🔒 유료 기사 숨기기", value=True)
    if hide_paywalled:
        filtered = filtered[~filtered["access_limited"]]

    st.sidebar.divider()

    st.sidebar.markdown("**분류 실행**")
    unclassified_count = int((~df["classified"]).sum())

    btn_label    = f"▶ Claude 분류 실행 ({unclassified_count}건)" if unclassified_count > 0 else "✓ 분류 완료"
    btn_type     = "primary" if unclassified_count > 0 else "secondary"
    btn_disabled = unclassified_count == 0

    if st.sidebar.button(btn_label, type=btn_type, disabled=btn_disabled, use_container_width=True):
        with st.spinner("Claude 분류 중..."):
            try:
                result = run_classifier()
                st.sidebar.success(
                    f"완료: 성공 {result['success']}건 / "
                    f"실패 {result['failed']}건 / "
                    f"남은 미분류 {result['remaining']}건"
                )
                reload()
            except RuntimeError as e:
                st.sidebar.error(str(e))

    return filtered, hide_paywalled, date_from, date_to


# ------------------------------------------------------------------
# 공통 테이블 렌더링 헬퍼
# ------------------------------------------------------------------

def _render_table(data: pd.DataFrame, extra_cols: dict = None):
    """게재일/제목(링크)/섹터/이벤트태그/분류근거 공통 테이블."""
    if data.empty:
        st.info("관련 기사 없음")
        return

    display = data.sort_values("published_at", ascending=False).copy()
    display["제목_text"] = display["title"]
    display["링크"] = display["url"]
    display["게재일"] = display["published_at"].dt.strftime("%Y-%m-%d")
    display["분류근거"] = display["claude_rationale"].str[:100]

    base_cols = {
        "게재일":     "게재일",
        "제목_text":  "제목",
        "링크":       "링크",
        "sector":    "섹터",
        "event_tags": "이벤트 태그",
        "분류근거":   "분류근거",
    }
    if extra_cols:
        merged = {}
        for k, v in base_cols.items():
            if k == "sector":
                merged.update(extra_cols)
            merged[k] = v
        base_cols = merged

    st.dataframe(
        display[list(base_cols.keys())].rename(columns=base_cols),
        use_container_width=True,
        hide_index=True,
        column_config={
            "게재일":    st.column_config.DateColumn(width=85, format="MM-DD"),
            "제목":      st.column_config.Column(width="large"),
            "링크":      st.column_config.LinkColumn("링크", width=60),
            "섹터":      st.column_config.Column(width=90),
            "이벤트 태그": st.column_config.Column(width=120),
            "분류근거":  st.column_config.Column(width="large"),
        },
    )


# ------------------------------------------------------------------
# 우미 관련 높음 섹션
# ------------------------------------------------------------------

def high_relevance_section(df: pd.DataFrame, hide_paywalled: bool, date_from, date_to):
    high = df[
        (df["woomi_relevance"] == "높음") &
        (~df["access_limited"]) &
        (df["published_at"].dt.date >= date_from) &
        (df["published_at"].dt.date <= date_to)
    ].copy()

    st.markdown(f"### ⭐ 우미 관련 높음 ({len(high):,}건)")

    if high.empty:
        st.info("이번 주 관련 기사가 없습니다.")
        return

    _render_table(high)


# ------------------------------------------------------------------
# 기사 테이블
# ------------------------------------------------------------------

def article_table(filtered: pd.DataFrame):
    st.markdown("### 전체 기사")

    if filtered.empty:
        st.info("조건에 맞는 기사가 없습니다.")
        return

    _render_table(filtered)


# ------------------------------------------------------------------
# 전략 신호 모니터 (4개 탭)
# ------------------------------------------------------------------

def signal_monitor_section(df: pd.DataFrame, hide_paywalled: bool, date_from, date_to):
    st.markdown("### 📡 전략 신호 모니터")

    base = df[
        (df["published_at"].dt.date >= date_from) &
        (df["published_at"].dt.date <= date_to)
    ].copy()
    if hide_paywalled:
        base = base[~base["access_limited"]]

    def has_tag(series: pd.Series, *tags) -> pd.Series:
        pattern = "|".join(tags)
        return series.str.contains(pattern, na=False)

    residential_sectors = ["BTR", "SFR", "Multifamily", "Workforce Housing", "Affordable Housing"]
    residential = base[
        base["sector"].isin(residential_sectors) |
        has_tag(base["event_tags"], "rent_occupancy", "construction_start", "delivery", "permit")
    ]

    cap = base[
        (base["sector"] == "Multifamily") & has_tag(base["event_tags"], "financing") |
        (base["source"] == "Federal Reserve")
    ]

    gp = base[
        (base["category"] == "GP·자본흐름") &
        base["sector"].isin(["BTR", "Multifamily"]) &
        has_tag(base["event_tags"], "transaction", "acquisition", "JV")
    ]

    sh_base = base[base["sector"] == "Student Housing"].copy()

    tab1, tab2, tab3, tab4 = st.tabs([
        f"🏗️ 주거시장 공급·수요 ({len(residential)}건)",
        f"💰 자본시장·금리 ({len(cap)}건)",
        f"🤝 GP·거래 동향 ({len(gp)}건)",
        f"🎓 Student Housing ({len(sh_base)}건)",
    ])

    with tab1:
        _render_table(residential)

    with tab2:
        _render_table(cap)

    with tab3:
        _render_table(gp)

    with tab4:
        show_low = st.checkbox("낮음 기사 포함", value=False, key="sh_show_low")
        sh = sh_base.copy()
        if not show_low:
            sh = sh[sh["woomi_relevance"] != "낮음"]

        if sh.empty:
            st.info("표시할 기사가 없습니다. '낮음 기사 포함'을 체크하면 전체 확인 가능합니다.")
        else:
            _render_table(sh)


# ------------------------------------------------------------------
# 메인
# ------------------------------------------------------------------

def main():
    st.title("🏠 US Residential Intelligence v2")
    st.caption("우미글로벌 해외사업팀 | 미국 주거시장 뉴스 수집·분류 대시보드")

    df = load_data()

    if df.empty:
        st.warning("articles.csv가 없습니다. 먼저 `python collector.py`를 실행하세요.")
        return

    filtered, hide_paywalled, date_from, date_to = sidebar_filters(df)
    high_relevance_section(df, hide_paywalled, date_from, date_to)
    st.divider()
    signal_monitor_section(df, hide_paywalled, date_from, date_to)
    st.divider()
    article_table(filtered)


if __name__ == "__main__":
    main()
