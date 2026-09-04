"""
US Residential Intelligence v2 — archive_manager.py
원장(archive/YYYY-MM.csv 월별 파티션) 읽기·쓰기를 담당한다.

원장은 append-only다. 한 번 쓴 과거 월 파티션은 다시 수정하지 않는다.
articles.csv(작업본)는 원장에서 파생되는 뷰이며, rebuild_working_set()으로
언제든 재생성할 수 있다. 원장이 source of truth다.

CSV_COLUMNS는 collector.py에서 import한다 — 여기서 재정의하지 않는다
(두 곳에 두면 언젠가 어긋난다).
"""

import csv
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta

from collector import CSV_COLUMNS, ARTICLES_CSV

ARCHIVE_DIR = "archive"
PLAYER_SOURCE_PREFIX = "Player — "

_DATE_RE = re.compile(r"^(\d{4}-\d{2})-\d{2} \d{2}:\d{2}:\d{2}$")


def archive_path(published_at: str):
    """published_at[:7] 기반 "archive/YYYY-MM.csv" 경로 반환.
    날짜 파싱 실패 시 None (호출부에서 skip 처리)."""
    m = _DATE_RE.match(published_at or "")
    if not m:
        return None
    return os.path.join(ARCHIVE_DIR, f"{m.group(1)}.csv")


def append_to_archive(articles: list[dict]) -> dict:
    """기사를 월별로 그룹핑해 각 파티션에 append한다.
    파티션이 없으면 헤더와 함께 생성한다.
    반환: {"2026-09": 12, "2026-08": 3, "_skipped": 1} 형태.
    "_skipped"는 published_at 형식이 깨져 archive_path()가 None을 반환한 건수."""
    grouped = defaultdict(list)
    skipped = 0

    for a in articles:
        path = archive_path(a.get("published_at", ""))
        if path is None:
            skipped += 1
            continue
        grouped[path].append(a)

    if grouped:
        os.makedirs(ARCHIVE_DIR, exist_ok=True)

    result = {}
    for path, group in grouped.items():
        file_exists = os.path.exists(path)
        with open(path, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            if not file_exists:
                writer.writeheader()
            writer.writerows(group)
        month = os.path.splitext(os.path.basename(path))[0]
        result[month] = len(group)

    if skipped:
        result["_skipped"] = skipped

    return result


def list_partitions() -> list[str]:
    """존재하는 파티션 월 목록("YYYY-MM")을 정렬해 반환."""
    if not os.path.isdir(ARCHIVE_DIR):
        return []
    months = []
    for fname in os.listdir(ARCHIVE_DIR):
        m = re.match(r"^(\d{4}-\d{2})\.csv$", fname)
        if m:
            months.append(m.group(1))
    return sorted(months)


def read_archive(months: list = None) -> list[dict]:
    """지정 월 파티션을 읽어 반환. months=None이면 전체.
    존재하지 않는 파티션은 조용히 skip."""
    if months is None:
        months = list_partitions()

    rows = []
    for month in months:
        path = os.path.join(ARCHIVE_DIR, f"{month}.csv")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", newline="") as f:
            rows.extend(csv.DictReader(f))
    return rows


def rebuild_working_set(retention_days: int = 90) -> dict:
    """원장 전체에서 작업본(articles.csv)을 재생성한다.
    포함 기준: published_at이 최근 retention_days 이내 또는
    source가 "Player — "로 시작 (Player는 기간 무관 전량 유지).
    반환: {"total": N, "recent": N, "player": N, "partitions_read": N}
    (recent·player는 겹칠 수 있어 합이 total과 다를 수 있다 — 진단용 원시 카운트)."""
    partitions = list_partitions()
    all_rows = read_archive(partitions)
    cutoff = datetime.now() - timedelta(days=retention_days)

    recent_rows = []
    player_rows = []
    final_rows = []

    for r in all_rows:
        pub = r.get("published_at", "")
        is_recent = False
        if _DATE_RE.match(pub):
            try:
                is_recent = datetime.strptime(pub, "%Y-%m-%d %H:%M:%S") >= cutoff
            except ValueError:
                is_recent = False
        is_player = (r.get("source") or "").startswith(PLAYER_SOURCE_PREFIX)

        if is_recent:
            recent_rows.append(r)
        if is_player:
            player_rows.append(r)
        if is_recent or is_player:
            final_rows.append(r)

    with open(ARTICLES_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(final_rows)

    return {
        "total": len(final_rows),
        "recent": len(recent_rows),
        "player": len(player_rows),
        "partitions_read": len(partitions),
    }
