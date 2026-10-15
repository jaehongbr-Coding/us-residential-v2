# Plan_market.md — The Brief 시장 데이터 풀 + 시장 맥락 판정 구현 계획

> 버전 v0.5 (2026-10-15) · 근거: `research_market.md` v0.1 + Phase 0·1 실측 + **2026-10-15 저장소 구조 조사** · 선행: `CLAUDE.md` (현 구조 정본)
> **v0.5: Phase 0~4 완료. 실측 확정값과 코드 동기화.** §4.1 코드 블록은 커밋된 market_collect.py와 동일, §4.2·§4.3은 상수·로직이 동일하다 — 불일치 시 코드가 정본.
> ⚠️ v0.4 핵심: v0.1~v0.3이 가정한 `geo_tags.csv`·`articles.csv` 기사 우주가 **틀렸음**. 실제는 원장 `archive/*.csv` 10,249건 + 렌즈 SQLite 3개(`labels.db`·`geo_tags.db`·`seen_index.db`) + 조인 산출물 `archive_index.json`. geo는 **완료 상태**(7,099→10,249건 백필, Haiku). Phase 2·3·4를 실제 구조에 맞춰 재작성.
> ⚠️ v0.2 핵심 변경: BPS 월간 파일에 보고분/대체추정 분리가 **없음**이 확인됨 → `rep_share` 기반 unknown 규칙을 **물량 하한(volume floor)** 으로 교체. 열 위치 고정 → 헤더명 탐색으로 교체. SOC 파서 확정.
> §9 미해결 질문은 전부 기본안으로 확정 (Q1 3년 / Q2 70% / Q3 전수 / Q4 유지 / Q5 Phase 2 / Q6 별도 / Q7 별도 워크플로)
> 구현 원칙: **단계별 독립 커밋, 각 단계 후 검증·보고 후 진행.** 이 문서 승인 전 구현 금지.

---

## 0. 불변조건 — geo Plan.md I1~I8 전부 계승 + 추가

| # | 불변조건 | 이유 |
|---|---|---|
| I1~I8 | geo Plan.md §0 그대로 적용 | — |
| M1 | `woomi_relevance`와 market flag를 **합산한 단일 점수를 어디에도 만들지 않는다** (CSV·JSON·화면 전부) | 근거 은닉 방지 (research_market §3.1) |
| M2 | `market_rules.py`의 규칙은 **6개를 넘기지 않는다.** 7번째를 넣으려면 하나를 빼고 문서 이력에 사유를 남긴다 | IC Helper flag_rules 교훈 |
| M3 | 모든 판정 행에 `rule_version`을 남긴다 | 규칙 변경 후 과거 행 재해석 |
| M4 | 규칙 입력은 `data/market/` 커밋 파일만. **런타임 네트워크 호출 금지** (수집은 전용 워크플로에서만) | I7 계승 |
| M5 | 기사 건수(뉴스량)를 공급 판정 입력으로 쓰지 않는다 | 프록시 방향 불일치 |
| M6 | 3년 평균 물량이 하한 미만이면 ratio를 산출하되 판정은 `unknown` (ratio는 노이즈) | 원칙 ② |
| M7 | `articles.csv`, `archive/`, `classifier.py`, `collector.py`, `geo_*.py`, `label_store.py`, `archive_manager.py`를 수정하지 않는다. **예외: `build_archive_index.py`는 market 조인 1곳만 추가** | 원장·렌즈 분리 |
| M8 | market 렌즈는 저장소 관례(labels.db·geo_tags.db)를 따라 **SQLite 사이드카 `market_flags.db`** + `market_store.py`. `.gitattributes`에 `binary merge=ours` 선언 | 기존 충돌 복구 경로 재사용 |

---

## 1. 아키텍처 (v0.4 — 실제 구조 기준)

```
┌─ 수집 (월 1회, monthly_market.yml) — Phase 1 완료 ─────────────────┐
│  market_collect.py → data/market/raw/*.xls, bps_cbsa.csv(48,258행), │
│                      soc_lag.csv(1,375행), bps_anomalies.csv        │
└─────────────────────────────────────────────────────────────────────┘
                              │
┌─ 판정 (일 1회, daily_collect.yml: geo 뒤·build_archive_index 앞) ───┐
│  market_tagger.py                                                   │
│    archive_manager.read_archive()  ─ article_id, published_at       │
│    geo_store.get_geo()             ─ geo_cbsa_code|scope|confidence │
│    data/market/{bps_cbsa,soc_lag,state_region}.csv                  │
│         │                                                           │
│         ├─ market_context.compute()  (순수)                         │
│         └─ market_rules.judge()      (규칙 ≤6)                      │
│                    │                                                │
│         ┌──────────┴──────────────┐                                 │
│         ▼                         ▼                                 │
│  market_flags.db (렌즈, SQLite)   data/market/context_latest.json   │
│  PK (article_id, cbsa_code, rule_version)                           │
└─────────────────────────────────────────────────────────────────────┘
                              │
┌─ 조인 (build_archive_index.py, 기존) ─────────────────────────────┐
│  archive × labels.db × geo_tags.db × **market_flags.db**(추가)      │
│  → archive_index.json  records[].mk = [[cbsa, flags, ratio, cov]]  │
└─────────────────────────────────────────────────────────────────────┘
                              │
┌─ 화면 (index.html, 정적) ─────────────────────────────────────────┐
│  아카이브 카드: rel 칩 옆에 mk 칩 ("높음" · "공급 감소 · ATL")       │
│  마켓워치 섹션(신규): context_latest.json → Chart.js (재도입)        │
└─────────────────────────────────────────────────────────────────────┘
```

**실측 전제 (2026-10-15 조사)**
- 원장 `archive/2024-09.csv` ~ `2026-10.csv` 26파일 10,249행, article_id 중복 0. published_at 2024-09-11~2026-10-14, collected_at 2026-06-08~
- `geo_tags.db` 10,249행. `geo_cbsa_code` 비어있지 않음 5,185행, 다중(`|`) 90행. confidence 6종: exact 2,338 / inferred 2,757 / source_inferred 90 / state 309 / ambiguous 239 / none 4,516. scope 6종: local 7,259 / metro 131 / national 419 / regional 120 / state 309 / none 2,011
- 관심 7 CBSA 기사 수 (scope metro|local): ATL 126 / DFW 175 / LA 388 / SEA 163 / DEN 83 / PHX 166 / Columbia MO 20
- `labels.db`가 `woomi_relevance` 정본 (낮음 6,627 / 보통 2,107 / 높음 1,515). articles.csv는 조인 뷰
- `index.html`에 트렌드 차트·Chart.js 참조 **없음** (ac2afbb에서 삭제). 마켓워치는 신규 섹션
- BPS 2019-11 시작 → 48개월 창은 as_of ≥ 2023-11. 원장 최초 기사 2024-09 → as_of 2024-07 → **전 기사 판정 가능**

**push와 pull이 같은 함수:** `market_context.compute()`를 tagger가 기사별로 호출하고, 같은 실행 끝에 전 CBSA를 JSON으로 덤프. 화면은 읽기만.

## 2. 파일 변경 계획

### 2.1 신규

| 경로 | 종류 | 역할 | 상태 |
|---|---|---|---|
| `market_collect.py` | 실행 | BPS/SOC 수집 | **완료** (Phase 1) |
| `data/market/raw/`, `bps_cbsa.csv`, `bps_download_log.csv`, `bps_anomalies.csv`, `soc_lag.csv`, `state_region.csv` | 데이터 | 원장 | **완료** |
| `.github/workflows/monthly_market.yml` | 워크플로 | 월 1회 수집 | **완료** (tagger 스텝은 Phase 3) |
| `market_context.py` | 모듈 (순수) | CBSA×시점 → 시장 상태 | Phase 2 |
| `market_rules.py` | 모듈 (순수) | 상태 → flag 목록 | Phase 2 |
| `market_store.py` | 모듈 | `market_flags.db` 접근. `geo_store.py` 패턴 복제 | Phase 3 |
| `market_tagger.py` | 실행 | archive × geo × context → market_flags.db + context_latest.json | Phase 2(context) / 3(태깅) |
| `market_flags.db` | 데이터 (루트) | 렌즈. SQLite 사이드카 | Phase 3 |
| `data/market/context_latest.json` | 데이터 | 전 CBSA 최신 context (화면용) | Phase 2 |
| `tests/test_market_context.py`, `tests/test_market_rules.py`, `tests/test_market_store.py` | 테스트 | | Phase 2·3 |

