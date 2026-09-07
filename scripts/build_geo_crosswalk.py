"""Census delineation 파일 -> data/geo/cbsa_crosswalk.json 생성.

1회성 스크립트. vintage 갱신 시에만 재실행. geo_aliases.yaml이 대학 alias를
크로스워크(city_idx)에서 자동 도출하므로, 대학 alias를 갱신했다면 이 스크립트를
다시 실행해 alias_idx를 크로스워크에 반영해야 한다 (2-pass 빌드).

원본 파일: data/geo/raw/list1_2023.xlsx (CBSAs/카운티), list2_2023.xlsx(principal cities)
  https://www.census.gov/geographies/reference-files/time-series/demo/metro-micro/delineation-files.html
  2026.09 실측 결과 Plan.md가 가정한 파일명(cbsa_delineation_2023.xlsx 등)과
  실제 다운로드 파일명(list1_2023.xlsx/list2_2023.xlsx)이 달라 후자를 그대로 쓴다.

⚠️ 문서(Plan.md)에 적힌 CBSA 개수(393 MSA / 542 uSA 등)를 하드코딩하지 않는다.
   실제 파싱 결과를 카운트해 출력한다.
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd
import yaml

# Windows cp949 터미널에서 한글·특수문자 출력 가능하도록 (CLAUDE.md 관례)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from geo_norm import norm, norm_university, campus_base, STATE_ABBR

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/geo/raw"
OUT = ROOT / "data/geo/cbsa_crosswalk.json"
ALIASES = ROOT / "data/geo/geo_aliases.yaml"
VINTAGE = "2023"  # OMB Bulletin 23-01 기준. 절대 혼용 금지.

# 2026.09 실측: 두 파일 모두 상단 2행이 제목, 3번째 행(0-idx 2)이 실제 헤더.
# Plan.md의 skiprows=2 가정과 결과적으로 동일(header=2 == skiprows=2,header=0).
HEADER_ROW = 2


def _clean_code(raw) -> str | None:
    """CBSA/FIPS 코드를 문자열로 안전 변환. 엑셀이 숫자로 읽어 '10100.0'이 되는
    경우와 각주 행(문자열 전체가 코드 칸에 들어간 경우)을 모두 방어한다."""
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None
    s = s.split(".")[0]
    if not s.isdigit():
        return None
    return s


def _load_list1() -> pd.DataFrame:
    d = pd.read_excel(RAW / f"list1_{VINTAGE}.xlsx", header=HEADER_ROW)
    d["_cbsa_code"] = d["CBSA Code"].apply(_clean_code)
    d = d[d["_cbsa_code"].notna()].copy()
    d["_cbsa_code"] = d["_cbsa_code"].str.zfill(5)
    return d


def _load_list2() -> pd.DataFrame:
    d = pd.read_excel(RAW / f"list2_{VINTAGE}.xlsx", header=HEADER_ROW)
    d["_cbsa_code"] = d["CBSA Code"].apply(_clean_code)
    d = d[d["_cbsa_code"].notna()].copy()
    d["_cbsa_code"] = d["_cbsa_code"].str.zfill(5)
    return d


def build():
    # --- 0) FIPS 주 코드 -> 2자리 약칭 매핑 (list1에서 도출) -----------------
    # list1엔 FIPS State Code(숫자) + State Name(전체명) 둘 다 있지만,
    # list2엔 FIPS State Code만 있고 State Name이 없다. list1로 대응표를 만든다.
    d1_raw = pd.read_excel(RAW / f"list1_{VINTAGE}.xlsx", header=HEADER_ROW)
    fips_to_abbr: dict[str, str] = {}
    for _, r in d1_raw.iterrows():
        fips = _clean_code(r.get("FIPS State Code"))
        state_name = str(r.get("State Name", "")).strip()
        if fips and state_name and state_name.lower() != "nan":
            abbr = STATE_ABBR.get(norm(state_name))
            if abbr:
                fips_to_abbr[fips.zfill(2)] = abbr

    # --- 1) CBSA <-> 카운티 -------------------------------------------------
    d = _load_list1()

    cbsa: dict[str, dict] = {}       # code -> {code, title, type, states, counties}
    county_idx: dict[str, list] = {}  # "norm_county|ST" -> [code, ...]

    for _, r in d.iterrows():
        code = r["_cbsa_code"]
        title = str(r.get("CBSA Title", "")).strip()
        state_name = str(r.get("State Name", "")).strip()
        county = str(r.get("County/County Equivalent", "")).strip()
        cbsa_type = str(r.get("Metropolitan/Micropolitan Statistical Area", "")).strip()

        e = cbsa.setdefault(code, {
            "code": code, "title": title, "type": cbsa_type,
            "states": [], "counties": [],
        })
        st_abbr = STATE_ABBR.get(norm(state_name))
        if st_abbr and st_abbr not in e["states"]:
            e["states"].append(st_abbr)
        if county and county.lower() != "nan":
            e["counties"].append(county)
            if st_abbr:
                county_idx.setdefault(f"{norm(county)}|{st_abbr}", []).append(code)

    # --- 2) Principal cities -> city 인덱스 ----------------------------------
    p = _load_list2()

    city_idx: dict[str, list] = {}      # "norm_city|ST" -> [code, ...]
    city_noState: dict[str, list] = {}  # norm_city -> [code, ...]  (모호성 판정용)

    for _, r in p.iterrows():
        code = r["_cbsa_code"]
        if code not in cbsa:
            continue
        place = str(r.get("Principal City Name", "")).strip()
        if not place or place.lower() == "nan":
            continue
        # 2026.09 실측: Principal City Name은 "Atlanta"처럼 도시명만 있고
        # ", Georgia" 같은 주 표기가 붙지 않는다 (Plan.md 가정과 다름).
        # 주는 FIPS State Code(숫자)를 fips_to_abbr로 변환해 얻는다.
        fips_state = _clean_code(r.get("FIPS State Code"))
        st_abbr = fips_to_abbr.get(fips_state.zfill(2)) if fips_state else None
        n = norm(place)
        if st_abbr:
            city_idx.setdefault(f"{n}|{st_abbr}", []).append(code)
        city_noState.setdefault(n, []).append(code)

    # --- 3) CBSA 타이틀 자체를 인덱스에 추가 ----------------------------------
    title_idx: dict[str, list] = {}
    for code, e in cbsa.items():
        # "Atlanta-Sandy Springs-Roswell, GA" -> "atlanta-sandy springs-roswell"
        t = e["title"].rsplit(",", 1)[0]
        title_idx.setdefault(norm(t), []).append(code)
        # 첫 토큰도 인덱스 ("atlanta")
        first = norm(t.split("-")[0])
        city_noState.setdefault(first, []).append(code)

    # --- 4) 수작업 alias 병합 -------------------------------------------------
    # 지명(legacy_titles/submarkets/colloquial)은 norm(), 대학명(universities/
    # university_abbreviations)은 norm_university()로 — 정규화 규칙이 다르므로
    # 서로 다른 인덱스(alias_idx vs university_idx)에 별도로 넣는다.
    # 2026.09 Phase 2.5: 하나의 alias_idx에 두 정규화를 섞어 넣으면 빌드 시점
    # 키(norm_university)와 조회 시점 키(norm)가 어긋나 매칭이 실패한다.
    alias_idx: dict[str, str] = {}
    university_idx: dict[str, str] = {}
    university_base_idx: dict[str, list] = {}
    if ALIASES.exists():
        aliases = yaml.safe_load(ALIASES.read_text(encoding="utf-8")) or {}

        for name, code in (aliases.get("universities") or {}).items():
            code = str(code).strip()
            if not code:
                continue
            code = code.zfill(5)
            university_idx[norm_university(name)] = code
            base = campus_base(name)
            # ⚠️ 2026.09 Phase 2.5 실측으로 발견: 하이픈이 없는 이름(예: "University
            # of Missouri", Columbia MO)은 campus_base()가 그대로 돌려주므로
            # base == 자기 자신의 정식명이 된다. 이걸 university_base_idx에 넣으면
            # "University of Missouri-Kansas City"(전혀 다른 독립 대학, Kansas
            # City MO-KS 소재)가 campus_base로 "university of missouri"까지
            # 잘려 이 무관한 항목과 충돌 — Columbia로 오판정됐다. 실제로 하이픈이
            # 있어 잘린 이름만 base 인덱스에 넣는다(캠퍼스 접미사가 있는 것끼리만
            # 모호성 판단 대상). 이미 정확히 일치하는 이름은 위 university_idx의
            # 정확매칭(0단계)이 처리하므로 base fallback에 새지 않아도 된다.
            if base != norm_university(name):
                university_base_idx.setdefault(base, []).append(code)

        for section in ("university_abbreviations", "university_colloquial"):
            for abbr, code in (aliases.get(section) or {}).items():
                code = str(code).strip()
                if not code:
                    continue
                university_idx[norm_university(abbr)] = code.zfill(5)

        for section in ("legacy_titles", "submarkets", "colloquial"):
            for alias, code in (aliases.get(section) or {}).items():
                code = str(code).strip()
                if not code:
                    continue  # 의도적 공백(미해결 처리, 예: "Mid-Missouri") — 건너뜀
                alias_idx[norm(alias)] = code.zfill(5)
    else:
        print(f"[WARN] {ALIASES} 없음 — alias_idx/university_idx 비어있는 채로 빌드")

    # --- 5) 중복 제거 후 저장 ---------------------------------------------------
    def dedupe(dd: dict) -> dict:
        return {k: sorted(set(v)) for k, v in dd.items()}

    county_idx = dedupe(county_idx)
    city_idx = dedupe(city_idx)
    city_noState = dedupe(city_noState)
    title_idx = dedupe(title_idx)
    university_base_idx = dedupe(university_base_idx)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "vintage": VINTAGE,
        "source": "OMB Bulletin 23-01 / US Census Bureau delineation files (list1/list2)",
        "built_at": pd.Timestamp.now("UTC").isoformat(),
        "cbsa": cbsa,
        "county_idx": county_idx,
        "city_idx": city_idx,
        "city_noState": city_noState,
        "title_idx": title_idx,
        "alias_idx": alias_idx,
        "university_idx": university_idx,
        "university_base_idx": university_base_idx,
        "state_abbr": STATE_ABBR,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # --- 검증 출력 --------------------------------------------------------
    msa = sum(1 for e in cbsa.values() if e["type"] == "Metropolitan Statistical Area")
    usa = sum(1 for e in cbsa.values() if e["type"] == "Micropolitan Statistical Area")
    print(f"CBSA 총 {len(cbsa)}개 (MSA {msa} / uSA {usa} / 기타 {len(cbsa) - msa - usa})")
    print(f"city_idx {len(city_idx)} / county_idx {len(county_idx)} "
          f"/ title_idx {len(title_idx)} / alias_idx {len(alias_idx)}")
    print(f"university_idx {len(university_idx)} / university_base_idx {len(university_base_idx)}")
    multi_campus = {k: v for k, v in university_base_idx.items() if len(v) >= 2}
    print(f"  캠퍼스 base 공유(2개 이상, 확정 금지 대상) {len(multi_campus)}개")

    print("\n확인 코드:")
    for code in ("12060", "17860", "17900", "12020", "41180"):
        e = cbsa.get(code)
        print(f"  {code}: {e['title'] if e else '(존재하지 않음)'}")

    print("\ncity_noState 모호 도시(코드 2개 이상) 상위 20개:")
    ambiguous = sorted(
        ((name, codes) for name, codes in city_noState.items() if len(codes) >= 2),
        key=lambda kv: -len(kv[1]),
    )
    for name, codes in ambiguous[:20]:
        print(f"  {name!r}: {len(codes)}건 {codes}")


if __name__ == "__main__":
    build()
