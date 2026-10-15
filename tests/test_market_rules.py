"""market_rules 경계값 테스트."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from market_context import MarketContext  # noqa: E402
from market_rules import judge  # noqa: E402


def ctx(ratio=1.0, coverage="ok"):
    return MarketContext("99999", "2026-08", coverage, 1000, 1000.0, ratio, "South", 21.8)


def test_boundaries():
    assert judge(ctx(ratio=1.25)) == ["supply_surge"]
    assert judge(ctx(ratio=1.249)) == []
    assert judge(ctx(ratio=0.75)) == ["supply_drought"]
    assert judge(ctx(ratio=0.751)) == []


def test_unknown():
    assert judge(ctx(coverage="low_volume", ratio=0.3)) == ["unknown"]
    assert judge(ctx(coverage="no_data", ratio=None)) == ["unknown"]
    assert judge(ctx(ratio=None)) == ["unknown"]