### 2.2 기존 수정 (최소)

| 경로 | 변경 | Phase |
|---|---|---|
| `build_archive_index.py` | records에 `mk` 필드 추가 (`market_store.get_flags` 조인). `filters`에 `market_flags` 값 목록 추가 | 3 |
| `daily_collect.yml` | `Geo tagging` 뒤·`Build archive index` 앞에 `Market tagging` 스텝. git add에 `market_flags.db data/market/context_latest.json` | 3 |
| `monthly_market.yml` | soc 뒤에 `python market_tagger.py --mode context-only` 스텝 | 2 |
| `.gitattributes` | `market_flags.db binary merge=ours` | 3 |
| `index.html` | (a) 아카이브 카드에 mk 칩 (b) 마켓워치 섹션 신규 + Chart.js CDN 재도입 | 4 |
| `CLAUDE.md` | 시장 데이터 풀 섹션 추가, 데이터 현황 표 갱신(10,249) | 5 |

## 3. 데이터 스키마

### 3.1 `data/market/bps_cbsa.csv` (원장)

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `period` | `YYYY-MM` | 파일 행3 열0의 YYYYMM (파일 단위) |
| `cbsa_code` | str 5자리 | 조인 키 |
| `cbsa_name` | str | 파일 표기 그대로 (vintage 추적용, 조인에 쓰지 않음) |
| `metro_micro` | str | 2024+ 파일의 `Metro /Micro Code` 원값. 2023 이전은 빈값 |
| `u1_units` | int | 1 Unit (Current Month) |
| `u5_units` | int | **5 Units or More (Current Month)** — 핵심 지표 |
| `u5_structures` | int | Num of Structures With 5 Units or More (Current Month) |
| `u5_units_ytd` | int | 5 Units or More (Year to Date) — 무결성 검증용 |
| `u5_value_k` | int | 'MSA Value' 시트의 5 Units or More (Current Month), $천 |
| `source_file` | str | `cbsamonthly_202608.xls` |
| `parsed_at` | ISO8601 | |

- **보고분(rep) 열은 존재하지 않는다** (Phase 0 실측). 2004 샘플과 다름
- 2~4유닛 저장 안 함. 원본 xls는 raw/에 보관
- UNIQUE: (`period`, `cbsa_code`). 재파싱 시 스킵
- 커버리지 **[Phase 1 실측]**: 2019-11~2021-12 **368행**, 2022-01~2023-12 **384행**, 2024-01+ **921행**(2026-04·05만 922). Micro는 2027-01 전까지 3년 기저선 불가 → `no_data`로 자연 처리. 총 82파일 48,258행
- 시트명이 연도별로 다름 **[Phase 1 실측]**: 2019-11~12 `Units`/`Valuation`, 2020-01~2023-12 및 2024-02+ `MSA Units`/`MSA Value`, 2024-01만 `CBSA Units`/`CBSA Value` → `_pick_sheet()`가 이름 끝부분으로 선택. 헤더 행·컬럼명은 전 기간 동일
- 무결성 정책 **[v0.3 확정]**: 1월 파일은 `u5_units == u5_units_ytd`, 그 외 `u5_units ≤ u5_units_ytd`. 위반이 **전체 행의 1% 초과면 파서 오류로 raise**, 이하면 **원본 그대로 저장 + `bps_anomalies.csv` 기록**. 실측: 2026-05 파일 2행(Adrian MI 5>0, Kenosha WI 11>10)만 해당. 원장은 Census가 낸 값을 바꾸지 않는다
- 2019-11~2021-12 파일에만 `Monthly Coverage Percent*` 열 존재 **[Phase 1 실측]** — 저장하지 않음. 2022 cutoff sample 전환으로 사라진 보고 커버리지 지표로 추정 [추정]. §8 C6

### 3.2 `data/market/soc_lag.csv`

| 컬럼 | 설명 |
|---|---|
| `year` | 참조연도 |
| `region` | `US` / `Northeast` / `Midwest` / `South` / `West` |
| `unit_bucket` | `2-4` / `5-9` / `10-19` / `20+` / `2+` |
| `months_auth_to_start` | float |
| `months_start_to_comp` | float |
| `months_auth_to_comp` | float = 합 |

### 3.3 `data/market/state_region.csv` (정적, 커밋)

`state,region` 51행. Census Region 정의 [학습지식 — 구현 시 census.gov/geographies/reference-maps/2010/geo/2010-census-regions-and-divisions-of-the-united-states.html 대조]
- Northeast: CT ME MA NH RI VT NJ NY PA
- Midwest: IL IN MI OH WI IA KS MN MO NE ND SD
- South: DE DC FL GA MD NC SC VA WV AL KY MS TN AR LA OK TX
- West: AZ CO ID MT NV NM UT WY AK CA HI OR WA

### 3.4 `market_flags.db` (렌즈, 루트, SQLite) — v0.4

```sql
CREATE TABLE IF NOT EXISTS market_flags (
    article_id       TEXT NOT NULL,
    cbsa_code        TEXT NOT NULL,      -- geo_cbsa_code를 '|'로 분리한 각각. 기사 1건이 CBSA 2개면 2행
    rule_version     TEXT NOT NULL,
    as_of            TEXT,               -- YYYY-MM. published_at − 2개월 (BPS 공표 지연)
    coverage         TEXT,               -- ok | low_volume | no_data | not_applicable
    units_12m        INTEGER,
    units_avg3y      REAL,
    ratio_12m_vs_3y  REAL,
    flags            TEXT,               -- '|' 구분. 빈 문자열 가능
    tagged_at        TEXT,
    PRIMARY KEY (article_id, cbsa_code, rule_version)
);
CREATE INDEX IF NOT EXISTS idx_mf_cbsa  ON market_flags(cbsa_code);
CREATE INDEX IF NOT EXISTS idx_mf_flags ON market_flags(flags);
```

- **적용 조건**: `geo_cbsa_code` 비어있지 않음 AND `geo_scope ∈ {metro, local}` AND `geo_confidence ∈ {exact, inferred, source_inferred}`. 그 외 CBSA가 있어도 `coverage=not_applicable`, flags 빈값으로 **행은 남긴다** (왜 판정 안 했는지 추적)
- `geo_cbsa_code` 빈값 → 행 없음
- 멱등 키에 `rule_version` 포함 → 규칙 상향 시 전 기사 자동 재태깅, 과거 행 보존 (M3)
- `market_store.py` 함수: `open_market()`, `get_flags(conn, article_ids) -> {aid: [row…]}`, `upsert_flag(conn, row)`, `count_flags(conn)`, `tagged_keys(conn, rule_version) -> set[(aid, cbsa)]`

### 3.5 `data/market/context_latest.json`

```json
{
  "generated_at": "2026-10-15T06:10:00Z",
  "as_of": "2026-08",
  "rule_version": "v1",
  "cbsa": {
    "12060": {
      "name": "Atlanta-Sandy Springs-Roswell GA",
      "region": "South",
      "coverage": "ok",
      "units_12m": 9120, "units_avg3y": 14830, "ratio_12m_vs_3y": 0.615,
      "flags": ["supply_drought"],
      "monthly": [{"period":"2023-09","u5_units":1240}, "... 36개"],
      "article_counts": {"total": 126, "flagged": 98},
      "expected_completion": {"lag_months": 17.5, "bucket": "20+", "by_quarter": {"2027Q4": 2310, "2028Q1": 1980, "2028Q2": 1750, "2028Q3": 2100}}
    }
  }
}
```

- 전 CBSA 포함 (Q3 전수). 약 920 × 36개월 ≈ 1.5MB. 화면은 관심 목록만 그린다
- `article_counts`는 market_flags.db 집계 (scope metro|local 기사 수 / coverage ok 수). Phase 3 전에는 생략
- `expected_completion`은 **추정**. 화면에 "SOC 지역 평균 lag 적용, 미착공·취소 미반영" 고정 문구

---

## 4. 코드

### 4.1 `market_collect.py`

