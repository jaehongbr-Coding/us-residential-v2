"""market_store 테스트. 임시 DB만 쓴다 (market_flags.db 비의존)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from market_store import count_flags, get_flags, open_market, tagged_keys, upsert_flag  # noqa: E402


def _row(aid="a1", cbsa="12060", rv="v1", **kw):
    r = dict(article_id=aid, cbsa_code=cbsa, rule_version=rv, as_of="2026-06", coverage="ok",
             units_12m=12000, units_avg3y=13000.0, ratio_12m_vs_3y=0.923, flags="",
             tagged_at="2026-10-15T00:00:00+00:00")
    r.update(kw)
    return r


def test_upsert_then_get(tmp_path):
    c = open_market(str(tmp_path / "m.db"))
    upsert_flag(c, _row(flags="supply_drought"))
    upsert_flag(c, _row(cbsa="19100"))
    got = get_flags(c, ["a1", "zz"])
    assert set(got) == {"a1"}
    assert {r["cbsa_code"]: r["flags"] for r in got["a1"]} == {"12060": "supply_drought", "19100": ""}


def test_reupsert_same_pk_keeps_count(tmp_path):
    c = open_market(str(tmp_path / "m.db"))
    upsert_flag(c, _row(flags=""))
    upsert_flag(c, _row(flags="supply_surge"))
    assert count_flags(c) == 1
    assert get_flags(c, ["a1"])["a1"][0]["flags"] == "supply_surge"


def test_tagged_keys_per_rule_version(tmp_path):
    c = open_market(str(tmp_path / "m.db"))
    upsert_flag(c, _row(rv="v1"))
    upsert_flag(c, _row(aid="a2", rv="v2"))
    assert tagged_keys(c, "v1") == {("a1", "12060")}
    assert tagged_keys(c, "v2") == {("a2", "12060")}
    assert len(get_flags(c, ["a1", "a2"], rule_version="v1")) == 1


def test_not_applicable_row_saved(tmp_path):
    c = open_market(str(tmp_path / "m.db"))
    upsert_flag(c, dict(article_id="a3", cbsa_code="31080", rule_version="v1", as_of="2026-06",
                        coverage="not_applicable", flags="", tagged_at="t"))
    r = get_flags(c, ["a3"])["a3"][0]
    assert r["coverage"] == "not_applicable" and r["units_12m"] is None and r["flags"] == ""
