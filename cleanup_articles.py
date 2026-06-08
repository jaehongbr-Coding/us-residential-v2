"""
US Residential Intelligence v2 — cleanup_articles.py
published_at이 오늘 기준 30일 초과한 기사를 articles.csv에서 삭제.
실행 전 articles_backup.csv 백업 생성.
"""

import csv
import os
import shutil
import sys
from datetime import datetime, timedelta

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ARTICLES_CSV = "articles.csv"
BACKUP_CSV   = "articles_backup.csv"

CSV_COLUMNS = [
    "article_id", "collected_at", "published_at", "source",
    "title", "url", "summary", "classified",
    "category", "event_tags", "signal_type", "sector",
    "woomi_relevance", "claude_rationale", "access_limited",
]


def main():
    print("=== US Residential Intelligence v2 — Cleanup ===")
    print(f"시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    if not os.path.exists(ARTICLES_CSV):
        print(f"[ERROR] {ARTICLES_CSV} 파일이 없습니다.")
        return

    # 백업
    shutil.copy2(ARTICLES_CSV, BACKUP_CSV)
    print(f"백업 완료: {BACKUP_CSV}")

    # 로드
    with open(ARTICLES_CSV, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    total_before = len(rows)
    print(f"삭제 전 기사 수: {total_before}건\n")

    cutoff = datetime.now() - timedelta(days=30)
    kept    = []
    removed = []

    for row in rows:
        pub = row.get("published_at", "").strip()
        try:
            pub_dt = datetime.strptime(pub, "%Y-%m-%d %H:%M:%S")
            if pub_dt < cutoff:
                removed.append(row)
            else:
                kept.append(row)
        except ValueError:
            # 파싱 불가 → 보존
            kept.append(row)

    # 저장
    with open(ARTICLES_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(kept)

    print(f"--- 정리 완료 ---")
    print(f"  삭제된 기사:  {len(removed)}건")
    print(f"  남은 기사:    {len(kept)}건")
    print(f"  기준 날짜:    {cutoff.strftime('%Y-%m-%d')} 이후만 유지")
    print(f"  백업 위치:    {BACKUP_CSV}")


if __name__ == "__main__":
    main()
