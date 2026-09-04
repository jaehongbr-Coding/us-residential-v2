# 일회성 정리 스크립트 — article_id 완전 중복(TODO #9, 2026-09-03 이중 실행 사고분) 제거.
#
# ⚠️ append-only 원칙의 명시적 예외다. CLAUDE.md 설계 원칙:
#   "단, 동일 기사의 물리적 중복 제거는 판단이 아니므로 허용한다"
# 에 따라 archive/ 파티션을 통째로 다시 쓴다. 이는 렌즈 판단이 아니라
# 물리적으로 동일한 행(같은 article_id, collected_at만 다름)을 하나로
# 합치는 작업이므로 예외가 정당화된다.
#
# 정리 대상: collected_at 외 다른 수집 필드(published_at/source/title/url/
# summary/access_limited)가 전부 같은 중복 쌍만. 다른 필드가 조금이라도
# 다르면 서로 다른 상황일 수 있으므로 손대지 않는다.
# 규칙: 같은 article_id 중 collected_at이 가장 이른 행을 남기고 나머지 제거.
import sys
import csv
import os
from collections import defaultdict

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from collector import ARTICLES_CSV, CSV_COLUMNS
from archive_manager import list_partitions, ARCHIVE_DIR

COLLECT_FIELDS = ["published_at", "source", "title", "url", "summary", "access_limited"]
LOG_PATH = "removed_duplicates.log"


def find_dupes(rows):
    by_id = defaultdict(list)
    for r in rows:
        aid = r.get("article_id")
        if aid:
            by_id[aid].append(r)
    return {k: v for k, v in by_id.items() if len(v) > 1}


def compute_keep_map(all_rows):
    """{article_id: kept_collected_at} 반환. collected_at 외 필드가 다른
    쌍은 제외한다."""
    dupes = find_dupes(all_rows)
    keep_map = {}
    unsafe = set()

    for aid, group in dupes.items():
        base = {f: group[0].get(f, "") for f in COLLECT_FIELDS}
        is_unsafe = any(
            other.get(f, "") != base[f]
            for other in group[1:]
            for f in COLLECT_FIELDS
        )
        if is_unsafe:
            unsafe.add(aid)
            continue
        earliest = min(group, key=lambda r: r.get("collected_at", ""))
        keep_map[aid] = earliest.get("collected_at", "")

    return keep_map, unsafe


def rewrite_file(path, keep_map, log_lines, label):
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    before = len(rows)
    final_rows = []
    for r in rows:
        aid = r.get("article_id")
        if aid in keep_map:
            if r.get("collected_at", "") == keep_map[aid]:
                final_rows.append(r)
            else:
                log_lines.append(
                    f"{label}\t{aid}\tremoved\tcollected_at={r.get('collected_at','')}"
                )
        else:
            final_rows.append(r)

    after = len(final_rows)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(final_rows)

    return before, after


def main():
    partitions = list_partitions()
    all_rows = []
    for month in partitions:
        path = os.path.join(ARCHIVE_DIR, f"{month}.csv")
        with open(path, encoding="utf-8", newline="") as f:
            all_rows.extend(csv.DictReader(f))

    keep_map, unsafe = compute_keep_map(all_rows)
    print(f"정리 대상(안전) 중복 article_id: {len(keep_map)}건")
    print(f"제외(다른 수집 필드 차이) article_id: {len(unsafe)}건\n")

    log_lines = []

    print("--- archive/ 파티션별 정리 ---")
    total_before = total_after = 0
    for month in partitions:
        path = os.path.join(ARCHIVE_DIR, f"{month}.csv")
        before, after = rewrite_file(path, keep_map, log_lines, f"archive/{month}.csv")
        total_before += before
        total_after += after
        if before != after:
            print(f"  {month}.csv: {before}행 → {after}행 ({before - after}건 제거)")
    print(f"\n  archive/ 합계: {total_before}행 → {total_after}행 "
          f"({total_before - total_after}건 제거)\n")

    print("--- articles.csv 정리 ---")
    before, after = rewrite_file(ARTICLES_CSV, keep_map, log_lines, ARTICLES_CSV)
    print(f"  {before}행 → {after}행 ({before - after}건 제거)\n")

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("file\tarticle_id\taction\tdetail\n")
        f.write("\n".join(log_lines) + ("\n" if log_lines else ""))
    print(f"제거 로그: {LOG_PATH} ({len(log_lines)}줄)")


if __name__ == "__main__":
    main()
