# Plan.md — The Brief geo 태깅 구현 계획

> 선행 문서: `research.md` v0.1
> 방법론 단계: 2단계(계획). **본 문서 승인 전 구현 금지.**
> 대상 저장소: `us-residential-v2`
> 작성일: 2026-08-24

---

## 0. 불변조건 (Invariants) — 구현 시 절대 위반 금지

| # | 불변조건 | 이유 |
|---|---|---|
| I1 | `classifier.py`를 **한 줄도 수정하지 않는다** | research.md §3.3 프롬프트 간섭 차단 |
| I2 | 기존 16개 컬럼의 **이름·순서를 변경하지 않는다.** 신규 컬럼은 뒤에만 추가(append-only) | 기존 파서 호환 |
| I3 | geo 관련 코드는 `geo_*` 컬럼에만 write한다 | 오염 경로 물리적 차단 |
| I4 | geo 프롬프트에 category / event_tags / sector / signal_type / woomi_relevance를 **언급하지 않는다** | 동일 |
| I5 | `woomi_relevance` 산식에 geo를 넣지 않는다 | 재현성 파괴 방지 (research.md §3.4c) |
| I6 | The Brief UI(`index.html`, `app.py`)에 geo 필터를 노출하지 않는다 (이번 라운드) | 본 기능 열화 방지 |
| I7 | 런타임에 census.gov 등 외부 네트워크에 의존하지 않는다 | 크로스워크는 저장소에 커밋 |
| I8 | 모호한 지명은 **추정하지 않고 미해결로 남긴다** | research.md §4.4 |

---

## 1. Phase 0 — 즉시 실행 (계획 승인 불필요)

> **⚠️ 이 항목은 Plan.md 검토를 기다리지 말고 오늘 실행할 것.** 하루 지연 = 하루치 데이터 영구 손실. (research.md §5.1)

### 1.1 보관기간 연장

```bash
git pull --no-rebase
grep -rn "90" collector.py | grep -i "day\|retention\|timedelta\|prune"
```

확인 후, pruning 상수를 다음과 같이 변경한다. (실제 변수명은 V3 확인 결과에 따름)

```python
# collector.py — before
RETENTION_DAYS = 90

# collector.py — after
RETENTION_DAYS = 730   # 2026-08: 기저선(base rate) 산출을 위해 연장.
                       # 90일 유지 시 계절성 흡수 불가 + 매일 데이터 영구 소실.
```

**커밋 메시지**: `feat: 기사 보관기간 90일 → 730일 (기저선 산출 목적)`

### 1.2 백업 브랜치 생성

과거 CSV 손상(5,576 → 5,442) 이력이 있으므로 작업 전 스냅샷을 확보한다.

```bash
git checkout -b backup/pre-geo-20260824
git push -u origin backup/pre-geo-20260824
git checkout main
```

### 1.3 현황 실측 (research.md §2.3 V7·V8 해소)

```bash
python - <<'PY'
import pandas as pd
d = pd.read_csv("articles.csv")
print("rows:", len(d), "| cols:", len(d.columns))
print("published_at:", d.published_at.min(), "~", d.published_at.max())
print("file MB:", round(__import__("os").path.getsize("articles.csv")/1e6, 2))
blob = (d.title.fillna("") + " " + d.summary.fillna("")).str.lower()
for kw in ["columbia", "mizzou", "university of missouri", "atlanta",
           "sandy springs", "boone county", "buckhead", "marietta"]:
    print(f"{kw:26s}: {blob.str.contains(kw).sum():5d}")
print(d.category.value_counts())
print(d.woomi_relevance.value_counts())
PY
```

**이 출력값을 Plan.md §7 Q3(커버리지 임계치)과 §6(백필 범위) 확정에 사용한다.**

---

## 2. 아키텍처 개요

```
┌──────────────────────────────────────────────────────────────┐
│  기존 파이프라인 (동결 구간 — 수정 없음)                        │
│  collector.py ──→ articles.csv ──→ classifier.py             │
│   (RSS 수집)        (16 cols)      (Sonnet 4.6, 분류)         │
└──────────────────────────────────────────────────────────────┘
                            │ 읽기 전용
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  신규 geo 파이프라인 (완전 분리)                                │
│                                                              │
│  geo_tagger.py                                               │
│    Stage A: Claude Haiku 4.5 (Batch API)                     │
│             title+summary → 원문 지명 배열 (JSON)              │
│             ※ 프롬프트에 CBSA 목록·기존 분류체계 없음            │
│                            │                                 │
│                            ▼                                 │
│    Stage B: geo_resolver.py (순수 Python, LLM 호출 없음)       │
│             원문 지명 → CBSA 코드                              │
│             data/geo/cbsa_crosswalk.json 조회                 │
│                            │                                 │
│                            ▼                                 │
│              articles.csv 의 geo_* 컬럼에만 write             │
└──────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  baseline.py — 기저선 산출 (읽기 전용)                          │
│    CBSA 코드별 관측창 빈도 / 최근 4주 빈도 / n / 커버리지 판정    │
│                            │                                 │
│                            ▼                                 │
│    geo_index.json  ←── IC Helper가 소비하는 산출물              │
└──────────────────────────────────────────────────────────────┘
```

