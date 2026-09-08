"""Stage B: 원문 지명 -> CBSA 코드. LLM 호출 없음. 100% 재현 가능.

Plan.md §5.4 기반. norm()은 geo_norm.py에서 import한다 (문서 자체의
"공용 모듈로 추출" 경고 반영 — build_geo_crosswalk.py와 완전히 동일한
정규화를 써야 빌드 시점 키와 조회 시점 키가 어긋나지 않는다).
"""
import json
from functools import lru_cache
from pathlib import Path

from geo_norm import norm, norm_university, campus_base, STATE_ABBR

CROSSWALK = Path(__file__).resolve().parent / "data/geo/cbsa_crosswalk.json"
REGIONAL_TERMS = {"sun belt", "sunbelt", "southeast", "midwest", "northeast",
                  "mountain west", "pacific northwest", "west coast", "east coast"}


@lru_cache(maxsize=1)
def _xw():
    return json.loads(CROSSWALK.read_text(encoding="utf-8"))


def _lookup_one(name: str, state: str | None) -> tuple[list[str], str, list[str]]:
    """단일 지명 해석. 반환: (CBSA 코드 리스트, confidence, candidates)

    candidates는 confidence가 "ambiguous"일 때 그 모호성을 만든 후보 코드
    전체다(2026.09 Phase 2: source_hint가 이 후보 목록 안에 있는지 확인하는
    용도로만 쓰며, 후보 밖의 코드를 만들어내지 않는다 — I8). ambiguous가
    아닌 경우 candidates == codes."""
    xw = _xw()
    n = norm(name)
    st = (state or "").upper().strip() or None

    if not n:
        return [], "none", []
    if n in REGIONAL_TERMS:
        return [], "none", []      # 광역 지칭은 CBSA로 매핑하지 않는다

    # 0) 대학명 — 정식명·약칭 정확 매칭 (norm_university, 지명 정규화와 별도).
    #    2026.09 Phase 2.5: 50건 샘플에서 confidence=none 27건 중 11건이
    #    대학이었다. "N.Y.U."는 norm()으로 "nyu"가 되어 alias_idx의
    #    "new york university"와 어긋났다 — norm_university()로 별도 인덱스
    #    (university_idx)를 조회해야 표기 변형이 흡수된다.
    hit = xw["university_idx"].get(norm_university(name))
    if hit:
        return [hit], ("exact" if st else "inferred"), [hit]

    # 0b) 대학명 — 캠퍼스 미지정 fallback (campus_base).
    #    "University of Wisconsin"(캠퍼스 없음)은 university_idx에 없다
    #    (등재된 건 "University of Wisconsin - Madison"/"- Milwaukee"뿐).
    #    campus_base로 하이픈 앞부분만 비교해 후보를 모으되, ⚠️ Columbia/
    #    Miami/Glendale과 동일한 실패 패턴(후보 여럿 중 하나를 임의로 확정)을
    #    반복하지 않는다 — 후보가 정확히 1개일 때만 채택한다.
    base_hit = xw["university_base_idx"].get(campus_base(name))
    if base_hit:
        codes_set = sorted(set(base_hit))
        if len(codes_set) == 1:
            return codes_set, "inferred", codes_set
        return [], "ambiguous", codes_set   # Milwaukee냐 Madison이냐 — 추정 금지 (I8)

    # 1) (도시, 주) 정확 매칭 — 주가 주어졌으면 수작업 alias보다 먼저 확인한다.
    #    ⚠️ 2026.09 Phase 2.5: 뉴욕 자치구 alias("Manhattan"->35620) 추가를
    #    준비하며 발견한 순서 문제. "Manhattan"은 alias로 보면 뉴욕이지만
    #    city_idx에는 "Manhattan, KS"(Kansas State University 소재)도 실존한다.
    #    alias를 먼저 보면(원안의 순서) state="KS"가 명시된 기사까지 alias가
    #    무조건 뉴욕으로 덮어써 버린다 — Columbia/Miami/Glendale과 같은 계열의
    #    "후보가 있는데 다른 걸 확정" 오류를 새로 만드는 셈이다. 이제 주가
    #    주어지면 그 주의 실제 city/county 매칭을 alias보다 먼저 신뢰한다.
    if st:
        for idx in ("city_idx", "county_idx"):
            hit = xw[idx].get(f"{n}|{st}")
            if hit:
                return hit[:1], "exact", hit[:1]

    # 2) 수작업 alias — 지명(구명칭·서브마켓·통칭·뉴욕 자치구)
    hit = xw["alias_idx"].get(n)
    if hit:
        return [hit], ("exact" if st else "inferred"), [hit]

    # 3) 주가 주어졌을 때만: CBSA 타이틀에서 그 주를 가진 것 우선 채택
    if st:
        hit = xw["title_idx"].get(n)
        if hit:
            filtered = [c for c in hit if st in xw["cbsa"][c]["states"]]
            if filtered:
                return filtered[:1], "exact", filtered[:1]
            # 주가 주어졌지만 그 주를 가진 타이틀이 없다 — 4번으로 폴스루

    # 4) title_idx ∪ city_noState 통합 조회.
    #    ⚠️ 2026.09 Phase 2 샘플 검수로 발견한 버그 2건, 둘 다 3번을 title_idx만
    #    보고 독립적으로 단정하던 구버전에서 발생했다:
    #
    #    (a) "Miami"(주 없음) — title_idx["miami"] == ["33060"](Miami, OK, 이름이
    #        하이픈 없는 단일 CBSA라 title_idx에 그대로 들어감) 딱 1건이라 구버전은
    #        "inferred"로 확정했다. 그러나 city_noState["miami"]에는 principal city
    #        경로로 들어온 Miami, FL(33100)까지 2건이 있다 — title_idx만 보면 안
    #        보이는 모호성이었다. 이제 두 인덱스를 합쳐서 판단한다.
    #    (b) "Glendale"(state="AZ") — city_idx["glendale|AZ"]가 아예 없다(Glendale,
    #        AZ는 principal city 목록에 없음). 구버전은 이 경우 그대로 아래 5번(현재는
    #        통합된 4번)으로 넘어가 **주 필터링 없이** city_noState["glendale"](LA
    #        metro, CA 하나뿐)을 그대로 채택해버렸다 — state="AZ"가 주어졌는데
    #        CA 코드를 "inferred"로 확정하는 오판정이었다. 이제 주가 주어졌으면
    #        이 통합 인덱스도 반드시 그 주로 필터링하고, 필터링 후 후보가 없으면
    #        (주어진 주와 모순되는 유일한 후보뿐이면) 추정하지 않고 "none"으로
    #        멈춘다 — "주가 있는데도 매칭 실패"는 "주가 아예 없어서 모호"와 달리
    #        모르는 것이지, 다른 주의 후보로 때울 일이 아니다 (I8).
    combined = set(xw["title_idx"].get(n, [])) | set(xw["city_noState"].get(n, []))
    if st:
        filtered = sorted(c for c in combined if st in xw["cbsa"][c]["states"])
        if len(filtered) == 1:
            return filtered, "inferred", filtered
        if len(filtered) > 1:
            return [], "ambiguous", filtered
        return [], "none", []   # 주가 주어졌지만 그 주와 맞는 후보가 하나도 없다
    if len(combined) == 1:
        result = list(combined)
        return result, "inferred", result
    if len(combined) > 1:
        # research.md §4.4는 이 상태를 "none"으로, Plan.md §5.4 코드는
        # "ambiguous"로 반환한다 — 두 문서가 불일치한다. 이 구현은
        # "ambiguous"를 채택한다: "찾지 못함(none)"과 "여러 후보가 있어
        # 판정 불가(ambiguous)"는 서로 다른 상태이고, 후자는 alias 보강
        # 대상을 식별하는 신호이므로(예: Columbia MO/SC/MD 3-way 충돌)
        # 구분할 가치가 있다 (I8: 추정하지 않되, 상태는 구분한다).
        return [], "ambiguous", sorted(combined)   # ⚠️ Columbia 문제. 추정하지 않는다 (I8)

    return [], "none", []


