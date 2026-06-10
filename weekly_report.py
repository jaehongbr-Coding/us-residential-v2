"""
US Residential Intelligence v2 — weekly_report.py
articles.csv 기반 인텔리전스 리포트(주간/월간/분기/반기) 자동 생성.

사용법:
  python weekly_report.py                  # 기본: 최근 7일 (weekly)
  python weekly_report.py --period monthly  # 최근 30일
  python weekly_report.py --period quarterly
  python weekly_report.py --period semi-annual
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta, timezone

import anthropic
from dotenv import load_dotenv

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ------------------------------------------------------------------
# 설정
# ------------------------------------------------------------------

ARTICLES_CSV = "articles.csv"
REPORTS_DIR  = "reports"
MODEL        = "claude-sonnet-4-5"
MAX_TOKENS   = 4000

PERIOD_DAYS = {
    "weekly":       7,
    "monthly":      30,
    "quarterly":    90,
    "semi-annual": 180,
}

PERIOD_LABEL = {
    "weekly":       "주간",
    "monthly":      "월간",
    "quarterly":    "분기",
    "semi-annual":  "반기",
}

SYSTEM_PROMPT = (
    "당신은 우미글로벌 해외사업팀의 미국 주거시장 리서치 애널리스트입니다. "
    "수집된 뉴스 기사를 바탕으로 경영진과 팀원이 읽을 원페이저 인텔리전스 리포트를 작성합니다."
)

REPORT_TEMPLATE = """\
아래는 {period_label} 수집된 미국 주거시장 뉴스 기사 {count}건입니다.
기간: {date_from} ~ {date_to}

{articles_text}

---

위 기사들을 바탕으로 아래 4개 섹션으로 구성된 한국어 인텔리전스 리포트를 작성해주세요.
각 섹션은 3~5개 bullet point로 핵심만 간결하게 정리합니다.
수치·규모·지역 정보가 있으면 반드시 포함하세요.

## 1. 개발 현황
섹터별 주요 개발 프로젝트, 지역, unit 수 (가능한 경우), 주목할 움직임.

## 2. 정책·이슈
인허가·세금·금리 관련 주요 정부 정책 및 시장 이슈.

## 3. 거래현황
상품별 거래 규모, 주요 자본 흐름 (domestic vs. 글로벌), 주요 플레이어.

## 4. 시사점
우미글로벌 해외사업팀 관점에서의 전략적 함의. BTR/Student Housing/GP 파트너십 기회 중심.
"""


# ------------------------------------------------------------------
# 데이터 로드 및 필터
# ------------------------------------------------------------------

def load_articles() -> list[dict]:
    if not os.path.exists(ARTICLES_CSV):
        return []
    with open(ARTICLES_CSV, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def filter_by_period(articles: list[dict], days: int) -> list[dict]:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    result = []
    for a in articles:
        raw = a.get("published_at", "")
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                result.append(a)
        except ValueError:
            continue
    return result


def format_articles(articles: list[dict]) -> str:
    lines = []
    for i, a in enumerate(articles, 1):
        tags = a.get("event_tags", "")
        lines.append(
            f"{i}. [{a.get('category','')} / {a.get('sector','')}] "
            f"{a.get('title','')}\n"
            f"   요약: {a.get('summary','')[:200]}\n"
            f"   태그: {tags}"
        )
    return "\n\n".join(lines)


# ------------------------------------------------------------------
# 리포트 생성
# ------------------------------------------------------------------

def generate_report(articles: list[dict], period: str) -> str:
    days = PERIOD_DAYS[period]

    date_to   = datetime.now().strftime("%Y-%m-%d")
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # woomi_relevance 높음 우선, 최대 100건으로 제한
    sorted_articles = sorted(
        articles,
        key=lambda a: (0 if a.get("woomi_relevance") == "높음" else 1 if a.get("woomi_relevance") == "보통" else 2)
    )[:100]
    articles_text = format_articles(sorted_articles)
    user_prompt = REPORT_TEMPLATE.format(
        period_label=PERIOD_LABEL[period],
        count=len(articles),
        date_from=date_from,
        date_to=date_to,
        articles_text=articles_text,
    )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text.strip()


# ------------------------------------------------------------------
# 저장
# ------------------------------------------------------------------

def save_report(content: str, period: str) -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)

    today    = datetime.now().strftime("%Y%m%d")
    filename = f"{today}_{period}.md"
    filepath = os.path.join(REPORTS_DIR, filename)

    days      = PERIOD_DAYS[period]
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    date_to   = datetime.now().strftime("%Y-%m-%d")
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    meta = (
        f"---\n"
        f"기간: {date_from} ~ {date_to} ({PERIOD_LABEL[period]})\n"
        f"생성: {generated}\n"
        f"---\n\n"
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(meta + content)

    return filepath


# ------------------------------------------------------------------
# 메인
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="US Residential Intelligence 리포트 생성")
    parser.add_argument(
        "--period",
        choices=list(PERIOD_DAYS.keys()),
        default="weekly",
        help="리포트 기간 (기본값: weekly)",
    )
    args = parser.parse_args()

    period = args.period
    days   = PERIOD_DAYS[period]

    print(f"=== US Residential Intelligence — {PERIOD_LABEL[period]} 리포트 생성 ===")
    print(f"기간: 최근 {days}일\n")

    articles = load_articles()
    if not articles:
        print("articles.csv가 없거나 비어 있습니다. collector.py를 먼저 실행하세요.")
        return

    filtered = filter_by_period(articles, days)
    if not filtered:
        print(f"최근 {days}일 내 기사가 없습니다. 리포트를 생성하지 않습니다.")
        return

    print(f"대상 기사: {len(filtered)}건")
    print("Claude API 호출 중...\n")

    try:
        report_content = generate_report(filtered, period)
    except RuntimeError as e:
        print(f"오류: {e}")
        return

    filepath = save_report(report_content, period)
    print(f"리포트 저장 완료: {filepath}")
    print("\n--- 리포트 미리보기 (처음 500자) ---")
    print(report_content[:500])


if __name__ == "__main__":
    main()