**Stage A / Stage B 분리의 핵심 이점:** Stage A 출력(원문 지명)을 `geo_place_raw`에 원본 보존하므로, alias를 추가하거나 매칭 규칙을 바꿔도 **API 재호출 없이 Stage B만 재실행**하면 된다. 5,442건 재태깅 반복이 원천 차단된다.

---

## 3. 파일 변경 계획

### 3.1 신규 파일 목록

| 경로 | 성격 | 설명 |
|---|---|---|
| `data/geo/raw/cbsa_delineation_2023.xlsx` | 커밋 데이터 | Census 원본 (수동 다운로드) |
| `data/geo/raw/principal_cities_2023.xlsx` | 커밋 데이터 | Census 원본 (수동 다운로드) |
| `data/geo/geo_aliases.yaml` | 수작업 | 대학명·구명칭·서브마켓 별칭 |
| `data/geo/cbsa_crosswalk.json` | 빌드 산출물(커밋) | 런타임 조회 대상 |
| `scripts/build_geo_crosswalk.py` | 1회성 스크립트 | 위 json 생성 |
| `geo_resolver.py` | 모듈 | Stage B. 순수 함수, 테스트 가능 |
| `geo_tagger.py` | 실행 스크립트 | Stage A + Stage B 오케스트레이션 |
| `baseline.py` | 모듈 | 기저선 산출 → geo_index.json |
| `scripts/snapshot_regression.py` | 검증 | 작업 전/후 분류 분포 스냅샷 |
| `tests/test_geo_resolver.py` | 테스트 | 고정 케이스 회귀 |

### 3.2 기존 파일 수정 (최소)

| 경로 | 수정 내용 | 위험도 |
|---|---|---|
| `collector.py` | CSV 헤더 상수에 geo 7컬럼 추가 (값은 빈 문자열) | 중 — V1 확인 필수 |
| `.github/workflows/[daily].yml` | classify 단계 뒤에 geo_tag 단계 추가 | 하 |
| `requirements.txt` | `pyyaml`, `openpyxl` 추가 (미포함 시) | 하 |
| `CLAUDE.md` | 스키마 16 → 23컬럼, 규칙 갱신 | 하 |

**`classifier.py`는 수정 대상이 아니다 (I1).**

---

## 4. 스키마 변경

### 4.1 신규 컬럼 7개 (17~23번, append-only)

| # | 컬럼 | 타입 | 예시 | 설명 |
|---|---|---|---|---|
| 17 | `geo_place_raw` | str, `\|` 구분 | `Columbia\|University of Missouri` | Stage A가 추출한 원문 지명. **감사 추적 + 재매핑용. 절대 정규화하지 않는다.** |
| 18 | `geo_cbsa_code` | str, `\|` 구분 | `17860` | 5자리 CBSA 코드. **모든 조인·집계의 유일한 키.** 미해결 시 빈 문자열 |
| 19 | `geo_cbsa_title` | str, `\|` 구분 | `Columbia, MO` | 표시용 명칭 (2023 vintage) |
| 20 | `geo_state` | str, `\|` 구분 | `MO` | 2자리 주 코드 |
| 21 | `geo_scope` | str, 단일 | `local` | `national\|regional\|metro\|local\|none` |
| 22 | `geo_confidence` | str, 단일 | `exact` | `exact\|inferred\|ambiguous\|none` |
| 23 | `geo_tagged_at` | ISO8601 | `2026-08-25T06:12:00Z` | 태깅 시각. 재실행 대상 선별용 |

**설계 근거**
- 코드를 키로 삼는 이유: CBSA 명칭은 vintage마다 변경된다 (Atlanta-Sandy Springs-**Alpharetta** → **Roswell**). 코드 12060은 불변. (research.md §4.2)
- `geo_place_raw`를 남기는 이유: alias 수정 시 Stage B만 재실행하면 되므로 API 재호출 불필요.
- `geo_scope`를 두는 이유: 전국 기사가 Atlanta를 스쳐 언급한 건이 Atlanta 기저선을 오염시키는 것을 차단. (research.md §5.4)
- submarket 컬럼을 두지 **않는** 이유: submarket은 표준 어휘가 없어 §3.1의 제로섬 불안정성을 geo에 재도입한다. 해상도는 `geo_place_raw`로 확보하고 판단은 조회 계층에 위임. (research.md §4.3)

### 4.2 `collector.py` 수정 스니펫

⚠️ V1(헤더 정의 위치) 확인 후 실제 코드에 맞춰 적용.

```python
# collector.py

GEO_COLUMNS = [
    "geo_place_raw", "geo_cbsa_code", "geo_cbsa_title",
    "geo_state", "geo_scope", "geo_confidence", "geo_tagged_at",
]

COLUMNS = [
    "article_id", "collected_at", "published_at", "source", "title",
    "url", "summary", "classified", "category", "event_tags",
    "signal_type", "sector", "woomi_relevance", "claude_rationale",
    "access_limited", "korean_summary",
] + GEO_COLUMNS   # append-only. 순서 변경 금지 (I2)


def _blank_geo() -> dict:
    """신규 수집 기사는 geo 필드를 빈 값으로 생성. geo_tagger.py가 나중에 채운다."""
    return {c: "" for c in GEO_COLUMNS}
```

**⚠️ V2 위험**: `classifier.py`가 articles.csv를 전체 재작성한다면, 16컬럼만 쓰고 geo 컬럼을 날려버린다. 확인 결과가 "전체 재작성"이면 **I1(classifier 무수정)과 충돌**하므로, 그 경우 대안은:

