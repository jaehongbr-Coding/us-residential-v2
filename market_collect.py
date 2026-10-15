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
    end = end or ((today.year, today.month - 2) if today.month > 2 else (today.year - 1, today.month + 10))
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
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    parts = []
    for k, url in SOC_URLS.items():
        dest = RAW_DIR / f"soc_{k}.xlsx"
        if dest.exists(): dest.unlink()    # 연 1회 전체 갱신
        download(url, dest)
        parts.append(_parse_soc_file(dest, k))
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
