"""
US Residential Intelligence v2 — migrate_to_labels.py
일회성 마이그레이션: 렌즈 산출물(분류 8필드)을 labels.db로 이관한다.

절차:
  1. 현재 articles.csv(작업본)의 렌즈 필드를 labels.db에 적재 — 작업본이
     가장 최신 분류 상태이므로 우선 소스로 삼는다.
  2. archive/ 전체를 읽어, labels.db에 아직 없는 article_id만 추가 적재
     (작업본에서 이미 빠진 기사들이 여기서 들어온다). 이미 있는 id는
     덮어쓰지 않는다.
  3. 검증 후 통과 시에만 완료 보고.

사용법:
  python -u migrate_to_labels.py
"""

import csv
import random
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from collector import ARTICLES_CSV
from archive_manager import list_partitions, read_archive
from label_store import open_labels, upsert_labels, count_labels, LABEL_FIELDS


def main():
    conn = open_labels()

    # ------------------------------------------------------------------
    # 1. 작업본(articles.csv) 렌즈 필드 적재 — 우선 소스
    # ------------------------------------------------------------------
    print("[1/3] 작업본(articles.csv)에서 렌즈 필드 적재 중...")
    with open(ARTICLES_CSV, encoding="utf-8", newline="") as f:
        working_rows = list(csv.DictReader(f))

    for row in working_rows:
        aid = row.get("article_id")
        if not aid:
            continue
        label_dict = {f: row.get(f, "") for f in LABEL_FIELDS}
        upsert_labels(conn, aid, label_dict, lens_version="v1")
    conn.commit()

    from_working = count_labels(conn)
    print(f"  작업본 {len(working_rows)}건 처리 → labels.db {from_working}건\n")

    # ------------------------------------------------------------------
    # 2. archive/ 전체 — labels.db에 없는 article_id만 추가
    # ------------------------------------------------------------------
    print("[2/3] 원장(archive/)에서 누락분 적재 중...")
    partitions = list_partitions()
    archive_rows = read_archive(partitions)

    existing_ids = set(
        row[0] for row in conn.execute("SELECT article_id FROM labels").fetchall()
    )

    added_from_archive = 0
    seen_in_pass = set()  # 원장 내 중복(article_id 142건류) 재처리 방지
    for row in archive_rows:
        aid = row.get("article_id")
        if not aid or aid in existing_ids or aid in seen_in_pass:
            continue
        label_dict = {f: row.get(f, "") for f in LABEL_FIELDS}
        upsert_labels(conn, aid, label_dict, lens_version="v1")
        seen_in_pass.add(aid)
        added_from_archive += 1
    conn.commit()

    print(f"  원장 {len(archive_rows)}행 중 신규 {added_from_archive}건 추가\n")

    # ------------------------------------------------------------------
    # 3. 검증
    # ------------------------------------------------------------------
    print("[3/3] 검증 중...")
    total_labels = count_labels(conn)
    unique_archive_ids = set(r.get("article_id") for r in archive_rows if r.get("article_id"))
    print(f"  labels.db 행 수: {total_labels}")
    print(f"  원장 고유 article_id 수: {len(unique_archive_ids)}")

    ok = True
    if total_labels != len(unique_archive_ids):
        print(f"  [FAIL] labels.db 행 수가 원장 고유 article_id 수와 다릅니다 "
              f"({total_labels} != {len(unique_archive_ids)})")
        ok = False
    else:
        print("  [PASS] labels.db 행 수 == 원장 고유 article_id 수")

    # 무작위 표본 100건 비교 (작업본에 있는 건 중에서)
    sample_ids = [r["article_id"] for r in working_rows if r.get("article_id")]
    sample = random.sample(sample_ids, min(100, len(sample_ids)))
    mismatches = []
    working_by_id = {r["article_id"]: r for r in working_rows}
    for aid in sample:
        row = conn.execute(
            f"SELECT {','.join(LABEL_FIELDS)} FROM labels WHERE article_id = ?",
            (aid,),
        ).fetchone()
        if row is None:
            mismatches.append((aid, "labels.db에 없음"))
            continue
        db_vals = dict(zip(LABEL_FIELDS, row))
        csv_vals = {f: working_by_id[aid].get(f, "") for f in LABEL_FIELDS}
        if db_vals != csv_vals:
            diff_fields = [f for f in LABEL_FIELDS if db_vals.get(f) != csv_vals.get(f)]
            mismatches.append((aid, f"필드 불일치: {diff_fields}"))

    print(f"\n  표본 {len(sample)}건 비교 — 불일치: {len(mismatches)}건")
    if mismatches:
        print("  [FAIL] 불일치 상세:")
        for aid, reason in mismatches:
            print(f"    article_id={aid!r} {reason}")
        ok = False
    else:
        print("  [PASS] 표본 전부 일치")

    classified_count = conn.execute(
        "SELECT COUNT(*) FROM labels WHERE classified = 'True'"
    ).fetchone()[0]
    print(f"\n  classified=True 건수: {classified_count} (기준: 작업본 5,452건 이상)")
    if classified_count < 5452:
        print(f"  [FAIL] classified=True 건수가 기준 미달입니다.")
        ok = False
    else:
        print("  [PASS] classified=True 건수 기준 충족")

    conn.close()

    print()
    if ok:
        print("=== 전체 검증 통과 ===")
    else:
        print("=== [FAIL] 검증 실패 — labels.db는 보존하되 다음 단계로 진행하지 않습니다 ===")


if __name__ == "__main__":
    main()
