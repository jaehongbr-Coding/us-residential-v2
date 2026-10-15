"""archive × geo_tags.db × market_context → market_flags.db + context_latest.json
daily_collect.yml: Geo tagging 뒤, Build archive index 앞.
--mode incremental (기본): rule_version 기준 미태깅 (article_id, cbsa)만
--mode context-only       : 기사 태깅 없이 JSON만 (monthly_market.yml, Phase 2)
--mode backfill           : incremental과 동일 필터 (명시용)

market_store·archive_manager·geo_store는 기사 태깅 경로에서만 import한다 —
context-only는 data/market/ 파일만 읽는다 (M4). market_store는 Phase 3.0에서 추가된다."""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from market_context import compute, expected_completion, region_map, RULE_VERSION
from market_rules import judge

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BPS   = Path("data/market/bps_cbsa.csv"); SOC = Path("data/market/soc_lag.csv")
STREG = Path("data/market/state_region.csv"); OUT_JSON = Path("data/market/context_latest.json")
APPLICABLE_SCOPES = {"metro", "local"}
APPLICABLE_CONF   = {"exact", "inferred", "source_inferred"}


def as_of_for(published_at: str) -> str:
    dt = pd.to_datetime(published_at, errors="coerce", utc=True)
    return "" if pd.isna(dt) else str(dt.to_period("M") - 2)


def load():
    bps = pd.read_csv(BPS, dtype={"cbsa_code": str, "period": str})
    soc = pd.read_csv(SOC) if SOC.exists() else None
    return bps, soc, pd.read_csv(STREG)


def tag_articles(bps, soc, region_of) -> int:
    from archive_manager import read_archive
    from geo_store import open_geo, get_geo
    from market_store import open_market, tagged_keys, upsert_flag
    rows = read_archive()
    ids  = [r["article_id"] for r in rows]
    pub  = {r["article_id"]: r["published_at"] for r in rows}
    gconn = open_geo(); geo = get_geo(gconn, ids)
    mconn = open_market(); done = tagged_keys(mconn, RULE_VERSION)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds"); n = 0
    for aid in ids:
        g = geo.get(aid)
        if not g or not g.get("geo_cbsa_code"): continue
        for cbsa in g["geo_cbsa_code"].split("|"):
            cbsa = cbsa.strip()
            if not cbsa or (aid, cbsa) in done: continue
            as_of = as_of_for(pub[aid])
            base = dict(article_id=aid, cbsa_code=cbsa, rule_version=RULE_VERSION, as_of=as_of, tagged_at=now)
            if (g.get("geo_scope") not in APPLICABLE_SCOPES or g.get("geo_confidence") not in APPLICABLE_CONF or not as_of):
                upsert_flag(mconn, {**base, "coverage": "not_applicable", "flags": ""}); n += 1; continue
            c = compute(cbsa, as_of, bps, soc, region_of)
            upsert_flag(mconn, {**base, "coverage": c.coverage, "units_12m": c.units_12m,
                                "units_avg3y": c.units_avg3y, "ratio_12m_vs_3y": c.ratio_12m_vs_3y,
                                "flags": "|".join(judge(c))}); n += 1
    mconn.commit(); return n


def dump_context(bps, soc, region_of, with_counts: bool) -> None:
    as_of = str(pd.to_datetime(bps.period).max().to_period("M"))
    names = bps.drop_duplicates("cbsa_code", keep="last").set_index("cbsa_code").cbsa_name.to_dict()
    counts = {}
    if with_counts:
        from market_store import open_market
        mconn = open_market()
        for code, total, ok in mconn.execute(
            "SELECT cbsa_code, COUNT(*), SUM(coverage='ok') FROM market_flags WHERE rule_version=? AND coverage!='not_applicable' GROUP BY cbsa_code", (RULE_VERSION,)):
            counts[code] = {"total": total, "flagged": ok}
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "as_of": as_of, "rule_version": RULE_VERSION, "cbsa": {}}
    for code in sorted(names):
        c = compute(code, as_of, bps, soc, region_of)
        m = bps[bps.cbsa_code == code].sort_values("period").tail(36)[["period","u5_units"]].to_dict("records")
        out["cbsa"][code] = {**c.to_dict(), "name": names[code], "flags": judge(c), "monthly": m,
                             "article_counts": counts.get(code),
                             "expected_completion": {"lag_months": c.lag_months, "bucket": "20+",
                                                     "by_quarter": expected_completion(code, bps, c.lag_months)}}
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--mode", default="incremental",
        choices=["incremental", "backfill", "context-only"]); a = ap.parse_args()
    bps, soc, streg = load(); region_of = region_map(bps, streg)
    if a.mode != "context-only":
        print(f"market_flags +{tag_articles(bps, soc, region_of)}행")
    dump_context(bps, soc, region_of, with_counts=(a.mode != "context-only"))
    print(f"context_latest.json {OUT_JSON.stat().st_size//1024}KB")
