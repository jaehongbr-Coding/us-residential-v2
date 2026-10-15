"""market_tagger.as_of_for 테스트 (발행월 − 2개월, UTC 기준)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import json  # noqa: E402
import re  # noqa: E402

import pandas as pd  # noqa: E402
from market_store import open_market, upsert_flag  # noqa: E402
from market_tagger import as_of_for, dump_context  # noqa: E402


def test_as_of_iso_utc():
    assert as_of_for("2026-10-14T05:00:00Z") == "2026-08"


def test_as_of_naive_year_wrap():
    assert as_of_for("2026-01-05 00:00:00") == "2025-11"


def test_as_of_empty():
    assert as_of_for("") == ""


# ── dump_context: 모드 간 일치 ──
def _bps():
    periods = pd.period_range(end="2026-08", periods=48, freq="M").astype(str)
    rows = [dict(period=p, cbsa_code=c, cbsa_name=n, u5_units=u)
            for c, n, u in [("11111", "Alpha, GA", 100), ("22222", "Beta-Gamma, OR-WA", 1500)]
            for p in periods]
    return pd.DataFrame(rows)


def _no_gen(path):
    s, n = re.subn(r'"generated_at":\s*"[^"]*"', '"generated_at": ""', path.read_text(encoding="utf-8"))
    assert n == 1   # 정규식이 실제로 지웠는지 확인 (같은 초에 생성돼 우연히 통과하는 것 방지)
    return s


def test_dump_modes_identical_except_generated_at(tmp_path):
    db = tmp_path / "market_flags.db"
    c = open_market(str(db))
    upsert_flag(c, dict(article_id="a1", cbsa_code="22222", rule_version="v1", as_of="2026-06",
                        coverage="ok", flags="", tagged_at="t"))
    c.commit(); c.close()
    reg = {"11111": "South", "22222": "West"}
    # incremental/backfill/context-only 모두 __main__에서 같은 인자로 dump_context를 부른다
    n1 = dump_context(_bps(), None, reg, out_path=tmp_path / "ctx_only.json", market_db=db)
    n2 = dump_context(_bps(), None, reg, out_path=tmp_path / "incremental.json", market_db=db)
    assert n1 == n2 == 1
    assert _no_gen(tmp_path / "ctx_only.json") == _no_gen(tmp_path / "incremental.json")
    d = json.loads((tmp_path / "ctx_only.json").read_text(encoding="utf-8"))
    assert d["cbsa"]["22222"]["article_counts"] == {"total": 1, "flagged": 1}
    assert d["cbsa"]["11111"]["article_counts"] is None


def test_dump_without_market_db_counts_null(tmp_path):
    db = tmp_path / "missing.db"
    n = dump_context(_bps(), None, {}, out_path=tmp_path / "ctx.json", market_db=db)
    assert n is None and not db.exists()          # 읽기 전용: DB를 만들지 않는다
    d = json.loads((tmp_path / "ctx.json").read_text(encoding="utf-8"))
    assert all(v["article_counts"] is None for v in d["cbsa"].values())
