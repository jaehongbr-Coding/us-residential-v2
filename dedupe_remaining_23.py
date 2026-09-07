# 일회성 정리 스크립트 — dedupe_duplicates.py(b0307b3, 142건 중 119건)가
# "수집 필드 중 하나라도 다르면 손대지 않는다"는 이유로 제외했던 나머지
# 23건을 정리한다. 2026.09 geo Phase 2 백필 1차 시도가 Batch API의
# custom_id 중복으로 거부된 사고를 계기로 실태를 조사한 결과, 23건은
# 전부 2026-09-03 21:0x/23:2x 이중 실행(그 142건 사고와 동일 사건)의
# 잔여물이며 아래 세 갈래로 나뉜다. 규칙별 article_id를 명시적으로
# 나열한다 — 문자열 패턴으로 자동 판정하지 않는다(다른 이질적인 미래의
# 중복 쌍이 같은 규칙으로 잘못 처리되는 것을 막기 위함).
#
# (A) 20건 — Google News 발행사명 표기 차이(도메인형 vs 브랜드명형)뿐,
#     완전히 동일한 기사. dedupe_duplicates.py와 동일 규칙: 최초 collected_at 유지.
# (B) 3건 — title/summary 동일, source만 다름(전국판 "Connect CRE" vs
#     지역판 "Connect CRE Texas"/"Connect CRE California"). collected_at
#     순서와 무관하게 지역판(정보량이 많은 쪽)을 유지.
# (C) 1건 — 실제 CSV 파싱 손상. 21:04:18 행의 summary에 다른 기사
#     (468194b95d24)의 CSV 행 전체가 흘러들어와 있고 category에 이스케이프
#     안 된 따옴표가 붙어 있다. 최초 collected_at 규칙을 기계적으로 적용하면
#     손상 행이 영구 보존되므로 예외: 늦은(깨끗한) 쪽을 유지한다.
import csv
import os
import sys
from collections import defaultdict

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from collector import ARTICLES_CSV, CSV_COLUMNS
from archive_manager import list_partitions, ARCHIVE_DIR

LOG_PATH = "removed_duplicates.log"

# (A) 발행사명 표기 차이 20건 — 최초 collected_at 유지
RULE_A_IDS = {
    "26ca3af74fe2", "573cb29a9868", "2a3ab9a0ae36", "7c1e66e3c245",
    "c4465b1e576a", "a3f7440eb6bb", "1b98b8216dac", "f23f9bf82023",
    "7639b49a52a5", "83c4f97fb9f3", "20da515a8c91", "1e0e1b564001",
    "7e358b17ad28", "d2781c2cba59", "402afff7f825", "c70a5edf6d19",
    "48347709935f", "779b11912a65", "90959bb31bf2",
}

# (B) Connect CRE 지역판 교차 게재 3건 — 지역판 source 유지
RULE_B_IDS = {"397d78a88eca", "91cac39586d6", "44f65d096ea9"}

# (C) CSV 파싱 손상 1건 — 늦은(깨끗한) 쪽 유지
RULE_C_IDS = {"4aa03452266e"}

ALL_TARGET_IDS = RULE_A_IDS | RULE_B_IDS | RULE_C_IDS
assert len(ALL_TARGET_IDS) == 23, f"대상 23건이어야 하는데 {len(ALL_TARGET_IDS)}건"


def load_all_rows():
    partitions = list_partitions()
    all_rows = []
    for month in partitions:
        path = os.path.join(ARCHIVE_DIR, f"{month}.csv")
        with open(path, encoding="utf-8", newline="") as f:
            all_rows.extend(csv.DictReader(f))
    return all_rows


def _detect_lineterminator(path: str) -> str:
    """csv.DictWriter의 기본 lineterminator는 "\\r\\n"이라, newline=""로 열어도
    원본 파일의 줄바꿈 방식을 그대로 안 따르면 내용은 동일한데 줄바꿈만 바뀌어
    git diff가 전체 파일을 바뀐 것처럼 표시한다(2026.09 이번 정리에서 실제로
    겪음 — archive/*.csv는 LF, articles.csv는 CRLF로 서로 다르다). 원본 파일의
    첫 줄바꿈을 그대로 읽어 재사용한다."""
    with open(path, "rb") as f:
        chunk = f.read(65536)
    return "\r\n" if b"\r\n" in chunk else "\n"