```python
"""BPS(월간 CBSA 허가)·SOC(소요기간) 수집. monthly_market.yml 전용.
런타임(tagger·화면)은 이 스크립트의 산출 파일만 읽는다 (M4).
레이아웃은 Phase 0 진단(2026-10-15) 실측 기준."""
from __future__ import annotations
import csv, hashlib, re, sys, time
from datetime import date, datetime, timezone
from pathlib import Path
import pandas as pd
import requests

RAW_DIR   = Path("data/market/raw")
BPS_CSV   = Path("data/market/bps_cbsa.csv")
LOG_CSV   = Path("data/market/bps_download_log.csv")
SOC_CSV   = Path("data/market/soc_lag.csv")
ANOM_CSV  = Path("data/market/bps_anomalies.csv")
BPS_BASE  = "https://www.census.gov/construction/bps/xls/"
SOC_URLS  = {
    "auth_to_start": "https://www.census.gov/construction/nrc/xls/avg_authtostart_cust.xlsx",
    "start_to_comp": "https://www.census.gov/construction/nrc/xls/avg_starttocomp_cust.xlsx",
}
HEADERS   = {"User-Agent": "Mozilla/5.0 (compatible; WoomiGlobalResearchBot/2.0)"}
BPS_START = (2019, 11)
BPS_COLS  = ["period","cbsa_code","cbsa_name","metro_micro","u1_units","u5_units",
             "u5_structures","u5_units_ytd","u5_value_k","source_file","parsed_at"]

# 헤더명 (행7). 2024+는 'Metro /Micro Code' 열이 끼어들어 위치가 밀리므로 이름으로 찾는다.
# 같은 이름이 Current Month / Year to Date 두 블록에 나오므로 first/second 를 구분한다.
H_CBSA  = "CBSA"
H_NAME  = "Name"
H_MM    = "Metro /Micro Code"
H_U1    = "1 Unit"
H_U5    = "5 Units or More"
H_U5S   = "Num of Structures With 5 Units or More"


def bps_filename(y: int, m: int) -> str:
    return (f"cbsamonthly_{y}{m:02d}.xls" if (y, m) >= (2024, 1)
            else f"msamonthly_{y}{m:02d}.xls")


def months(start, end):
    y, m = start
    while (y, m) <= end:
        yield y, m
        m += 1
        if m == 13: y, m = y + 1, 1


def download(url: str, dest: Path) -> bool:
    if dest.exists():
        return True
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code == 404:
        print(f"  [SKIP] 404 {url}")
        return False
    r.raise_for_status()
    dest.write_bytes(r.content)
    time.sleep(1.0)
    return True


def _find_period(raw: pd.DataFrame) -> str:
    """행 0~6 중 열0이 6자리 숫자인 셀 → 'YYYY-MM'."""
    for i in range(min(8, len(raw))):
        v = str(raw.iat[i, 0]).strip().replace(".0", "")
        if re.fullmatch(r"\d{6}", v):
            return f"{v[:4]}-{v[4:]}"
    raise ValueError("period(YYYYMM) 셀을 찾지 못함")


def _header_row(raw: pd.DataFrame) -> int:
    for i in range(min(12, len(raw))):
        if str(raw.iat[i, 1]).strip() == H_CBSA:
            return i
    raise ValueError("헤더 행(열1 == 'CBSA')을 찾지 못함")


def _col_idx(header: list[str], label: str, nth: int = 0) -> int:
    hits = [i for i, h in enumerate(header) if h == label]
    if len(hits) <= nth:
        raise ValueError(f"헤더 '{label}' {nth+1}번째 없음. 헤더={header}")
    return hits[nth]


def _sheet_table(raw: pd.DataFrame):
    h = _header_row(raw)
    header = [str(x).strip() for x in raw.iloc[h].tolist()]
    body = raw.iloc[h + 1:].copy()
    cbsa_i = _col_idx(header, H_CBSA)
    body = body[body.iloc[:, cbsa_i].astype(str).str.strip().str.fullmatch(r"\d{5}(\.0)?")]
    return header, body


def _pick_sheet(names: list[str], suffixes: tuple[str, ...]) -> str:
    """시트명이 연도별로 다르다 (1.3 백필 실측): 2019-11~12 'Units'/'Valuation',
    2020-01~2023-12·2024-02+ 'MSA Units'/'MSA Value', 2024-01 'CBSA Units'/'CBSA Value'."""
    hits = [n for n in names if n.strip().endswith(suffixes)]
    if len(hits) != 1:
        raise ValueError(f"시트 {suffixes} 후보 {hits} (전체 {names})")
    return hits[0]


def parse_bps(path: Path) -> pd.DataFrame:
    x = pd.ExcelFile(path, engine="xlrd")
    units = x.parse(_pick_sheet(x.sheet_names, ("Units",)), header=None)
    value = x.parse(_pick_sheet(x.sheet_names, ("Value", "Valuation")), header=None)
    period = _find_period(units)

    hu, bu = _sheet_table(units)
    hv, bv = _sheet_table(value)
    g = lambda b, h, lab, nth=0: pd.to_numeric(b.iloc[:, _col_idx(h, lab, nth)], errors="coerce")
    code = lambda b, h: b.iloc[:, _col_idx(h, H_CBSA)].astype(str).str.extract(r"(\d{5})")[0]

    u = pd.DataFrame({
        "cbsa_code":     code(bu, hu),
        "cbsa_name":     bu.iloc[:, _col_idx(hu, H_NAME)].astype(str).str.strip(),
        "metro_micro":   (bu.iloc[:, _col_idx(hu, H_MM)].astype(str).str.replace(".0","",regex=False).str.strip()
                          if H_MM in hu else ""),
        "u1_units":      g(bu, hu, H_U1, 0).fillna(0).astype(int),
        "u5_units":      g(bu, hu, H_U5, 0).fillna(0).astype(int),
        "u5_structures": g(bu, hu, H_U5S, 0).fillna(0).astype(int),
        "u5_units_ytd":  g(bu, hu, H_U5, 1).fillna(0).astype(int),
    })
    v = pd.DataFrame({
        "cbsa_code":  code(bv, hv),
        "u5_value_k": g(bv, hv, H_U5, 0).fillna(0).astype(int),
    })
    out = u.merge(v, on="cbsa_code", how="left")
    out["u5_value_k"] = out.u5_value_k.fillna(0).astype(int)
    out.insert(0, "period", period)
    out["source_file"] = path.name
    out["parsed_at"]   = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # 무결성 (Phase 0 실측 기반)
    if out.cbsa_code.duplicated().any():
        raise ValueError(f"{path.name}: CBSA 중복")
    # 원장 원칙: 원본 값은 고치지도 버리지도 않는다. 1% 초과면 열 탐색 오류로 보고 raise
    viol = out[(out.u5_units != out.u5_units_ytd) if period.endswith("-01")
               else (out.u5_units > out.u5_units_ytd)]
    if len(viol) > max(1, int(len(out) * 0.01)):
        raise ValueError(f"{path.name}: 월간>YTD {len(viol)}행 (>1%) — 열 탐색 오류 의심")
    if len(viol):
        _log_anomalies(viol, path.name, period)
        print(f"  [ANOMALY] {path.name}: 월간>YTD {len(viol)}행 — 원본 그대로 저장, bps_anomalies.csv 기록")
    return out[BPS_COLS]


def _log_anomalies(viol: pd.DataFrame, source_file: str, period: str) -> None:
    """원장 보조 파일. Census 수정 파일이 나오면 대조용."""
    exists = ANOM_CSV.exists()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with ANOM_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["period","cbsa_code","cbsa_name","u5_units","u5_units_ytd",
                        "source_file","note","logged_at"])
        for r in viol.itertuples(index=False):
            w.writerow([period, r.cbsa_code, r.cbsa_name, r.u5_units, r.u5_units_ytd,
                        source_file, "monthly_gt_ytd", now])


def append_bps(df: pd.DataFrame) -> int:
    if BPS_CSV.exists():
        cur = pd.read_csv(BPS_CSV, dtype=str)
        key = set(zip(cur.period, cur.cbsa_code))
        new = df[~df.apply(lambda r: (r.period, r.cbsa_code) in key, axis=1)]
        if len(new): new.to_csv(BPS_CSV, mode="a", header=False, index=False)
    else:
        new = df
        new.to_csv(BPS_CSV, index=False)
    return len(new)


def log_download(path: Path, rows: int) -> None:
    exists = LOG_CSV.exists()
    with LOG_CSV.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["source_file","downloaded_at","rows_appended","sha256"])
        w.writerow([path.name, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    rows, hashlib.sha256(path.read_bytes()).hexdigest()])


def collect_bps(end: tuple[int,int] | None = None) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    # v0.3: 전월까지 시도. 미공표면 404로 스킵되고 다음 달 실행에서 잡힌다 (source_file 기준 멱등)
    end = end or ((today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12))
    parsed = set()
    if BPS_CSV.exists():
        parsed = set(pd.read_csv(BPS_CSV, dtype=str, usecols=["source_file"]).source_file)
    total = 0
    for y, m in months(BPS_START, end):
        fn = bps_filename(y, m)
        if fn in parsed:
            continue
        dest = RAW_DIR / fn
        if not download(BPS_BASE + fn, dest):
            continue
        df = parse_bps(dest)
        n = append_bps(df)
        log_download(dest, n)
        total += n
        print(f"  {fn}: +{n}행")
    print(f"BPS 완료: +{total}행")


# ---------------- SOC ----------------
SOC_SHEETS  = {"United States": "US", "Northeast": "Northeast", "Midwest": "Midwest",
               "South": "South", "West": "West"}
SOC_BUCKETS = {5: "2+", 6: "2-4", 7: "5-9", 8: "10-19", 9: "20+"}   # 열 인덱스 (Phase 0 실측)


def _parse_soc_file(path: Path, metric: str) -> pd.DataFrame:
    x = pd.ExcelFile(path, engine="openpyxl")
    rows = []
    for sheet, region in SOC_SHEETS.items():
        df = x.parse(sheet, header=None)
        # 행4 열5가 'Buildings with 2 units or more' 인지 확인 (레이아웃 가드)
        assert "2 units or more" in str(df.iat[4, 5]), f"{path.name}/{sheet}: 레이아웃 변경"
        for i in range(6, len(df)):
            y = str(df.iat[i, 0]).strip().replace(".0", "")
            if not re.fullmatch(r"\d{4}", y):
                break                      # 'RSE' 또는 빈 행에서 종료
            for ci, bucket in SOC_BUCKETS.items():
                v = pd.to_numeric(df.iat[i, ci], errors="coerce")   # 'A','NA' → NaN
                rows.append(dict(year=int(y), region=region, unit_bucket=bucket, metric=metric, months=v))
    return pd.DataFrame(rows)


def collect_soc() -> None:
    """v0.3: 원격 파일 sha256이 기존 raw와 같으면 재기록하지 않는다 (매달 빈 커밋 방지)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    parts, changed = [], False
    for k, url in SOC_URLS.items():
        dest = RAW_DIR / f"soc_{k}.xlsx"
        r = requests.get(url, headers=HEADERS, timeout=30); r.raise_for_status()
        new_sha = hashlib.sha256(r.content).hexdigest()
        old_sha = hashlib.sha256(dest.read_bytes()).hexdigest() if dest.exists() else None
        if new_sha != old_sha:
            dest.write_bytes(r.content); changed = True
        parts.append(_parse_soc_file(dest, k))
        time.sleep(1.0)
    if not changed and SOC_CSV.exists():
        print("SOC 변경 없음 — 스킵"); return
    long = pd.concat(parts)
    wide = long.pivot_table(index=["year","region","unit_bucket"], columns="metric", values="months").reset_index()
    wide = wide.rename(columns={"auth_to_start": "months_auth_to_start", "start_to_comp": "months_start_to_comp"})
    wide["months_auth_to_comp"] = wide.months_auth_to_start + wide.months_start_to_comp
    wide = wide.sort_values(["year","region","unit_bucket"])
    # 검증: 2025 South 2+ == 17.5, 20+ == 21.8 (Phase 0 실측 + NAHB 일치)
    s = wide[(wide.year == 2025) & (wide.region == "South")].set_index("unit_bucket")
    assert abs(s.loc["2+", "months_auth_to_comp"] - 17.5) < 0.05
    assert abs(s.loc["20+", "months_auth_to_comp"] - 21.8) < 0.05
    wide.to_csv(SOC_CSV, index=False)
    print(f"SOC 완료: {len(wide)}행, 최신 {wide.year.max()}")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "bps"
    {"bps": collect_bps, "soc": collect_soc}[what]()
```

