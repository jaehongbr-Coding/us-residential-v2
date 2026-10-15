"""BPS 파서 회귀 테스트. 기대값은 Phase 0 진단(2026-10-15) 실측값 — 바꾸지 말 것."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from market_collect import parse_bps  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


def test_2026_08_atlanta():
    df = parse_bps(FIX / "cbsamonthly_202608.xls")
    a = df[df.cbsa_code == "12060"].iloc[0]
    assert a.period == "2026-08" and a.u5_units == 875 and a.u5_units_ytd == 8361
    assert a.u5_structures == 92 and a.u5_value_k == 132251 and a.metro_micro == "2"
    assert len(df) >= 900


def test_2023_12_atlanta_old_layout():
    df = parse_bps(FIX / "msamonthly_202312.xls")
    a = df[df.cbsa_code == "12060"].iloc[0]
    assert a.period == "2023-12" and a.u5_units == 440 and a.u5_units_ytd == 14227
    assert a.u5_value_k == 79211 and a.metro_micro == ""
    assert 380 <= len(df) <= 400
