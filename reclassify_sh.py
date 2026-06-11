"""
reclassify_sh.py
Student Housing 높음 기사를 강화된 룰로 재분류 (Claude API 호출 없음).
"""

import csv
import re
import os

ARTICLES_CSV = "articles.csv"

CSV_COLUMNS = [
    "article_id", "collected_at", "published_at", "source",
    "title", "url", "summary", "classified",
    "category", "event_tags", "signal_type", "sector",
    "woomi_relevance", "claude_rationale", "access_limited",
]

MAJOR_PLATFORMS = ["core spaces", "landmark", "greystar", "hackberry", "balfour", "dinerstein"]
PLATFORM_KEYWORDS = ["platform", "portfolio"]

def has_tag(event_tags: str, *tags) -> bool:
    parts = {t.strip().lower() for t in event_tags.split(",")}
    return any(t.lower() in parts for t in tags)

def mentions_beds_500plus(text: str) -> bool:
    matches = re.findall(r"([\d,]+)\s*[-\s]?bed", text, re.IGNORECASE)
    for m in matches:
        try:
            if int(m.replace(",", "")) >= 500:
                return True
        except ValueError:
            pass
    return False

def mentions_50m_plus(text: str) -> bool:
    matches = re.findall(r"\$([\d,.]+)\s*(m|million|b|billion)", text, re.IGNORECASE)
    for amount, unit in matches:
        try:
            val = float(amount.replace(",", ""))
            if unit.lower() in ("b", "billion"):
                val *= 1000
            if val >= 50:
                return True
        except ValueError:
            pass
    return False

def mentions_major_platform(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in MAJOR_PLATFORMS)

def mentions_platform_keyword(text: str) -> bool:
    lower = text.lower()
    return any(k in lower for k in PLATFORM_KEYWORDS)

def should_keep_high(row: dict) -> bool:
    tags = row.get("event_tags", "")
    title = row.get("title", "")
    summary = row.get("summary", "")
    combined = f"{title} {summary}"

    if mentions_major_platform(combined):
        return True
    if mentions_50m_plus(combined):
        return True
    if mentions_beds_500plus(combined):
        return True
    if has_tag(tags, "transaction") and has_tag(tags, "acquisition"):
        return True
    if has_tag(tags, "jv"):
        return True
    if mentions_platform_keyword(combined):
        return True

    return False


def main():
    if not os.path.exists(ARTICLES_CSV):
        print(f"{ARTICLES_CSV} 없음")
        return

    with open(ARTICLES_CSV, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    targets = [
        r for r in rows
        if r.get("sector") == "Student Housing" and r.get("woomi_relevance") == "높음"
    ]

    print(f"전체 기사: {len(rows)}건")
    print(f"Student Housing 높음 대상: {len(targets)}건\n")

    downgraded = 0
    kept = 0

    for row in rows:
        if row.get("sector") != "Student Housing" or row.get("woomi_relevance") != "높음":
            continue
        if should_keep_high(row):
            kept += 1
        else:
            row["woomi_relevance"] = "보통"
            downgraded += 1

    with open(ARTICLES_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"높음 유지: {kept}건")
    print(f"보통 다운그레이드: {downgraded}건")
    print(f"\n→ {ARTICLES_CSV} 저장 완료")


if __name__ == "__main__":
    main()
