import csv, re, shutil, os
shutil.copy("articles.csv", "articles.csv.bak")

def norm_title(t):
    t = re.sub(r"[^a-z0-9 ]", "", (t or "").lower())
    return re.sub(r"\s+", " ", t).strip()

RANK = {"높음": 0, "보통": 1, "낮음": 2, "": 3}
rows = list(csv.DictReader(open("articles.csv", encoding="utf-8", newline="")))
fields = list(rows[0].keys())
assert len(fields) == 16, f"컬럼 수 이상: {len(fields)}"

# A3
for r in rows:
    if r["article_id"] == "8270efb18db5" and r["category"] == "낮음":
        r["category"] = "시장"
        print("A3 수정:", r["title"][:60])

# A4 — 키는 (정규화 제목, 발행일 앞 10자).
# 발행일을 함께 쓰는 이유: 제목만으로 묶으면
# "Multifamily Starts Fall in July" 같은 정기 기사가 다른 달끼리 병합된다.
groups = {}
for r in rows:
    groups.setdefault((norm_title(r["title"]), r["published_at"][:10]), []).append(r)

kept, removed = [], 0
for _, g in groups.items():
    if len(g) == 1:
        kept.append(g[0]); continue
    # 같은 기사인데 분류가 갈린 그룹이 8개 있다.
    # 놓치는 쪽보다 나으므로 더 높게 평가된 판정을 남긴다. 동률이면 먼저 수집된 것.
    g.sort(key=lambda r: (RANK.get(r["woomi_relevance"], 3), r["collected_at"]))
    kept.append(g[0]); removed += len(g) - 1

kept.sort(key=lambda r: r["collected_at"])
print(f"{len(rows)} -> {len(kept)} (제거 {removed})")

VALID_CAT = {"개발", "시장", "GP·자본흐름", ""}
bad = [r["article_id"] for r in kept if r["category"] not in VALID_CAT]
print("category 이상값:", bad or "없음")

with open("articles.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader(); w.writerows(kept)
