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
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[.'’,]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    # 접미사 제거 (county/parish/borough 계열)
    s = re.sub(r"\s+(county|parish|borough|census area|city and borough)$", "", s)
    # 접두사 제거 (city of / town of / village of)
    s = re.sub(r"^(city of|town of|village of)\s+", "", s)
    return s
