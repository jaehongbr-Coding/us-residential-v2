"""market_context 항등식 테스트. 합성 데이터만 쓴다 (원장 비의존)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from market_context import compute, region_map  # noqa: E402

CBSA = "99999"


def _bps(values, end="2026-08", cbsa=CBSA):
    periods = pd.period_range(end=end, periods=len(values), freq="M").astype(str)
    return pd.DataFrame({"period": periods, "cbsa_code": cbsa, "u5_units": values})


def test_ratio_identity():
    ctx = compute(CBSA, "2026-08", _bps([100] * 36 + [60] * 12), None, {})
    assert ctx.coverage == "ok"
    assert ctx.units_avg3y == 1200 and ctx.units_12m == 720
    assert abs(ctx.ratio_12m_vs_3y - 0.6) < 1e-9


def test_low_volume():
    ctx = compute(CBSA, "2026-08", _bps([10] * 48), None, {})
    assert ctx.units_avg3y == 120
    assert ctx.coverage == "low_volume"
    assert ctx.ratio_12m_vs_3y is not None


def test_no_data_when_short():
    ctx = compute(CBSA, "2026-08", _bps([100] * 47), None, {})
    assert ctx.coverage == "no_data" and ctx.ratio_12m_vs_3y is None


def test_no_data_when_as_of_missing():
    ctx = compute(CBSA, "2026-08", _bps([100] * 48, end="2026-07"), None, {})
    assert ctx.coverage == "no_data"


def test_region_map():
    bps = pd.DataFrame({
        "cbsa_code": ["12060", "17980", "38900"],
        "cbsa_name": ["Atlanta-Sandy Springs-Roswell, GA", "Columbus, GA-AL",
                      "Portland-Vancouver-Hillsboro, OR-WA"],
    })
    sr = pd.read_csv(ROOT / "data" / "market" / "state_region.csv")
    assert region_map(bps, sr) == {"12060": "South", "17980": "South", "38900": "West"}
