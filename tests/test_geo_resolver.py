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


def test_source_hint_promotes_columbia_to_mo():
    out = resolve([{"name": "Columbia", "state": None, "type": "city", "primary": True}],
                   "local", source_hint=("17860", "MO"))
    assert out["geo_cbsa_code"] == "17860"
    assert out["geo_confidence"] == "source_inferred"


def test_source_hint_promotes_columbia_to_sc():
    out = resolve([{"name": "Columbia", "state": None, "type": "city", "primary": True}],
                   "local", source_hint=("17900", "SC"))
    assert out["geo_cbsa_code"] == "17900"
    assert out["geo_confidence"] == "source_inferred"


def test_source_hint_outside_candidates_is_ignored():
    """Atlanta(12060)는 Columbia의 후보 목록(12580/17860/17900)에 없으므로
    절대 채택하지 않는다 (I8) — ambiguous 유지."""
    out = resolve([{"name": "Columbia", "state": None, "type": "city", "primary": True}],
                   "local", source_hint=("12060", "GA"))
    assert out["geo_cbsa_code"] == ""
    assert out["geo_confidence"] == "ambiguous"


def test_source_hint_none_is_backward_compatible():
    out = resolve([{"name": "Columbia", "state": None, "type": "city", "primary": True}], "local")
    assert out["geo_cbsa_code"] == ""
    assert out["geo_confidence"] == "ambiguous"


def test_miami_without_state_is_ambiguous_not_miami_ok():
    """⚠️ 회귀 가드: title_idx["miami"]는 Miami, OK 하나뿐이지만
    city_noState["miami"]에는 principal city 경로로 들어온 Miami, FL도
    있다. title_idx만 보고 확정하면 Miami, FL 기사가 Miami, OK로
    오판정된다 (2026.09 Phase 2 샘플 검수에서 실제 발견)."""
    out = resolve([{"name": "Miami", "state": None, "type": "city", "primary": True}], "local")
    assert out["geo_cbsa_code"] != "33060"  # Miami, OK로 단정하면 안 된다
    assert out["geo_confidence"] == "ambiguous"


def test_glendale_with_wrong_state_available_returns_none_not_other_state():
    """⚠️ 회귀 가드: Glendale, AZ는 principal city 목록에 없어 city_idx로
    못 잡는다. state="AZ"가 명시됐는데도 상태 필터 없이 city_noState를
    그대로 채택하면 Glendale, CA(LA metro)로 오판정된다 — 실제로 주어진
    state와 모순되는 유일한 후보를 "inferred"로 확정해버리는 버그였다
    (2026.09 Phase 2 샘플 검수에서 실제 발견). 주어진 주와 안 맞으면
    추정하지 않고 none으로 멈춰야 한다 (I8)."""
    out = resolve([{"name": "Glendale", "state": "AZ", "type": "city", "primary": True}], "local")
    assert out["geo_cbsa_code"] != "31080"  # LA metro(CA)로 단정하면 안 된다
    assert out["geo_confidence"] == "none"


def test_carson_without_state_does_not_falsely_resolve_to_carson_city():
    """⚠️ 회귀 가드: " city"/" town" 접미사를 norm()에서 일괄 제거하면
    title_idx가 "Carson City, NV"를 "carson"으로 정규화해, LA metro의
    principal city "Carson, CA"와 구분 없이 exact/inferred로 오판정하게
    된다(2026.09 Phase 1.5에서 발견 후 해당 규칙을 되돌림). 이 테스트가
    실패하면 그 규칙이 되살아난 것이다."""
    out = resolve([{"name": "Carson", "state": None, "type": "city", "primary": True}], "local")
    assert out["geo_confidence"] != "exact"
    assert out["geo_cbsa_code"] != "16180"  # Carson City, NV로 단정하면 안 된다


# --- Phase 2.5: 대학 지명 매칭 갭 (표기 변형·캠퍼스·약칭) ---

def test_nyu_abbreviation_resolves_to_nyc_metro():
    """"N.Y.U."는 norm()으로는 "nyu"가 되어 alias_idx의 "new york university"와
    어긋난다 — university_idx(norm_university 기반)로 별도 조회해야 한다."""
    out = resolve([{"name": "N.Y.U.", "state": None, "type": "university", "primary": True}], "local")
    assert out["geo_cbsa_code"] == "35620"
    assert out["geo_confidence"] == "inferred"


def test_the_university_of_texas_at_austin_matches_hyphen_variant():
    """"The University of Texas at Austin" == "University of Texas at Austin"
    (geo_aliases.yaml 등재 표기) — "the " 접두사·"at" 처리 확인."""
    out = resolve([{"name": "The University of Texas at Austin", "state": None,
                    "type": "university", "primary": True}], "local")
    assert out["geo_cbsa_code"] == "12420"


def test_university_of_wisconsin_without_campus_is_ambiguous():
    """캠퍼스 미지정 "University of Wisconsin"은 Madison/Milwaukee 2개 후보 —
    절대 첫 번째를 확정하지 않는다 (Columbia/Miami/Glendale과 동일 원칙)."""
    out = resolve([{"name": "University of Wisconsin", "state": None,
                    "type": "university", "primary": True}], "local")
    assert out["geo_cbsa_code"] == ""
    assert out["geo_confidence"] == "ambiguous"


def test_purdue_university_northwest_not_collapsed_to_base():
    """"Purdue University Northwest"는 별도 캠퍼스이며 하이픈이 없어 campus_base가
    자기 자신 그대로다 — "Purdue University"(Lafayette)로 축약되면 안 된다.
    geo_aliases.yaml에 등재되지 않았으므로 none이 정답이다."""
    out = resolve([{"name": "Purdue University Northwest", "state": None,
                    "type": "university", "primary": True}], "local")
    assert out["geo_cbsa_code"] == ""
    assert out["geo_confidence"] == "none"


