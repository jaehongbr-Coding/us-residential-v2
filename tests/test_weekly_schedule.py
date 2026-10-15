"""weekly_report KST 날짜·중복 가드 테스트 (실행 시각 재설계 2026-10-16). API 호출 없음."""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import weekly_report  # noqa: E402

# 월 04:47 KST = 일 19:47 UTC — UTC 날짜로 찍으면 전날(일요일)이 된다
MON_0447_KST = datetime(2026, 10, 19, 4, 47)


def test_now_kst_is_seoul():
    assert weekly_report.KST.utcoffset(datetime(2026, 10, 19)).total_seconds() == 9 * 3600


def test_report_filename_uses_kst_date(tmp_path, monkeypatch):
    monkeypatch.setattr(weekly_report, "REPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(weekly_report, "_now_kst", lambda: MON_0447_KST)
    md = Path(weekly_report.save_report("본문", "weekly"))
    docx = Path(weekly_report.save_report_docx("## 1. 개발 현황\n- x", "weekly"))
    assert md.name == "20261019_weekly.md" and docx.name == "20261019_weekly.docx"
    assert "기간: 2026-10-12 ~ 2026-10-19 (주간)" in md.read_text(encoding="utf-8")


def test_skip_guard(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(weekly_report, "REPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(weekly_report, "_now_kst", lambda: MON_0447_KST)
    assert weekly_report.report_exists_today("weekly") is False
    (tmp_path / "20261018_weekly.md").write_text("전날", encoding="utf-8")       # UTC 날짜 파일은 오늘이 아니다
    assert weekly_report.report_exists_today("weekly") is False
    (tmp_path / "20261019_weekly.md").write_text("주 cron 산출", encoding="utf-8")
    assert weekly_report.report_exists_today("weekly") is True

    # main(--skip-if-exists)은 기사 로드·API 호출 전에 끝나야 한다
    monkeypatch.setattr(weekly_report, "load_articles", lambda: (_ for _ in ()).throw(AssertionError("로드하면 안 됨")))
    monkeypatch.setattr(sys, "argv", ["weekly_report.py", "--period", "weekly", "--export", "docx", "--skip-if-exists"])
    weekly_report.main()
    assert "[SKIP]" in capsys.readouterr().out