def compute_keep_map(all_rows):
    """article_id -> kept collected_at 값(archive 정리용), kept_rows:
    article_id -> 선택된 행 전체(dict, articles.csv 갱신용)."""
    by_id = defaultdict(list)
    for r in all_rows:
        aid = r.get("article_id")
        if aid in ALL_TARGET_IDS:
            by_id[aid].append(r)

    keep_map = {}
    kept_rows = {}
    rule_log = {}  # article_id -> (rule, kept_collected_at, note)

    for aid in RULE_A_IDS:
        group = by_id.get(aid, [])
        if len(group) < 2:
            print(f"[WARN] {aid} (규칙 A): 중복이 이미 없음, 건너뜀")
            continue
        earliest = min(group, key=lambda r: r.get("collected_at", ""))
        keep_map[aid] = earliest["collected_at"]
        kept_rows[aid] = earliest
        rule_log[aid] = ("A", earliest["collected_at"], "최초 collected_at 유지")

    for aid in RULE_B_IDS:
        group = by_id.get(aid, [])
        if len(group) < 2:
            print(f"[WARN] {aid} (규칙 B): 중복이 이미 없음, 건너뜀")
            continue
        regional = [r for r in group if r.get("source", "") != "Connect CRE"]
        if len(regional) != 1:
            print(f"[ERROR] {aid} (규칙 B): 지역판 판정 실패 (후보 {len(regional)}개) — 건너뜀")
            continue
        keep_map[aid] = regional[0]["collected_at"]
        kept_rows[aid] = regional[0]
        rule_log[aid] = ("B", regional[0]["collected_at"], f"지역판 source 유지: {regional[0]['source']!r}")

    for aid in RULE_C_IDS:
        group = by_id.get(aid, [])
        if len(group) < 2:
            print(f"[WARN] {aid} (규칙 C): 중복이 이미 없음, 건너뜀")
            continue
        latest = max(group, key=lambda r: r.get("collected_at", ""))
        keep_map[aid] = latest["collected_at"]
        kept_rows[aid] = latest
        rule_log[aid] = ("C", latest["collected_at"], "손상 행 제외, 늦은(깨끗한) collected_at 유지")

    return keep_map, kept_rows, rule_log


def rewrite_archive_file(path, keep_map, rule_log, log_lines, label):
    """archive/ 파티션 — 중복 행이 실제로 존재하므로 keep_map에 안 걸리는
    쪽을 삭제한다."""
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
                rule, kept_at, note = rule_log[aid]
                log_lines.append(
                    f"{label}\t{aid}\tremoved\trule={rule}\tcollected_at={r.get('collected_at','')}"
                    f"\tsource={r.get('source','')}\tkept_collected_at={kept_at}\tnote={note}"
                )
        else:
            final_rows.append(r)

    after = len(final_rows)
    if after != before:
        lineterminator = _detect_lineterminator(path)
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, lineterminator=lineterminator)
            writer.writeheader()
            writer.writerows(final_rows)

    return before, after


COLLECT_FIELDS = ["collected_at", "published_at", "source", "title", "url", "summary", "access_limited"]


def rewrite_working_set(path, kept_rows, rule_log, log_lines, label):
    """articles.csv — 이미 article_id당 1행뿐이라(과거에 이미 통합됨) archive와
    같은 삭제 로직을 쓰면 안 된다. 규칙 B처럼 현재 남아있는 행이 "잘못된" 쪽
    (전국판)일 경우 그대로 지워버리면 그 기사가 작업본에서 통째로 사라진다.
    대신 대상 23건에 한해 수집 8필드만 kept_rows의 값으로 덮어쓴다 — 렌즈
    8필드(classified 등)는 labels.db 조인 결과이므로 절대 건드리지 않는다."""
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    changed = 0
    for r in rows:
        aid = r.get("article_id")
        if aid not in kept_rows:
            continue
        kept = kept_rows[aid]
        before_vals = {f: r.get(f, "") for f in COLLECT_FIELDS}
        after_vals = {f: kept.get(f, "") for f in COLLECT_FIELDS}
        if before_vals != after_vals:
            rule, kept_at, note = rule_log[aid]
            log_lines.append(
                f"{label}\t{aid}\tupdated\trule={rule}\tbefore_source={before_vals['source']!r}"
                f"\tafter_source={after_vals['source']!r}\tnote={note}"
            )
            for f in COLLECT_FIELDS:
                r[f] = kept[f]
            changed += 1

    if changed:
        lineterminator = _detect_lineterminator(path)
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, lineterminator=lineterminator)
            writer.writeheader()
            writer.writerows(rows)

    return len(rows), changed


def main():
    all_rows = load_all_rows()
    keep_map, kept_rows, rule_log = compute_keep_map(all_rows)
    print(f"정리 대상: {len(keep_map)}건 (A={sum(1 for v in rule_log.values() if v[0]=='A')}, "
          f"B={sum(1 for v in rule_log.values() if v[0]=='B')}, "
          f"C={sum(1 for v in rule_log.values() if v[0]=='C')})\n")

    log_lines = []
    partitions = list_partitions()

    print("--- archive/ 파티션별 정리 (실제 중복 행 삭제) ---")
    total_before = total_after = 0
    for month in partitions:
        path = os.path.join(ARCHIVE_DIR, f"{month}.csv")
        before, after = rewrite_archive_file(path, keep_map, rule_log, log_lines, f"archive/{month}.csv")
        total_before += before
        total_after += after
        if before != after:
            print(f"  {month}.csv: {before}행 -> {after}행 ({before - after}건 제거)")
    print(f"\n  archive/ 합계: {total_before}행 -> {total_after}행 "
          f"({total_before - total_after}건 제거)\n")

    print("--- articles.csv 정리 (수집 8필드만 필요 시 갱신, 렌즈 필드 유지) ---")
    total_rows, changed = rewrite_working_set(ARTICLES_CSV, kept_rows, rule_log, log_lines, ARTICLES_CSV)
    print(f"  총 {total_rows}행 중 {changed}건 갱신 (행 수 변화 없음 — article_id당 이미 1행)\n")

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n# --- dedupe_remaining_23.py 실행분 (23건 잔여 중복 정리) ---\n")
        f.write("\n".join(log_lines) + ("\n" if log_lines else ""))
    print(f"제거 로그 추가: {LOG_PATH} ({len(log_lines)}줄)")


if __name__ == "__main__":
    main()
