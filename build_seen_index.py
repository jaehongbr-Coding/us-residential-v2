"""
US Residential Intelligence v2 — build_seen_index.py
articles.csv로부터 seen_index.db(SQLite 중복 체크 인덱스)를 생성/재생성한다.

seen_index.db는 articles.csv에서 파생되는 캐시다. 손상되거나 삭제되어도
이 스크립트를 다시 실행하면 언제든 재생성할 수 있다. 중복 판정 규칙
(article_id 일치 OR (정규화제목, 발행일 앞 10자) 일치)은 collector.py의
구버전(전량 CSV 로드 방식)과 완전히 동일하다.

사용법:
  python -u build_seen_index.py
"""

import csv
import os
import re
import sqlite3
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# collector.py._norm_title / make_article_id를 그대로 재사용해 정규화 규칙이
# 어긋나지 않도록 한다. collector.py는 임포트해도 네트워크 부수효과가 없다
# (main()은 __main__ 가드 안에만 있음).
from collector import _norm_title  # noqa: E402

ARTICLES_CSV = "articles.csv"
SEEN_DB      = "seen_index.db"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
_ID_RE   = re.compile(r"^[0-9a-f]{12}$")


def build():
    if not os.path.exists(ARTICLES_CSV):
        print(f"[ERROR] {ARTICLES_CSV} 가 없습니다.")
        return

    # 멱등성 — 기존 DB가 있으면 파일째 삭제 후 재생성
    if os.path.exists(SEEN_DB):
        os.remove(SEEN_DB)
        print(f"[INFO] 기존 {SEEN_DB} 삭제 후 재생성합니다.")

    conn = sqlite3.connect(SEEN_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            article_id  TEXT PRIMARY KEY,
            title_key   TEXT NOT NULL,
            source      TEXT,
            published   TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_title_key ON seen(title_key)")

    inserted = 0
    dup_ids  = 0
    skipped  = []

    with open(ARTICLES_CSV, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            article_id = (row.get("article_id") or "").strip()
            published  = row.get("published_at") or ""
            title      = row.get("title") or ""
            source     = row.get("source") or ""

            # 손상 행(article_id가 12자 hex가 아니거나 published_at이 날짜 형식이
            # 아닌 행)은 인덱스에서 제외한다. 정상 article_id는 sha256(url)[:12]
            # 이므로 손상 문자열과 충돌할 수 없고, 해당 원본 기사는 향후 정상
            # 형식으로 재수집된다.
            if not _ID_RE.match(article_id) or not _DATE_RE.match(published):
                reason = ("article_id가 12자리 hex 형식이 아님" if not _ID_RE.match(article_id)
                          else "published_at 날짜 형식 아님")
                skipped.append((row, source, reason))
                continue

            title_key = f"{_norm_title(title)}|{published[:10]}"
            cur = conn.execute(
                "INSERT OR IGNORE INTO seen (article_id, title_key, source, published) "
                "VALUES (?, ?, ?, ?)",
                (article_id, title_key, source, published),
            )
            if cur.rowcount:
                inserted += 1
            else:
                dup_ids += 1  # article_id가 CSV 내에서 이미 중복 — PRIMARY KEY라 무시됨

    conn.commit()

    db_size = os.path.getsize(SEEN_DB)
    with open(ARTICLES_CSV, encoding="utf-8", newline="") as f:
        total_rows = sum(1 for _ in csv.DictReader(f))

    print("\n--- build_seen_index 완료 ---")
    print(f"  총 삽입: {inserted}건")
    print(f"  skip: {len(skipped)}건")
    if dup_ids:
        print(f"  CSV 내 article_id 중복(무시됨): {dup_ids}건")
    print(f"  DB 파일 크기: {db_size:,} bytes")
    print(f"  articles.csv 행 수: {total_rows}건 (삽입 {inserted}건과의 차이: {total_rows - inserted}건)")

    if skipped:
        print("\n--- skip된 손상 행 전체 필드 (원인 조사용) ---")
        for row, source, reason in skipped:
            print(f"  사유: {reason}")
            for k, v in row.items():
                print(f"    {k}: {v!r}")

    conn.close()


if __name__ == "__main__":
    build()