**트레이드오프**
- **헤더명 탐색** (v0.1 열 위치 고정에서 변경): 2024+ 파일에 `Metro /Micro Code` 열이 끼어들어 위치가 1칸 밀린다. 헤더 행은 단일 행(행7)이고 라벨이 깨끗하므로 이름 탐색이 안전. 같은 라벨이 Current Month/YTD 두 번 나오므로 `nth`로 구분. 무결성은 월간 ≤ YTD로 대체
- 원본 xls 커밋(13MB) vs 미커밋: 커밋한다. 원장 원칙 + 재파싱 가능. GitHub 1파일 100MB 제한과 무관
- SOC 파서는 Phase 0 실측으로 확정. 행4~5 2단 헤더, 열5~9 = Total2/2-4/5-9/10-19/20+, 'RSE' 행에서 종료. 검증값 South 2025 (2+ 17.5 / 20+ 21.8)이 NAHB 공표치와 일치

### 4.2 `market_context.py`

```python
"""CBSA × 시점 → 시장 상태. 순수 함수. LLM·네트워크 없음 (M4)."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import pandas as pd

RULE_VERSION     = "v1"
WINDOW_M         = 12      # 최근 창
BASE_YEARS       = 3       # 기저선 (Q1)
VOLUME_FLOOR     = 1000    # 2026-10-15 실측 확정: 판정 가능 80 CBSA, ratio p10~p90 0.64~1.46 (하한 300은 양극단이 프로젝트 1~2건 노이즈)
LAG_BUCKET       = "20+"   # research_market §4.2.5


@dataclass
class MarketContext:
    cbsa_code: str
    as_of: str                      # YYYY-MM
    coverage: str                   # ok | low_volume | no_data
    units_12m: int | None
    units_avg3y: float | None
    ratio_12m_vs_3y: float | None   # low_volume 에서도 산출 (참고용), 판정은 unknown
    region: str | None
    lag_months: float | None
    def to_dict(self): return asdict(self)


def _window(bps: pd.DataFrame, cbsa: str, end: str, n: int) -> pd.DataFrame:
    d = bps[(bps.cbsa_code == cbsa) & (bps.period <= end)].sort_values("period")
    return d.tail(n)


def compute(cbsa: str, as_of: str, bps: pd.DataFrame, soc: pd.DataFrame | None,
            region_of: dict[str, str]) -> MarketContext:
    need = WINDOW_M * (BASE_YEARS + 1)
    w = _window(bps, cbsa, as_of, need)
    region = region_of.get(cbsa)
    lag = None
    if soc is not None and region:
        s = soc[(soc.region == region) & (soc.unit_bucket == LAG_BUCKET)].dropna(subset=["months_auth_to_comp"]).sort_values("year")
        if len(s): lag = float(s.iloc[-1].months_auth_to_comp)

    if len(w) < need or w.period.iloc[-1] != as_of:
        return MarketContext(cbsa, as_of, "no_data", None, None, None, region, lag)

    recent = w.tail(WINDOW_M)
    base   = w.head(WINDOW_M * BASE_YEARS)
    units_12m   = int(recent.u5_units.sum())
    units_avg3y = float(base.u5_units.sum() / BASE_YEARS)
    ratio = (units_12m / units_avg3y) if units_avg3y > 0 else None
    cov = "low_volume" if units_avg3y < VOLUME_FLOOR else "ok"
    return MarketContext(cbsa, as_of, cov, units_12m, round(units_avg3y, 1),
                         None if ratio is None else round(ratio, 3), region, lag)


def expected_completion(cbsa: str, bps: pd.DataFrame, lag_months: float | None,
                        horizon_q: int = 4) -> dict[str, int]:
    """허가 월 + lag → 준공 분기. 추정치. 미착공·취소 미반영 (화면 고지 필수)."""
    if lag_months is None:
        return {}
    d = bps[bps.cbsa_code == cbsa].copy()
    if d.empty: return {}
    d["period_dt"] = pd.to_datetime(d.period, format="%Y-%m")
    d["comp_dt"]   = d.period_dt + pd.DateOffset(months=int(round(lag_months)))
    d["comp_q"]    = d.comp_dt.dt.to_period("Q")
    last_q = pd.Timestamp.today().to_period("Q")
    fut = d[d.comp_q > last_q]
    agg = fut.groupby("comp_q").u5_units.sum().sort_index().head(horizon_q)
    return {str(q): int(v) for q, v in agg.items()}


def region_map(bps: pd.DataFrame, state_region: pd.DataFrame) -> dict[str, str]:
    """cbsa_name 'Atlanta-Sandy Springs-Roswell, GA' / 'Columbus, GA-AL' → 쉼표 뒤 첫 주 → region."""
    s2r = dict(zip(state_region.state, state_region.region))
    names = bps.drop_duplicates("cbsa_code", keep="last").set_index("cbsa_code").cbsa_name
    out = {}
    for code, name in names.items():
        if "," not in name: continue
        st = name.split(",")[-1].strip().split("-")[0].strip()
        if st in s2r: out[code] = s2r[st]
    return out
```