def _overall_confidence(codes: list[str], confs: list[str]) -> str:
    """codes/confs로부터 종합 confidence를 보수적으로 판정한다 (기존 resolve()에서
    분리 — 2026.09 state/secondary 폴백에서 재사용하기 위함, 로직 변경 없음).

    order.index로 min()을 매기면 confs가 전부 "ambiguous"/"none"뿐이고
    codes가 비어 있을 때도 min(..., default="inferred")가 "inferred"를
    반환해버려 codes가 없는데 confidence만 "inferred"로 찍히는 모순이
    생긴다(Plan.md §5.4 원안의 버그). 아래처럼 codes 유무로 먼저 분기하고,
    codes가 있을 때만 exact/inferred 중에서 최저 등급을 고른다."""
    order = ["exact", "inferred", "ambiguous", "none"]
    if codes:
        exact_or_inferred = [c for c in confs if c in ("exact", "inferred")]
        return min(exact_or_inferred, key=order.index) if exact_or_inferred else "inferred"
    elif "ambiguous" in confs:
        return "ambiguous"
    return "none"


def _aggregate(targets: list[dict], xw: dict):
    """place 목록 하나를 조회해 (codes, titles, states, raws, confs, ambiguous_candidates)를
    반환한다. resolve()의 기존 for-loop를 그대로 함수로 뺀 것 — 2026.09 secondary
    폴백에서 targets 대신 secondaries에 대해 동일 로직을 재사용하기 위함."""
    codes, titles, states, raws, confs = [], [], [], [], []
    ambiguous_candidates: set[str] = set()
    for p in targets:
        raw = (p.get("name") or "").strip()
        if raw:
            raws.append(raw)
        cs, conf, cands = _lookup_one(raw, p.get("state"))
        confs.append(conf)
        if conf == "ambiguous":
            ambiguous_candidates.update(cands)
        for c in cs:
            if c not in codes:
                codes.append(c)
                titles.append(xw["cbsa"][c]["title"])
                for s in xw["cbsa"][c]["states"]:
                    if s not in states:
                        states.append(s)
    return codes, titles, states, raws, confs, ambiguous_candidates