def test_umkc_not_conflated_with_university_of_missouri_columbia():
    """⚠️ 회귀 가드: "University of Missouri-Kansas City"(독립된 별개 대학,
    Kansas City MO-KS 소재)가 campus_base로 "university of missouri"까지
    잘려 "University of Missouri"(Columbia MO, 하이픈 없는 이름)와 충돌해
    Columbia로 오판정된 적이 있다(2026.09 Phase 2.5 실측 발견). 하이픈 없는
    이름은 university_base_idx에 넣지 않도록 고쳐서 해결했다."""
    out = resolve([{"name": "University of Missouri-Kansas City", "state": None,
                    "type": "university", "primary": True}], "local")
    assert out["geo_cbsa_code"] != "17860"  # Columbia, MO로 단정하면 안 된다


@pytest.mark.parametrize("abbr", ["UTA", "UWM", "USC", "UGA", "UT", "UW", "ASU", "MSU"])
def test_discarded_abbreviations_are_not_in_alias(abbr):
    """충돌(UTA/UWM/USC/ASU/MSU)하거나 3글자 미만(UT/UW)이라 버린 약칭,
    그리고 기계적으로 생성 불가능한 통칭(UGA)은 alias에 없어야 한다 —
    절대 임의로 하나를 확정하지 않는다."""
    out = resolve([{"name": abbr, "state": None, "type": "university", "primary": True}], "local")
    assert out["geo_confidence"] != "exact"
    assert out["geo_confidence"] != "inferred"


# --- Phase 2.5 2차: 백필 검증에서 발견한 뉴욕 자치구 + 대학 구어체 축약 ---

def test_manhattan_without_state_resolves_to_nyc():
    """뉴욕 자치구 alias 추가 확인 — 실제 백필에서 116건이 Manhattan, KS로
    오판정됐던 것을 바로잡는다."""
    out = resolve([{"name": "Manhattan", "state": None, "type": "city", "primary": True}], "local")
    assert out["geo_cbsa_code"] == "35620"


def test_manhattan_with_kansas_state_wins_over_nyc_alias():
    """⚠️ 회귀 가드 — 이번 작업에서 가장 중요한 테스트: state="KS"가 명시되면
    alias(뉴욕)보다 실제 city_idx의 Manhattan, KS가 이겨야 한다. 그렇지 않으면
    Kansas State University 관련 기사가 전부 뉴욕으로 오판정된다.
    geo_resolver의 순서를 "주 명시 시 city/county 정확매칭 -> alias"로
    바꿔서 해결했다 — 원안(alias 최우선)이었다면 이 테스트가 실패한다."""
    out = resolve([{"name": "Manhattan", "state": "KS", "type": "city", "primary": True}], "local")
    assert out["geo_cbsa_code"] == "31740"
    assert out["geo_confidence"] == "exact"


@pytest.mark.parametrize("borough,code", [
    ("Brooklyn", "35620"), ("Queens", "35620"), ("Bronx", "35620"),
    ("The Bronx", "35620"), ("Staten Island", "35620"),
])
def test_nyc_boroughs_resolve_to_nyc_metro(borough, code):
    out = resolve([{"name": borough, "state": None, "type": "city", "primary": True}], "local")
    assert out["geo_cbsa_code"] == code


@pytest.mark.parametrize("name,code", [
    ("Emory", "12060"), ("Notre Dame", "43780"), ("UMass Amherst", "11200"),
])
def test_university_colloquial_names_resolve(name, code):
    """작업 2에서 채택된 대학 구어체 축약 alias 샘플 검증."""
    out = resolve([{"name": name, "state": None, "type": "university", "primary": True}], "local")
    assert out["geo_cbsa_code"] == code


@pytest.mark.parametrize("name", ["UofM", "University of Hawaii", "UW"])
def test_rejected_university_colloquial_candidates_not_in_alias(name):
    """폐집합(BLUE_VISTA_UNIVERSITIES 175개) 밖의 위험 때문에 제외한 후보들.
    UofM(Michigan/Minnesota와 전국적으로 혼용), University of Hawaii(bare —
    Hilo/West Oahu 등 다른 캠퍼스 존재), UW(University of Washington의 흔한
    약칭과 충돌, Washington State 기사에서 추출된 것은 Stage A 오류로 의심)."""
    out = resolve([{"name": name, "state": None, "type": "university", "primary": True}], "local")
    assert out["geo_confidence"] not in ("exact", "inferred")


@pytest.mark.parametrize("abbr", ["CSUF", "ISU", "KSU", "PSU"])
def test_abbreviations_removed_after_175_way_collision_check(abbr):
    """⚠️ 회귀 가드: 이 4개는 애초에 university_abbreviations에 있었으나,
    "코드가 있는 154개"만 대상으로 한 충돌 검사가 "코드가 없던 미해결 21건"과의
    충돌(CSUF=Fresno/Fullerton, ISU=Iowa State/Illinois State,
    KSU=Kansas State/Kennesaw State/Kent State, PSU=Portland State/
    Pennsylvania State)을 놓쳐서 실제 백필 데이터에 오판정 6건이 났다
    (2026.09 Phase 2.5 2차). 제거 후 재발 방지 — 되살아나면 이 테스트가 실패한다."""
    out = resolve([{"name": abbr, "state": None, "type": "university", "primary": True}], "local")
    assert out["geo_confidence"] not in ("exact", "inferred")
