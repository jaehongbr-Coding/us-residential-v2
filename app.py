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

    # 날짜 컬럼 변환
    for col in ("collected_at", "published_at"):
        df[col] = pd.to_datetime(df[col], errors="coerce")

    # bool 변환
    df["classified"]    = df["classified"].str.lower() == "true"
    df["access_limited"] = df["access_limited"].str.lower() == "true"

    return df


def reload():
    st.cache_data.clear()
    st.rerun()


# ------------------------------------------------------------------
# 사이드바 — 필터 + 분류 버튼
# ------------------------------------------------------------------

def sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.title("🔍 필터")

    def multiselect_filter(label: str, col: str) -> list:
        options = sorted(df[col].dropna().unique().tolist())
        options = [o for o in options if o != ""]
        return st.sidebar.multiselect(label, options, default=[])

    sel_category  = multiselect_filter("카테고리",  "category")
    sel_sector    = multiselect_filter("섹터",      "sector")
    sel_signal    = multiselect_filter("시그널",    "signal_type")
    sel_source    = multiselect_filter("출처",      "source")

    st.sidebar.divider()

    # 날짜 필터
    st.sidebar.markdown("**게재일 범위**")
    min_date = df["published_at"].min()
    max_date = df["published_at"].max()

    if pd.isna(min_date):
        min_date = datetime.now() - timedelta(days=30)
    if pd.isna(max_date):
        max_date = datetime.now()

    date_from = st.sidebar.date_input("From", value=min_date.date())
    date_to   = st.sidebar.date_input("To",   value=max_date.date())

    # 필터 적용
    filtered = df.copy()
    if sel_category:  filtered = filtered[filtered["category"].isin(sel_category)]
    if sel_sector:    filtered = filtered[filtered["sector"].isin(sel_sector)]
    if sel_signal:    filtered = filtered[filtered["signal_type"].isin(sel_signal)]
    if sel_source:    filtered = filtered[filtered["source"].isin(sel_source)]

    filtered = filtered[
        (filtered["published_at"].dt.date >= date_from) &
        (filtered["published_at"].dt.date <= date_to)
    ]

    st.sidebar.divider()

    # 유료 기사 필터
    hide_paywalled = st.sidebar.checkbox("🔒 유료 기사 숨기기", value=True)
    if hide_paywalled:
        filtered = filtered[~filtered["access_limited"]]

    st.sidebar.divider()

    # 분류 실행 버튼
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

    return filtered, hide_paywalled


# ------------------------------------------------------------------
# 상단 요약 카드
# ------------------------------------------------------------------