def _aggregate_secondary_with_context(secondaries: list[dict], xw: dict, article_states: list[str]):
    """secondary 폴백 전용 조회. _aggregate()와 동일하되, place 자체에 state가
    없을 때 place 자체를 무주 조회하지 않고 "기사 내 다른 place가 명시한 state"
    (article_states)로만 시도한다. 2026.09 Medford(NJ 기사가 secondary
    "Medford"를 무주로 조회해 Medford, OR로 확정됐던 사고)·Georgetown(D.C. 기사가
    "Georgetown"을 무주로 조회해 Georgetown, TX로 확정됐던 사고) 대응.

    article_states가 비어 있으면(기사 전체에 state 단서가 없으면) 그 place는
    아예 조회하지 않고 결과 없음으로 둔다 — "근거 없는 확정보다 미해결이 낫다"
    (모호하면 채택하지 않는다, I8과 동일한 정신). place 자체가 state를 갖고
    있으면 이 함수도 기존과 완전히 동일하게 그 state로 조회한다(변경 없음).

    article_states가 여럿이면 각각 시도해 서로 다른 CBSA가 하나라도 갈리면
    (found_codes가 2개 이상) 채택하지 않는다 — 후보 복수 시 첫 번째를 확정하지
    않는다는 원칙(I8)을 기사 단위 state 후보에도 동일하게 적용."""
    codes, titles, states, raws, confs = [], [], [], [], []
    ambiguous_candidates: set[str] = set()
    for p in secondaries:
        raw = (p.get("name") or "").strip()
        if raw:
            raws.append(raw)
        own_state = p.get("state")
        if own_state:
            cs, conf, cands = _lookup_one(raw, own_state)
        elif len(article_states) == 1:
            cs, conf, cands = _lookup_one(raw, article_states[0])
        elif len(article_states) > 1:
            found_codes: set[str] = set()
            for cst in article_states:
                cs2, conf2, _cands2 = _lookup_one(raw, cst)
                if conf2 in ("exact", "inferred") and cs2:
                    found_codes.update(cs2)
            if len(found_codes) == 1:
                cs, conf, cands = list(found_codes), "inferred", list(found_codes)
            else:
                cs, conf, cands = [], "none", []
        else:
            # 기사 전체에 state 단서가 없다 — 무주 조회 자체를 하지 않는다(보류).
            cs, conf, cands = [], "none", []
        confs.append(conf)
        if conf == "ambiguous":
            ambiguous_candidates.update(cands)
        for c in cs:
            if c not in codes:
                codes.append(c)
                titles.append(xw["cbsa"][c]["title"])
                for s in xw["cbsa"][c]["states"]:
                    if s not in states:
                        states.append(s)
    return codes, titles, states, raws, confs, ambiguous_candidates