- 대안 A: `geo_tagger.py`를 워크플로에서 classifier **뒤에** 배치 (매일 geo가 마지막에 채워짐). 단, classifier가 매일 전체 재작성하면 과거 geo도 날아가므로 매일 전량 재태깅이 필요 → 비효율.
- 대안 B (권장): geo를 **별도 파일 `geo_tags.csv`** (article_id + geo 7컬럼)로 분리하고, 조회 시 article_id로 조인. articles.csv 스키마를 아예 건드리지 않으므로 I1·I2를 완벽히 만족.

> **V2 확인 결과가 "전체 재작성"이면 대안 B로 전환한다.** 이 분기는 구현 착수 전에 반드시 확정할 것. 본 계획의 나머지 부분은 두 경우 모두 동일하게 적용된다.

---

## 5. Vocabulary 구성

### 5.1 크로스워크 빌드 스크립트

**경로:** `scripts/build_geo_crosswalk.py`

```python
"""
Census delineation 파일 → data/geo/cbsa_crosswalk.json 생성.
1회성 스크립트. vintage 갱신 시에만 재실행.

원본 파일은 수동 다운로드 후 data/geo/raw/ 에 커밋한다.
  https://www.census.gov/geographies/reference-files/time-series/
    demo/metro-micro/delineation-files.html
  - "Core based statistical areas (CBSAs), metropolitan divisions,
     and combined statistical areas (CSAs)"  → cbsa_delineation_2023.xlsx
  - "Principal cities of metropolitan and micropolitan statistical areas"
                                             → principal_cities_2023.xlsx
"""
import json, re, unicodedata
from pathlib import Path
import pandas as pd
import yaml

RAW = Path("data/geo/raw")
OUT = Path("data/geo/cbsa_crosswalk.json")
VINTAGE = "2023"           # OMB Bulletin 23-01 기준. 절대 혼용 금지.


def norm(s: str) -> str:
    """조회 키 정규화. 소문자, 악센트 제거, 구두점 제거, 공백 단일화."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[.'’,]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    # 접미사 제거
    s = re.sub(r"\s+(county|parish|borough|census area|city and borough)$", "", s)
    s = re.sub(r"^(city of|town of|village of)\s+", "", s)
    return s


def build():
    # --- 1) CBSA ↔ 카운티 ---------------------------------------------
    # ⚠️ 헤더 행 위치는 파일마다 다르다. 구현 시 실제 파일을 열어 확인할 것.
    #     (통상 상단 2~3행이 제목 행)
    d = pd.read_excel(RAW / f"cbsa_delineation_{VINTAGE}.xlsx", skiprows=2)
    d.columns = [norm(c).replace(" ", "_") for c in d.columns]

    cbsa = {}          # code -> {title, type, states, counties}
    county_idx = {}    # (norm_county, ST) -> [code, ...]

    for _, r in d.iterrows():
        code = str(r["cbsa_code"]).strip()
        if not code or code == "nan":
            continue
        code = code.split(".")[0].zfill(5)
        title = str(r["cbsa_title"]).strip()
        st = str(r.get("state_name", "")).strip()
        county = str(r.get("countycounty_equivalent", "")).strip()

        e = cbsa.setdefault(code, {
            "code": code, "title": title,
            "type": str(r.get("metropolitanmicropolitan_statistical_area", "")).strip(),
            "states": [], "counties": [],
        })
        st_abbr = STATE_ABBR.get(norm(st))
        if st_abbr and st_abbr not in e["states"]:
            e["states"].append(st_abbr)
        if county:
            e["counties"].append(county)
            if st_abbr:
                county_idx.setdefault(f"{norm(county)}|{st_abbr}", []).append(code)

    # --- 2) Principal cities → city 인덱스 ------------------------------
    p = pd.read_excel(RAW / f"principal_cities_{VINTAGE}.xlsx", skiprows=2)
    p.columns = [norm(c).replace(" ", "_") for c in p.columns]

    city_idx = {}      # (norm_city, ST) -> [code, ...]
    city_noState = {}  # norm_city -> [code, ...]   ← 모호성 판정용

    for _, r in p.iterrows():
        code = str(r["cbsa_code"]).split(".")[0].zfill(5)
        place = str(r.get("principal_city_name", "")).strip()
        if not place or code not in cbsa:
            continue
        # "Atlanta city, Georgia" 형태 → 도시명/주 분리
        m = re.match(r"^(.*?)\s+(city|town|village|cdp|borough)?,\s*(.+)$", place, re.I)
        name, state = (m.group(1), m.group(3)) if m else (place, "")
        st_abbr = STATE_ABBR.get(norm(state), "")
        n = norm(name)
        if st_abbr:
            city_idx.setdefault(f"{n}|{st_abbr}", []).append(code)
        city_noState.setdefault(n, []).append(code)

    # --- 3) CBSA 타이틀 자체를 인덱스에 추가 -----------------------------
    title_idx = {}
    for code, e in cbsa.items():
        # "Atlanta-Sandy Springs-Roswell, GA" → "atlanta-sandy springs-roswell"
        t = e["title"].rsplit(",", 1)[0]
        title_idx.setdefault(norm(t), []).append(code)
        # 첫 토큰도 인덱스 ("atlanta")
        first = norm(t.split("-")[0])
        city_noState.setdefault(first, []).append(code)

    # --- 4) 수작업 alias 병합 -------------------------------------------
    aliases = yaml.safe_load(Path("data/geo/geo_aliases.yaml").read_text(encoding="utf-8"))
    alias_idx = {}
    for section in ("universities", "legacy_titles", "submarkets", "colloquial"):
        for alias, code in (aliases.get(section) or {}).items():
            alias_idx[norm(alias)] = str(code).zfill(5)

    # --- 5) 중복 제거 후 저장 --------------------------------------------
    dedupe = lambda d: {k: sorted(set(v)) for k, v in d.items()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "vintage": VINTAGE,
        "source": "OMB Bulletin 23-01 / US Census Bureau delineation files",
        "built_at": pd.Timestamp.utcnow().isoformat(),
        "cbsa": cbsa,
        "county_idx": dedupe(county_idx),
        "city_idx": dedupe(city_idx),
        "city_noState": dedupe(city_noState),
        "title_idx": dedupe(title_idx),
        "alias_idx": alias_idx,
        "state_abbr": STATE_ABBR,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"CBSA {len(cbsa)} / city {len(city_idx)} / county {len(county_idx)} "
          f"/ alias {len(alias_idx)}")
    # ⚠️ 출력된 CBSA 개수를 문서의 수치와 대조할 것. 문서 수치를 코드에 하드코딩하지 않는다.


STATE_ABBR = {  # 전체 50개 주 + DC + PR. 구현 시 완성할 것.
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT",
    # ... (생략 — 구현 시 전량 기재)
    "georgia": "GA", "missouri": "MO", "south carolina": "SC",
}

if __name__ == "__main__":
    build()
```

