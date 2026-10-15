"""market_report 시장 섹션 + weekly_report docx 표 분기 테스트. API 호출 없음."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import weekly_report  # noqa: E402
from market_context import WATCH  # noqa: E402
from market_report import build_market_section  # noqa: E402

CTX = ROOT / "data" / "market" / "context_latest.json"


def _rows(md):
    return [ln for ln in md.splitlines() if ln.startswith("|") and not ln.startswith("|---")][1:]   # 헤더 제외


def test_real_context_seven_rows_and_low_volume():
    md = build_market_section(str(CTX))
    rows = _rows(md)
    assert len(rows) == 7
    como = next(r for r in rows if r.startswith("| COMO"))
    assert [c.strip() for c in como.strip("|").split("|")][1:] == ["—", "—", "—", "판정불가(물량 부족)", "—"]
    assert "기준월 " in md and "출처 Census BPS·SOC" in md and "미착공·취소 미반영" in md


def test_missing_file_no_exception(tmp_path):
    md = build_market_section(str(tmp_path / "nope.json"))
    assert "시장 데이터 없음" in md and "|" not in md


def test_broken_json_no_exception(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text('{"as_of": "2026-08", "cbsa": {', encoding="utf-8")
    md = build_market_section(str(p))
    assert "시장 데이터 없음" in md and "|" not in md


def test_no_watch_key_falls_back_to_constant(tmp_path):
    d = json.loads(CTX.read_text(encoding="utf-8"))
    d.pop("watch", None)
    p = tmp_path / "nowatch.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    rows = _rows(build_market_section(str(p)))
    assert [r.split("|")[1].strip().split(" · ")[0] for r in rows] == [s for _, s in WATCH]


def test_insert_before_implications_or_append():
    sec = "## 시장 데이터(공급) — WATCH 7\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    with_h = "## 1. 개발 현황\n- x\n\n## 4. 시사점 (우미글로벌 관점)\n- y"
    out = weekly_report.insert_market_section(with_h, sec)
    assert out.index("## 시장 데이터") < out.index("## 4. 시사점") and out.endswith("- y")
    without_h = "## 1. 개발 현황\n- x"
    out2 = weekly_report.insert_market_section(without_h, sec)
    assert out2.startswith(without_h) and out2.rstrip().endswith("| 1 | 2 |")


def test_reference_block_skipped_without_data(monkeypatch):
    import market_report
    monkeypatch.setattr(market_report, "build_market_table", lambda *a, **k: None)
    assert weekly_report.market_reference_block() == ""
    monkeypatch.setattr(market_report, "build_market_table", lambda *a, **k: "| t |\n|---|\n| 1 |")
    blk = weekly_report.market_reference_block()
    assert "--- 참고: 시장 데이터(공급) ---" in blk and "| 1 |" in blk and "다시 쓰지 말라" in blk


def test_region_tokens_missing_db(tmp_path):
    assert weekly_report.load_watch_regions(["a1"], db_path=str(tmp_path / "none.db")) == {}
    arts = [{"article_id": "a1", "title": "T", "summary": "S", "event_tags": "x"}]
    assert weekly_report.format_articles(arts) == weekly_report.format_articles(arts, {})
    assert weekly_report.format_articles(arts, {"a1": "LA"}).endswith("태그: x [지역: LA]")


def test_docx_table_branch_and_fallback(tmp_path, monkeypatch):
    from docx import Document
    monkeypatch.setattr(weekly_report, "REPORTS_DIR", str(tmp_path))
    md = ("## 섹션\n\n일반 문단입니다.\n\n"
          "| 지역 | 비율 |\n|---|---|\n| ATL | 0.91 |\n\n"
          "| 깨진 | 표 |\n| 셀 하나 |\n")
    path = weekly_report.save_report_docx(md, "weekly")
    doc = Document(path)
    assert len(doc.tables) == 1
    t = doc.tables[0]
    assert (len(t.rows), len(t.columns)) == (2, 2)
    assert t.cell(0, 0).text == "지역" and t.cell(1, 1).text == "0.91"
    assert t.cell(0, 0).paragraphs[0].runs[0].bold is True
    texts = [p.text for p in doc.paragraphs]
    assert "일반 문단입니다." in texts
    assert "| 깨진 | 표 |" in texts and "| 셀 하나 |" in texts   # 셀 수 불일치 → 텍스트 폴백
