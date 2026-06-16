"""
US Residential Intelligence v2 — classifier.py
미분류 기사(classified=False)를 읽어 Claude API로 분류 후 CSV에 write-back.
"""

import csv
import json
import os
import sys
import time
from datetime import datetime

import anthropic
from dotenv import load_dotenv

load_dotenv()

# Windows cp949 터미널에서 한글·특수문자 출력 가능하도록
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ------------------------------------------------------------------
# 1. 설정
# ------------------------------------------------------------------

ARTICLES_CSV  = "articles.csv"
BATCH_SIZE    = 300
MODEL         = "claude-sonnet-4-6"

CSV_COLUMNS = [
    "article_id", "collected_at", "published_at", "source",
    "title", "url", "summary", "classified",
    "category", "event_tags", "signal_type", "sector",
    "woomi_relevance", "claude_rationale", "access_limited", "korean_summary",
]

SYSTEM_PROMPT = """You are a real estate research analyst for Woomi Global, a Korean residential developer active in the US market.

WOOMI_RELEVANCE PRIORITY (apply in order):
1. Does the article involve a named strategic partner or competitor of Woomi? → likely "높음"
2. Does it signal a large-scale platform deal, institutional capital move, or macro rate change? → likely "높음"
3. Does it involve BTR/SFR groundbreaking, completion, or institutional capital event? → "높음" (no size threshold)
4. Does it involve a Known GP (Kennedy Wilson / Harrison Street / PCCP / Blue Vista / Lionheart / NexMetro / Middleburg / Hillpointe) in any residential deal? → always "높음"
5. Does it involve Student Housing specifically? → apply STRICTER criteria: $50M+ deal or major platform only for "높음"; Student Housing under 500 beds (not units, beds) AND not a major platform → "보통" or "낮음"
6. Is the information too local, too small, or off-sector? → "낮음"
7. Everything else → "보통"

Classify the given article and return ONLY a JSON object with these exact fields:

{
  "category":         one of ["개발" | "시장" | "GP·자본흐름"],
  "event_tags":       array of applicable tags from [construction_start, delivery, permit, land_acquisition, transaction, acquisition, JV, policy, market_data, rent_occupancy, construction_cost, financing],
  "signal_type":      one of ["강세" | "약세" | "중립" | "혼재"],
  "sector":           one of ["Multifamily" | "BTR" | "SFR" | "Student Housing" | "Senior Housing" | "Affordable Housing" | "Workforce Housing" | "Mixed-use"],
  "woomi_relevance":  one of ["높음" | "보통" | "낮음"],
  "claude_rationale": one sentence in Korean explaining the classification,
  "korean_summary":   "3~5문장 한국어 요약. 핵심 내용, 주요 수치, 우미글로벌 관점의 의미를 포함."
}

category rules — EXACTLY one of ["개발", "시장", "GP·자본흐름"]. No other value is valid.
- "개발": article's core subject is groundbreaking, delivery, permitting, land sale, or development plan announcement
- "시장": article's core subject is rent/vacancy/absorption data, supply pipeline, interest rates, demand data — INCLUDING all policy, regulatory, and government articles affecting housing or real estate
- "GP·자본흐름": article's core subject is asset transaction, equity investment, JV formation, fund formation, or GP activity

CRITICAL: Do NOT use "Policy", "Other", or any English word as a category value.
Policy and regulatory articles → always "시장"
If uncertain which of the three applies → default to "시장"

sector rules:
CRITICAL: "Other" and "Policy" are NOT valid sector values. Never use them.
Valid sectors ONLY: ["Multifamily", "BTR", "SFR", "Student Housing", "Senior Housing", "Affordable Housing", "Workforce Housing", "Mixed-use"]
Assignment rules:
  - industrial / office / commercial real estate → "Mixed-use"
  - residential-related but unclear type → "Multifamily"
  - unrelated to residential (e.g. biotech, awards, finance unrelated to RE) → sector = "Multifamily", woomi_relevance = "낮음"
  - affordable housing / low-income policy → "Affordable Housing"
  - general housing / multifamily policy → "Multifamily"
  - zoning / land use policy → "Multifamily"

financing rule (strictly enforced):
Financing, loan, and refinancing content must NEVER determine the category.
Determine category from the core action (development / market data / transaction), then add "financing" to event_tags if financing content is present.

event_tags rules:
- Select all tags that apply. Multiple tags are expected and encouraged.
- "financing": add whenever the article mentions a loan, debt, refinancing, or capital raise, regardless of category.

woomi_relevance rules (apply differently by category):

[GP·자본흐름 category]
- "높음": BTR/SFR/Multifamily platform acquisition or M&A by major institutional player (e.g. Berkshire Hathaway, Blackstone, Invitation Homes acquiring operator platforms); large-scale development project announcement $100M+ regardless of sector; vertically integrated developer platform formation or significant expansion; BTR/SFR platform M&A or operator acquisition; Multifamily portfolio deal $50M+; vertically integrated developer activity (Mavrek, NexMetro, Christopher Todd, Hillpointe, Middleburg); Japanese or Korean capital in US residential; JV/Co-GP/development partnership structure; niche sector fund formation (BTR/SFR/Senior/Workforce); direct mention of Kennedy Wilson/Blue Vista/Lionheart/Core Spaces/Continental; LP fund exit pressure or capital recovery acceleration; Student Housing deal $50M+ OR involving Core Spaces/Landmark/Greystar as developer/operator (under 500 beds AND non-major platform → "보통"); BTR/SFR operator or developer receiving institutional equity $30M+; any deal involving Known GPs: Kennedy Wilson / Harrison Street / PCCP / Blue Vista / Lionheart / NexMetro / Middleburg / Hillpointe
- "보통": single-asset MF transaction under $50M, small-to-mid-size fund, Student Housing deal under $50M not involving major platform
- "낮음": sub-$20M single asset deal, out-of-focus sector

[시장 category]
- "높음": Fed rate decision or mortgage rate movement; national or Sun Belt new-supply rent/absorption trend for BTR/SFR/Multifamily; Multifamily sector-wide supply, absorption, or rent trend data (national or Sun Belt); housing supply policy (zoning reform, YIMBY, LIHTC); national multifamily starts or permits data; BTR/SFR tenant retention rate or average tenure data; BTR oversupply or absorption slowdown signal; family renter demand or long-term lease preference data; Sun Belt BTR starts/permits/absorption data; national-level Student Housing market data only (nationwide occupancy, rent growth across multiple campuses); BTR/SFR sector-wide supply, absorption, or rent trend data; construction cost trend (lumber, steel, labor) affecting residential development; cap rate compression or expansion trend for MF/BTR assets; institutional investor sentiment shift toward or away from residential
- "보통": single-city rent trend or demand data; single-campus Student Housing demand or occupancy article
- "낮음": simple regional stat, individual building leasing update, individual campus housing update

[개발 category]
- "높음": confirmed groundbreaking or broke-ground article for projects $50M+ or 200+ units; BTR/SFR/Multifamily permit filing or zoning approval; development in LA/Atlanta/Dallas/Houston/Phoenix; BTR/SFR groundbreaking or completion regardless of size; Sun Belt (Atlanta/Dallas/Houston/Phoenix/Charlotte) Multifamily 200+ units development announcement or groundbreaking; LA/West Coast Multifamily 200+ units development announcement or groundbreaking; suburban Atlanta/Dallas/Houston residential development; Student Housing project 500+ beds (not units, beds) OR involving Core Spaces/Landmark/Greystar
- "보통": general MF development plan announcement in other markets; small-scale groundbreaking under $50M and under 200 units outside Sun Belt; Student Housing project under 500 beds (not units, beds) not involving major platform
- "낮음": vague development intent, speculative land acquisition article

korean_summary rules:
- 3~5 sentences in Korean
- Include: core news content, key figures ($, units/beds, %, location), and one sentence on strategic relevance to Woomi Global
- Do NOT repeat claude_rationale verbatim
- If article is unrelated to residential real estate, write "주거 부동산과 직접적 관련이 없는 기사입니다." only

Return only the JSON object. No explanation, no markdown, no code fences.
"""