def resolve(places: list[dict], scope: str, source_hint: tuple[str, str] | None = None) -> dict:
    """Stage A 출력 -> geo_* 컬럼 값 dict.

    source_hint: (cbsa_code, state) 튜플. collector.py의 source 라벨
    (예: "Student Housing — University of Missouri (MO)")에서 호출부가
    도출해 넘긴다(geo_store.derive_source_hint 참조). 본문 추론이 아니라
    수집 메타데이터이므로 I8 위반은 아니지만 100% 확실하지도 않으므로,
    Stage B가 "ambiguous"로 판정했고 그 모호성의 후보 코드 목록 안에
    source_hint의 코드가 있을 때만 그것을 채택하고 confidence를
    "source_inferred"로 표기한다. 후보 밖이면 절대 채택하지 않고 ambiguous를
    유지한다(I8). source_hint=None이면 이전 동작과 완전히 동일하다.

    2026.09 두 폴백 추가 (둘 다 1차 조회가 "none"으로 완전히 실패했을 때만
    발동 — 이미 exact/inferred/ambiguous로 판정된 건에는 절대 개입하지 않는다.
    "기존에 해결된 건을 퇴화시키지 않는다"는 원칙 그대로 적용):

    1) secondary 폴백 — primary가 있어 secondary가 버려진 채로 1차 조회가
       실패했을 때만, 버려진 secondary들을 조회한다. secondary들이 서로 다른
       CBSA로 복수 해결되면 채택하지 않고 ambiguous로 남긴다(첫 번째를
       확정하지 않는다, I8). secondary 자체에 state가 없으면 무주 조회하지
       않고 "같은 기사 내 다른 place가 명시한 state"(article_states)로만
       시도한다 — 2026.09 Medford/Georgetown 오판정(주 없는 secondary가
       크로스워크에 유일하게 등재된, 하지만 틀린 동명 도시로 확정된 사고)
       대응. 기사 전체에 state 단서가 없으면 그 secondary는 조회 자체를
       하지 않고 결과 없음으로 둔다(_aggregate_secondary_with_context 참조).
    2) state 폴백 — 그래도 실패했고, 1차 targets 전원이 type=="state"일 때만
       geo_norm.STATE_ABBR(또는 place 자체의 2자리 state 필드)로 주 코드만
       채운다. CBSA/타이틀은 채우지 않는다(정밀도를 부풀리지 않는다) —
       geo_scope를 'state'로, geo_confidence도 'state'로 표기해 CBSA 수준
       exact/inferred와 구분한다.
    """
    xw = _xw()

    has_primary = any(p.get("primary") for p in places)
    targets = [p for p in places if p.get("primary")] if has_primary else places
    secondaries = [p for p in places if not p.get("primary")] if has_primary else []

    codes, titles, states, raws, confs, ambiguous_candidates = _aggregate(targets, xw)
    overall = _overall_confidence(codes, confs)
    geo_scope_out = scope or "none"

    # 1) secondary 폴백 — primary(targets)가 완전히 실패("none")했고 버려진
    #    secondary가 있을 때만 시도한다. ambiguous였던 경우는 건드리지 않는다
    #    (I8 — 이미 "모른다"고 판정한 것을 secondary로 덮어쓰지 않는다).
    if overall == "none" and secondaries:
        article_states = sorted({
            (p.get("state") or "").strip().upper()
            for p in places if p.get("state")
        })
        sec_codes, sec_titles, sec_states, sec_raws, sec_confs, sec_ambig = \
            _aggregate_secondary_with_context(secondaries, xw, article_states)
        distinct_sec_codes = set(sec_codes)
        if len(distinct_sec_codes) == 1:
            codes, titles, states = sec_codes, sec_titles, sec_states
            raws = raws + sec_raws
            overall = _overall_confidence(codes, sec_confs)
        elif len(distinct_sec_codes) > 1:
            overall = "ambiguous"
            ambiguous_candidates.update(distinct_sec_codes)
        # distinct_sec_codes가 0개(전부 실패)면 overall은 "none"으로 유지되고
        # 아래 state 폴백으로 폴스루한다.

    # 2) state 폴백 — 여전히 완전히 실패("none")했고, 1차 targets 전원이
    #    type=="state"일 때만. secondary 폴백으로 이미 해결/ambiguous가 됐으면
    #    건드리지 않는다.
    if overall == "none" and targets and all(p.get("type") == "state" for p in targets):
        state_codes: list[str] = []
        for p in targets:
            raw_name = (p.get("name") or "").strip()
            st = (p.get("state") or "").strip().upper()
            if not (st and len(st) == 2):
                st = STATE_ABBR.get(norm(raw_name), "")
            if st and st not in state_codes:
                state_codes.append(st)
        if state_codes:
            states = state_codes
            geo_scope_out = "state"
            overall = "state"
            # codes/titles는 비운 채로 둔다 — state만 알 뿐 CBSA는 모른다.

    # source_inferred 승격: ambiguous일 때만, 후보 목록 안에 있을 때만 (I8)
    if overall == "ambiguous" and source_hint is not None:
        hint_code, _hint_state = source_hint
        if hint_code in ambiguous_candidates:
            overall = "source_inferred"
            codes = [hint_code]
            titles = [xw["cbsa"][hint_code]["title"]]
            states = list(xw["cbsa"][hint_code]["states"])

    return {
        "geo_place_raw":  "|".join(raws),
        "geo_cbsa_code":  "|".join(codes),
        "geo_cbsa_title": "|".join(titles),
        "geo_state":      "|".join(states),
        "geo_scope":      geo_scope_out,
        "geo_confidence": overall,
    }
