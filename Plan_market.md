# Plan_market.md — The Brief 시장 데이터 풀 + 시장 맥락 판정 구현 계획

> 버전 v0.3 (2026-10-15) · 근거: `research_market.md` v0.1 + Phase 0 진단 + **Phase 1 실측** · 선행: `Plan.md` v0.3 (geo)
> Phase 1 완료 (커밋 ed6344a..9e73b7b, 2026-10-15). v0.3는 실측 차이 반영 + Phase 2 착수 전 수정 2건(2.0).
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
| M7 | `articles.csv`, `classifier.py`, `collector.py`, `geo_*.py`를 수정하지 않는다 | 원장·렌즈 분리 |

---

## 1. 아키텍처

```
┌─ 수집 (월 1회, monthly_market.yml) ─────────────────────────────┐
│  market_collect.py                                              │
│    census.gov ─xls→ data/market/raw/cbsamonthly_YYYYMM.xls      │
│               ─parse→ data/market/bps_cbsa.csv  (append-only)   │
│    census.gov ─xlsx→ data/market/soc_lag.csv    (연 1회 갱신)    │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─ 판정 (일 1회, daily_collect.yml geo 스텝 뒤) ──────────────────┐
│  market_tagger.py                                               │
│    geo_tags.csv ──┐                                             │
│                   ├─ market_context.py (순수 계산)               │
│    bps_cbsa.csv ──┤        │                                    │
│    soc_lag.csv ───┘        ▼                                    │
│                    market_rules.py (규칙 ≤6)                     │
│                            │                                    │
│         ┌──────────────────┴──────────────────┐                 │
│         ▼                                     ▼                 │
│  market_flags.csv (기사별)        data/market/context_latest.json│
│                                   (전 CBSA, 화면용)              │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─ 화면 (index.html, 정적) ───────────────────────────────────────┐
│  기사 카드: "높음 · supply_drought"  (두 칩, 합산 없음)            │
│  마켓워치 탭: 하드코딩 차트 → context_latest.json 실데이터        │
└─────────────────────────────────────────────────────────────────┘
```

**push와 pull이 같은 함수를 쓴다:** `market_context.compute(cbsa, as_of, bps, soc)`를 `market_tagger.py`가 기사별로 호출하고, 같은 실행의 끝에 전 CBSA에 대해 호출해 JSON으로 덤프한다. 화면은 계산하지 않고 읽기만 한다.

---

## 2. 파일 변경 계획

### 2.1 신규

| 경로 | 종류 | 역할 |
|---|---|---|
| `market_collect.py` | 실행 스크립트 | BPS/SOC 다운로드·파싱·append |
| `market_context.py` | 모듈 (순수) | CBSA×시점 → 시장 상태 계산 |
| `market_rules.py` | 모듈 (순수) | 시장 상태 → flag 목록 |
| `market_tagger.py` | 실행 스크립트 | geo_tags × context → market_flags.csv + context_latest.json |
| `data/market/raw/` | 디렉터리 | 원본 .xls/.xlsx 보관 (원장) |
| `data/market/bps_cbsa.csv` | 데이터 | 파싱 결과 (원장, append-only) |
| `data/market/bps_download_log.csv` | 데이터 | 파일명·받은 시각·행수·sha256 |
| `data/market/bps_anomalies.csv` | 데이터 | 원본 이상값 기록 (월간>YTD 등). 원장 보조. **v0.3 추가** |
| `data/market/soc_lag.csv` | 데이터 | 연×region×bucket 소요기간 |
| `data/market/state_region.csv` | 데이터 | 주 → Census Region (정적 51행) |
| `data/market/context_latest.json` | 데이터 | 전 CBSA 최신 context |
| `market_flags.csv` | 데이터 (루트) | 렌즈. geo_tags.csv와 같은 위치 |
| `tests/test_market_parse.py` | 테스트 | xls 열 위치 고정 |
| `tests/test_market_context.py` | 테스트 | 기저선 산식 항등식 |
| `tests/test_market_rules.py` | 테스트 | 규칙 경계값 |
| `.github/workflows/diagnose_market.yml` | 워크플로 | Phase 0 일회성 (census.gov 접근 확인) |
| `.github/workflows/monthly_market.yml` | 워크플로 | 월 1회 수집 |