### 5.2 `data/geo/geo_aliases.yaml` — 수작업 별칭 테이블

이 파일이 정확도를 좌우한다. 초기 시드 예시:

```yaml
# data/geo/geo_aliases.yaml
# alias(정규화 전 원문) -> CBSA 5자리 코드
# vintage 2023 (OMB Bulletin 23-01) 기준

universities:
  # Blue Vista 175개 대학 RSS 목록을 시드로 확장할 것 (V1 확인 후)
  "University of Missouri": "17860"
  "Mizzou": "17860"
  "Mizzou Tigers": "17860"
  "MU": "17860"            # ⚠️ 오탐 위험 — 대문자 2글자. 규칙에서 최소 길이 제한 검토
  "Georgia Tech": "12060"
  "Georgia State University": "12060"
  "Emory University": "12060"
  # 주의: University of Georgia(Athens-Clarke County, GA)는 Atlanta MSA가 아니다.
  #      Atlanta CSA에는 포함되나 CBSA는 별도. 코드는 빌드 산출물에서 확인 후 기입.

legacy_titles:
  # 구 vintage 명칭 → 현행 코드 (research.md §4.2)
  "Atlanta-Sandy Springs-Alpharetta": "12060"
  "Atlanta-Sandy Springs-Marietta": "12060"

submarkets:
  # 대형 메트로의 관용 지명. CBSA 코드로 흡수하되 원문은 geo_place_raw에 보존
  "Buckhead": "12060"
  "Midtown Atlanta": "12060"
  "Perimeter": "12060"
  "Sandy Springs": "12060"
  "Alpharetta": "12060"
  "Marietta": "12060"

colloquial:
  "Metro Atlanta": "12060"
  "CoMo": "17860"          # Columbia, MO 지역 통칭
  "Mid-Missouri": ""       # ⚠️ 의도적 공백 — Columbia/Jefferson City 양쪽. 미해결 처리

# 아래는 CBSA로 매핑하지 않고 scope=regional 처리 대상 (참조용, 코드 매핑 없음)
regional_terms_no_mapping:
  - "Sun Belt"
  - "Southeast"
  - "Midwest"
  - "Mountain West"
  - "Pacific Northwest"
```

### 5.3 Stage A 프롬프트 (전문 — 그대로 사용)

**경로:** `geo_tagger.py` 내 상수

