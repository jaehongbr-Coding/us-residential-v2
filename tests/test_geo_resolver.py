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


# --- Phase 1.5: 대학 alias 미매핑 28건 정리 회귀 케이스 ---

def test_university_of_louisville_resolved_via_norm_fix():
    """geo_norm의 '/'+'(balance)' 정규화로 city_idx가 직접 잡는 케이스."""
    out = resolve([{"name": "University of Louisville", "state": None,
                    "type": "university", "primary": True}], "local")
    assert out["geo_cbsa_code"] == "31140"


def test_university_of_georgia_resolved_via_title_idx_prefix():
    """city_idx로는 못 잡고(Athens는 principal city 목록에 없음) title_idx
    접두사 매칭(갈래 B)으로 해소된 케이스 — alias_idx 고정 등재분."""
    out = resolve([{"name": "University of Georgia", "state": None,
                    "type": "university", "primary": True}], "local")
    assert out["geo_cbsa_code"] == "12020"


def test_carson_without_state_does_not_falsely_resolve_to_carson_city():
    """⚠️ 회귀 가드: " city"/" town" 접미사를 norm()에서 일괄 제거하면
    title_idx가 "Carson City, NV"를 "carson"으로 정규화해, LA metro의
    principal city "Carson, CA"와 구분 없이 exact/inferred로 오판정하게
    된다(2026.09 Phase 1.5에서 발견 후 해당 규칙을 되돌림). 이 테스트가
    실패하면 그 규칙이 되살아난 것이다."""
    out = resolve([{"name": "Carson", "state": None, "type": "city", "primary": True}], "local")
    assert out["geo_confidence"] != "exact"
    assert out["geo_cbsa_code"] != "16180"  # Carson City, NV로 단정하면 안 된다