**트레이드오프**
- `as_of` 직전 완결월 기준 vs 발행월: BPS는 전월분을 18번째 근무일에 내므로 발행월 데이터는 없다. 기사 `published_at`의 **2개월 전**을 as_of로 쓴다 (tagger에서 계산). 정확성보다 가용성
- 기저선 12m 합 vs 월별 이동평균: 월별은 프로젝트 1건에 흔들린다. 12m 합이 "연간 공급" 개념과 맞는다
- `no_data` 기준을 48개월 전수로 둔 이유: 3년 기저선 + 1년 최근. 2019-11 시작이므로 2023-11 이후 as_of만 판정 가능. 기존 기사(2026-03~)는 전부 충족. Micro 지역은 2024-01부터만 존재하므로 2027-01 전까지 자동 no_data
- `low_volume` (v0.1 `imputed` 대체): 보고분 열이 없어 대체추정 비율을 알 수 없다. 대신 3년 평균 연간 5+유닛이 VOLUME_FLOOR 미만이면 ratio가 프로젝트 1~2건에 좌우되는 노이즈이므로 판정하지 않는다. ratio 자체는 참고용으로 남긴다

### 4.3 `market_rules.py`

```python
"""시장 상태 → flag 목록. 규칙은 6개 상한 (M2). 결정론."""
from market_context import MarketContext

RULE_VERSION = "v1"
THRESH = dict(surge=1.25, drought=0.75)   # 2026-10-15 실측 확정: VOLUME_FLOOR 1000 기준 p80 1.256 / p20 0.742 반올림

def judge(ctx: MarketContext) -> list[str]:
    if ctx.coverage in ("no_data", "low_volume"):  return ["unknown"]   # S3
    flags = []
    r = ctx.ratio_12m_vs_3y
    if r is None:                  return ["unknown"]
    if r >= THRESH["surge"]:       flags.append("supply_surge")    # S1
    if r <= THRESH["drought"]:     flags.append("supply_drought")  # S2
    # S4 completion_wave — Phase 2 (ACS 재고 필요)
    # T1 absorption_slow, T2 rent_soft — Phase 2
    return flags
```

규칙 추가 절차(M2): 이 파일 상단 주석에 `# RULES: S1 supply_surge / S2 supply_drought / S3 unknown — 상한 6 (M2)` 목록을 유지하고, 추가 시 `RULE_VERSION`을 올린다.

### 4.4 `market_store.py` + `market_tagger.py` — v0.4

```python
# market_store.py — geo_store.py 패턴
"""market_flags.db 접근. 렌즈 계층. 원장을 읽지 않는다."""
from __future__ import annotations
import sqlite3
from pathlib import Path
DB = Path("market_flags.db")
SCHEMA = """…§3.4 DDL…"""
COLS = ["article_id","cbsa_code","rule_version","as_of","coverage","units_12m",
        "units_avg3y","ratio_12m_vs_3y","flags","tagged_at"]

def open_market() -> sqlite3.Connection:
    c = sqlite3.connect(DB); c.executescript(SCHEMA); return c

def tagged_keys(c, rule_version: str) -> set[tuple[str, str]]:
    return set(c.execute("SELECT article_id, cbsa_code FROM market_flags WHERE rule_version=?", (rule_version,)))

def upsert_flag(c, row: dict) -> None:
    c.execute(f"INSERT OR REPLACE INTO market_flags ({','.join(COLS)}) VALUES ({','.join('?'*len(COLS))})",
              [row.get(k) for k in COLS])

def get_flags(c, article_ids: list[str], rule_version: str | None = None) -> dict[str, list[dict]]:
    out = {}
    for i in range(0, len(article_ids), 900):
        chunk = article_ids[i:i+900]
        q = f"SELECT {','.join(COLS)} FROM market_flags WHERE article_id IN ({','.join('?'*len(chunk))})"
        args = list(chunk)
        if rule_version: q += " AND rule_version=?"; args.append(rule_version)
        for r in c.execute(q, args):
            d = dict(zip(COLS, r)); out.setdefault(d["article_id"], []).append(d)
    return out

def count_flags(c) -> int:
    return c.execute("SELECT COUNT(*) FROM market_flags").fetchone()[0]
```

```python
# market_tagger.py
"""archive × geo_tags.db × market_context → market_flags.db + context_latest.json
daily_collect.yml: Geo tagging 뒤, Build archive index 앞.
--mode incremental (기본): rule_version 기준 미태깅 (article_id, cbsa)만
--mode context-only       : 기사 태깅 없이 JSON만 (monthly_market.yml, Phase 2)
--mode backfill           : incremental과 동일 필터 (명시용)"""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from archive_manager import read_archive            # 기존. article_id, published_at 포함 행 반환
from geo_store import open_geo, get_geo             # 기존
from market_store import open_market, tagged_keys, upsert_flag, get_flags
from market_context import compute, expected_completion, region_map, RULE_VERSION
from market_rules import judge

BPS   = Path("data/market/bps_cbsa.csv"); SOC = Path("data/market/soc_lag.csv")
STREG = Path("data/market/state_region.csv"); OUT_JSON = Path("data/market/context_latest.json")
APPLICABLE_SCOPES = {"metro", "local"}
APPLICABLE_CONF   = {"exact", "inferred", "source_inferred"}


def as_of_for(published_at: str) -> str:
    dt = pd.to_datetime(published_at, errors="coerce", utc=True)
    return "" if pd.isna(dt) else str(dt.to_period("M") - 2)


def load():
    bps = pd.read_csv(BPS, dtype={"cbsa_code": str, "period": str})
    soc = pd.read_csv(SOC) if SOC.exists() else None
    return bps, soc, pd.read_csv(STREG)


def tag_articles(bps, soc, region_of) -> int:
    rows = read_archive()                                     # list[dict] 또는 DataFrame — 기존 시그니처에 맞춘다
    ids  = [r["article_id"] for r in rows]
    pub  = {r["article_id"]: r["published_at"] for r in rows}
    gconn = open_geo(); geo = get_geo(gconn, ids)
    mconn = open_market(); done = tagged_keys(mconn, RULE_VERSION)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds"); n = 0
    for aid in ids:
        g = geo.get(aid)
        if not g or not g.get("geo_cbsa_code"): continue
        for cbsa in g["geo_cbsa_code"].split("|"):
            cbsa = cbsa.strip()
            if not cbsa or (aid, cbsa) in done: continue
            as_of = as_of_for(pub[aid])
            base = dict(article_id=aid, cbsa_code=cbsa, rule_version=RULE_VERSION, as_of=as_of, tagged_at=now)
            if (g.get("geo_scope") not in APPLICABLE_SCOPES or g.get("geo_confidence") not in APPLICABLE_CONF or not as_of):
                upsert_flag(mconn, {**base, "coverage": "not_applicable", "flags": ""}); n += 1; continue
            c = compute(cbsa, as_of, bps, soc, region_of)
            upsert_flag(mconn, {**base, "coverage": c.coverage, "units_12m": c.units_12m,
                                "units_avg3y": c.units_avg3y, "ratio_12m_vs_3y": c.ratio_12m_vs_3y,
                                "flags": "|".join(judge(c))}); n += 1
    mconn.commit(); return n


def dump_context(bps, soc, region_of, with_counts: bool) -> None:
    as_of = str(pd.to_datetime(bps.period).max().to_period("M"))
    names = bps.drop_duplicates("cbsa_code", keep="last").set_index("cbsa_code").cbsa_name.to_dict()
    counts = {}
    if with_counts:
        mconn = open_market()
        for code, total, ok in mconn.execute(
            "SELECT cbsa_code, COUNT(*), SUM(coverage='ok') FROM market_flags WHERE rule_version=? AND coverage!='not_applicable' GROUP BY cbsa_code", (RULE_VERSION,)):
            counts[code] = {"total": total, "flagged": ok}
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "as_of": as_of, "rule_version": RULE_VERSION, "cbsa": {}}
    for code in sorted(names):
        c = compute(code, as_of, bps, soc, region_of)
        m = bps[bps.cbsa_code == code].sort_values("period").tail(36)[["period","u5_units"]].to_dict("records")
        out["cbsa"][code] = {**c.to_dict(), "name": names[code], "flags": judge(c), "monthly": m,
                             "article_counts": counts.get(code),
                             "expected_completion": {"lag_months": c.lag_months, "bucket": "20+",
                                                     "by_quarter": expected_completion(code, bps, c.lag_months)}}
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--mode", default="incremental",
        choices=["incremental", "backfill", "context-only"]); a = ap.parse_args()
    bps, soc, streg = load(); region_of = region_map(bps, streg)
    if a.mode != "context-only":
        print(f"market_flags +{tag_articles(bps, soc, region_of)}행")
    dump_context(bps, soc, region_of, with_counts=(a.mode != "context-only"))
    print(f"context_latest.json {OUT_JSON.stat().st_size//1024}KB")
```

