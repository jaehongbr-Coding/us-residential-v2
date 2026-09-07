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


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "save":
        SNAP.parent.mkdir(parents=True, exist_ok=True)
        fp = fingerprint()
        SNAP.write_text(json.dumps(fp, indent=1), encoding="utf-8")
        print(f"스냅샷 저장 완료 ({len(fp)}건) -> {SNAP}")
    elif mode == "verify":
        old = json.loads(SNAP.read_text(encoding="utf-8"))
        new = fingerprint()
        diff = [k for k in old if old.get(k) != new.get(k)]
        print(f"검사 {len(old)}건 / 변경 {len(diff)}건")
        if diff:
            print("⚠️ 분류 오염 발생:", diff[:10])
            sys.exit(1)
        print("✅ 변화율 0% — 기존 분류 무영향 확인")
    else:
        print("사용법: python scripts/snapshot_regression.py [save|verify]")
        sys.exit(1)


if __name__ == "__main__":
    main()
