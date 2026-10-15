"""market_tagger.as_of_for 테스트 (발행월 − 2개월, UTC 기준)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from market_tagger import as_of_for  # noqa: E402


def test_as_of_iso_utc():
    assert as_of_for("2026-10-14T05:00:00Z") == "2026-08"


def test_as_of_naive_year_wrap():
    assert as_of_for("2026-01-05 00:00:00") == "2025-11"


def test_as_of_empty():
    assert as_of_for("") == ""