### 2.2 기존 수정 (최소)

| 경로 | 변경 | 비고 |
|---|---|---|
| `requirements.txt` | `xlrd>=2.0.1` 추가 | BPS .xls 구형 |
| `daily_collect.yml` | geo 스텝 **뒤에** `python market_tagger.py` 스텝 추가 + `git add market_flags.csv data/market/context_latest.json` | Phase 3. geo 워크플로 스텝이 먼저 있어야 함 |
| `index.html` | (a) 기사 카드에 시장 맥락 칩 (b) `renderTrendCharts()` 하드코딩 → JSON | Phase 4 |

---

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

### 3.4 `market_flags.csv` (렌즈, 루트)

| 컬럼 | 설명 |
|---|---|
| `article_id` | articles.csv 키 |
| `cbsa_code` | geo_tags.csv의 `geo_cbsa_code`를 `\|`로 분리한 **각각** — 기사 1건이 CBSA 2개면 2행 |
| `as_of` | `YYYY-MM`. 기사 `published_at` 기준 **직전 완결월** (BPS 공표 지연 반영) |
| `coverage` | `ok` / `low_volume` / `no_data` / `not_applicable` |
| `units_12m` | int 또는 빈값 |
| `units_avg3y` | float 또는 빈값 |
| `ratio_12m_vs_3y` | float 또는 빈값 |
| `flags` | `\|` 구분. 빈값 가능. 예: `supply_drought` |
| `rule_version` | `v1` |
| `tagged_at` | ISO8601 |

- `geo_scope ∉ {metro, local}` → `coverage=not_applicable`, flags 빈값. 전국 기사가 Atlanta를 스치는 경우 차단 (geo research §5.4 계승)
- `geo_cbsa_code` 빈값 → 행을 만들지 않는다

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
      "expected_completion": {"lag_months": 17.5, "bucket": "20+", "by_quarter": {"2027Q4": 2310, "2028Q1": 1980, "2028Q2": 1750, "2028Q3": 2100}}
    }
  }
}
```

- 전 CBSA 포함 (Q3 전수). 약 900 × 36개월 ≈ 1.5MB. 화면은 관심 목록만 그린다
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


def parse_bps(path: Path) -> pd.DataFrame:
    x = pd.ExcelFile(path, engine="xlrd")
    units = x.parse("MSA Units", header=None)
    value = x.parse("MSA Value", header=None)
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
    if period.endswith("-01"):
        bad = out[out.u5_units != out.u5_units_ytd]
    else:
        bad = out[out.u5_units > out.u5_units_ytd]
    if len(bad):
        raise ValueError(f"{path.name}: 월간 > YTD {len(bad)}행 — 열 탐색 오류 의심")
    return out[BPS_COLS]


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
VOLUME_FLOOR     = 300     # 3년 평균 연간 5+유닛 하한 (초안). Phase 2.2 실측 분포로 보정
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
THRESH = dict(surge=1.30, drought=0.70)   # Phase 1 실측 분포로 보정 (§7.3)

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

규칙 추가 절차(M2): 이 파일 상단 주석에 `# RULES: S1 S2 S3` 목록을 유지하고, 추가 시 `RULE_VERSION`을 올린다.

### 4.4 `market_tagger.py`

