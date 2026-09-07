"""Stage B: 원문 지명 -> CBSA 코드. LLM 호출 없음. 100% 재현 가능.

Plan.md §5.4 기반. norm()은 geo_norm.py에서 import한다 (문서 자체의
"공용 모듈로 추출" 경고 반영 — build_geo_crosswalk.py와 완전히 동일한
정규화를 써야 빌드 시점 키와 조회 시점 키가 어긋나지 않는다).
"""
import json
from functools import lru_cache
from pathlib import Path

from geo_norm import norm

CROSSWALK = Path(__file__).resolve().parent / "data/geo/cbsa_crosswalk.json"
REGIONAL_TERMS = {"sun belt", "sunbelt", "southeast", "midwest", "northeast",
                  "mountain west", "pacific northwest", "west coast", "east coast"}


@lru_cache(maxsize=1)
def _xw():
    return json.loads(CROSSWALK.read_text(encoding="utf-8"))


def _lookup_one(name: str, state: str | None) -> tuple[list[str], str]:
    """단일 지명 해석. 반환: (CBSA 코드 리스트, confidence)"""
    xw = _xw()
    n = norm(name)
    st = (state or "").upper().strip() or None

    if not n:
        return [], "none"
    if n in REGIONAL_TERMS:
        return [], "none"          # 광역 지칭은 CBSA로 매핑하지 않는다

    # 1) 수작업 alias — 최우선. 대학명·구명칭·서브마켓
    hit = xw["alias_idx"].get(n)
    if hit:
        return [hit], "exact" if st else "inferred"

    # 2) (도시, 주) 정확 매칭
    if st:
        for idx in ("city_idx", "county_idx"):
            hit = xw[idx].get(f"{n}|{st}")
            if hit:
                return hit[:1], "exact"

    # 3) CBSA 타이틀 매칭
    #    ⚠️ 2026.09 테스트로 발견한 버그(Plan.md §5.4 원안): 주 정보 없이 hit가
    #    2개 이상이면(예: title_idx["columbia"] == ["17860", "17900"], MO/SC
    #    둘 다 CBSA 타이틀이 "Columbia, ..."로 시작) 원안은 hit[:1]로 첫 코드를
    #    묵시적으로 골라 "inferred"로 반환했다 — 4번 단계(city_noState)가 막으려는
    #    바로 그 모호성을 3번 단계가 먼저 새어나가게 하는 구조였다(I8 위반).
    #    아래는 주 없이 2개 이상이면 ambiguous로 멈추고, 주가 있는데 그 주를 가진
    #    타이틀이 하나도 없으면(원안의 `or hit` 폴백 제거) 4번 단계로 넘긴다.
    hit = xw["title_idx"].get(n)
    if hit:
        if st:
            filtered = [c for c in hit if st in xw["cbsa"][c]["states"]]
            if filtered:
                return filtered[:1], "exact"
            # 주가 주어졌지만 그 주를 가진 타이틀이 없다 — 4번 단계로 폴스루
        elif len(hit) == 1:
            return hit, "inferred"
        else:
            return [], "ambiguous"

    # 4) 주 없이 도시명만 — 전국 유일할 때만 채택
    hit = xw["city_noState"].get(n, [])
    if len(hit) == 1:
        return hit, "inferred"
    if len(hit) > 1:
        # research.md §4.4는 이 상태를 "none"으로, Plan.md §5.4 코드는
        # "ambiguous"로 반환한다 — 두 문서가 불일치한다. 이 구현은
        # "ambiguous"를 채택한다: "찾지 못함(none)"과 "여러 후보가 있어
        # 판정 불가(ambiguous)"는 서로 다른 상태이고, 후자는 alias 보강
        # 대상을 식별하는 신호이므로(예: Columbia MO/SC/MD 3-way 충돌)
        # 구분할 가치가 있다 (I8: 추정하지 않되, 상태는 구분한다).
        return [], "ambiguous"     # ⚠️ Columbia 문제. 추정하지 않는다 (I8)

    return [], "none"


def resolve(places: list[dict], scope: str) -> dict:
    """Stage A 출력 -> geo_* 컬럼 값 dict."""
    xw = _xw()
    codes, titles, states, raws, confs = [], [], [], [], []

    # primary가 있으면 primary만, 없으면 전부
    targets = [p for p in places if p.get("primary")] or places

    for p in targets:
        raw = (p.get("name") or "").strip()
        if raw:
            raws.append(raw)
        cs, conf = _lookup_one(raw, p.get("state"))
        confs.append(conf)
        for c in cs:
            if c not in codes:
                codes.append(c)
                titles.append(xw["cbsa"][c]["title"])
                for s in xw["cbsa"][c]["states"]:
                    if s not in states:
                        states.append(s)

    # 전체 confidence = 가장 낮은 등급으로 보수적 판정.
    # order.index로 min()을 매기면 confs가 전부 "ambiguous"/"none"뿐이고
    # codes가 비어 있을 때도 min(..., default="inferred")가 "inferred"를
    # 반환해버려 codes가 없는데 confidence만 "inferred"로 찍히는 모순이
    # 생긴다(Plan.md §5.4 원안의 버그). 아래처럼 codes 유무로 먼저 분기하고,
    # codes가 있을 때만 exact/inferred 중에서 최저 등급을 고른다.
    order = ["exact", "inferred", "ambiguous", "none"]
    if codes:
        exact_or_inferred = [c for c in confs if c in ("exact", "inferred")]
        overall = min(exact_or_inferred, key=order.index) if exact_or_inferred else "inferred"
    elif "ambiguous" in confs:
        overall = "ambiguous"
    else:
        overall = "none"

    return {
        "geo_place_raw":  "|".join(raws),
        "geo_cbsa_code":  "|".join(codes),
        "geo_cbsa_title": "|".join(titles),
        "geo_state":      "|".join(states),
        "geo_scope":      scope or "none",
        "geo_confidence": overall,
    }
