"""
US Residential Intelligence v2 — geo_tagger.py
geo Phase 2 — Stage A(Claude Haiku, Batch API) + Stage B(geo_resolver) 오케스트레이션.

원장(archive/) 전체를 대상으로 한다 — 작업본(articles.csv)이 아니다.
결과는 articles.csv/archive/labels.db 어디에도 쓰지 않고 geo_tags.db
사이드카에만 쓴다(I2, I3).

사용법:
  python geo_tagger.py --mode sample --limit 50       # 육안 검수용 (기본값)
  python geo_tagger.py --mode sample --limit 50 --article-ids-file ids.txt
                                                        # 특정 article_id만 표본으로
  python geo_tagger.py --mode backfill                 # 원장 전체 중 미태깅분
  python geo_tagger.py --mode incremental              # 일일 운영용, 미태깅분만
  python geo_tagger.py --mode resolve-only             # API 재호출 없이 Stage B만 재실행
  python geo_tagger.py --mode backfill --dry-run       # 대상 건수만 출력

⚠️ 실행 전 반드시 `git pull --no-rebase` (CLAUDE.md 규칙)
⚠️ 동일 스크립트 중복 실행 금지 — Batch API에 중복 배치가 쌓인다 (CLAUDE.md 규칙).
   배치 제출 전 계정에 in_progress 배치가 있으면 제출하지 않고 경고 후 종료한다.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import anthropic
from dotenv import load_dotenv

import archive_manager
import geo_store
from geo_resolver import resolve

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ------------------------------------------------------------------
# 1. 설정
# ------------------------------------------------------------------

MODEL = "claude-haiku-4-5-20251001"   # classifier(Sonnet 4.6)와 의도적으로 분리
BATCH_ID_FILE = "current_geo_batch_id.txt"
MAX_TOKENS = 600

# Plan.md §5.3 그대로 사용. ⚠️ I4: category/event_tags/sector/signal_type/
# woomi_relevance 등 기존 분류체계 용어를 언급하지 않는다.
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

_SHOTS_TEXT = "\n\n".join(f"TEXT:\n{i}\n\nJSON:\n{o}" for i, o in GEO_FEWSHOT)

# few-shot은 기사별로 달라지지 않는 고정 텍스트다 — GEO_SYSTEM_PROMPT 뒤에 붙여
# system 블록 전체를 캐시 대상으로 만든다. 이 결합 문자열의 끝이 곧 캐시
# 브레이크포인트(변하지 않는 접두부의 끝)이며, 그 뒤(user 메시지)부터는
# 기사마다 달라지는 내용만 온다.
GEO_SYSTEM_FULL = f"{GEO_SYSTEM_PROMPT}\n\n{_SHOTS_TEXT}"


def _strip_fence(t: str) -> str:
    """CLAUDE.md 기록된 기존 버그 대응 — 코드펜스 제거 (classifier.py와 동일 관례)."""
    text = t.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1].lstrip("json").strip() if len(parts) >= 2 else text
    return text.strip()


def build_geo_prompt(article: dict) -> str:
    """few-shot은 GEO_SYSTEM_FULL(system 블록)로 옮겨졌으므로 기사 본문만 담는다."""
    text = f"{article.get('title', '')}\n\n{article.get('summary', '')}".strip()[:4000]
    return f"TEXT:\n{text}\n\nJSON:"


# ------------------------------------------------------------------
# 2. 대상 선정
# ------------------------------------------------------------------

def _dedupe_by_article_id(rows: list[dict]) -> list[dict]:
    """원장에 남아있는 article_id 완전 중복 23건(CLAUDE.md TODO #9 잔여분,
    title/summary/source가 달라 정리 대상에서 제외됐던 것) 방어.
    Batch API는 같은 배치 안에 custom_id 중복을 허용하지 않아 그대로 두면
    batches.create() 자체가 400으로 거부된다(2026.09 백필 1차 시도 실패 원인).
    article_id당 collected_at이 가장 이른 행 하나만 남긴다 — dedupe_duplicates.py가
    실제 원장 중복을 정리할 때 쓴 것과 동일한 기준."""
    by_id: dict[str, dict] = {}
    for r in rows:
        aid = r["article_id"]
        existing = by_id.get(aid)
        if existing is None or r.get("collected_at", "") < existing.get("collected_at", ""):
            by_id[aid] = r
    return list(by_id.values())


def _load_archive_and_tagged() -> tuple[list[dict], set]:
    """원장 전체(article_id 중복 제거) + 이미 태깅된 article_id 집합."""
    all_rows = _dedupe_by_article_id(archive_manager.read_archive())
    conn = geo_store.open_geo()
    tagged_ids = {
        row[0] for row in conn.execute(
            "SELECT article_id FROM geo_tags WHERE geo_tagged_at IS NOT NULL AND geo_tagged_at != ''"
        )
    }
    conn.close()
    return all_rows, tagged_ids


def _default_stratified_sample(all_rows: list[dict], limit: int) -> list[dict]:
    """--mode sample의 기본 표본 구성 — 소스 유형별로 비례 배분한다.
    (이번 라운드 육안 검수용 특정 50건 구성은 --article-ids-file로 넘긴다.)"""
    sh = [r for r in all_rows if r.get("source", "").startswith("Student Housing")]
    player = [r for r in all_rows if r.get("source", "").startswith(archive_manager.PLAYER_SOURCE_PREFIX)]
    general = [r for r in all_rows
               if not r.get("source", "").startswith("Student Housing")
               and not r.get("source", "").startswith(archive_manager.PLAYER_SOURCE_PREFIX)]

    n_sh = min(len(sh), limit // 3)
    n_player = min(len(player), limit // 3)
    n_general = max(0, limit - n_sh - n_player)
    return sh[:n_sh] + player[:n_player] + general[:n_general]


def select_targets(mode: str, limit: int, article_ids_file: str | None) -> list[dict]:
    all_rows, tagged_ids = _load_archive_and_tagged()

    if article_ids_file:
        with open(article_ids_file, encoding="utf-8") as f:
            wanted = {line.strip() for line in f if line.strip()}
        by_id = {r["article_id"]: r for r in all_rows}
        missing = wanted - set(by_id)
        if missing:
            print(f"[WARN] article_ids_file에 원장에 없는 id {len(missing)}건: {sorted(missing)[:5]} ...")
        return [by_id[aid] for aid in wanted if aid in by_id]

    untagged = [r for r in all_rows if r["article_id"] not in tagged_ids]

    if mode == "sample":
        return _default_stratified_sample(untagged, limit)
    if mode in ("backfill", "incremental"):
        return untagged
    raise ValueError(f"select_targets는 resolve-only에 쓰지 않는다 (mode={mode})")


# ------------------------------------------------------------------
# 3. 중복 실행 가드
# ------------------------------------------------------------------

def get_in_progress_batches(client: anthropic.Anthropic) -> list:
    return [b for b in client.messages.batches.list(limit=20) if b.processing_status == "in_progress"]


# ------------------------------------------------------------------
# 4. Stage A 배치 실행 + Stage B
# ------------------------------------------------------------------

def run_batch(client: anthropic.Anthropic, targets: list[dict]) -> dict:
    """Stage A 배치 제출 -> polling -> 각 article의 Stage B까지 실행.
    반환: {"ok": int, "fail": int}"""
    requests = [
        {
            "custom_id": article["article_id"],
            "params": {
                "model": MODEL,
                "max_tokens": MAX_TOKENS,
                "system": [{
                    "type": "text",
                    "text": GEO_SYSTEM_FULL,
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                }],
                "messages": [{"role": "user", "content": build_geo_prompt(article)}],
            },
        }
        for article in targets
    ]

    batch = client.messages.batches.create(requests=requests)
    print(f"    배치 생성 완료: {batch.id} ({len(requests)}건)")

    with open(BATCH_ID_FILE, "w") as f:
        f.write(batch.id)

    while batch.processing_status != "ended":
        time.sleep(30)
        batch = client.messages.batches.retrieve(batch.id)
        print(f"    상태: {batch.processing_status} ...")

    if os.path.exists(BATCH_ID_FILE):
        os.remove(BATCH_ID_FILE)

    by_id = {a["article_id"]: a for a in targets}
    conn = geo_store.open_geo()
    ok = fail = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_creation_tokens = 0
    total_cache_read_tokens = 0

    for item in client.messages.batches.results(batch.id):
        aid = item.custom_id
        article = by_id.get(aid, {})
        source_hint = geo_store.derive_source_hint(article.get("source", ""))
        tagged_at = datetime.now(timezone.utc).isoformat()

        if item.result.type != "succeeded":
            print(f"    [WARN] 배치 실패: {aid} ({item.result.type})")
            geo_store.upsert_geo(conn, aid, {
                "stage_a_json": "", "geo_confidence": "none",
                "geo_scope": "none", "geo_tagged_at": tagged_at,
                "stage_a_model": MODEL,
            })
            fail += 1
            continue

        usage = item.result.message.usage
        total_input_tokens += getattr(usage, "input_tokens", 0) or 0
        total_output_tokens += getattr(usage, "output_tokens", 0) or 0
        total_cache_creation_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        total_cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0

        raw = item.result.message.content[0].text
        try:
            parsed = json.loads(_strip_fence(raw))
            vals = resolve(parsed.get("places", []), parsed.get("scope", "none"), source_hint=source_hint)
            ok += 1
        except Exception as e:
            # 파싱 실패해도 원문(raw)은 보존한다 — 나중에 재파싱 가능해야 한다
            print(f"    [WARN] JSON 파싱 실패: {aid}: {e}")
            vals = {
                "geo_place_raw": "", "geo_cbsa_code": "", "geo_cbsa_title": "",
                "geo_state": "", "geo_scope": "none", "geo_confidence": "none",
            }
            fail += 1

        vals["stage_a_json"] = raw
        vals["geo_tagged_at"] = tagged_at
        vals["stage_a_model"] = MODEL
        geo_store.upsert_geo(conn, aid, vals)

    conn.commit()  # 배치 결과를 전부 받은 뒤 한 번만 commit
    conn.close()
    print(
        f"    [USAGE] input_tokens {total_input_tokens} / output_tokens {total_output_tokens} "
        f"/ cache_creation_input_tokens {total_cache_creation_tokens} "
        f"/ cache_read_input_tokens {total_cache_read_tokens}"
    )
    return {
        "ok": ok, "fail": fail,
        "usage": {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "cache_creation_input_tokens": total_cache_creation_tokens,
            "cache_read_input_tokens": total_cache_read_tokens,
        },
    }


def run_resolve_only(resolver_version: str) -> dict:
    """API 호출 없이 stage_a_json으로 Stage B만 재실행. alias/크로스워크
    보강 후 재매핑할 때 쓴다."""
    all_rows, _ = _load_archive_and_tagged()
    source_by_id = {r["article_id"]: r.get("source", "") for r in all_rows}

    conn = geo_store.open_geo()
    rows = list(geo_store.iter_stage_a(conn))
    ok = fail = 0

    for aid, stage_a_json, stage_a_model in rows:
        source_hint = geo_store.derive_source_hint(source_by_id.get(aid, ""))
        try:
            parsed = json.loads(_strip_fence(stage_a_json))
            vals = resolve(parsed.get("places", []), parsed.get("scope", "none"), source_hint=source_hint)
            ok += 1
        except Exception as e:
            print(f"    [WARN] 재파싱 실패: {aid}: {e}")
            vals = {
                "geo_place_raw": "", "geo_cbsa_code": "", "geo_cbsa_title": "",
                "geo_state": "", "geo_scope": "none", "geo_confidence": "none",
            }
            fail += 1
        vals["stage_a_json"] = stage_a_json
        vals["geo_tagged_at"] = datetime.now(timezone.utc).isoformat()
        vals["stage_a_model"] = stage_a_model or MODEL
        geo_store.upsert_geo(conn, aid, vals, resolver_version=resolver_version)

    conn.commit()
    conn.close()
    return {"ok": ok, "fail": fail, "total": len(rows)}


# ------------------------------------------------------------------
# 5. 실행
# ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["sample", "backfill", "incremental", "resolve-only"],
                    default="sample")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--article-ids-file", default=None,
                    help="이 파일에 나열된 article_id만 대상으로 한다 (한 줄에 하나)")
    ap.add_argument("--resolver-version", default="v1",
                    help="resolve-only 모드에서 geo_tags.db에 기록할 버전 태그")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    print("=== geo_tagger.py (Phase 2, Stage A/B) ===")
    print(f"시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} / mode={a.mode}\n")

    if a.mode == "resolve-only":
        if a.dry_run:
            conn = geo_store.open_geo()
            n = len(list(geo_store.iter_stage_a(conn)))
            conn.close()
            print(f"대상 {n}건 (resolve-only, API 호출 없음)")
            return
        result = run_resolve_only(a.resolver_version)
        print(f"완료: 성공 {result['ok']} / 실패 {result['fail']} / 전체 {result['total']}")
        return

    targets = select_targets(a.mode, a.limit, a.article_ids_file)
    if a.mode == "sample" and not a.article_ids_file:
        targets = targets[:a.limit]

    print(f"대상 {len(targets)}건 (mode={a.mode})")
    if a.dry_run or not targets:
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")
    client = anthropic.Anthropic(api_key=api_key)

    in_progress = get_in_progress_batches(client)
    if in_progress:
        ids = ", ".join(b.id for b in in_progress)
        print(f"[SKIP] 이미 in_progress 상태인 배치가 있어 새 배치를 제출하지 않습니다: {ids}")
        return

    result = run_batch(client, targets)
    print(f"완료: 성공 {result['ok']} / 실패 {result['fail']}")
    usage = result.get("usage") or {}
    if usage:
        print(
            f"  누적 토큰 — input {usage.get('input_tokens', 0)} / "
            f"output {usage.get('output_tokens', 0)} / "
            f"cache_write {usage.get('cache_creation_input_tokens', 0)} / "
            f"cache_read {usage.get('cache_read_input_tokens', 0)}"
        )


if __name__ == "__main__":
    main()
