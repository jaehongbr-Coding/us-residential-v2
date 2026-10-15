"""CBSA × 시점 → 시장 상태. 순수 함수. LLM·네트워크 없음 (M4)."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import pandas as pd

RULE_VERSION     = "v1"
WINDOW_M         = 12      # 최근 창
BASE_YEARS       = 3       # 기저선 (Q1)
VOLUME_FLOOR     = 300     # 3년 평균 연간 5+유닛 하한 (초안). Phase 2.2 실측 분포로 보정
LAG_BUCKET       = "20+"   # research_market §4.2.5


@dataclass
class MarketContext:
    cbsa_code: str
    as_of: str                      # YYYY-MM
    coverage: str                   # ok | low_volume | no_data
    units_12m: int | None
    units_avg3y: float | None
    ratio_12m_vs_3y: float | None   # low_volume 에서도 산출 (참고용), 판정은 unknown
    region: str | None
    lag_months: float | None
    def to_dict(self): return asdict(self)


def _window(bps: pd.DataFrame, cbsa: str, end: str, n: int) -> pd.DataFrame:
    d = bps[(bps.cbsa_code == cbsa) & (bps.period <= end)].sort_values("period")
    return d.tail(n)


def compute(cbsa: str, as_of: str, bps: pd.DataFrame, soc: pd.DataFrame | None,
            region_of: dict[str, str]) -> MarketContext:
    need = WINDOW_M * (BASE_YEARS + 1)
    w = _window(bps, cbsa, as_of, need)
    region = region_of.get(cbsa)
    lag = None
    if soc is not None and region:
        s = soc[(soc.region == region) & (soc.unit_bucket == LAG_BUCKET)].dropna(subset=["months_auth_to_comp"]).sort_values("year")
        if len(s): lag = float(s.iloc[-1].months_auth_to_comp)

    if len(w) < need or w.period.iloc[-1] != as_of:
        return MarketContext(cbsa, as_of, "no_data", None, None, None, region, lag)

    recent = w.tail(WINDOW_M)
    base   = w.head(WINDOW_M * BASE_YEARS)
    units_12m   = int(recent.u5_units.sum())
    units_avg3y = float(base.u5_units.sum() / BASE_YEARS)
    ratio = (units_12m / units_avg3y) if units_avg3y > 0 else None
    cov = "low_volume" if units_avg3y < VOLUME_FLOOR else "ok"
    return MarketContext(cbsa, as_of, cov, units_12m, round(units_avg3y, 1),
                         None if ratio is None else round(ratio, 3), region, lag)


def expected_completion(cbsa: str, bps: pd.DataFrame, lag_months: float | None,
                        horizon_q: int = 4) -> dict[str, int]:
    """허가 월 + lag → 준공 분기. 추정치. 미착공·취소 미반영 (화면 고지 필수)."""
    if lag_months is None:
        return {}
    d = bps[bps.cbsa_code == cbsa].copy()
    if d.empty: return {}
    d["period_dt"] = pd.to_datetime(d.period, format="%Y-%m")
    d["comp_dt"]   = d.period_dt + pd.DateOffset(months=int(round(lag_months)))
    d["comp_q"]    = d.comp_dt.dt.to_period("Q")
    last_q = pd.Timestamp.today().to_period("Q")
    fut = d[d.comp_q > last_q]
    agg = fut.groupby("comp_q").u5_units.sum().sort_index().head(horizon_q)
    return {str(q): int(v) for q, v in agg.items()}


def region_map(bps: pd.DataFrame, state_region: pd.DataFrame) -> dict[str, str]:
    """cbsa_name 'Atlanta-Sandy Springs-Roswell, GA' / 'Columbus, GA-AL' → 쉼표 뒤 첫 주 → region."""
    s2r = dict(zip(state_region.state, state_region.region))
    names = bps.drop_duplicates("cbsa_code", keep="last").set_index("cbsa_code").cbsa_name
    out = {}
    for code, name in names.items():
        if "," not in name: continue
        st = name.split(",")[-1].strip().split("-")[0].strip()
        if st in s2r: out[code] = s2r[st]
    return out
