import pytest

from geo_resolver import resolve


def test_columbia_without_state_is_ambiguous():
    """Columbia MO / Columbia SC / Columbia (MD 흡수) — 주 정보 없으면 추정하지 않는다 (I8)."""
    out = resolve([{"name": "Columbia", "state": None, "type": "city", "primary": True}], "local")
    assert out["geo_cbsa_code"] == ""
    assert out["geo_confidence"] == "ambiguous"
    assert out["geo_place_raw"] == "Columbia"   # 원문은 반드시 보존


def test_columbia_with_state_mo_resolves():
    out = resolve([{"name": "Columbia", "state": "MO", "type": "city", "primary": True}], "local")
    assert out["geo_cbsa_code"] == "17860"
    assert out["geo_confidence"] == "exact"


def test_columbia_with_state_sc_resolves_distinctly():
    """MO와 SC가 서로 다른 코드로 구분되는지 (Columbia 3-way 충돌 검증)."""
    out = resolve([{"name": "Columbia", "state": "SC", "type": "city", "primary": True}], "local")
    assert out["geo_cbsa_code"] == "17900"
    assert out["geo_confidence"] == "exact"


def test_mizzou_alias_not_seeded():
    """약칭(Mizzou)은 이번 라운드에 alias로 넣지 않았으므로 자동 도출되지 않는다.
    (University of Missouri 같은 정식명만 자동 도출 대상 — 작업 4 참조)"""
    out = resolve([{"name": "Mizzou", "state": None, "type": "university", "primary": True}], "local")
    assert out["geo_cbsa_code"] == ""
    assert out["geo_confidence"] == "none"


def test_legacy_atlanta_title():
    out = resolve([{"name": "Atlanta-Sandy Springs-Alpharetta", "state": "GA",
                    "type": "metro", "primary": True}], "metro")
    assert out["geo_cbsa_code"] == "12060"


def test_submarket_maps_to_metro_but_keeps_raw():
    out = resolve([{"name": "Buckhead", "state": None, "type": "neighborhood", "primary": True}], "local")
    assert out["geo_cbsa_code"] == "12060"
    assert out["geo_place_raw"] == "Buckhead"   # submarket 해상도 보존 (research.md §4.3)


def test_regional_term_not_mapped():
    out = resolve([{"name": "Sun Belt", "state": None, "type": "region", "primary": False}], "regional")
    assert out["geo_cbsa_code"] == ""


def test_primary_filter():
    """전국 기사에서 primary가 없으면 전부 사용하되 scope로 걸러진다."""
    out = resolve([{"name": "Atlanta", "state": "GA", "type": "city", "primary": False},
                   {"name": "Dallas", "state": "TX", "type": "city", "primary": False}], "national")
    assert out["geo_scope"] == "national"


def test_nonexistent_place_is_none():
    out = resolve([{"name": "Zzyzxville", "state": None, "type": "city", "primary": True}], "local")
    assert out["geo_cbsa_code"] == ""
    assert out["geo_confidence"] == "none"


def test_empty_places_is_none():
    out = resolve([], "none")
    assert out["geo_cbsa_code"] == ""
    assert out["geo_confidence"] == "none"
    assert out["geo_place_raw"] == ""


def test_university_alias_university_of_missouri():
    """geo_aliases.yaml의 자동 도출분 샘플 검증 #1 (city_idx: Columbia|MO)."""
    out = resolve([{"name": "University of Missouri", "state": None,
                    "type": "university", "primary": True}], "local")
    assert out["geo_cbsa_code"] == "17860"
    assert out["geo_confidence"] == "inferred"   # alias 매칭 + state 없음


def test_university_alias_brigham_young():
    """geo_aliases.yaml의 자동 도출분 샘플 검증 #2 (city_idx: Provo|UT)."""
    out = resolve([{"name": "Brigham Young University", "state": None,
                    "type": "university", "primary": True}], "local")
    assert out["geo_cbsa_code"] == "39340"
    assert out["geo_confidence"] == "inferred"