```python
GEO_SYSTEM_PROMPT = """You are a geographic entity extractor for US real estate news.

Your ONLY task is to extract place names that appear in the given text. \
You do not classify, rate, summarize, or judge the article in any other way.

Return exactly one JSON object. No prose. No markdown code fences.

Schema:
{
  "places": [
    {
      "name":    "<place name copied verbatim from the text>",
      "state":   "<two-letter US state code, or null>",
      "type":    "city" | "county" | "metro" | "state" | "university" | "neighborhood" | "region",
      "primary": true | false
    }
  ],
  "scope": "national" | "regional" | "metro" | "local" | "none"
}

Rules:

1. VERBATIM ONLY. Extract only places written in the text. Copy "name" exactly as
   it appears. Do not normalize, expand, abbreviate, correct, or translate it.
   If the text says "Sandy Springs", return "Sandy Springs" - never "Atlanta".

2. NEVER INFER STATE. Fill "state" only when the two-letter code or the full state
   name appears in the text, or when the place string itself contains it
   ("Atlanta, GA" -> "GA"). If the text says only "Columbia", return null.
   Do not guess from context, from the publication, or from your own knowledge.

3. TYPE:
   - "university": a college or university name ("University of Missouri", "Mizzou")
   - "neighborhood": a sub-city area ("Buckhead", "Midtown")
   - "region": a multi-state or sub-national area ("Sun Belt", "Midwest")

4. PRIMARY: true for the place(s) where the reported event physically occurs.
   If the article is not about a specific location, every entry is false.

5. SCOPE:
   - "national": about the US market as a whole; any place named is an example
   - "regional": about a multi-state region, no specific site
   - "metro": about one metro area as a whole (a market report, a rent survey)
   - "local": about a specific project, site, building, or municipality
   - "none": no place identifiable

6. If no place appears: {"places": [], "scope": "none"}

7. Output nothing except the JSON object."""


GEO_FEWSHOT = [
    # (입력, 기대 출력) — 프롬프트 말미에 예시로 삽입
    (
        "Hillpointe breaks ground on 312-unit multifamily community in Cartersville, Georgia",
        '{"places":[{"name":"Cartersville","state":"GA","type":"city","primary":true}],'
        '"scope":"local"}'
    ),
    (
        "NMHC survey: apartment market conditions tighten nationwide; Atlanta and "
        "Dallas post the largest rent gains",
        '{"places":[{"name":"Atlanta","state":null,"type":"city","primary":false},'
        '{"name":"Dallas","state":null,"type":"city","primary":false}],'
        '"scope":"national"}'
    ),
    (
        "Developer files permit for 220-bed student housing project near campus in Columbia",
        '{"places":[{"name":"Columbia","state":null,"type":"city","primary":true}],'
        '"scope":"local"}'
    ),
    (
        "Blue Vista acquires student housing asset serving the University of Missouri",
        '{"places":[{"name":"University of Missouri","state":null,"type":"university",'
        '"primary":true}],"scope":"local"}'
    ),
]
```

**프롬프트 설계 근거**
- CBSA 목록을 넣지 않는다 → 토큰 최소화 + 긴 목록에서의 선택 정확도 저하 회피 (research.md §6 대안 A 기각)
- 기존 분류체계 용어를 전혀 쓰지 않는다 → I4
- "state는 절대 추론하지 말라"를 강하게 명시 → 3번째 few-shot(Columbia, state null)이 이 규칙을 강화. 모호성은 Stage B가 처리한다 (I8)
- `primary` 플래그로 "사건 발생지"와 "언급된 지역"을 구분 → scope와 함께 기저선 오염 차단

### 5.4 `geo_resolver.py` — Stage B (결정론적)

```python
"""Stage B: 원문 지명 → CBSA 코드. LLM 호출 없음. 100% 재현 가능."""
import json, re, unicodedata
from functools import lru_cache
from pathlib import Path

CROSSWALK = Path("data/geo/cbsa_crosswalk.json")
REGIONAL_TERMS = {"sun belt", "sunbelt", "southeast", "midwest", "northeast",
                  "mountain west", "pacific northwest", "west coast", "east coast"}


@lru_cache(maxsize=1)
def _xw():
    return json.loads(CROSSWALK.read_text(encoding="utf-8"))


def norm(s: str) -> str:
    """build_geo_crosswalk.py의 norm()과 반드시 동일해야 한다.
    ⚠️ 구현 시 공용 모듈로 추출하여 중복 정의를 피할 것."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[.'’,]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+(county|parish|borough|census area|city and borough)$", "", s)
    s = re.sub(r"^(city of|town of|village of)\s+", "", s)
    return s


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
    hit = xw["title_idx"].get(n)
    if hit:
        if st:
            hit = [c for c in hit if st in xw["cbsa"][c]["states"]] or hit
        return hit[:1], "exact" if st else "inferred"

    # 4) 주 없이 도시명만 — 전국 유일할 때만 채택
    hit = xw["city_noState"].get(n, [])
    if len(hit) == 1:
        return hit, "inferred"
    if len(hit) > 1:
        return [], "ambiguous"     # ⚠️ Columbia 문제. 추정하지 않는다 (I8)

    return [], "none"


def resolve(places: list[dict], scope: str) -> dict:
    """Stage A 출력 → geo_* 컬럼 값 dict."""
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

    # 전체 confidence = 가장 낮은 등급으로 보수적 판정
    order = ["exact", "inferred", "ambiguous", "none"]
    overall = "none"
    if codes:
        overall = min((c for c in confs if c in ("exact", "inferred")),
                      key=order.index, default="inferred")
    elif "ambiguous" in confs:
        overall = "ambiguous"

    return {
        "geo_place_raw":  "|".join(raws),
        "geo_cbsa_code":  "|".join(codes),
        "geo_cbsa_title": "|".join(titles),
        "geo_state":      "|".join(states),
        "geo_scope":      scope or "none",
        "geo_confidence": overall,
    }
```

### 5.5 `tests/test_geo_resolver.py` — 고정 케이스

```python
import pytest
from geo_resolver import resolve

def test_columbia_without_state_is_ambiguous():
    """Columbia MO / Columbia SC — 주 정보 없으면 추정하지 않는다 (I8)."""
    out = resolve([{"name": "Columbia", "state": None, "type": "city", "primary": True}], "local")
    assert out["geo_cbsa_code"] == ""
    assert out["geo_confidence"] == "ambiguous"
    assert out["geo_place_raw"] == "Columbia"   # 원문은 반드시 보존

def test_columbia_with_state_resolves():
    out = resolve([{"name": "Columbia", "state": "MO", "type": "city", "primary": True}], "local")
    assert out["geo_cbsa_code"] == "17860"
    assert out["geo_confidence"] == "exact"

def test_mizzou_alias():
    out = resolve([{"name": "Mizzou", "state": None, "type": "university", "primary": True}], "local")
    assert out["geo_cbsa_code"] == "17860"

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
```

