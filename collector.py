"""
US Residential Intelligence v2 — collector.py
수집 전용. RSS 파싱 → 중복 제거 → articles.csv append.
분류는 classifier.py가 담당.
"""

import csv
import hashlib
import os
import sys
from datetime import datetime
from html import unescape

# Windows cp949 터미널에서 한글·특수문자 출력 가능하도록
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import feedparser
import requests
from bs4 import BeautifulSoup

# ------------------------------------------------------------------
# 1. 설정
# ------------------------------------------------------------------

ARTICLES_CSV = "articles.csv"

CSV_COLUMNS = [
    "article_id", "collected_at", "published_at", "source",
    "title", "url", "summary", "classified",
    "category", "event_tags", "signal_type", "sector",
    "woomi_relevance", "claude_rationale", "access_limited",
]

RSS_FEEDS = [
    # 코어 — Multifamily
    {"source": "Multifamily Dive",       "url": "https://www.multifamilydive.com/feeds/news/",           "sector": "Multifamily"},
    {"source": "Multifamily Executive",  "url": "https://www.multifamilyexecutive.com/rss.xml",           "sector": "Multifamily"},
    {"source": "YieldPro",               "url": "https://yieldpro.com/feed/",                             "sector": "Multifamily"},
    {"source": "Multi-Housing News",     "url": "https://www.multihousingnews.com/feed/",                 "sector": "Multifamily"},
    {"source": "GlobeSt",                "url": "https://www.globest.com/feed/",                          "sector": "CRE"},
    {"source": "Bisnow",                 "url": "https://www.bisnow.com/rss",                             "sector": "CRE"},
    {"source": "Commercial Observer",    "url": "https://commercialobserver.com/feed/",                   "sector": "CRE"},
    {"source": "Connect CRE",            "url": "https://www.connectcre.com/feed/",                       "sector": "CRE"},
    {"source": "The Real Deal",          "url": "https://therealdeal.com/feed/",                          "sector": "CRE"},
    {"source": "HousingWire",            "url": "https://www.housingwire.com/feed/",                      "sector": "Residential"},
    {"source": "Eye on Housing (NAHB)",  "url": "https://eyeonhousing.org/category/multifamily/feed/",    "sector": "Multifamily"},
    {"source": "Construction Dive",      "url": "https://www.constructiondive.com/feeds/news/",           "sector": "Construction"},
    # 협회·정책
    {"source": "NMHC",                   "url": "https://www.nmhc.org/news/rss/",                         "sector": "Policy"},
    {"source": "Urban Land Institute",   "url": "https://urbanland.uli.org/feed/",                        "sector": "Policy"},
    {"source": "Federal Reserve",        "url": "https://www.federalreserve.gov/feeds/press_all.xml",     "sector": "Macro"},
    # 자본·금융
    {"source": "Walker & Dunlop",        "url": "https://www.walkerdunlop.com/insights/feed/",            "sector": "Capital"},
    {"source": "Berkadia",               "url": "https://berkadia.com/feed/",                             "sector": "Capital"},
    {"source": "Blackstone",             "url": "https://www.blackstone.com/news/rss/",                   "sector": "Capital"},
    # 지역 — Sun Belt + West Coast
    {"source": "Connect CRE Texas",       "url": "https://www.connectcre.com/feed?story-market=texas",          "sector": "Multifamily"},
    {"source": "Connect CRE South FL",    "url": "https://www.connectcre.com/feed?story-market=south-florida",  "sector": "Multifamily"},
    {"source": "Connect CRE Phoenix",     "url": "https://www.connectcre.com/feed?story-market=phoenix",        "sector": "Multifamily"},
    {"source": "Connect CRE Atlanta",     "url": "https://www.connectcre.com/feed?story-market=atlanta",        "sector": "Multifamily"},
    {"source": "Connect CRE Charlotte",   "url": "https://www.connectcre.com/feed?story-market=charlotte",      "sector": "Multifamily"},
    {"source": "Connect CRE Seattle",    "url": "https://www.connectcre.com/region/seattle/feed",               "sector": "Multifamily"},
    {"source": "Connect CRE Denver",     "url": "https://www.connectcre.com/region/denver/feed",                "sector": "Multifamily"},
    {"source": "Connect CRE California", "url": "https://www.connectcre.com/region/california/feed",            "sector": "Multifamily"},
    {"source": "Yardi Matrix Blog",      "url": "https://www.yardimatrix.com/blog/feed",                        "sector": "Multifamily"},
    {"source": "LA Urbanize",             "url": "https://la.urbanize.city/rss.xml",                            "sector": "Residential"},
    {"source": "California YIMBY",        "url": "https://californiayimby.com/feed",                            "sector": "Policy"},
    {"source": "SF YIMBY",                "url": "https://sfyimby.com/feed",                                    "sector": "Policy"},
]

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; WoomiGlobalResearchBot/2.0)"
}
FETCH_TIMEOUT = 15  # seconds


