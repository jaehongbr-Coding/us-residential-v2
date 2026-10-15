"""
US Residential Intelligence v2 — market_store.py
시장 맥락 판정(market_tagger.py) 산출물을 저장하는 SQLite 사이드카.

geo_store.py·label_store.py와 동일한 패턴이다: articles.csv/archive에는 아무것도
쓰지 않고, article_id로 조인해서만 쓰는 렌즈 저장소다. 원장을 읽지 않는다.
PK에 rule_version을 포함해 규칙 상향 시 과거 행을 보존한다 (M3).
"""
from __future__ import annotations
import sqlite3

MARKET_DB = "market_flags.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS market_flags (
    article_id       TEXT NOT NULL,
    cbsa_code        TEXT NOT NULL,
    rule_version     TEXT NOT NULL,
    as_of            TEXT,
    coverage         TEXT,
    units_12m        INTEGER,
    units_avg3y      REAL,
    ratio_12m_vs_3y  REAL,
    flags            TEXT,
    tagged_at        TEXT,
    PRIMARY KEY (article_id, cbsa_code, rule_version)
);
CREATE INDEX IF NOT EXISTS idx_mf_cbsa  ON market_flags(cbsa_code);
CREATE INDEX IF NOT EXISTS idx_mf_flags ON market_flags(flags);
"""

COLS = ["article_id", "cbsa_code", "rule_version", "as_of", "coverage", "units_12m",
        "units_avg3y", "ratio_12m_vs_3y", "flags", "tagged_at"]


def open_market(path: str = MARKET_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def tagged_keys(conn: sqlite3.Connection, rule_version: str) -> set[tuple[str, str]]:
    return set(conn.execute(
        "SELECT article_id, cbsa_code FROM market_flags WHERE rule_version=?", (rule_version,)))


def upsert_flag(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        f"INSERT OR REPLACE INTO market_flags ({','.join(COLS)}) VALUES ({','.join('?' * len(COLS))})",
        [row.get(k) for k in COLS],
    )


def get_flags(conn: sqlite3.Connection, article_ids: list[str],
              rule_version: str | None = None) -> dict[str, list[dict]]:
    """article_id 목록으로 일괄 조회. 반환: {article_id: [행 dict, ...]} (CBSA별 1행)."""
    out: dict[str, list[dict]] = {}
    CHUNK = 900  # SQLite 변수 바인딩 상한(기본 999) 대비 청크 분할
    for i in range(0, len(article_ids), CHUNK):
        chunk = article_ids[i:i + CHUNK]
        q = f"SELECT {','.join(COLS)} FROM market_flags WHERE article_id IN ({','.join('?' * len(chunk))})"
        args = list(chunk)
        if rule_version:
            q += " AND rule_version=?"
            args.append(rule_version)
        for r in conn.execute(q, args):
            d = dict(zip(COLS, r))
            out.setdefault(d["article_id"], []).append(d)
    return out


def count_flags(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM market_flags").fetchone()[0]