---

## 6. `geo_tagger.py` — 실행 스크립트

```python
"""
Stage A(Batch API) + Stage B 오케스트레이션.

사용법:
  python geo_tagger.py --mode incremental     # geo_tagged_at 비어있는 건만 (일일 운영)
  python geo_tagger.py --mode backfill --limit 500
  python geo_tagger.py --mode resolve-only    # Stage A 재호출 없이 Stage B만 재실행

⚠️ 실행 전 반드시 `git pull --no-rebase` (CLAUDE.md 규칙)
⚠️ 동일 스크립트 중복 실행 금지 — Batch API에 중복 배치가 쌓인다 (CLAUDE.md 규칙)
"""
import argparse, json, os, sys, time
from datetime import datetime, timezone
import pandas as pd
from anthropic import Anthropic
from geo_resolver import resolve
from dotenv import load_dotenv

if sys.platform == "win32":                      # CLAUDE.md: Windows UTF-8 처리
    sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

MODEL = "claude-haiku-4-5-20251001"   # classifier(Sonnet 4.6)와 의도적으로 분리
CSV = "articles.csv"
GEO_COLS = ["geo_place_raw", "geo_cbsa_code", "geo_cbsa_title",
            "geo_state", "geo_scope", "geo_confidence", "geo_tagged_at"]


def _strip_fence(t: str) -> str:
    """CLAUDE.md 기록된 기존 버그 대응 — 코드펜스 제거."""
    t = t.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0]
    return t.strip()


def build_requests(df):
    from geo_tagger_prompts import GEO_SYSTEM_PROMPT, GEO_FEWSHOT   # 5.3 참조
    shots = "\n\n".join(f"TEXT:\n{i}\n\nJSON:\n{o}" for i, o in GEO_FEWSHOT)
    reqs = []
    for _, r in df.iterrows():
        text = f"{r.get('title','')}\n\n{r.get('summary','')}".strip()[:4000]
        reqs.append({
            "custom_id": str(r["article_id"]),
            "params": {
                "model": MODEL,
                "max_tokens": 600,
                "system": GEO_SYSTEM_PROMPT,
                "messages": [{"role": "user",
                              "content": f"{shots}\n\nTEXT:\n{text}\n\nJSON:"}],
            },
        })
    return reqs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["incremental", "backfill", "resolve-only"],
                    default="incremental")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    df = pd.read_csv(CSV, dtype=str).fillna("")
    for c in GEO_COLS:                       # 컬럼 없으면 생성 (최초 1회)
        if c not in df.columns:
            df[c] = ""

    # ---- resolve-only: Stage A 재호출 없이 Stage B만 -------------------
    if a.mode == "resolve-only":
        raw_col = "geo_stage_a_json"         # Stage A 원본 보관 (아래 참조)
        # 구현 노트: Stage A 원본 JSON을 data/geo/stage_a/{article_id}.json 으로
        #            보관하면 재매핑이 자유롭다. CSV를 비대화시키지 않는 편이 낫다.
        ...
        return

    todo = df[df["geo_tagged_at"] == ""]
    if a.mode == "backfill" and a.limit:
        todo = todo.head(a.limit)
    print(f"대상 {len(todo)}건 / 전체 {len(df)}건")
    if a.dry_run or todo.empty:
        return

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    batch = client.messages.batches.create(requests=build_requests(todo))
    print("batch:", batch.id)

    while True:                              # 폴링
        b = client.messages.batches.retrieve(batch.id)
        if b.processing_status == "ended":
            break
        print("  ...", b.processing_status, flush=True)
        time.sleep(30)

    ok = fail = 0
    idx = df.set_index("article_id")
    stage_a_dir = __import__("pathlib").Path("data/geo/stage_a")
    stage_a_dir.mkdir(parents=True, exist_ok=True)

    for res in client.messages.batches.results(batch.id):
        aid = res.custom_id
        try:
            raw = _strip_fence(res.result.message.content[0].text)
            parsed = json.loads(raw)
            (stage_a_dir / f"{aid}.json").write_text(raw, encoding="utf-8")  # 원본 보존
            vals = resolve(parsed.get("places", []), parsed.get("scope", "none"))
            vals["geo_tagged_at"] = datetime.now(timezone.utc).isoformat()
            for k, v in vals.items():
                idx.at[aid, k] = v
            ok += 1
        except Exception as e:
            print(f"  FAIL {aid}: {e}")
            fail += 1

    df = idx.reset_index()[list(df.columns)]   # 컬럼 순서 보존 (I2)
    df.to_csv(CSV, index=False, encoding="utf-8")
    print(f"완료: 성공 {ok} / 실패 {fail}")

    # 분포 출력 — 눈으로 검수
    print(df["geo_confidence"].value_counts())
    print(df["geo_scope"].value_counts())
    print(df[df.geo_cbsa_code != ""]["geo_cbsa_title"].str.split("|").explode()
            .value_counts().head(25))


if __name__ == "__main__":
    main()
```