**`build_archive_index.py` 수정 (1곳)**
```python
# 기존: labels = get_labels(...); geo = get_geo(...)
from market_store import open_market, get_flags
mk = get_flags(open_market(), ids, rule_version=RULE_VERSION)   # RULE_VERSION은 market_context에서 import
# records 생성 시:
#   rows = [r for r in mk.get(aid, []) if r["coverage"] != "not_applicable"]
#   if rows: rec["mk"] = [[r["cbsa_code"], r["flags"], r["ratio_12m_vs_3y"], r["coverage"]] for r in rows]
# filters["market_flags"] = sorted({f for rs in mk.values() for r in rs for f in r["flags"].split("|") if f})
```
`mk`는 not_applicable 행을 제외하고, 없으면 키 자체를 생략한다 (9MB 파일 크기 관리).

**트레이드오프 (v0.4)**
- SQLite vs CSV: 저장소에 이미 labels.db·geo_tags.db 패턴(store 모듈, binary merge=ours, 행 수 감소 감지)이 있다. 같은 패턴을 따르면 충돌 복구·조인 코드를 재사용한다. CSV의 diff 가독성은 `context_latest.json`과 `bps_anomalies.csv`가 대신한다
- 기사 우주 = archive 10,249 (작업본 5,944가 아님): 렌즈는 원장 전체를 덮어야 archive_index.json과 일치한다. 2024-09 기사도 BPS 48개월 창을 충족
- confidence 필터에 `state`·`ambiguous` 제외: state는 CBSA 없음, ambiguous는 동명 미해소. 둘 다 판정하면 추정이 된다 (I8·M6)

### 4.5 `tests/`

```python
# tests/test_market_parse.py — Phase 1.2에서 받은 실제 파일 2개를 fixtures로 복사
# fixtures: cbsamonthly_202608.xls (2024+ 레이아웃), msamonthly_202312.xls (2023 레이아웃)
def test_2026_08_atlanta():
    df = parse_bps(Path("tests/fixtures/cbsamonthly_202608.xls"))
    a = df[df.cbsa_code == "12060"].iloc[0]
    assert a.period == "2026-08" and a.u5_units == 875 and a.u5_units_ytd == 8361
    assert a.u5_structures == 92 and a.u5_value_k == 132251 and a.metro_micro == "2"
    assert len(df) >= 900
def test_2023_12_atlanta_old_layout():
    df = parse_bps(Path("tests/fixtures/msamonthly_202312.xls"))
    a = df[df.cbsa_code == "12060"].iloc[0]
    assert a.period == "2023-12" and a.u5_units == 440 and a.u5_units_ytd == 14227
    assert a.u5_value_k == 79211 and a.metro_micro == ""
    assert 380 <= len(df) <= 400
def test_soc_south_2025():
    s = pd.read_csv("data/market/soc_lag.csv")
    r = s[(s.year==2025)&(s.region=="South")].set_index("unit_bucket")
    assert abs(r.loc["2+","months_auth_to_comp"] - 17.5) < 0.05
    assert abs(r.loc["20+","months_auth_to_comp"] - 21.8) < 0.05

# tests/test_market_context.py — 합성 데이터로 항등식
def test_ratio_identity():
    # 48개월, 첫 36개월 월 100유닛, 최근 12개월 월 60유닛 → avg3y 1200, 12m 720, ratio 0.6
    assert ctx.units_avg3y == 1200 and ctx.units_12m == 720 and abs(ctx.ratio_12m_vs_3y - 0.6) < 1e-9
def test_low_volume():
    # 월 10유닛 → avg3y 120 < 300 → coverage == "low_volume", ratio는 산출됨
def test_no_data_when_short():
    # 47개월 → "no_data"
def test_no_data_when_as_of_missing():
    # 48개월 있으나 마지막 period != as_of → "no_data"

# tests/test_market_rules.py — 경계값
def test_boundaries():
    assert judge(ctx(ratio=1.30)) == ["supply_surge"]
    assert judge(ctx(ratio=1.299)) == []
    assert judge(ctx(ratio=0.70)) == ["supply_drought"]
    assert judge(ctx(coverage="low_volume", ratio=0.3)) == ["unknown"]
```

### 4.6 워크플로

**`.github/workflows/diagnose_market.yml`** (Phase 0, 일회성)
```yaml
name: Diagnose Market Sources (one-off)
on: { workflow_dispatch: }
concurrency: { group: diagnose-market, cancel-in-progress: false }
permissions: { contents: read }
jobs:
  diagnose:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - run: python diagnose_market.py   # 아래 §4.7
```

**`.github/workflows/monthly_market.yml`** (Phase 1)
```yaml
name: Monthly Market Collect
on:
  schedule:
    - cron: "0 2 29 * *"   # v0.3: 매월 29일 02:00 UTC = 11:00 KST. 18번째 근무일이 26~27일인 달이 있어 여유 확보
  workflow_dispatch:
concurrency: { group: monthly-market, cancel-in-progress: false }
permissions: { contents: write }
jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { token: "${{ secrets.GITHUB_TOKEN }}" }
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - run: python market_collect.py bps
      - run: python market_tagger.py          # context_latest.json 갱신 (기사 태깅은 geo 있을 때만)
      - name: Commit & push
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/market/
          git diff --cached --quiet && echo "변경 없음" || (git commit -m "auto: market data $(date +%Y-%m)" && git pull --rebase origin main && git push)
```
- `daily_collect`(21:00 UTC)·`weekly_report`(일 23:00 UTC)와 시각이 겹치지 않는다 (A1 교훈)

**`daily_collect.yml` 수정** (Phase 3) — 현재 스텝 순서: … 7 classifier → 8 `geo_tagger.py --mode incremental` → 9 `build_archive_index.py` → 10 요약 → 11 배치취소 → 12 commit
```yaml
      # 8과 9 사이에 삽입 (가드 조건 if: steps.guard.outputs.skip == 'false' 동일 적용)
      - name: Market tagging
        if: steps.guard.outputs.skip == 'false'
        run: python market_tagger.py --mode incremental
      # 12 commit 의 git add 에 추가: market_flags.db data/market/context_latest.json
      # 충돌 처리 블록에서 labels/geo DB와 같은 "행 수 감소 감지"를 market_flags.db에도 적용
```
`.gitattributes`: `market_flags.db binary merge=ours`

**`monthly_market.yml` 수정** (Phase 2): soc 뒤에 `python market_tagger.py --mode context-only`, git add에 `data/market/` 포함(이미 포함)

### 4.7 `diagnose_market.py` (Phase 0)

```python
"""일회성. (1) Actions 러너에서 census.gov 접근 가능한지 (2) BPS xls 실제 열 구조
(3) SOC xlsx 시트·행 구조를 출력. 아무 파일도 쓰지 않는다(권한 read)."""
import requests, pandas as pd, io
H = {"User-Agent": "Mozilla/5.0 (compatible; WoomiGlobalResearchBot/2.0)"}
U = ["https://www.census.gov/construction/bps/xls/cbsamonthly_202608.xls",
     "https://www.census.gov/construction/bps/xls/msamonthly_202312.xls",
     "https://www.census.gov/construction/nrc/xls/avg_authtostart_cust.xlsx",
     "https://www.census.gov/construction/nrc/xls/avg_starttocomp_cust.xlsx"]
for u in U:
    r = requests.get(u, headers=H, timeout=30)
    print("="*100); print(u, "status", r.status_code, "bytes", len(r.content))
    if r.status_code != 200: continue
    eng = "xlrd" if u.endswith(".xls") else "openpyxl"
    x = pd.ExcelFile(io.BytesIO(r.content), engine=eng)
    for sh in x.sheet_names:
        df = x.parse(sh, header=None)
        print(f"--- sheet {sh!r} shape {df.shape}")
        print(df.head(12).to_string())
        if "cbsamonthly" in u or "msamonthly" in u:
            hit = df[df.astype(str).apply(lambda c: c.str.contains("12060")).any(axis=1)]
            print("--- Atlanta(12060) 행:"); print(hit.to_string())
```
→ 출력으로 열 위치(COL)·SOC 파서를 확정하고 Plan v0.2에 반영한 뒤 Phase 1 착수.

