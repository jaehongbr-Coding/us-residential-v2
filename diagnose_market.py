"""일회성. (1) Actions 러너에서 census.gov 접근 가능한지 (2) BPS xls 실제 열 구조
(3) SOC xlsx 시트·행 구조를 출력. 아무 파일도 쓰지 않는다(권한 read). print만 한다."""
import io
import time

import pandas as pd
import requests

pd.set_option("display.width", 400)
pd.set_option("display.max_columns", None)
pd.set_option("display.max_colwidth", 60)

H = {"User-Agent": "Mozilla/5.0 (compatible; WoomiGlobalResearchBot/2.0)"}
U = ["https://www.census.gov/construction/bps/xls/cbsamonthly_202608.xls",
     "https://www.census.gov/construction/bps/xls/msamonthly_202312.xls",
     "https://www.census.gov/construction/nrc/xls/avg_authtostart_cust.xlsx",
     "https://www.census.gov/construction/nrc/xls/avg_starttocomp_cust.xlsx"]


def diagnose_bps(df: pd.DataFrame) -> None:
    # (a) Atlanta(12060) 포함 행 전체
    hit = df[df.astype(str).apply(lambda c: c.str.contains("12060", regex=False)).any(axis=1)]
    print(f"--- (a) Atlanta(12060) 행: {len(hit)}건")
    print(hit.to_string())
    # (b) 첫 열이 6자리 숫자(YYYYMM)인 행 수
    is_data = df.iloc[:, 0].astype(str).str.strip().str.fullmatch(r"\d{6}(\.0)?")
    print(f"--- (b) 첫 열 YYYYMM 데이터 행 수: {int(is_data.sum())}")
    # (c) 첫 데이터 행의 모든 열 (열 위치 확정용)
    if is_data.any():
        first = df[is_data].iloc[0]
        print(f"--- (c) 첫 데이터 행 (원본 행 인덱스 {first.name}) 열별 값:")
        for i, v in enumerate(first.tolist()):
            print(f"  [{i:2d}] {v!r}")
    else:
        print("--- (c) 데이터 행 없음")


for idx, u in enumerate(U):
    if idx > 0:
        time.sleep(1.0)
    print("=" * 100)
    try:
        r = requests.get(u, headers=H, timeout=30)
    except Exception as e:
        print(u, "REQUEST FAILED", type(e).__name__, str(e))
        continue
    print(u, "status", r.status_code, "bytes", len(r.content))
    if r.status_code != 200:
        print("  content-type:", r.headers.get("Content-Type"))
        print("  body head:", r.content[:300])
        continue
    is_bps = "cbsamonthly" in u or "msamonthly" in u
    eng = "xlrd" if u.endswith(".xls") else "openpyxl"
    try:
        x = pd.ExcelFile(io.BytesIO(r.content), engine=eng)
    except Exception as e:
        print("  EXCEL OPEN FAILED", type(e).__name__, str(e))
        print("  body head:", r.content[:300])
        continue
    print("sheets:", x.sheet_names)
    for sh in x.sheet_names:
        try:
            df = x.parse(sh, header=None)
        except Exception as e:
            print(f"--- sheet {sh!r} PARSE FAILED", type(e).__name__, str(e))
            continue
        print(f"--- sheet {sh!r} shape {df.shape}")
        if is_bps:
            print(df.head(12).to_string())
            try:
                diagnose_bps(df)
            except Exception as e:
                print("  BPS DIAGNOSE FAILED", type(e).__name__, str(e))
        else:
            print(df.to_string())
