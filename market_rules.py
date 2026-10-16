"""시장 상태 → flag 목록. 규칙은 6개 상한 (M2). 결정론."""
# RULES: S1 supply_surge / S2 supply_drought / S3 unknown — 상한 6 (M2)
from market_context import MarketContext

RULE_VERSION = "v1"

# 판정 결과의 한국어 표시 라벨 — 정본은 여기 하나 (2026-10-16 측정 사실 기준으로 변경).
# market_report·weekly_report 사후검사·context_latest.json "labels"·index.html(LABELS_KO)이 같은 맵을 쓴다.
# 규칙 ID는 그대로다. "flat"은 판정 가능(ok)하나 S1·S2 어디에도 해당하지 않는 경우(flags 빈 목록)의 표시용 ID.
LABELS_KO = {
    "flat": "평균 수준",
    "supply_surge": "허가 급증",
    "supply_drought": "허가 급감",
    "unknown": "판정 제외",
}
THRESH = dict(surge=1.25, drought=0.75)   # 2026-10-15 실측 (VOLUME_FLOOR 1000, 80 CBSA) p80/p20 근방


def judge(ctx: MarketContext) -> list[str]:
    if ctx.coverage in ("no_data", "low_volume"):  return ["unknown"]   # S3
    flags = []
    r = ctx.ratio_12m_vs_3y
    if r is None:                  return ["unknown"]                   # S3
    if r >= THRESH["surge"]:       flags.append("supply_surge")    # S1
    if r <= THRESH["drought"]:     flags.append("supply_drought")  # S2
    # S4 completion_wave — Phase 2 (ACS 재고 필요)
    # T1 absorption_slow, T2 rent_soft — Phase 2
    return flags