### 4.8 `index.html` (Phase 4) — v0.5 실제 구현

index.html은 `articles.csv`, `archive_index.json`, `data/market/context_latest.json`(신규), `reports/`, `manifest.json`을 읽는다.

**(a) 시장 맥락 칩 — 아카이브 표 제목 셀.** 아카이브는 카드가 아니라 표이고 `rel`은 50px 텍스트 칸이라 그 옆에 칩이 들어가지 않는다. 제목 링크 아래 `<div class="mk-row">`에 `rec.mk` 행마다 `<span class="mk-chip mk-{flat|unknown|surge|drought}">`. `mk`가 없으면 줄 자체를 만들지 않는다. 필터용 `.chip`과 별개 클래스(표시 전용).
- 라벨: 평년 / 판정불가 / 공급 급증 / 공급 감소 + ` · ` + 약칭
- 약칭: `CBSA_SHORT[cbsa]`(ATL DFW LA SEA DEN PHX COMO) ?? `cbsa_titles[cbsa].split(",")[0].split("-")[0].trim()` ("Orlando-Kissimmee-Sanford, FL" → "Orlando")
- title: `{cbsa_titles} · BPS 5+유닛 12개월합/3년평균 {ratio(ok일 때만) | —} · 발행월 기준`
- 색(기존 팔레트): flat #eee/#555, unknown 흰 바탕 점선 #999, surge #fff4d6/#f4b400, drought #e8eef5/#1B3A5C
- 관련성 칸·정렬·필터 불변 (M1·I6)