# ------------------------------------------------------------------
# 2. RSS 수집
# ------------------------------------------------------------------

def _clean_html(raw: str) -> str:
    return BeautifulSoup(unescape(raw or ""), "html.parser").get_text(separator=" ").strip()


def _parse_published(entry) -> str:
    """published 날짜 파싱. 실패 시 오늘 날짜 반환."""
    try:
        t = entry.get("published_parsed") or entry.get("updated_parsed")
        if t:
            return datetime(*t[:6]).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fetch_feed(source: str, url: str, sector: str) -> list[dict]:
    try:
        feed = feedparser.parse(url, request_headers=REQUEST_HEADERS)
    except Exception as e:
        print(f"  [SKIP] {source} — feedparser 오류: {e}")
        return []

    articles = []
    for entry in feed.entries:
        title = _clean_html(entry.get("title", "")).strip()
        link  = (entry.get("link") or "").strip()
        if not title or not link:
            continue

        # summary: description 우선, 없으면 content
        raw_summary = (
            entry.get("summary")
            or (entry.get("content", [{}])[0].get("value", ""))
        )
        summary = _clean_html(raw_summary)[:400]

        articles.append({
            "article_id":    make_article_id(link),
            "collected_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "published_at":  _parse_published(entry),
            "source":        source,
            "title":         title,
            "url":           link,
            "summary":       summary,
            "classified":    False,
            "category":      "",
            "event_tags":    "",
            "signal_type":   "",
            "sector":        sector,
            "woomi_relevance": "",
            "claude_rationale": "",
            "access_limited": len(summary) < 150,
        })
    return articles


# ------------------------------------------------------------------
# 3. 중복 제거
# ------------------------------------------------------------------

def make_article_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def load_existing_ids() -> set:
    if not os.path.exists(ARTICLES_CSV):
        return set()
    with open(ARTICLES_CSV, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return {row["article_id"] for row in reader}


# ------------------------------------------------------------------
# 4. CSV 저장
# ------------------------------------------------------------------

def save_articles(articles: list[dict]) -> None:
    file_exists = os.path.exists(ARTICLES_CSV)
    with open(ARTICLES_CSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(articles)


# ------------------------------------------------------------------
# 5. 실행
# ------------------------------------------------------------------

def main():
    print(f"=== US Residential Intelligence v2 — Collector ===")
    print(f"시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    existing_ids = load_existing_ids()
    print(f"기존 누적 기사: {len(existing_ids)}건\n")

    total_fetched = 0
    total_skipped = 0
    new_articles   = []

    for feed in RSS_FEEDS:
        source = feed["source"]
        url    = feed["url"]
        sector = feed["sector"]
        print(f"  수집 중: {source}")

        fetched = fetch_feed(source, url, sector)
        total_fetched += len(fetched)

        for article in fetched:
            if article["article_id"] in existing_ids:
                total_skipped += 1
            else:
                existing_ids.add(article["article_id"])
                new_articles.append(article)

    if new_articles:
        save_articles(new_articles)

    print(f"\n--- 수집 완료 ---")
    print(f"  수집: {total_fetched}건")
    print(f"  중복 skip: {total_skipped}건")
    print(f"  신규 저장: {len(new_articles)}건")
    print(f"  → {ARTICLES_CSV}")


if __name__ == "__main__":
    main()