```python
"""geo_tags.csv × market_context → market_flags.csv + context_latest.json.
daily_collect.yml에서 geo 스텝 뒤에 실행. 멱등: 이미 같은 rule_version으로 태깅된 행은 스킵."""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from market_context import compute, expected_completion, region_map, RULE_VERSION
from market_rules import judge

GEO      = Path("geo_tags.csv")
ART      = Path("articles.csv")
BPS      = Path("data/market/bps_cbsa.csv")
SOC      = Path("data/market/soc_lag.csv")
STREG    = Path("data/market/state_region.csv")
OUT_CSV  = Path("market_flags.csv")
OUT_JSON = Path("data/market/context_latest.json")
FLAG_COLS = ["article_id","cbsa_code","as_of","coverage","units_12m",
             "units_avg3y","ratio_12m_vs_3y","flags","rule_version","tagged_at"]
APPLICABLE_SCOPES = {"metro", "local"}


def as_of_for(published_at: str) -> str:
    dt = pd.to_datetime(published_at, errors="coerce", utc=True)
    if pd.isna(dt): return ""
    m = dt.to_period("M") - 2            # 직전 완결월 (§4.2 트레이드오프)
    return str(m)


def load():
    bps = pd.read_csv(BPS, dtype={"cbsa_code": str, "period": str})
    soc = pd.read_csv(SOC) if SOC.exists() else None
    streg = pd.read_csv(STREG)
    return bps, soc, streg


def tag_articles(bps, soc, region_of) -> pd.DataFrame:
    geo = pd.read_csv(GEO, dtype=str).fillna("")
    art = pd.read_csv(ART, dtype=str, usecols=["article_id","published_at"]).fillna("")
    g = geo.merge(art, on="article_id", how="inner")
    done = set()
    if OUT_CSV.exists():
        prev = pd.read_csv(OUT_CSV, dtype=str).fillna("")
        done = set(zip(prev.article_id, prev.cbsa_code, prev.rule_version))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for r in g.itertuples(index=False):
        if not r.geo_cbsa_code: continue
        for cbsa in r.geo_cbsa_code.split("|"):
            cbsa = cbsa.strip()
            if not cbsa or (r.article_id, cbsa, RULE_VERSION) in done: continue
            as_of = as_of_for(r.published_at)
            if r.geo_scope not in APPLICABLE_SCOPES or not as_of:
                rows.append(dict(article_id=r.article_id, cbsa_code=cbsa, as_of=as_of,
                                 coverage="not_applicable", units_12m="",
                                 units_avg3y="", ratio_12m_vs_3y="", flags="",
                                 rule_version=RULE_VERSION, tagged_at=now))
                continue
            c = compute(cbsa, as_of, bps, soc, region_of)
            rows.append(dict(article_id=r.article_id, cbsa_code=cbsa, as_of=as_of,
                             coverage=c.coverage,
                             units_12m=c.units_12m or "", units_avg3y=c.units_avg3y or "",
                             ratio_12m_vs_3y=c.ratio_12m_vs_3y or "",
                             flags="|".join(judge(c)), rule_version=RULE_VERSION, tagged_at=now))
    new = pd.DataFrame(rows, columns=FLAG_COLS)
    new.to_csv(OUT_CSV, mode="a" if OUT_CSV.exists() else "w",
               header=not OUT_CSV.exists(), index=False)
    return new


def dump_context(bps, soc, region_of) -> None:
    as_of = str(pd.to_datetime(bps.period).max().to_period("M"))
    names = bps.drop_duplicates("cbsa_code").set_index("cbsa_code").cbsa_name.to_dict()
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "as_of": as_of, "rule_version": RULE_VERSION, "cbsa": {}}
    for code in sorted(names):
        c = compute(code, as_of, bps, soc, region_of)
        m = (bps[bps.cbsa_code == code].sort_values("period").tail(36)
             [["period","u5_units"]].to_dict("records"))
        out["cbsa"][code] = {**c.to_dict(), "name": names[code], "flags": judge(c),
                             "monthly": m,
                             "expected_completion": {"lag_months": c.lag_months, "bucket": "20+",
                                                     "by_quarter": expected_completion(code, bps, c.lag_months)}}
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    bps, soc, streg = load()
    region_of = region_map(bps, streg)
    if GEO.exists():
        n = tag_articles(bps, soc, region_of)
        print(f"market_flags +{len(n)}행")
    else:
        print("geo_tags.csv 없음 — 기사 태깅 스킵, context만 생성")
    dump_context(bps, soc, region_of)
    print(f"context_latest.json 생성 ({OUT_JSON.stat().st_size//1024}KB)")
```

