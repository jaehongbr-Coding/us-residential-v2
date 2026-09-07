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
