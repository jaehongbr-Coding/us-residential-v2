"""시장 상태 → flag 목록. 규칙은 6개 상한 (M2). 결정론."""
# RULES: S1 supply_surge / S2 supply_drought / S3 unknown — 상한 6 (M2)
from market_context import MarketContext

RULE_VERSION = "v1"
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