**트레이드오프**
- geo_tags.csv 없을 때 스킵하고 context만 만든다 → **geo 전에 Phase 1~2·4를 끝낼 수 있다** (research §7)
- 멱등 키에 `rule_version` 포함: 규칙을 올리면 전 기사가 자동 재태깅. 과거 행은 남는다 (M3)
- 기사당 CBSA 다중 행: 집계 쉬움. 화면은 article_id로 묶어 칩 여러 개

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
          git add data/market/ market_flags.csv
          git diff --cached --quiet && echo "변경 없음" || (git commit -m "auto: market data $(date +%Y-%m)" && git pull --rebase origin main && git push)
```
- `daily_collect`(21:00 UTC)·`weekly_report`(일 23:00 UTC)와 시각이 겹치지 않는다 (A1 교훈)

**`daily_collect.yml` 수정** (Phase 3 — geo 스텝이 들어간 뒤)
```yaml
      - name: Market tagging
        run: python market_tagger.py
      # Commit 스텝의 git add에 추가: market_flags.csv data/market/context_latest.json
```

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

### 4.8 `index.html` (Phase 4)

**(a) 기사 카드 칩** — 기존 `woomi_relevance` 칩 **옆에** 추가. 합산 없음 (M1)
```javascript
const FLAGS_URL = "https://raw.githubusercontent.com/jaehongbr-Coding/us-residential-v2/main/market_flags.csv";
const FLAG_LABEL = { supply_surge:"공급 급증", supply_drought:"공급 감소", unknown:"시장맥락 판정불가" };
// Papa.parse(FLAGS_URL) → byArticle: Map<article_id, [{cbsa_code, flags, ratio_12m_vs_3y, coverage}]>
// 카드 렌더 시:
//   <span class="chip chip-rel">높음</span>
//   <span class="chip chip-mkt" title="BPS 5+유닛 12m 9,120 / 3y평균 14,830 = 0.62">공급 감소 · ATL</span>
// coverage=not_applicable 이면 칩 생략. unknown 이면 회색 칩 "판정불가(물량 부족)"
```

**(b) 마켓워치** — `renderTrendCharts()`의 하드코딩 3개 차트 중 **차트 1·2는 유지**(뉴스 통계, 별건), **차트 3 자리에** 시장 차트를 넣고 섹션 제목을 "마켓워치"로
```javascript
const CTX_URL = ".../data/market/context_latest.json";
const WATCH = ["12060","19100","31080","42660","19740","38060","17860"]; // ATL DFW LA SEA DEN PHX Columbia MO
// 셀렉트 박스로 CBSA 선택 → monthly 36개월 bar(u5_units) + 12개월 이동합 line
// 상단 요약: ratio_12m_vs_3y, coverage, flags, expected_completion.by_quarter
// 고정 문구: "준공 예상은 SOC 지역 평균 lag(bucket 20+) 적용 추정치. 미착공·취소 미반영."
// 색: #1B3A5C(월간) #2E75B6(12m 이동합) — 기존 팔레트
```
- I6(geo 필터 UI 미노출) 유지: 기사 목록에 CBSA 필터를 넣지 않는다. 칩 표시만

---

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
- Phase 3: `daily_collect.yml`에서 스텝 제거, `market_flags.csv` 삭제. geo_tags.csv 무관
- Phase 4: `index.html` 해당 커밋 revert. 칩·차트만 사라짐
- 모든 단계가 **독립 커밋**이므로 `git revert <sha>` 단위로 되돌린다

---

## 7. To-Do (승인 후 순차 실행 — 각 단계 독립 커밋, 검증·보고 후 다음)

### Phase 0 — 진단 (구현 아님)
- [ ] 0.1 `requirements.txt`에 `xlrd>=2.0.1` 추가 — 커밋 `chore: xlrd 추가 (BPS .xls 파싱)`
- [ ] 0.2 `diagnose_market.py` + `diagnose_market.yml` — 커밋 `diag: 시장 데이터 소스 진단 워크플로`
- [x] 0.3 Actions 수동 실행 → 로그 전문 → **Plan v0.2** (완료 2026-10-15: 4 URL 200, 헤더명 탐색으로 전환, SOC 파서 확정, rep→volume floor)

### Phase 1 — 수집 (geo 무관)
- [ ] 1.1 `data/market/state_region.csv` 51행 — 커밋 `data: state→Census Region 정적 테이블`
- [ ] 1.2 `market_collect.py` (bps) + `tests/test_market_parse.py` + fixtures 2파일(202608, 202312) — 커밋 `feat: BPS 월간 CBSA 수집기`
- [ ] 1.3 로컬에서 `python market_collect.py bps` 백필 (2019-11~2026-08, 약 82파일) → `data/market/raw/`·`bps_cbsa.csv`·log 커밋 `data: BPS 백필 2019-11~2026-08`
  - 검증: 2024+ 32파일 × ~929 + 2019-11~2023-12 50파일 × ~393 ≈ 49,400행, Atlanta 12060 82개월 전부 존재, 월간 ≤ YTD 전수, (period, cbsa) 중복 0
- [ ] 1.4 `market_collect.py` (soc) — 커밋 `feat: SOC 소요기간 수집기` + `data/market/soc_lag.csv`
  - 검증: 2025 South 2+ = 17.5, 20+ = 21.8 (assert 내장). 행수 = 연도(1971~2025 중 유효) × 5 region × 5 bucket
- [ ] 1.5 `monthly_market.yml` — 커밋 `ci: 월간 시장 데이터 수집 워크플로`

### Phase 2 — 판정 (geo 무관)
- [ ] 2.0 **수집기 보정** (Phase 1 피드백): (a) `collect_bps` 종료월 `month-2`→`month-1` (b) `collect_soc` sha256 멱등 (c) `monthly_market.yml` cron 26→29일 — 커밋 `fix: 수집기 종료월·SOC 멱등·cron 조정`
- [ ] 2.1 `market_context.py` + `tests/test_market_context.py` — 커밋 `feat: 시장 상태 계산 (순수)`
- [ ] 2.2 **임계값 보정**: 전 CBSA 2026-08 기준 (a) units_avg3y 분포(분위수 10/25/50/75/90) → VOLUME_FLOOR 확정. 관심 7개 CBSA의 coverage 결과를 **기록**하되 **하한을 그들에 맞추지 않는다** (Columbia MO 271 → low_volume 예상, 그대로 둠) (b) ok인 CBSA의 ratio 분포 → 상·하위 20% 지점으로 THRESH 확정 → Plan v0.4 기록
  - 사전 실측 (2026-08, 48개월 창): ATL 0.913 / DFW 0.912 / LA 1.461 / SEA 1.330 / DEN 0.847 / PHX 0.875 / Columbia MO 1.080(avg3y 271)
- [ ] 2.3 `market_rules.py` + `tests/test_market_rules.py` — 커밋 `feat: 시장 맥락 규칙 S1~S3`
- [ ] 2.4 `market_tagger.py` (geo 없을 때 context만) → `context_latest.json` — 커밋 `feat: 시장 context 덤프`
  - 검증: 관심 7개 CBSA의 coverage·ratio·flags를 표로 보고

### Phase 3 — 기사 태깅 (**geo_tags.csv 존재 후**)
- [ ] 3.1 geo 백필 완료 확인
- [ ] 3.2 `python market_tagger.py` → `market_flags.csv` 소급 생성 — 커밋 `data: market_flags 백필`
  - 검증: 행수, coverage 분포, flags 분포, `woomi_relevance`×flags 교차표 보고
- [ ] 3.3 `daily_collect.yml`에 스텝 추가 — 커밋 `ci: daily에 market tagging 추가`

### Phase 4 — 화면
- [ ] 4.1 마켓워치 차트 (context_latest.json) — 커밋 `feat(ui): 마켓워치 BPS 차트`
- [ ] 4.2 기사 카드 시장 맥락 칩 — 커밋 `feat(ui): 시장 맥락 칩`
- [ ] 4.3 스크린샷 → 공모전 증빙 6번용 보관

### Phase 5 — 정리
- [ ] 5.1 research_market.md 정정 3건: §4.1.3 보고분 열 부재→물량 하한 / §4.2.5 "South가 짧다"는 2+ 전체(17.5 vs West 20.6)에서만 성립하고 **20+ 구간은 South 21.8 ≈ West 22.6**, 최단은 Midwest 17.6 / §9 결정·실측 임계값
- [ ] 5.2 공모전 Before/After 지표 1행 작성: "공급 판정 근거: 기사 건수 → BPS 5+유닛 허가 12m합 / 3y평균, 보고율 표기"

---

## 8. 검토 요청 (사용자 확인)

| # | 항목 | 기본안 |
|---|---|---|
| C1 | 관심 CBSA 7개 목록(§4.8) 적정한가 — Houston(26420)·Charlotte(16740) 추가? | 7개 유지, 필요 시 상수 1줄 |
| C2 | 기사 카드 칩 문구: "공급 감소" vs "supply_drought" 원문 | 한글 라벨 + title 속성에 수치 |
| C3 | Phase 3을 geo보다 먼저 할 방법은 없다 — geo 착수 시점 확인 | — |
| C4 | ~~SOC 파서~~ 확정됨 | — |
| C5 | `metro_micro` 코드 의미(Atlanta=2, Aberdeen SD=5)를 Census 문서로 확인 — 2=Metro, 5=Micro 추정 [추정]. 화면 필터에 쓰기 전 확인 | Phase 4 전 확인 |
| C6 | 2019-11~2021-12 파일의 `Monthly Coverage Percent*` 열 재파싱 여부 — 백필 구간 기저선 신뢰도 참고용. 현재 판정에는 미사용 | Phase 5 검토, 기본 보류 |

---

## 9. 문서 이력

| 버전 | 일자 | 변경 |
|---|---|---|
| v0.1 | 2026-10-15 | 최초 작성. research_market §9 기본안 전부 채택. geo Plan.md I1~I8 계승 + M1~M7 추가 |
| v0.3 | 2026-10-15 | Phase 1 완료 반영. ① 시트명 연도별 차이(`_pick_sheet`) ② 행수 실측 368/384/921 ③ 이상값 정책 확정(1% 임계, `bps_anomalies.csv`) ④ Columbia MO avg3y 271 → `low_volume` 유지 결정, 2.2 문구를 "맞추지 않는다"로 수정 ⑤ SOC 20+ 지역 격차 실측(NE 25.7 / MW 17.6 / S 21.8 / W 22.6 / US 21.7) — research §4.2.5 Sun Belt 논거 정정 필요 ⑥ Phase 2.0 추가(종료월 month-1, SOC sha256 멱등, cron 29일) ⑦ C6 추가 |
| v0.2 | 2026-10-15 | Phase 0 진단 반영. ① 4 URL 200 → 자동 수집 확정 ② BPS 월간 파일에 보고분(rep)·MONCOV 없음 → `rep_share`/`imputed` 폐기, `VOLUME_FLOOR`/`low_volume`로 교체 (M6 수정) ③ 2024+ 파일 `Metro /Micro Code` 열 삽입으로 열 위치 밀림 → 헤더명 탐색 ④ 2023 이전 Metro만 393행, 2024+ Metro+Micro 929행 ⑤ SOC 파서 확정(행4~5 2단 헤더, 열5~9, 검증값 South 2025 2+ 17.5 / 20+ 21.8) ⑥ 실측값 Atlanta 2026-08 u5=875/YTD 8,361, 2023-12 u5=440/YTD 14,227 |