# ------------------------------------------------------------------
# 2. 프롬프트 구성
# ------------------------------------------------------------------

def build_prompt(article: dict) -> str:
    return (
        f"Source: {article['source']}\n"
        f"Title: {article['title']}\n"
        f"Summary: {article['summary']}"
    )


# ------------------------------------------------------------------
# 3. 결과 파싱
# ------------------------------------------------------------------

EMPTY_RESULT = {
    "category": "", "event_tags": "", "signal_type": "",
    "sector": "", "woomi_relevance": "", "claude_rationale": "", "korean_summary": "",
}

def parse_result(raw: str, article_id: str) -> dict:
    empty = dict(EMPTY_RESULT)
    try:
        text = raw.strip()
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1].lstrip("json").strip() if len(parts) >= 2 else text
        result = json.loads(text)
        if isinstance(result.get("event_tags"), list):
            result["event_tags"] = ",".join(result["event_tags"])
        for key in empty:
            if key not in result:
                result[key] = ""
        return result
    except json.JSONDecodeError:
        print(f"    [WARN] JSON 파싱 실패: {article_id}")
        return empty
    except Exception as e:
        print(f"    [WARN] 파싱 예외 ({article_id}): {e}")
        return empty


# ------------------------------------------------------------------
# 4. Batch API 호출
# ------------------------------------------------------------------

