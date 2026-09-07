"""geo 크로스워크/리졸버 공용 정규화 모듈.

Plan.md §5.1의 norm()을 build_geo_crosswalk.py와 geo_resolver.py 양쪽에
중복 정의하지 않고 여기 하나로 모아 import한다 (Plan.md 자체 경고 반영).
"""
import re
import unicodedata

# 전체 50개 주 + DC + PR. 값은 정식 2자리 약칭.
STATE_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "puerto rico": "PR", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}


def norm(s: str) -> str:
    """조회 키 정규화. 소문자, 악센트 제거, 구두점 제거, 공백 단일화.

    build_geo_crosswalk.py / geo_resolver.py 양쪽에서 반드시 이 함수 하나만
    써야 한다 — 둘이 다르게 정규화하면 빌드 시점 키와 조회 시점 키가
    어긋나 크로스워크가 있어도 매칭이 실패한다.

    2026.09 Phase 1.5: Census list2의 consolidated city-county 법정 표기
    (예: "Indianapolis city (balance)", "Louisville/Jefferson County metro
    government (balance)", "Urban Honolulu")를 통상 지명으로 되돌리는 규칙을
    추가했다. ⚠️ " city"/" town" 접미사 일괄 제거는 시도했다가 **되돌렸다**:
    CBSA 타이틀 자체가 "Oklahoma City, OK" / "Kansas City, MO-KS" /
    "Carson City, NV"처럼 city/town이 고유 지명의 일부인 경우가 많아,
    title_idx에 "oklahoma"/"kansas"/"carson" 같은 키가 생겨버린다.
    이 중 "carson"은 city_noState에서 LA metro의 principal city "Carson, CA"와
    충돌해 모호 판정으로만 끝나지만(무해), "oklahoma"/"kansas"는 title_idx
    **단일** 키가 되어 버려(다른 곳에서 안 겹침) 리졸버가 "exact/inferred"로
    확정 판정해버린다 — 즉 기사에 주(state) 이름 "Oklahoma"만 나와도(도시가
    아니라) Oklahoma City의 CBSA로 **소리 없이 오판정**하는 심각한 위험이다.
    city_noState 모호 도시 수 증가(+2, 100→102)는 작아 보였지만, 실제로는
    이 잠재적 오판정이 훨씬 심각한 문제라 규칙 자체를 제거했다 (아래 build
    로그 비교 및 CLAUDE.md/보고 참조).
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    # "Indianapolis city (balance)" -> "Indianapolis city" (Census 부기 표현 제거)
    s = re.sub(r"\s*\(balance\)$", "", s)
    # "Louisville/Jefferson County metro government" -> "Louisville"
    # (복합 지자체 법정명은 첫 세그먼트만 통상 지명으로 취급)
    if "/" in s:
        s = s.split("/", 1)[0].strip()
    s = re.sub(r"[.'’,]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    # "Urban Honolulu" -> "Honolulu"
    s = re.sub(r"^urban\s+", "", s)
    # 접미사 제거 (county/parish/borough 계열)
    s = re.sub(r"\s+(county|parish|borough|census area|city and borough)$", "", s)
    # 접두사 제거 (city of / town of / village of)
    s = re.sub(r"^(city of|town of|village of)\s+", "", s)
    return s


def norm_university(s: str) -> str:
    """대학명 전용 정규화. norm()과 규칙이 다르므로 분리한다 —
    지명은 county/city 접미사를 다루지만 대학명은 표기 변형
    ("N.Y.U." vs "New York University", "... at Austin" vs "... - Austin")을
    다룬다. 하나로 합치면 서로 다른 종류의 규칙이 뒤섞여 유지보수가 어려워진다.

    2026.09 Phase 2.5: 50건 샘플 검수에서 confidence=none 27건 중 11건이
    대학이었다 — Stage A는 "N.Y.U."를 정확히 추출했지만 alias_idx 키는
    "New York University"로만 등재돼 있어 매칭에 실패했다. 이 함수는 그
    표기 차이만 흡수한다. 캠퍼스 접미사("- Madison" 등) 처리는 여기서
    하지 않는다 — 그건 여러 캠퍼스가 서로 다른 CBSA일 수 있어 별도
    로직(geo_resolver의 캠퍼스 fallback)에서 후보 개수를 보고 판단해야
    한다(I8: 후보 2개 이상이면 확정하지 않는다).
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[.'’,]", "", s)          # "n.y.u." -> "nyu"
    s = re.sub(r"[-–—]", " ", s)           # 하이픈/대시 -> 공백
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^the\s+", "", s)          # "The University of Texas..." -> "university of texas..."
    s = re.sub(r"\bat\b", "", s)           # "... at Austin" == "... Austin"
    s = re.sub(r"\s+", " ", s).strip()
    return s


def campus_base(s: str) -> str:
    """캠퍼스 접미사를 뗀 "base" 키를 만든다. norm_university() 결과에서
    마지막 " - 캠퍼스명" 또는 마지막 " 캠퍼스명"(하이픈이 이미 공백으로
    치환된 뒤이므로) 세그먼트를 하나 제거한다.

    ⚠️ 이 결과 하나만으로 확정하지 않는다 — 호출부(geo_resolver)가 이
    base 키로 alias_idx를 조회했을 때 후보가 몇 개인지 반드시 확인해야
    한다. "University of Wisconsin"처럼 여러 캠퍼스가 있는 이름은 base가
    아니라 이미 그 자체가 애매한 이름이므로, 이 함수는 오직
    "University of X - Y" -> "University of X" 방향의 캠퍼스명 제거만
    한다(마지막 공백 이후 토큰 나열을 통째로 잘라내는 것이 아니라, 원본
    문자열에 하이픈이 있었던 경우에만 그 이후를 자른다 — 안 그러면
    "Purdue University Northwest"의 "Northwest"까지 캠퍼스명으로 오인해
    "Purdue University"로 잘못 축약해버린다).
    """
    if not s or "-" not in s and "–" not in s and "—" not in s:
        return norm_university(s)
    # 원본에 하이픈이 있었던 경우에만 그 앞부분을 base로 취급한다
    base_raw = re.split(r"[-–—]", s, maxsplit=1)[0]
    return norm_university(base_raw)
