"""
US Residential Intelligence v2 — geo_store.py
geo 태깅(Stage A + Stage B) 산출물을 저장하는 SQLite 사이드카.

label_store.py와 동일한 패턴이다: articles.csv/archive에는 아무것도 쓰지
않고(I2), article_id로 조인해서만 쓰는 완전히 분리된 저장소다.

stage_a_json에 Stage A(Claude Haiku) 원본 응답 전문을 그대로 보존한다 —
data/geo/stage_a/{article_id}.json 형태로 7,099개 파일을 커밋하는 대신
이 컬럼 하나로 대체한다(Plan.md §2 "alias 추가 시 API 재호출 없이 Stage B만
재실행" 이점은 동일하게 유지된다 — geo_tagger.py --mode resolve-only가
stage_a_json을 다시 읽어 geo_resolver.resolve()만 재실행한다).
"""

import re
import sqlite3
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import yaml

GEO_DB = "geo_tags.db"
GEO_ALIASES_YAML = Path(__file__).resolve().parent / "data/geo/geo_aliases.yaml"
_SOURCE_SH_RE = re.compile(r"^Student Housing — (.+?) \(([A-Z]{2})\)$")

GEO_FIELDS = [
    "stage_a_json", "geo_place_raw", "geo_cbsa_code", "geo_cbsa_title",
    "geo_state", "geo_scope", "geo_confidence", "geo_tagged_at",
    "stage_a_model", "resolver_version",
]


def open_geo() -> sqlite3.Connection:
    conn = sqlite3.connect(GEO_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS geo_tags (
            article_id       TEXT PRIMARY KEY,
            stage_a_json     TEXT,
            geo_place_raw    TEXT,
            geo_cbsa_code    TEXT,
            geo_cbsa_title   TEXT,
            geo_state        TEXT,
            geo_scope        TEXT,
            geo_confidence   TEXT,
            geo_tagged_at    TEXT,
            stage_a_model    TEXT,
            resolver_version TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_geo_code ON geo_tags(geo_cbsa_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_geo_conf ON geo_tags(geo_confidence)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_geo_scope ON geo_tags(geo_scope)")
    return conn


def get_geo(conn: sqlite3.Connection, article_ids: list) -> dict:
    """article_id 목록으로 일괄 조회. 없는 id는 결과에서 빠진다.
    반환: {article_id: {필드: 값, ...}}"""
    if not article_ids:
        return {}

    result = {}
    CHUNK = 900  # SQLite 변수 바인딩 상한(기본 999) 대비 청크 분할
    for i in range(0, len(article_ids), CHUNK):
        chunk = article_ids[i:i + CHUNK]
        placeholders = ",".join("?" * len(chunk))
        cols = ["article_id"] + GEO_FIELDS
        rows = conn.execute(
            f"SELECT {','.join(cols)} FROM geo_tags WHERE article_id IN ({placeholders})",
            chunk,
        ).fetchall()
        for row in rows:
            aid = row[0]
            result[aid] = dict(zip(GEO_FIELDS, row[1:]))
    return result


def upsert_geo(conn: sqlite3.Connection, article_id: str, vals: dict,
               resolver_version: str = "v1") -> None:
    """vals는 GEO_FIELDS 중 stage_a_model 이전까지(geo_tagged_at 포함)를 채운
    dict를 기대한다. resolver_version은 이 함수 인자로 별도 전달한다 —
    --mode resolve-only로 Stage B만 재실행했을 때 몇 번째 버전으로
    재매핑됐는지 추적하기 위함이다."""
    tagged_at = vals.get("geo_tagged_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = {f: vals.get(f, "") for f in GEO_FIELDS}
    row["geo_tagged_at"] = tagged_at
    row["resolver_version"] = resolver_version
    values = [article_id] + [row[f] for f in GEO_FIELDS]
    conn.execute(
        f"""INSERT OR REPLACE INTO geo_tags
            (article_id, {",".join(GEO_FIELDS)})
            VALUES ({",".join("?" * len(values))})""",
        values,
    )


def count_geo(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM geo_tags").fetchone()[0]


def iter_stage_a(conn: sqlite3.Connection):
    """(article_id, stage_a_json, stage_a_model) 전량 순회.
    --mode resolve-only(재매핑, API 재호출 없음)에서 사용한다."""
    cur = conn.execute(
        "SELECT article_id, stage_a_json, stage_a_model FROM geo_tags "
        "WHERE stage_a_json IS NOT NULL AND stage_a_json != ''"
    )
    for row in cur:
        yield row[0], row[1], row[2]


@lru_cache(maxsize=1)
def _university_codes() -> dict:
    if not GEO_ALIASES_YAML.exists():
        return {}
    aliases = yaml.safe_load(GEO_ALIASES_YAML.read_text(encoding="utf-8")) or {}
    return aliases.get("universities") or {}


def derive_source_hint(source: str):
    """collector.py의 source 라벨에서 (cbsa_code, state) 힌트를 도출한다.

    "Student Housing — <대학명> (<주>)" 형식만 힌트를 준다. geo_aliases.yaml의
    universities 섹션에 그 대학명이 있으면 (code, state)를, 없으면(대학은
    맞지만 alias 미매핑) None을 반환한다 — 지어내지 않는다(I8).
    "Player — <회사명>"과 일반 RSS 소스는 지명 힌트가 없는 게 정상이므로
    항상 None이다.

    본문을 추론하는 것이 아니라 collector.py가 이미 확정해 둔 수집 메타데이터를
    그대로 읽는 것뿐이므로 I8(모호하면 추정 금지) 위반이 아니다 — 단 이 힌트
    자체가 100% 확실하지는 않다(해당 대학 피드가 다른 지역 기사를 반환할 수
    있음)는 이유로 geo_resolver.resolve()는 이를 "exact"가 아니라 별도 등급
    "source_inferred"로만 채택한다.
    """
    if not source:
        return None
    m = _SOURCE_SH_RE.match(source)
    if not m:
        return None
    name, state = m.group(1), m.group(2)
    code = _university_codes().get(name)
    if not code:
        return None
    return (str(code), state)