**⚠️ 구현 노트:** `--limit` 소량(50건)으로 먼저 돌려 출력 분포를 육안 검수한 뒤 전량을 돌린다. CLAUDE.md의 "동일 스크립트 중복 실행 금지" 규칙을 지킬 것.

---

## 7. `baseline.py` — 기저선 산출

```python
"""CBSA별 기저선 산출 → geo_index.json. IC Helper가 소비한다."""
import json
import pandas as pd

WINDOW_DAYS   = 180    # 실제 데이터 범위로 자동 축소됨
RECENT_WEEKS  = 4
MIN_N         = 12     # 커버리지 임계치 — Phase 0 §1.3 실측 후 조정 (research.md §5.2)
COUNT_SCOPES  = {"metro", "local"}   # national/regional 배제 (research.md §5.4)


def build(csv="articles.csv", out="geo_index.json"):
    d = pd.read_csv(csv, dtype=str).fillna("")
    d["dt"] = pd.to_datetime(d["published_at"], errors="coerce", utc=True)
    d = d.dropna(subset=["dt"])
    d = d[d["geo_scope"].isin(COUNT_SCOPES) & (d["geo_cbsa_code"] != "")]

    end = d["dt"].max()
    start = max(d["dt"].min(), end - pd.Timedelta(days=WINDOW_DAYS))
    win = d[d["dt"] >= start]
    weeks = max((end - start).days / 7, 1)
    recent = win[win["dt"] >= end - pd.Timedelta(weeks=RECENT_WEEKS)]

    ex = win.assign(code=win["geo_cbsa_code"].str.split("|")).explode("code")
    rx = recent.assign(code=recent["geo_cbsa_code"].str.split("|")).explode("code")

    idx = {}
    for code, g in ex.groupby("code"):
        n = len(g)
        r = len(rx[rx["code"] == code])
        base_wk = n / weeks
        idx[code] = {
            "cbsa_title":    g["geo_cbsa_title"].str.split("|").explode().mode().iloc[0],
            "n_window":      int(n),
            "window_days":   int((end - start).days),
            "baseline_weekly": round(base_wk, 2),
            "recent_4w":     int(r),
            "recent_weekly": round(r / RECENT_WEEKS, 2),
            "ratio":         round((r / RECENT_WEEKS) / base_wk, 2) if base_wk else None,
            # ⚠️ 커버리지 부족 시 ratio를 신뢰하지 말 것. 소표본에서 비율은 폭주한다.
            "coverage":      "sufficient" if n >= MIN_N else "insufficient",
            "warning":       None if n >= MIN_N else
                             f"커버리지 부족 (관측창 {int((end-start).days)}일 내 {n}건). "
                             f"판단 근거로 사용 불가.",
            "supply_events": {
                t: int(g["event_tags"].str.contains(t).sum())
                for t in ("permit", "land_acquisition", "construction_start", "delivery")
            },
        }

    payload = {
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "window_start": start.isoformat(),
        "window_end":   end.isoformat(),
        "min_n":        MIN_N,
        "note": "national/regional scope 기사는 집계에서 제외됨",
        "cbsa": idx,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"CBSA {len(idx)}개 / 커버리지 충분 "
          f"{sum(1 for v in idx.values() if v['coverage']=='sufficient')}개")


if __name__ == "__main__":
    build()
```

---

## 8. 회귀 검증

**경로:** `scripts/snapshot_regression.py`

```python
"""geo 작업이 기존 분류에 영향을 주지 않았음을 입증한다 (research.md §3.4a).

  python scripts/snapshot_regression.py save    # 작업 전
  python scripts/snapshot_regression.py verify  # 작업 후 → 반드시 0 diff
"""
import hashlib, json, sys
import pandas as pd

SNAP = "tests/regression_snapshot.json"
COLS = ["category", "event_tags", "signal_type", "sector", "woomi_relevance"]


def fingerprint(csv="articles.csv"):
    d = pd.read_csv(csv, dtype=str).fillna("")
    d = d.sort_values("article_id").head(300)     # 고정 샘플
    return {r["article_id"]:
            hashlib.sha256("|".join(r[c] for c in COLS).encode()).hexdigest()[:16]
            for _, r in d.iterrows()}


if __name__ == "__main__":
    if sys.argv[1] == "save":
        json.dump(fingerprint(), open(SNAP, "w"), indent=1)
        print("스냅샷 저장 완료")
    else:
        old, new = json.load(open(SNAP)), fingerprint()
        diff = [k for k in old if old.get(k) != new.get(k)]
        print(f"검사 {len(old)}건 / 변경 {len(diff)}건")
        if diff:
            print("⚠️ 분류 오염 발생:", diff[:10])
            sys.exit(1)
        print("✅ 변화율 0% — 기존 분류 무영향 확인")
```

**이 출력은 공모전 제안서의 "시스템 구현도" 근거로 캡처해둘 것.**

---

## 9. GitHub Actions 수정

```yaml
# .github/workflows/[daily].yml — classify 단계 뒤에 삽입
      - name: Geo tagging
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python geo_tagger.py --mode incremental

      - name: Rebuild geo index
        run: python baseline.py
```

**⚠️ 순서 중요:** collect → classify → geo_tag → baseline → commit.
**⚠️ V2 확인 결과가 "classifier가 CSV 전체 재작성"이면 §4.2 대안 B(별도 파일)로 전환.**

---

## 10. 트레이드오프 정리

