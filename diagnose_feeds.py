"""
diagnose_feeds.py — 일회성 진단 스크립트. production(GitHub Actions) 러너에서
실행해야 의미가 있다 (로컬 PC 테스트는 로컬 IP가 차단당해 살아있는 대조군까지
403으로 나와 판정 불가였음 — 그래서 이 스크립트를 만듦).

이 파일은 어떤 기존 파일도 수정하지 않으며, 자기 자신도 어떤 파일에 쓰지 않는다.
articles.csv는 테스트 3에서 읽기만 한다.

collector.py는 528행에 `if __name__ == "__main__":` 가드가 있어 import해도
main()이 실행되지 않는다 (확인됨). 따라서 ast/정규식 우회 없이 그대로 import한다.

RSS_FEEDS / REQUEST_HEADERS / _FETCH_SOURCES는 collector.py에서 그대로 가져와
production 실제 값으로 테스트한다 (재정의하지 않음).
"""
import time

import feedparser
import pandas as pd
import requests
from bs4 import BeautifulSoup

from collector import RSS_FEEDS, REQUEST_HEADERS, _FETCH_SOURCES

UA_BOT = REQUEST_HEADERS  # production 값 그대로 (WoomiGlobalResearchBot/2.0 포함)
UA_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def _report_feed(source: str, ua_label: str, url: str) -> None:
    headers = UA_BOT if ua_label == "BOT" else UA_BROWSER
    try:
        f = feedparser.parse(url, request_headers=headers)
        entries = f.entries
        status = getattr(f, "status", "?")
        bozo = getattr(f, "bozo", "?")
        bozo_exc = type(f.bozo_exception).__name__ if getattr(f, "bozo_exception", None) else "-"
        latest = entries[0].get("published", "-")[:25] if entries else "-"
        print(
            f"{source:28s} | {ua_label:7s} | status={str(status):>5} | "
            f"entries={len(entries):>3} | bozo={str(bozo):>5} | "
            f"bozo_exc={bozo_exc:20s} | latest={latest}"
        )
    except Exception as e:
        print(f"{source:28s} | {ua_label:7s} | ERROR {type(e).__name__}: {e}")


def test1_all_feeds() -> None:
    print("=" * 100)
    print(f"테스트 1 — RSS_FEEDS 전체 ({len(RSS_FEEDS)}개) x UA_BOT/UA_BROWSER")
    print("=" * 100)
    for feed in RSS_FEEDS:
        source, url = feed["source"], feed["url"]
        _report_feed(source, "BOT", url)
        time.sleep(1.0)
        _report_feed(source, "BROWSER", url)
        time.sleep(1.0)


def test2_connect_cre_patterns() -> None:
    print()
    print("=" * 100)
    print("테스트 2 — Connect CRE 지역 피드 URL 패턴 후보 (UA_BOT)")
    print("=" * 100)
    candidates = [
        ("CCRE Seattle (story-market)", "https://www.connectcre.com/feed?story-market=seattle"),
        ("CCRE Denver (story-market)", "https://www.connectcre.com/feed?story-market=denver"),
        ("CCRE California (story-market)", "https://www.connectcre.com/feed?story-market=california"),
        ("CCRE LA (story-market)", "https://www.connectcre.com/feed?story-market=los-angeles"),
        ("CCRE Charlotte (story-market)", "https://www.connectcre.com/feed?story-market=charlotte"),
        ("CCRE North Carolina (story-market)", "https://www.connectcre.com/feed?story-market=north-carolina"),
        ("CCRE Atlanta (region/, 대조군)", "https://www.connectcre.com/region/atlanta/feed"),
    ]
    for name, url in candidates:
        _report_feed(name, "BOT", url)
        time.sleep(1.0)
    print()
    print(
        "※ 대조군(Atlanta, region/ 패턴)이 0이면 'region/X/feed' 패턴 자체가 죽은 것"
        "(패턴 가설 확증). 정상이면 패턴 가설 기각 — 시장별 개별 문제로 봐야 함."
    )


def test3_body_fetch() -> None:
    print()
    print("=" * 100)
    print("테스트 3 — 본문 fetch 실측 (A6 검증: fetch 성공 vs 조용한 실패 구분)")
    print("=" * 100)

    try:
        df = pd.read_csv("articles.csv", dtype=str).fillna("")
    except FileNotFoundError:
        print("articles.csv 없음 — 테스트 3 스킵")
        return

    for source in sorted(_FETCH_SOURCES):
        sub = df[df.source == source]
        if sub.empty:
            print(f"{source:24s} | 기사 없음 (수집 이력 없음)")
            continue
        sub = sub.sort_values("published_at", ascending=False).head(2)
        for _, row in sub.iterrows():
            url = row["url"]
            try:
                resp = requests.get(url, headers=UA_BOT, timeout=5)
                text = BeautifulSoup(resp.text, "html.parser").get_text(separator=" ")
                text_len = len(text.strip())
                judged = text_len < 300  # 현재 _judge_access_limited() 로직 기준
                print(
                    f"{source:24s} | status={resp.status_code:>3} | text_len={text_len:>5} "
                    f"| access_limited(len<300)={str(judged):5} | url={url}"
                )
            except Exception as e:
                print(f"{source:24s} | EXCEPTION {type(e).__name__}: {e} | url={url}")
            time.sleep(1.0)


if __name__ == "__main__":
    test1_all_feeds()
    test2_connect_cre_patterns()
    test3_body_fetch()