def summary_cards(df: pd.DataFrame, filtered: pd.DataFrame):
    total       = len(df)
    unclassified = int((~df["classified"]).sum())
    high_rel    = int((df["woomi_relevance"] == "높음").sum())
    one_week_ago = datetime.now() - timedelta(days=7)
    this_week   = int((df["published_at"] >= one_week_ago).sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("전체 기사",   f"{total:,}건")
    c2.metric("미분류",      f"{unclassified:,}건")
    c3.metric("높음 (우미관련)", f"{high_rel:,}건")
    c4.metric("이번 주 수집", f"{this_week:,}건")


# ------------------------------------------------------------------
# 기사 테이블
# ------------------------------------------------------------------

def article_table(filtered: pd.DataFrame):
    st.markdown(f"### 기사 목록 ({len(filtered):,}건)")

    if filtered.empty:
        st.info("조건에 맞는 기사가 없습니다.")
        return

    display = filtered.copy()

    display["제목"] = display.apply(
        lambda r: f"{'🔒 ' if r['access_limited'] else ''}{r['title']}",
        axis=1,
    )
    display["게재일"] = display["published_at"].dt.strftime("%Y-%m-%d")

    cols = {
        "게재일":           "게재일",
        "source":          "출처",
        "제목":            "제목",
        "url":             "원문",
        "category":        "카테고리",
        "sector":          "섹터",
        "event_tags":      "이벤트 태그",
        "signal_type":     "시그널",
        "claude_rationale": "분류 근거",
    }

    st.dataframe(
        display[list(cols.keys())].rename(columns=cols),
        use_container_width=True,
        hide_index=True,
        column_config={
            "제목": st.column_config.Column(width="large"),
            "원문": st.column_config.LinkColumn(
                display_text="🔗 링크",
                width="small",
            ),
            "분류 근거": st.column_config.Column(width="large"),
        },
    )


# ------------------------------------------------------------------
# Student Housing 모니터
# ------------------------------------------------------------------

def show_student_housing_section(df: pd.DataFrame, hide_paywalled: bool = True):
    st.markdown("### 🎓 Student Housing 모니터")

    sh = df[df["sector"] == "Student Housing"].copy()
    if hide_paywalled:
        sh = sh[~sh["access_limited"]]

    if sh.empty:
        st.info("Student Housing 기사가 없습니다.")
        return

    # 대학명 추출: "Student Housing — {name} ({state})" → name
    def parse_university(source: str) -> str:
        try:
            after = source.split("Student Housing — ", 1)[1]
            return after.rsplit(" (", 1)[0]
        except (IndexError, ValueError):
            return source

    sh["대학명"] = sh["source"].apply(parse_university)

    # 대학별 집계 테이블
    univ_total = sh.groupby("대학명").size().rename("기사 수")
    univ_high  = sh[sh["woomi_relevance"] == "높음"].groupby("대학명").size().rename("높음 건수")
    univ_stats = pd.concat([univ_total, univ_high], axis=1).fillna(0).astype(int)
    univ_stats = univ_stats.sort_values("기사 수", ascending=False).reset_index()

    st.dataframe(univ_stats, use_container_width=True, hide_index=True, height=200)

    # 낮음 기사 포함 토글
    show_low = st.checkbox("낮음 기사 포함", value=False, key="sh_show_low")
    if not show_low:
        sh = sh[sh["woomi_relevance"] != "낮음"]

    if sh.empty:
        st.info("표시할 기사가 없습니다. '낮음 기사 포함'을 체크하면 전체 확인 가능합니다.")
        return

    # 기사 테이블 (woomi_relevance == "높음" 이면 ⭐)
    sh["제목"] = sh.apply(
        lambda r: f"{'⭐ ' if r['woomi_relevance'] == '높음' else ''}{'🔒 ' if r['access_limited'] else ''}{r['title']}",
        axis=1,
    )
    sh["게재일"] = sh["published_at"].dt.strftime("%Y-%m-%d")

    cols = {
        "게재일":           "게재일",
        "대학명":           "대학",
        "제목":            "제목",
        "url":             "원문",
        "event_tags":      "이벤트 태그",
        "woomi_relevance": "우미 관련도",
        "claude_rationale": "분류 근거",
    }

    st.dataframe(
        sh[list(cols.keys())].rename(columns=cols),
        use_container_width=True,
        hide_index=True,
        column_config={
            "제목": st.column_config.Column(width="large"),
            "원문": st.column_config.LinkColumn(display_text="🔗 링크", width="small"),
            "분류 근거": st.column_config.Column(width="large"),
        },
    )


# ------------------------------------------------------------------
# CSV 내보내기
# ------------------------------------------------------------------

def export_button(filtered: pd.DataFrame):
    if filtered.empty:
        return
    csv_bytes = filtered.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="CSV 내보내기",
        data=csv_bytes,
        file_name=f"residential_intel_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )


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

    filtered, hide_paywalled = sidebar_filters(df)
    summary_cards(df, filtered)
    st.divider()
    article_table(filtered)
    st.divider()
    export_button(filtered)
    st.divider()
    show_student_housing_section(df, hide_paywalled)


if __name__ == "__main__":
    main()