**(b) 마켓워치 — 세 번째 페이지 탭 `📈 마켓워치`.** `.page-tabs`에 버튼 + `#page-market` 패널, `switchPage()` 분기. `loadMarketData()`가 `marketLoaded` 플래그로 탭 첫 진입 시 1회 fetch(1.5MB). `MARKET_CTX_URL`은 `ARCHIVE_INDEX_URL` 옆 상수.
- Chart.js: cdnjs `4.4.1/chart.umd.min.js`, onerror 콘솔 기록
- 구성: 메타 한 줄(기준월·규칙·출처) → CBSA `<select>`(WATCH 7개 약칭+이름, 구분선, 나머지 이름순, 기본 12060) → 타일 4개(3년 대비 / 판정 / 12개월 허가+3년평균 / 기사 수, 모바일 2×2) → flags 칩(mk-chip, 약칭 없음) → 차트(높이 240, bar u5_units #1B3A5C + 12개월 이동합 line #2E75B6 우측 축, 첫 11개월 null) → 준공 예상 표(by_quarter, 비면 "lag 산출 불가") → 고정 문구(기저선 설명 + SOC region lag, low_volume이면 "판정 불가 — 3년 평균 …유닛/년 < 하한 1,000" 선행)
- x축 라벨: 3개월마다, **모바일(<600px)은 6개월마다**(겹침 방지)
- 셀렉트 변경 시 기존 Chart 인스턴스 destroy 후 재생성
- 기사 수 타일은 `article_counts.total` = not_applicable 제외 판정 행 수

**(c) `service-worker.js`** — Network First 조건에 `context_latest.json` 추가(articles.csv·archive_index.json과 같은 이유: daily·monthly 갱신 데이터가 Cache First로 굳는 것 방지).

- I6 유지: 아카이브 필터에 CBSA·flag 필터를 추가하지 않았다. `filters.market_flags`는 데이터에만 있다.

## 5. 트레이드오프 총괄

| 선택 | 대안 | 채택 이유 |
|---|---|---|
| 길 B (Python 규칙) | 길 A (프롬프트 주입) | 재현·감사·기존 5,496건 무재분류 (research §3.1) |
| 두 칩 나란히 | 합산 점수 | 근거 은닉 방지 (M1) |
| 전 CBSA 계산 | 관심 7개만 | 비용 무시 가능, 신규 딜 시장 즉시 조회 |
| 별도 monthly 워크플로 | daily에 포함 | A1 충돌 교훈, 월간 데이터에 일간 실행은 낭비 |
| 원본 xls 커밋 | raw 미보관 | 원장 원칙, 재파싱 가능 |
| 기저선 3년 | 2년 | 팬데믹 급등 포함하면서 과거 과다 미반영 (Q1) |
| as_of = 발행월−2 | 발행월 | BPS 공표 지연. 가용성 우선 |
| unknown 근거 = 물량 하한 | 보고 비율 | 월간 파일에 보고분 열이 없음 (Phase 0 실측). 비율이 노이즈인 소규모 시장을 거르는 것이 목적이므로 물량 하한이 대체 가능 |
| Legistar 미포함 | 포함 | Seattle만 응답. 별도 Plan |
| 원본 이상값 저장+기록 | 행 삭제 / raise | 원장 원칙. 1% 임계로 파서 오류와 원본 이상을 구분 (v0.3) |
| Columbia MO `low_volume` 유지 | 하한을 271 아래로 | 원하는 결과에 임계를 맞추지 않는다. 연 271유닛은 프로젝트 1건이 ratio를 0.7 흔드는 규모. Theory Sterling 수요 근거는 BPS가 아니라 IPEDS (v0.3) |

---

## 6. 롤백

- Phase 1~2: `data/market/`·신규 .py·tests 삭제, requirements에서 xlrd 제거. 기존 기능 영향 0
- Phase 3: `daily_collect.yml`에서 스텝 제거, `market_flags.db`·`market_store.py` 삭제, `build_archive_index.py`의 mk 조인 revert. geo_tags.db·labels.db 무관
- Phase 4: `index.html` 해당 커밋 revert. 칩·차트만 사라짐
- 모든 단계가 **독립 커밋**이므로 `git revert <sha>` 단위로 되돌린다

---

## 7. To-Do (승인 후 순차 실행 — 각 단계 독립 커밋, 검증·보고 후 다음)

### Phase 0 — 진단 (구현 아님)
- [x] 0.1 `requirements.txt`에 `xlrd>=2.0.1` 추가 — 커밋 `chore: xlrd 추가 (BPS .xls 파싱)`
- [x] 0.2 `diagnose_market.py` + `diagnose_market.yml` — 커밋 `diag: 시장 데이터 소스 진단 워크플로`
- [x] 0.3 Actions 수동 실행 → 로그 전문 → **Plan v0.2** (완료 2026-10-15: 4 URL 200, 헤더명 탐색으로 전환, SOC 파서 확정, rep→volume floor)

### Phase 1 — 수집 (geo 무관)
- [x] 1.1 `data/market/state_region.csv` 51행 — 커밋 `data: state→Census Region 정적 테이블`
- [x] 1.2 `market_collect.py` (bps) + `tests/test_market_parse.py` + fixtures 2파일(202608, 202312) — 커밋 `feat: BPS 월간 CBSA 수집기`
- [x] 1.3 로컬에서 `python market_collect.py bps` 백필 (2019-11~2026-08, 약 82파일) → `data/market/raw/`·`bps_cbsa.csv`·log 커밋 `data: BPS 백필 2019-11~2026-08`
  - 검증: 2024+ 32파일 × ~929 + 2019-11~2023-12 50파일 × ~393 ≈ 49,400행, Atlanta 12060 82개월 전부 존재, 월간 ≤ YTD 전수, (period, cbsa) 중복 0
- [x] 1.4 `market_collect.py` (soc) — 커밋 `feat: SOC 소요기간 수집기` + `data/market/soc_lag.csv`
  - 검증: 2025 South 2+ = 17.5, 20+ = 21.8 (assert 내장). 행수 = 연도(1971~2025 중 유효) × 5 region × 5 bucket
- [x] 1.5 `monthly_market.yml` — 커밋 `ci: 월간 시장 데이터 수집 워크플로`

### Phase 2 — 판정 (geo 무관)
- [x] 2.0 **수집기 보정** (Phase 1 피드백): (a) `collect_bps` 종료월 `month-2`→`month-1` (b) `collect_soc` sha256 멱등 (c) `monthly_market.yml` cron 26→29일 — 커밋 `fix: 수집기 종료월·SOC 멱등·cron 조정`
- [x] 2.1 `market_context.py` + `tests/test_market_context.py` — 커밋 `feat: 시장 상태 계산 (순수)`
- [x] 2.2 **임계값 보정**: 전 CBSA 2026-08 기준 (a) units_avg3y 분포(분위수 10/25/50/75/90) → VOLUME_FLOOR 확정. 관심 7개 CBSA의 coverage 결과를 **기록**하되 **하한을 그들에 맞추지 않는다** (Columbia MO 271 → low_volume 예상, 그대로 둠) (b) ok인 CBSA의 ratio 분포 → 상·하위 20% 지점으로 THRESH 확정 → Plan v0.5 기록
  - 사전 실측 (2026-08, 48개월 창): ATL 0.913 / DFW 0.912 / LA 1.461 / SEA 1.330 / DEN 0.847 / PHX 0.875 / Columbia MO 1.080(avg3y 271)
- [x] 2.3 `market_rules.py` + `tests/test_market_rules.py` — 커밋 `feat: 시장 맥락 규칙 S1~S3`
- [x] 2.4 `market_tagger.py --mode context-only` → `context_latest.json`; `monthly_market.yml`에 스텝 추가 — 커밋 `feat: 시장 context 덤프`
  - 검증: 관심 7개 CBSA의 coverage·ratio·flags·lag_months·by_quarter 표

### Phase 3 — 기사 태깅 (**전제 충족됨**: geo_tags.db 10,249행 존재)
- [x] 3.0 `market_store.py` + `tests/test_market_store.py` + `.gitattributes` — 커밋 `feat: market_flags.db 렌즈 스토어`
- [x] 3.1 `market_tagger.py --mode incremental` 로컬 1회 실행 = 원장 10,249건 소급 — 커밋 `data: market_flags 백필`
  - 검증: 행수(≈5,185 + 다중 90), coverage 분포, flags 분포, 관심 7 CBSA별 coverage 분포, `woomi_relevance`(labels.db) × flags 교차표
- [x] 3.2 `build_archive_index.py` mk 조인 → `archive_index.json` 재생성 — 커밋 `feat: archive_index에 시장 맥락 조인`
  - 검증: mk 키 있는 records 수, 파일 크기 증가분(9.0MB 대비)
- [x] 3.3 `daily_collect.yml` 스텝·git add·충돌처리 추가 — 커밋 `ci: daily에 market tagging 추가`. 익일 06:00 KST 실행 로그 확인

### Phase 4 — 화면
- [x] 4.1 아카이브 카드 mk 칩 — 커밋 `feat(ui): 시장 맥락 칩`
- [x] 4.2 마켓워치 섹션 신규 + Chart.js 재도입 — 커밋 `feat(ui): 마켓워치`
- [ ] 4.3 스크린샷 → 공모전 증빙 6번용 보관

### Phase 5 — 정리
- [x] 5.0 CBSA 약칭 하이픈 앞까지 (index.html) — 커밋 `fix(ui): CBSA 약칭 하이픈 앞까지`
- [x] 5.1 research_market.md §12 정정 섹션(본문 불변): 보고분 열 부재→물량 하한 / 20+ 구간 Sun Belt 이점 없음 / geo 완료 전제 오류 / 임계 확정 / relevance×flags 독립 / Columbia MO — 커밋 `docs: research_market 정정 섹션 추가 (Phase 0~4 실측)`
- [x] 5.2 `CLAUDE.md` 갱신: 데이터 현황(10,249), 일일 파이프라인(collect→classify→geo→**market**→index), 시장 데이터 풀 절, docs/history 이동·트렌드 차트 삭제 — 커밋 `docs: CLAUDE.md 시장 데이터 풀 반영`
- [x] 5.3 Plan_market v0.5 (이 문서, 코드 동기화) — 커밋 `docs: Plan_market v0.5 (Phase 0~4 완료, 코드 동기화)`
- [ ] 5.4 `docs/contest_evidence.md` 공모전 Before/After·확산 가능성·커버리지 정직성 재료 — 커밋 `docs: 공모전 증빙 재료 초안`

---

## 8. 검토 요청 (사용자 확인)

| # | 항목 | 상태 |
|---|---|---|
| C1 | 관심 CBSA 7개 목록 — Houston(26420)·Charlotte(16740) 추가? | 7개 유지, 필요 시 `CBSA_SHORT`·`MARKET_WATCH` 상수 1줄 |
| C2 | 칩 문구 | **확정: 한글 라벨**(평년/공급 급증/공급 감소/판정불가) + title에 수치 |
| C3 | ~~geo 착수 시점~~ | 해소 (geo 완료) |
| C4 | ~~SOC 파서~~ | 해소 |
| C5 | `metro_micro` 코드 의미 | **정정**: 실측 값은 2·4·5 세 가지(2026-08: 2=275, 4=112, 5=534). "2=Metro, 5=Micro" 추정은 불완전, 의미 미확인. **어떤 필터·판정에도 쓰지 않는다** |
| C6 | 2019-11~2021-12 `Monthly Coverage Percent*` 재파싱 | 보류 유지 (판정 미사용) |
| C7 | `read_archive()` 반환 타입 | **해소**: `list[dict]`(csv.DictReader), `article_id`·`published_at` 키 존재 — tagger 무수정 |
| C8 | A6 후속(`_judge_access_limited` 본문→summary) | 이 Plan 범위 밖, 유지 |
| C9 | index.html의 marked.js가 jsdelivr에서 **버전 미고정**(`npm/marked/marked.min.js`) | 신규, 별건 |

---

## 9. 문서 이력

| 버전 | 일자 | 변경 |
|---|---|---|
| v0.1 | 2026-10-15 | 최초 작성. research_market §9 기본안 전부 채택. geo Plan.md I1~I8 계승 + M1~M7 추가 |
| v0.5 | 2026-10-15 | **Phase 0~4 완료, 코드 동기화.** ① §4.1 코드 블록을 커밋된 market_collect.py로 교체(_pick_sheet, 이상값 1% 정책·bps_anomalies.csv, 종료월 month-1, SOC sha256 멱등) ② VOLUME_FLOOR 1000·THRESH 1.25/0.75 실측 확정 ③ §4.8 실제 구현(제목 셀 mk-row, 세 번째 페이지 탭, 모바일 x축 6개월, service-worker Network First, 약칭 하이픈 규칙) ④ §8 C2 확정·C5 정정·C7 해소·C9 추가 ⑤ §7 Phase 0·1 체크 누락 복구, Phase 5 재작성(공모전 항목 5.4로) |
| v0.4 | 2026-10-15 | **저장소 구조 조사 반영.** ① geo는 완료(geo_tags.db 10,249행) — Phase 3 전제 충족 ② 기사 우주를 articles.csv→archive/ 원장으로 ③ 렌즈 저장을 csv→`market_flags.db`(M8) + `market_store.py` ④ 조인은 `build_archive_index.py`(mk 필드) ⑤ 적용 조건에 confidence 필터 추가 ⑥ index.html 트렌드 차트 부재 확인 → 마켓워치 신규 섹션 + Chart.js 재도입 ⑦ daily 스텝 위치 geo 뒤·index 앞 ⑧ C3 해소, C7·C8 추가 |
| v0.3 | 2026-10-15 | Phase 1 완료 반영. ① 시트명 연도별 차이(`_pick_sheet`) ② 행수 실측 368/384/921 ③ 이상값 정책 확정(1% 임계, `bps_anomalies.csv`) ④ Columbia MO avg3y 271 → `low_volume` 유지 결정, 2.2 문구를 "맞추지 않는다"로 수정 ⑤ SOC 20+ 지역 격차 실측(NE 25.7 / MW 17.6 / S 21.8 / W 22.6 / US 21.7) — research §4.2.5 Sun Belt 논거 정정 필요 ⑥ Phase 2.0 추가(종료월 month-1, SOC sha256 멱등, cron 29일) ⑦ C6 추가 |
| v0.2 | 2026-10-15 | Phase 0 진단 반영. ① 4 URL 200 → 자동 수집 확정 ② BPS 월간 파일에 보고분(rep)·MONCOV 없음 → `rep_share`/`imputed` 폐기, `VOLUME_FLOOR`/`low_volume`로 교체 (M6 수정) ③ 2024+ 파일 `Metro /Micro Code` 열 삽입으로 열 위치 밀림 → 헤더명 탐색 ④ 2023 이전 Metro만 393행, 2024+ Metro+Micro 929행 ⑤ SOC 파서 확정(행4~5 2단 헤더, 열5~9, 검증값 South 2025 2+ 17.5 / 20+ 21.8) ⑥ 실측값 Atlanta 2026-08 u5=875/YTD 8,361, 2023-12 u5=440/YTD 14,227 |