def classify_batch(client: anthropic.Anthropic, batch_articles: list[dict]) -> dict[str, dict]:
    """배치 요청 전송 → polling → {article_id: result_dict} 반환"""
    requests = [
        {
            "custom_id": article["article_id"],
            "params": {
                "model": MODEL,
                "max_tokens": 300,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": build_prompt(article)}],
            },
        }
        for article in batch_articles
    ]

    batch = client.messages.batches.create(requests=requests)
    print(f"    배치 생성 완료: {batch.id} ({len(requests)}건)")

    while batch.processing_status != "ended":
        time.sleep(30)
        batch = client.messages.batches.retrieve(batch.id)
        print(f"    상태: {batch.processing_status} ...")

    results: dict[str, dict] = {}
    for item in client.messages.batches.results(batch.id):
        aid = item.custom_id
        if item.result.type == "succeeded":
            raw = item.result.message.content[0].text
            results[aid] = parse_result(raw, aid)
        else:
            print(f"    [WARN] 배치 실패: {aid} ({item.result.type})")
            results[aid] = dict(EMPTY_RESULT)

    return results


# ------------------------------------------------------------------
# 5. CSV read / write-back
# ------------------------------------------------------------------

def load_articles() -> list[dict]:
    if not os.path.exists(ARTICLES_CSV):
        return []
    with open(ARTICLES_CSV, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def save_articles(articles: list[dict]) -> None:
    with open(ARTICLES_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(articles)


# ------------------------------------------------------------------
# 6. 실행
# ------------------------------------------------------------------

def run_classifier() -> dict:
    """
    미분류 기사를 BATCH_SIZE만큼 분류하고 결과를 반환한다.
    app.py에서 직접 import해 호출할 수 있도록 분리.
    반환: {"success": int, "failed": int, "remaining": int}
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")

    client = anthropic.Anthropic(api_key=api_key)

    articles = load_articles()
    if not articles:
        return {"success": 0, "failed": 0, "remaining": 0}

    unclassified = [a for a in articles if a.get("classified", "").lower() != "true"]
    batch_articles = unclassified[:BATCH_SIZE]

    if not batch_articles:
        return {"success": 0, "failed": 0, "remaining": 0}

    article_map = {a["article_id"]: a for a in articles}

    batch_results = classify_batch(client, batch_articles)

    success = 0
    failed  = 0
    for article in batch_articles:
        aid = article["article_id"]
        result = batch_results.get(aid, dict(EMPTY_RESULT))
        if result["woomi_relevance"]:
            article_map[aid].update(result)
            article_map[aid]["classified"] = True
            success += 1
        else:
            failed += 1

    save_articles(list(article_map.values()))

    remaining = len(unclassified) - len(batch_articles)
    return {"success": success, "failed": failed, "remaining": remaining}


def main():
    print("=== US Residential Intelligence v2 — Classifier ===")
    print(f"시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    articles = load_articles()
    if not articles:
        print("articles.csv가 없거나 비어 있습니다. collector.py를 먼저 실행하세요.")
        return

    unclassified = [a for a in articles if a.get("classified", "").lower() != "true"]
    print(f"전체 기사: {len(articles)}건")
    print(f"미분류:    {len(unclassified)}건")
    print(f"이번 배치: {min(len(unclassified), BATCH_SIZE)}건 (BATCH_SIZE={BATCH_SIZE})\n")

    if not unclassified:
        print("분류할 기사가 없습니다.")
        return

    result = run_classifier()

    print(f"\n--- 분류 완료 ---")
    print(f"  성공: {result['success']}건")
    print(f"  실패: {result['failed']}건")
    print(f"  남은 미분류: {result['remaining']}건")
    print(f"  → {ARTICLES_CSV}")


if __name__ == "__main__":
    main()
