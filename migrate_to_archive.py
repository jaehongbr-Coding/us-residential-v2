"""
US Residential Intelligence v2 — migrate_to_archive.py
일회성 마이그레이션: 현재 articles.csv 전체를 archive/YYYY-MM.csv 월별 파티션으로
옮기고, articles.csv를 rebuild_working_set()으로 재생성한다.

사용법:
  python -u migrate_to_archive.py
"""

import csv
import os
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from collector import ARTICLES_CSV, CSV_COLUMNS
from archive_manager import (
    append_to_archive,
    list_partitions,
    read_archive,
    rebuild_working_set,
)


def main():
    if not os.path.exists(ARTICLES_CSV):
        print(f"[ERROR] {ARTICLES_CSV} 가 없습니다.")
        return

    # ------------------------------------------------------------------
    # 1. articles.csv 전량 읽기
    # ------------------------------------------------------------------
    with open(ARTICLES_CSV, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    csv_row_count = len(rows)
    print(f"articles.csv 행 수: {csv_row_count}건\n")

    original_size = os.path.getsize(ARTICLES_CSV)

    # ------------------------------------------------------------------
    # 2. append_to_archive()로 월별 파티션 생성
    # ------------------------------------------------------------------
    print("[1/4] 원장(archive/) 파티션 생성 중...")
    write_result = append_to_archive(rows)
    skipped_count = write_result.pop("_skipped", 0)

    for month in sorted(write_result):
        print(f"  {month}.csv: {write_result[month]}건")
    if skipped_count:
        print(f"  손상 행 skip: {skipped_count}건 (published_at 형식 불량)")

    archived_count = sum(write_result.values())
    print(f"\n  원장 기록: {archived_count}건 / skip: {skipped_count}건\n")

    # ------------------------------------------------------------------
    # 3. 검증 — 원장 전체 행 수 == articles.csv 행 수 - skip된 손상 행 수
    # ------------------------------------------------------------------
    print("[2/4] 검증 중...")
    partitions = list_partitions()
    archive_rows = read_archive(partitions)
    archive_total = len(archive_rows)

    expected = csv_row_count - skipped_count
    print(f"  원장 전체 행 수: {archive_total}건")
    print(f"  기대값 (articles.csv {csv_row_count} - skip {skipped_count}): {expected}건")

    if archive_total != expected:
        print("\n[FAIL] 검증 실패 — 원장 전체 행 수가 기대값과 다릅니다.")
        print("       articles.csv는 손대지 않았습니다. 파티션 파일도 그대로 두었으니")
        print("       원인을 조사한 뒤 다시 실행하거나 수동으로 정리하세요.")
        return

    print("  [PASS] 검증 통과 — 원장에 전량 반영 확인.\n")

    # ------------------------------------------------------------------
    # 4. rebuild_working_set(90)으로 articles.csv 재생성
    # ------------------------------------------------------------------
    print("[3/4] 작업본(articles.csv) 재생성 중 (retention_days=90)...")
    rebuild_result = rebuild_working_set(retention_days=90)
    print(f"  total={rebuild_result['total']} recent={rebuild_result['recent']} "
          f"player={rebuild_result['player']} partitions_read={rebuild_result['partitions_read']}\n")

    # ------------------------------------------------------------------
    # 5. 재생성 전후 비교 보고
    # ------------------------------------------------------------------
    print("[4/4] 최종 보고")
    print(f"  원장 총 행 수: {archive_total}건 / 파티션 수: {len(partitions)}개")
    print("  파티션별 행 수:")
    for month in partitions:
        month_rows = [r for r in archive_rows if r.get("published_at", "").startswith(month)]
        print(f"    {month}: {len(month_rows)}건")

    new_size = os.path.getsize(ARTICLES_CSV)
    with open(ARTICLES_CSV, encoding="utf-8", newline="") as f:
        new_rows = list(csv.DictReader(f))
    new_count = len(new_rows)

    print(f"\n  새 articles.csv 행 수: {new_count}건")
    print(f"    최근 90일분: {rebuild_result['recent']}건")
    print(f"    Player분: {rebuild_result['player']}건")

    new_ids = set(r["article_id"] for r in new_rows)
    old_ids = set(r["article_id"] for r in rows if r.get("article_id"))
    archive_ids = set(r["article_id"] for r in archive_rows)

    dropped_ids = old_ids - new_ids
    dropped_not_in_archive = dropped_ids - archive_ids
    print(f"\n  작업본에서 빠진 기사 수: {len(dropped_ids)}건")
    if dropped_not_in_archive:
        print(f"  [WARN] 원장에도 없는 기사: {len(dropped_not_in_archive)}건 — 손실 가능성!")
        for aid in list(dropped_not_in_archive)[:10]:
            print(f"    article_id={aid!r}")
    else:
        print("  빠진 기사 전부 원장에 존재함 확인.")

    print(f"\n  articles.csv 파일 크기: {original_size:,} bytes → {new_size:,} bytes "
          f"({new_size - original_size:+,} bytes)")


if __name__ == "__main__":
    main()