| 결정 | 채택안 | 포기한 것 | 대가 |
|---|---|---|---|
| 어휘 주입 방식 | 2단계 (LLM 추출 + Python 조회) | 프롬프트 vocabulary 주입 | 크로스워크 구축 초기 공수 |
| 저장 키 | CBSA 코드 | 명칭 | 사람이 CSV를 눈으로 읽기 불편 (title 병기로 완화) |
| 해상도 | MSA + 원문 지명 보존 | submarket 태깅 | Atlanta 내부 비교는 조회 계층에서 별도 구현 필요 |
| 모호성 | 미해결 처리 | 최선 추정 | Columbia 등 일부 기사가 기저선에서 누락 |
| 모델 | Haiku 4.5 | Sonnet 4.6 | 복잡한 문맥 지명 추출에서 정확도 소폭 손실 가능 — 50건 샘플로 검증 |
| CSV 스키마 | 컬럼 추가 | 별도 파일 분리 | "스키마 변경 금지" 자체 규칙 갱신 필요 (V2 결과에 따라 역전 가능) |
| UI 노출 | 미노출 | geo 필터 | 공모전 데모에서 The Brief 단독 화면으로는 geo가 안 보임 → IC Helper 화면으로 시연 |

---

## 11. 롤백 계획

| 실패 시나리오 | 감지 | 롤백 |
|---|---|---|
| 컬럼 추가로 index.html 깨짐 | 배포 후 화면 확인 | `git revert` — CSV는 컬럼만 늘어난 상태이므로 무해 |
| classifier가 geo 컬럼 삭제 | 다음날 geo 열 전부 공백 | §4.2 대안 B(별도 파일)로 전환 |
| 회귀 테스트 실패 | `verify` 종료코드 1 | geo_tagger 즉시 중단, 원인 규명 전까지 재실행 금지 |
| CSV 손상 | 행 수 급감 | `backup/pre-geo-20260824` 브랜치에서 복구 |
| Batch 중복 제출 | Anthropic 콘솔에서 배치 다수 확인 | 중복 배치 취소, 스크립트 단일 실행 |

---

## 12. To-Do (승인 후 순차 실행)

### Phase 0 — 오늘 (승인 불필요)
- [ ] 0-1. 보관기간 730일로 연장 후 push
- [ ] 0-2. `backup/pre-geo-20260824` 브랜치 생성·push
- [ ] 0-3. §1.3 실측 스크립트 실행, 결과 기록
- [ ] 0-4. V1~V9 코드 확인, research.md §2.3 표 채우기
- [ ] 0-5. **V2 결과에 따라 스키마 방식 확정 (컬럼 추가 vs 별도 파일)**

### Phase 1 — 어휘체계 (1주차)
- [ ] 1-1. Census delineation·principal cities 파일 수동 다운로드 → `data/geo/raw/` 커밋
- [ ] 1-2. `scripts/build_geo_crosswalk.py` 작성·실행, CBSA 개수 검증
- [ ] 1-3. `geo_aliases.yaml` 작성 — Blue Vista 175개 대학 목록을 시드로 확장
- [ ] 1-4. `geo_resolver.py` + `tests/test_geo_resolver.py` 작성, 전 케이스 통과

### Phase 2 — 태깅 (2주차)
- [ ] 2-1. `scripts/snapshot_regression.py save` 실행
- [ ] 2-2. `geo_tagger.py` 작성
- [ ] 2-3. `--mode backfill --limit 50` 실행 → **육안 검수** → 프롬프트/alias 보정
- [ ] 2-4. 전량 백필 실행 (단일 실행, 중복 금지)
- [ ] 2-5. `scripts/snapshot_regression.py verify` → 0 diff 확인·캡처
- [ ] 2-6. `baseline.py` 작성·실행, Atlanta·Columbia MO 결과 확인
- [ ] 2-7. GitHub Actions에 geo 단계 추가, 익일 자동 실행 정상 확인
- [ ] 2-8. `CLAUDE.md` 갱신 (스키마, 신규 파일, 실행 규칙)

### Phase 3 — IC Helper 연동 (3주차 이후)
- [ ] 별도 Plan 문서로 분리. 본 문서 범위 밖.

---

## 13. 검토 요청 사항 (사용자 확인 필요)

아래는 판단이 필요한 항목이다. 에디터에서 이 문서에 직접 주석을 달아 회신할 것.

| # | 항목 | 초안 | 확인 필요 |
|---|---|---|---|
| R1 | 보관기간 730일 | 730 | 무제한이 나은지, CSV 크기 우려가 있는지 |
| R2 | 백필 범위 | 전량 5,442건 | 우선순위 부분집합으로 축소할지 |
| R3 | 커버리지 임계치 MIN_N | 12건 | Phase 0 실측 후 재결정 |
| R4 | Stage A 모델 | Haiku 4.5 | 50건 샘플 검증 후 Sonnet 승격 여부 |
| R5 | 대학 alias 범위 | Blue Vista 175개 전량 | 딜 관련 대학 위주로 축소할지 |
| R6 | `geo_scope=national` 처리 | 기저선에서 배제 | 별도 "전국 동향" 지표로 활용할지 |

---

## 14. 문서 이력

| 버전 | 일자 | 내용 |
|---|---|---|
| v0.1 | 2026-08-24 | 초안. V1~V9 미확인 상태에서 작성. §4.2 대안 B 분기 미확정 |
