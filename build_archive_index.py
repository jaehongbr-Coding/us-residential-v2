"""
US Residential Intelligence v2 — build_archive_index.py
원장(archive/) + labels.db + geo_tags.db를 조인해 브라우저용 정적 조회
인덱스(archive_index.json)를 생성한다.

index.html은 SQLite를 읽을 수 없다 — articles.csv(작업본, 90일 롤링)만
읽는다. 딜이 들어왔을 때 "그 지역·섹터의 과거 사례를 아카이브에서 조회"하려면
원장 전체(7,099건)를 대상으로 하는 별도 조회 인덱스가 필요하다. 이 스크립트는
그 인덱스만 만든다 — 읽기 전용 조인이며 원장/labels.db/geo_tags.db 중
어느 것도 쓰지 않는다.

Plan.md §7 baseline.py(geo_index.json, 기저선 통계)와 같은 "3계층 중 화면
직전 산출물" 패턴이지만, 이건 기저선 집계가 아니라 검색 인덱스다 —
baseline.py와는 목적이 다르므로 별도로 둔다.

사용법: python build_archive_index.py
출력: archive_index.json (repo 루트, index.html이 fetch로 읽을 예정 — 다음 단계)
"""
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

import archive_manager
import label_store
import geo_store

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_PATH = "archive_index.json"
TOP_CBSA_LIMIT = 100


def build():
    rows = archive_manager.read_archive()
    article_ids = [r["article_id"] for r in rows if r.get("article_id")]

    labels_conn = label_store.open_labels()
    labels_map = label_store.get_labels(labels_conn, article_ids)
    labels_conn.close()

    geo_conn = geo_store.open_geo()
    geo_map = geo_store.get_geo(geo_conn, article_ids)
    geo_conn.close()

    records = []
    labels_missing = 0
    geo_missing = 0
    cbsa_titles: dict[str, str] = {}

    sector_counter = Counter()
    state_counter = Counter()
    cbsa_counter = Counter()
    cbsa_title_by_code: dict[str, str] = {}
    category_counter = Counter()
    event_tag_counter = Counter()
    year_counter = Counter()

    published_dates = []

    for r in rows:
        aid = r.get("article_id")
        if not aid:
            continue

        label = labels_map.get(aid)
        if label is None:
            labels_missing += 1
            label = {f: "" for f in label_store.LABEL_FIELDS}

        geo = geo_map.get(aid)
        if geo is None:
            geo_missing += 1
            geo = {}

        pub = (r.get("published_at") or "")[:10]
        if pub:
            published_dates.append(pub)
            year = pub[:4]
            if year:
                year_counter[year] += 1

        sector = label.get("sector", "")
        category = label.get("category", "")
        event_tags = label.get("event_tags", "")
        korean_summary = label.get("korean_summary", "") or (r.get("summary", "") or "")[:200]

        cbsa_code = geo.get("geo_cbsa_code", "") or ""
        cbsa_title = geo.get("geo_cbsa_title", "") or ""
        geo_state = geo.get("geo_state", "") or ""

        # --- 필터용 사전 집계 (판단 없이 그대로 노출) ---
        if sector:
            sector_counter[sector] += 1
        if category:
            category_counter[category] += 1
        for tag in [t.strip() for t in event_tags.split(",") if t.strip()]:
            event_tag_counter[tag] += 1
        for st in [s.strip() for s in geo_state.split("|") if s.strip()]:
            state_counter[st] += 1
        codes = [c.strip() for c in cbsa_code.split("|") if c.strip()]
        titles = [t.strip() for t in cbsa_title.split("|") if t.strip()]
        for i, code in enumerate(codes):
            cbsa_counter[code] += 1
            if code not in cbsa_title_by_code and i < len(titles):
                cbsa_title_by_code[code] = titles[i]
            if code not in cbsa_titles and i < len(titles):
                cbsa_titles[code] = titles[i]

        records.append({
            "id": aid,
            "d": pub,
            "s": r.get("source", ""),
            "t": r.get("title", ""),
            "u": r.get("url", ""),
            "sec": sector,
            "cat": category,
            "ev": event_tags,
            "rel": label.get("woomi_relevance", ""),
            "ks": korean_summary,
            "cbsa": cbsa_code,
            "st": geo_state,
            "sc": geo.get("geo_scope", "") or "",
            "gc": geo.get("geo_confidence", "") or "",
        })

    window_start = min(published_dates) if published_dates else ""
    window_end = max(published_dates) if published_dates else ""

    filters = {
        "sectors": [{"value": k, "count": v} for k, v in sector_counter.most_common()],
        "states": [{"value": k, "count": v} for k, v in state_counter.most_common()],
        "cbsas": [
            {"code": k, "title": cbsa_title_by_code.get(k, ""), "count": v}
            for k, v in cbsa_counter.most_common(TOP_CBSA_LIMIT)
        ],
        "categories": [{"value": k, "count": v} for k, v in category_counter.most_common()],
        "event_tags": [{"value": k, "count": v} for k, v in event_tag_counter.most_common()],
        "years": [{"value": k, "count": v} for k, v in sorted(year_counter.items())],
    }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(records),
        "window_start": window_start,
        "window_end": window_end,
        "cbsa_titles": cbsa_titles,
        "filters": filters,
        "records": records,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    print(f"레코드 {len(records)}건 (원장 {len(rows)}행)")
    print(f"labels 조인 실패: {labels_missing}건 / geo 조인 실패: {geo_missing}건")
    print(f"cbsa_titles 룩업: {len(cbsa_titles)}개")
    print(f"관측창: {window_start} ~ {window_end}")
    print(f"출력: {OUT_PATH}")


if __name__ == "__main__":
    build()
