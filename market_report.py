"""주간 리포트용 시장 데이터(공급) 섹션 — context_latest.json → markdown 표.

순수 함수. 네트워크·DB 접근 없음 (M4). 판정은 context_latest.json에 이미 들어 있는
market_rules 결과를 라벨로 옮길 뿐, 여기서 새로 판단하지 않는다. 파일이 없거나 깨져도
예외를 올리지 않고 '시장 데이터 없음' 섹션을 돌려준다 — 리포트 생성이 깨지면 안 된다 (M9).
"""
from __future__ import annotations
import json
from pathlib import Path

from market_context import WATCH
from market_rules import LABELS_KO   # 판정 라벨 정본 (index.html LABELS_KO 와 동일 — 테스트로 강제)

SECTION_TITLE = "## 시장 데이터(공급) — WATCH 7"
NO_DATA = f"{SECTION_TITLE}\n\n시장 데이터 없음(context_latest.json 미확인)\n"
EXCLUDED = LABELS_KO["unknown"]
COMPLETION_YEAR = "2027"


def _verdict(c: dict) -> str:
    cov = c.get("coverage")
    if cov == "ok":
        flags = c.get("flags") or []
        for f in ("supply_surge", "supply_drought"):
            if f in flags:
                return LABELS_KO[f]
        return LABELS_KO["flat"]
    return f"{EXCLUDED}(물량 부족)" if cov == "low_volume" else f"{EXCLUDED}(데이터 없음)"


def _num(v) -> str:
    return f"{int(round(v)):,}" if isinstance(v, (int, float)) else "—"


def _completion(c: dict) -> str:
    bq = ((c.get("expected_completion") or {}).get("by_quarter")) or {}
    vals = [v for q, v in bq.items() if str(q).startswith(COMPLETION_YEAR) and isinstance(v, (int, float))]
    return f"{int(sum(vals)):,}" if vals else "—"


def _watch_list(data: dict) -> list[tuple[str, str]]:
    w = data.get("watch")
    if isinstance(w, list) and w:
        try:
            return [(str(x["code"]), str(x.get("short") or x["code"])) for x in w]
        except (KeyError, TypeError):
            pass
    return list(WATCH)


def build_market_labels(context_path: str = "data/market/context_latest.json") -> str | None:
    """LLM 참조용 라벨 한 줄 — 'ATL 평균 수준 · DFW 평균 수준 · … · COMO 판정 제외'. 수치는 넣지 않는다.
    데이터가 없으면 None (참조 블록 생략)."""
    try:
        data = json.loads(Path(context_path).read_text(encoding="utf-8"))
        cbsa = data["cbsa"]
        if not isinstance(cbsa, dict):
            return None
        parts = []
        for code, short in _watch_list(data):
            c = cbsa.get(code) or {}
            v = _verdict(c) if c else EXCLUDED
            parts.append(f"{short} {EXCLUDED if v.startswith(EXCLUDED) else v}")
        return " · ".join(parts)
    except Exception:
        return None


def build_market_table(context_path: str = "data/market/context_latest.json") -> str | None:
    """시장 표(헤더+구분선+7행)만 — md 섹션 확인용. 데이터가 없으면 None."""
    md = build_market_section(context_path)
    if md == NO_DATA:
        return None
    return "\n".join(ln for ln in md.splitlines() if ln.startswith("|"))


def build_market_section(context_path: str = "data/market/context_latest.json") -> str:
    try:
        data = json.loads(Path(context_path).read_text(encoding="utf-8"))
        as_of, rule_version, cbsa = data["as_of"], data["rule_version"], data["cbsa"]
        if not isinstance(cbsa, dict):
            return NO_DATA
        rows = []
        for code, short in _watch_list(data):
            c = cbsa.get(code) or {}
            name = (c.get("name") or "").strip()
            region = f"{short} · {name}" if name else short
            verdict = _verdict(c) if c else f"{EXCLUDED}(데이터 없음)"
            if c.get("coverage") == "ok":
                ratio = c.get("ratio_12m_vs_3y")
                cells = [_num(c.get("units_12m")), _num(c.get("units_avg3y")),
                         f"{ratio:.2f}" if isinstance(ratio, (int, float)) else "—", verdict, _completion(c)]
            else:
                cells = ["—", "—", "—", verdict, "—"]
            rows.append(f"| {region} | " + " | ".join(cells) + " |")
    except Exception:   # 파일 없음·JSON 깨짐·필수 키 없음 — 리포트는 계속 생성돼야 한다
        return NO_DATA

    head = (f"| 지역 | 12개월 허가(5+유닛) | 3년 평균 | 비율 | 판정 | {COMPLETION_YEAR} 예상 준공 |\n"
            "|---|---|---|---|---|---|")
    foot = (f"기준월 {as_of} · 규칙 {rule_version} · 출처 Census BPS·SOC\n\n"
            "준공 예상은 SOC 지역 평균 lag(20+유닛) 적용 추정치 — 미착공·취소 미반영. "
            "판정불가는 3년 평균 1,000유닛/년 미만 또는 데이터 없음.")
    return f"{SECTION_TITLE}\n\n{head}\n" + "\n".join(rows) + f"\n\n{foot}\n"
