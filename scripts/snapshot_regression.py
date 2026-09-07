"""geo 작업이 기존 분류(labels.db)를 오염시키지 않았음을 입증한다
(Plan.md §8, research.md §3.4a).

  python scripts/snapshot_regression.py save    # geo 작업 전
  python scripts/snapshot_regression.py verify  # geo 작업 후 -> 반드시 0 diff

Plan.md 원안은 articles.csv를 대상으로 했으나, classifier.py 결과(분류
필드)의 source of truth는 이제 labels.db이므로(2026.09 렌즈/원장 분리)
여기서는 labels.db를 대상으로 한다.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import label_store

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SNAP = Path(__file__).resolve().parent.parent / "tests" / "regression_snapshot.json"
COLS = ["category", "event_tags", "signal_type", "sector", "woomi_relevance"]


def fingerprint() -> dict:
    conn = label_store.open_labels()
    rows = conn.execute(
        f"SELECT article_id, {','.join(COLS)} FROM labels ORDER BY article_id LIMIT 300"
    ).fetchall()
    conn.close()
    result = {}
    for row in rows:
        aid = row[0]
        vals = [str(v or "") for v in row[1:]]
        result[aid] = hashlib.sha256("|".join(vals).encode()).hexdigest()[:16]
    return result


def fingerprint_for_ids(ids: list[str]) -> dict:
    """스냅샷에 저장된 article_id 집합만 조회한다.
    ORDER BY article_id LIMIT 300로 재조회하면, 새 article_id가 사전식 정렬
    상위에 삽입될 때 표본 창(window)이 밀려 기존에 포함됐던 id가 빠지고
    무관한 신규 id가 들어와 위양성 diff가 발생한다 — 이를 막기 위해
    스냅샷이 가리키는 정확히 그 id들만 조회한다.
    """
    conn = label_store.open_labels()
    result = {}
    for aid in ids:
        row = conn.execute(
            f"SELECT {','.join(COLS)} FROM labels WHERE article_id = ?", (aid,)
        ).fetchone()
        if row is None:
            continue
        vals = [str(v or "") for v in row]
        result[aid] = hashlib.sha256("|".join(vals).encode()).hexdigest()[:16]
    conn.close()
    return result


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "save":
        SNAP.parent.mkdir(parents=True, exist_ok=True)
        fp = fingerprint()
        SNAP.write_text(json.dumps(fp, indent=1), encoding="utf-8")
        print(f"스냅샷 저장 완료 ({len(fp)}건) -> {SNAP}")
    elif mode == "verify":
        old = json.loads(SNAP.read_text(encoding="utf-8"))
        new = fingerprint_for_ids(list(old.keys()))
        missing = [k for k in old if k not in new]
        diff = [k for k in old if k in new and old.get(k) != new.get(k)]
        print(f"검사 {len(old)}건 / 변경 {len(diff)}건 / 소실(missing) {len(missing)}건")
        if missing:
            print("⚠️ labels.db에서 사라진 article_id:", missing[:10])
        if diff:
            print("⚠️ 분류 오염 발생:", diff[:10])
        if diff or missing:
            sys.exit(1)
        print("✅ 변화율 0% — 기존 분류 무영향 확인")
    else:
        print("사용법: python scripts/snapshot_regression.py [save|verify]")
        sys.exit(1)


if __name__ == "__main__":
    main()
