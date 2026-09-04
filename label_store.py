"""
US Residential Intelligence v2 — label_store.py
렌즈(classifier.py) 산출물을 저장하는 SQLite 저장소.

원장(archive/)은 수집 사실 8필드만 갖는 raw ledger다. 분류 필드
(classified, category, event_tags, signal_type, sector, woomi_relevance,
claude_rationale, korean_summary)는 언제든 교체 가능한 렌즈 산출물이므로
여기 labels.db에 분리 저장한다. article_id로 원장과 조인해 작업본
(articles.csv)을 만든다.
"""

import sqlite3
from datetime import datetime

LABELS_DB = "labels.db"

LABEL_FIELDS = [
    "classified", "category", "event_tags", "signal_type", "sector",
    "woomi_relevance", "claude_rationale", "korean_summary",
]


def open_labels() -> sqlite3.Connection:
    conn = sqlite3.connect(LABELS_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS labels (
            article_id       TEXT PRIMARY KEY,
            classified       TEXT,
            category         TEXT,
            event_tags       TEXT,
            signal_type      TEXT,
            sector           TEXT,
            woomi_relevance  TEXT,
            claude_rationale TEXT,
            korean_summary   TEXT,
            labeled_at       TEXT,
            lens_version     TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_labels_relevance ON labels(woomi_relevance)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_labels_sector ON labels(sector)")
    return conn


def get_labels(conn: sqlite3.Connection, article_ids: list) -> dict:
    """article_id 목록으로 일괄 조회. 없는 id는 결과에서 빠진다.
    반환: {article_id: {필드: 값, ...}}"""
    if not article_ids:
        return {}

    result = {}
    # SQLite 변수 바인딩 상한(기본 999) 대비 청크 분할
    CHUNK = 900
    for i in range(0, len(article_ids), CHUNK):
        chunk = article_ids[i:i + CHUNK]
        placeholders = ",".join("?" * len(chunk))
        cols = ["article_id"] + LABEL_FIELDS
        rows = conn.execute(
            f"SELECT {','.join(cols)} FROM labels WHERE article_id IN ({placeholders})",
            chunk,
        ).fetchall()
        for row in rows:
            aid = row[0]
            result[aid] = dict(zip(LABEL_FIELDS, row[1:]))
    return result


def upsert_labels(conn: sqlite3.Connection, article_id: str, label_dict: dict, lens_version: str = "v1") -> None:
    labeled_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    values = [article_id] + [label_dict.get(f, "") for f in LABEL_FIELDS] + [labeled_at, lens_version]
    conn.execute(
        f"""INSERT OR REPLACE INTO labels
            (article_id, {",".join(LABEL_FIELDS)}, labeled_at, lens_version)
            VALUES ({",".join("?" * len(values))})""",
        values,
    )


def count_labels(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
