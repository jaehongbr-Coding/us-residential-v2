# research_market.md — The Brief 시장 데이터 풀 + 시장 맥락 판정 리서치

> 버전 v0.1 (2026-10-15) · 작성: Claude · 검토: 김재홍
> 선행 문서: `research.md` / `Plan.md` v0.3 (geo 태깅). 이 문서는 geo 태깅 **위에** 얹는 기능을 다룬다.
> 신뢰도 표기: [확인됨: 출처 검색·코드 직독] / [학습지식: 미검증] / [추정]

---

## 0. 이 문서가 답하려는 질문

1. The Brief에 공공 정형 데이터(BPS·SOC 기본, 이후 임대료·공실·안건)를 붙일 때 **어디에 저장하고 어떻게 조회하는가**
2. 뉴스 중요도 판정에 그 데이터를 **어떤 방식으로 개입시키는가** — LLM 프롬프트에 넣는가(길 A), Python 규칙으로 분리하는가(길 B)
3. 데일리 자동 판정(push)과 마켓워치 수동 조회(pull)가 **같은 코드를 공유하는가**
4. geo 태깅이 미착수인 상태에서 **무엇을 먼저 시작할 수 있는가**

---

## 1. 결론 요약 (먼저 읽을 것)

| # | 결론 | 근거 |
|---|---|---|
| R1 | **길 B 채택.** 기존 `woomi_relevance`(LLM)는 불변, 별도 `market_flags.csv`(Python)를 나란히 둔다. 합산하지 않는다 | §3 |
| R2 | 공공 데이터는 "쌓을" 필요가 없다. BPS는 2019-11부터 월간, SOC는 1971부터 — **첫날부터 기저선이 있다** | §4.1, §4.2 |
| R3 | 데이터 풀은 방대하지 않다. BPS 월 1파일(~150KB, 약 900 CBSA), SOC 상수 16개, ZORI CSV 1장. 방대해질 수 있는 건 Legistar뿐 | §4 |
| R4 | **Legistar는 주력 시장 중 Seattle만 Web API 응답.** Atlanta·Dallas는 응답 없음 → Legistar는 Phase 3로 후순위 | §4.6 |
| R5 | BPS에는 `rep`(실제 보고분)와 총계(보고+대체추정)가 분리돼 있다. **보고 비율이 낮은 CBSA는 unknown** 처리 가능 — "모르면 unknown" 원칙을 데이터 자체가 지원한다 | §4.1.3 |
| R6 | classifier 프롬프트에 이미 지역 규칙이 **하드코딩**돼 있다("development in LA/Atlanta/Dallas/Houston/Phoenix → 높음"). 이게 지금의 '시장 맥락'이고, 고정값이다. market_flags는 이를 **데이터 기반으로 대체**하는 것이지 새 개념이 아니다 | §2.2 |
| R7 | `index.html`의 트렌드 차트는 **하드코딩 데이터**다(647행 주석). 마켓워치 화면은 이 차트를 실데이터로 교체하는 것으로 시작하면 된다 | §2.3 |
| R8 | push(데일리)와 pull(마켓워치)은 **같은 함수** `market_context(cbsa, as_of)`를 부른다. 기능이 둘이 아니라 호출 시점이 둘이다 | §3.3 |
| R9 | geo 태깅 전에 시작 가능한 것: BPS·SOC 수집기, 기저선 계산, 마켓워치 화면. geo 후에만 가능한 것: 기사별 market_flags 부여 | §7 |

---

## 2. 현재 시스템 이해 (코드 리서치)

### 2.1 데이터 흐름 [확인됨: 코드 직독]

```
collector.py ──► articles.csv (16컬럼) ──► classifier.py (Batch API, sonnet-4-6)
                                                │
                     ┌──────────────────────────┴──────────────┐
                     ▼                                         ▼
            index.html (PapaParse, raw.githubusercontent)   weekly_report.py
```

- `classifier.py` 31~36행: `CSV_COLUMNS` 16개 고정. 판정 결과 필드는 `category`, `event_tags`, `signal_type`, `sector`, **`woomi_relevance`**(높음/보통/낮음), `claude_rationale`, `korean_summary`
- `classifier.py` 242~244행: `csv.DictWriter(f, fieldnames=CSV_COLUMNS)` → 기존 geo 리서치의 결론(별도 파일 분리) 그대로 유효
- `classifier.py` 123~128행: `build_prompt()`는 **Source / Title / Summary 세 줄만** 보낸다. 외부 수치를 끼워 넣을 자리가 구조적으로 없다 — 길 A를 택하면 이 함수와 SYSTEM_PROMPT를 둘 다 고쳐야 한다
- `index.html` 443행: `CSV_URL = raw.githubusercontent.com/.../articles.csv` → 같은 방식으로 `market_flags.csv`, `data/market/*.csv`를 읽을 수 있다. **백엔드 없음.** 화면은 정적 파일만 읽는다
- `weekly_report.py` 85행 `load_articles()`: articles.csv만 읽는다. 시장 데이터를 리포트에 넣으려면 여기에 조인이 필요하나, **이번 범위 밖**

### 2.2 중요도 판정이 지금 어떻게 작동하는가 [확인됨: classifier.py 38~104행]

SYSTEM_PROMPT의 `woomi_relevance` 규칙에 지역이 **문자열로 박혀 있다**:

- `[개발]` "development in LA/Atlanta/Dallas/Houston/Phoenix" → 높음
- `[개발]` "Sun Belt (Atlanta/Dallas/Houston/Phoenix/Charlotte) Multifamily 200+ units" → 높음
- `[시장]` "Sun Belt BTR starts/permits/absorption data" → 높음

**함의:** 지금도 시장 맥락은 판정에 들어가 있다. 다만 (a) 지역 목록이 고정이고 (b) "그 지역이 지금 어떤 상태인지"는 전혀 반영되지 않는다. Atlanta 허가가 평년의 절반이든 두 배든 "Atlanta면 높음"이다. market_flags는 이 **고정 지역 가중을 동적 시장 상태로 바꾸는 것**이다. 기존 프롬프트의 지역 규칙은 그대로 두되(원장 불변), market_flags가 옆에 생기면 프롬프트 지역 규칙의 역할이 줄어든다 — 삭제는 별도 결정.

### 2.3 화면 [확인됨: index.html 647행]

```
/* ── Trend charts (하드코딩 데이터, articles.csv 실시간 연동 아님) ── */
```

트렌드 차트 섹션이 **정적 숫자**다. 마켓워치 Phase 1의 가장 싼 산출물은 이 차트를 `data/market/bps_cbsa.csv`로 갈아끼우는 것이다. 새 화면을 만들 필요가 없다.

### 2.4 ⚠️ 구현 전 확인 필요 (코드 리서치 공백)

| ID | 항목 | 왜 필요한가 |
|---|---|---|
| V1 | `index.html` 647행 이하 차트 코드가 Chart.js 어떤 버전·어떤 데이터 구조를 쓰는가 | 교체 시 데이터 shape 맞추기 |
| V2 | `daily_collect.yml`에 수집 스텝 추가 시 Actions 실행시간(현재 10분38초) 여유 | BPS 다운로드는 150KB라 무시 가능, xlrd 설치 시간만 확인 |
| V3 | `Plan.md`(geo) §4.1의 `geo_cbsa` 컬럼 정확한 이름·타입 | market_flags 조인 키 |
| V4 | `requirements.txt`에 `xlrd` 없음 — BPS가 **.xls(구형)** 이라 `openpyxl`로 못 읽는다 | pandas.read_excel(engine="xlrd") 필요. **requirements 추가 1건** |

---

## 3. 설계 결정 — 중요도 2성분 분리

### 3.1 길 A vs 길 B

| | 길 A: 프롬프트에 수치 주입 | 길 B: Python 규칙 분리 (채택) |
|---|---|---|
| 구현 | `build_prompt()`에 "참고: {cbsa} 허가 YoY {x}%" 추가 | `market_rules.py` 신규 + `market_flags.csv` 출력 |
| 재현성 | 같은 입력에 다른 출력 가능 | 결정론 |
| 감사 | "왜 높음인가"가 rationale 자연어에 섞임 | 규칙 ID가 flag에 그대로 남음 |
| 기존 5,496건 | 재분류 필요 (Batch 비용) 또는 불균질 | **재분류 불필요.** geo 백필만 되면 소급 계산 |
| IC Helper 선례 | 52.2% 일치율의 원인이 된 구조 | flag_rules.py와 동형 |
| 기사 텍스트 판단 | 가능 | **불가** — 그래서 LLM 열을 없애지 않는다 |

**결정: B.** 단, LLM의 `woomi_relevance`는 **그대로 둔다.** "Greystar 철수"와 "Greystar 사무실 이전"의 차이는 텍스트를 읽어야 알고, 그건 LLM이 맞다. 두 열을 나란히 보여주고 **합산 점수를 만들지 않는다** — 합산하면 근거가 숨는다.

### 3.2 market_flags의 성격

`market_flags.csv`는 **렌즈 계층**이다. 원장(articles.csv, data/market/)은 불변, 규칙(market_rules.py)은 언제든 교체·재계산. geo_tags.csv와 정확히 같은 위치.

```
원장:  articles.csv  +  data/market/bps_cbsa.csv  (판단 없음)
렌즈:  geo_tags.csv  +  market_flags.csv           (규칙, 재계산 가능)
화면:  index.html                                   (두 열 나란히 표시)
```

### 3.3 push와 pull은 같은 함수

```python
# market_context.py (순수 함수, LLM 호출 없음)
def market_context(cbsa: str, as_of: date) -> MarketContext | None:
    """BPS·SOC·(후속) ZORI를 조회해 그 시점의 시장 상태를 반환. 표본 부족 시 None."""
```

- **데일리 push:** `market_tagger.py`가 geo_tags.csv의 각 기사 CBSA에 대해 `market_context(cbsa, published_at)` 호출 → `market_rules.py`가 flag 부여 → `market_flags.csv`
- **마켓워치 pull:** 화면이 `data/market/*.csv`를 직접 읽어 같은 계산을 JS로 재현하거나, 사전 계산된 `data/market/context_latest.json`을 읽는다. **백엔드가 없으므로 후자**가 현실적 — `market_tagger.py` 실행 끝에 전 CBSA의 최신 context를 JSON으로 덤프

같은 Python 함수가 매일 자동으로 돌고, 그 결과를 화면이 읽는다. 기능 분리가 아니라 **호출 시점 분리**다.

---

## 4. 데이터 소스 상세

### 4.1 Census BPS — 건축허가 (Phase 1 기본) [확인됨]

**4.1.1 파일**
- URL 패턴: `https://www.census.gov/construction/bps/xls/cbsamonthly_YYYYMM.xls` (2024-01 이후). 2019-11~2023-12는 `msamonthly_YYYYMM.xls`
- 형식: **.xls 구형**. ~150KB. pandas + `xlrd` 필요 (V4)
- 갱신: 매월 약 18번째 근무일에 전월분. 월간 추정치는 최초 공표 후 **수정되지 않음** → 연간 확정치(5월 첫 근무일)와 섞으면 안 됨

**4.1.2 컬럼 (29열, 헤더 2행)** [확인됨: 샘플 파일 직독]

| 열 | 내용 |
|---|---|
| 1 | Date (YYYYMM) |
| 2 | CSA code |
| 3 | **CBSA code (5자리)** — geo 태깅 키와 동일 |
| 4 | MONCOV 플래그 (`C` = 월간 보고 커버리지 완전) |
| 5 | CBSA name (예: "Corvallis OR") |
| 6~17 | 1-unit / 2-units / 3-4 units / **5+ units** × (Bldgs, Units, Value) — **보고분 + 대체추정 합계** |
| 18~29 | 같은 구조, `rep` 접미 — **실제 보고분만** |

2024-01부터 Micropolitan 포함. 구분 필드 존재.

**4.1.3 보고분/총계 분리의 의미 — unknown 판정의 근거**
2022-01부터 cutoff sample 방식: 허가 활동이 많은 지자체만 매월 수집하고 나머지는 과거 평균으로 대체추정. 따라서
- `rep_units / total_units` 비율이 낮은 CBSA → 그 달 숫자는 **모델링 값**
- 소규모 시장(Columbia MO 류)은 이 비율이 낮을 가능성 높음 [추정]
- **규칙:** 보고 비율 < 임계(초안 70%)이면 `coverage = "imputed"` → market_flags는 `unknown`. 임계값은 Phase 1 실측 후 확정

이게 BPS를 택한 결정적 이유 중 하나다. 데이터가 **자기 신뢰도를 같이 준다.**

**4.1.4 CBSA vintage**
BPS는 OMB 최신 delineation을 따른다(2024-01 파일부터 2023 vintage로 추정 [학습지식]). geo 태깅 Plan.md가 vintage 2023 고정이므로 **일치**. 2019~2023 파일은 이전 vintage라 소수 CBSA 코드가 다를 수 있음 → 기저선 계산 시 코드 불일치 행은 버리고 로그에 남긴다.

**4.1.5 기저선 설계 초안**
- 지표: `units_5plus_12m` = 최근 12개월 5+유닛 허가 유닛 합
- 기준: `units_5plus_12m_avg3y` = 직전 36개월을 12개월 창 3개로 나눈 평균
- 편차: `ratio = 12m / avg3y`. 1.0 = 평년
- 왜 12개월 합인가: 허가는 월별 노이즈가 크다(한 프로젝트 500유닛이 한 달에 찍힘). 12개월 합이 안정적이고 "연간 공급"과 개념이 맞는다
- 왜 3년인가: 2019-11 시작이라 2026-10 시점에 약 7년치 있음. 3년이면 팬데믹 급등(2021~22)을 평균에 포함하면서도 과거 10년을 끌어오지 않음. **Plan에서 2년 vs 3년 선택 필요**
- MIN_N 개념은 BPS에는 적용 안 됨(표본이 아니라 전수). 대신 §4.1.3 보고 비율이 그 역할

### 4.2 Census SOC — 허가→준공 소요기간 (Phase 1 기본) [확인됨]

**4.2.1 파일** (2024 릴리스부터 .xlsx)
- `https://www.census.gov/construction/nrc/xls/avg_authtostart_cust.xlsx` — 허가→착공 평균(월)
- `https://www.census.gov/construction/nrc/xls/avg_starttocomp_cust.xlsx` — 착공→준공 평균(월)
- 갱신: 연 1회(전년분). 2025년치 공표됨

**4.2.2 분해 수준** [확인됨: NAHB 2026-09 분석]
- 지역 4개(Northeast / Midwest / South / West) × 유닛 규모 4구간(2~4 / 5~9 / 10~19 / 20+)
- 2025년 멀티패밀리 전국 평균 허가→준공 18.9개월, 20+유닛 21.7개월, South 17.5 / West 20.6
- **MSA 단위 없음.** Atlanta·Columbia MO·DFW가 전부 South

**4.2.3 저장 형태**
연간 16개 숫자(4지역 × 4규모) + 전국 평균. `data/market/soc_lag.csv`에 `year, region, unit_bucket, months_auth_to_start, months_start_to_comp` 로 저장. 파싱은 1회성이고 매년 5월 1회 갱신.

**4.2.4 CBSA → Region 매핑**
Census Region은 주(state) 단위로 정의. CBSA 코드 → 주 → Region. geo Plan.md의 크로스워크에 state가 있으면 바로 조인, 없으면 Census CBSA delineation 파일에서 principal state 추출 (V3 확인 사항).

**4.2.5 공급 퍼널 계산**
```
expected_completion_units(cbsa, target_quarter)
  = Σ permits_5plus(cbsa, month)  for month in [target − lag − 3mo, target − lag + 3mo]
  where lag = soc_lag[region(cbsa)][bucket="20+"].auth_to_comp
```
20+ 구간을 쓰는 이유: 우미 관심 상품(200+유닛 MF, BTR 커뮤니티)이 전부 20+ 구간. 2~4·5~9는 소규모 다세대라 무관.
⚠️ 이건 **추정**이다. 허가 후 미착공·취소분을 모르고, lag가 지역 평균이다. 화면에 "추정(SOC 지역 평균 적용)"을 반드시 표기.

### 4.3 Zillow ZORI — 임대료 (Phase 2) [확인됨]

- URL: `https://files.zillowstatic.com/research/public_csvs/zori/Metro_zori_uc_sfrcondomfr_sm_month.csv`
- 형식: wide CSV (RegionID, SizeRank, RegionName, RegionType, StateName, 월별 컬럼). RegionName이 "Atlanta, GA" 식 → **CBSA 코드 없음.** 이름 매칭 필요 (geo_aliases.yaml 재사용)
- 변형: 파일명의 `sfrcondomfr`은 SFR+콘도+MF 합산. **MF 단독 파일은 페이지에 미표시** — Phase 2 착수 시 재확인
- 갱신: 월간. 2015-01부터
- 지표: 35~65백분위 리스팅 임대료 평균(달러). 임대 재고 가중
- 프록시 검증: 리스팅 임대료 = **호가(asking)**. 실거래 임대료가 아님. 신축 Class A 흡수를 보려는 목적에는 방향이 맞으나, "시장 임대료 수준"으로 OM 검증에 쓰면 호가 상향 편향. → The Brief 시장 추세용 OK, IC Helper 벤치마크용 NG

### 4.4 Apartment List — 임대료·공실·Time On Market (Phase 2) [확인됨, 자동화 미확인]

- 페이지: `apartmentlist.com/rentonomics/rental-price-data/`
- 제공: Rent Estimates(2017-01~, 메트로·카운티·시), Vacancy Index, **Time On Market**
- ⚠️ 다운로드가 "Download Report 드롭다운" 뒤에 있음. **직접 CSV URL 미확인.** 자동 수집 가능 여부는 Phase 2 착수 시 실측. 안 되면 월 1회 수동 업로드(xlsx 스킬 경로)
- Time On Market이 핵심. 임대료보다 **선행**하는 리스업 속도 지표
- 프록시 검증: Apartment List 플랫폼 등록 물건 기준 → 전문 운영 신축 편향. 우리가 짓는 상품과 같은 세그먼트라 **오히려 적합**. 전체 시장 공실로 해석하면 안 됨

### 4.5 Census HVS — 공식 임대공실률 (Phase 2 보강) [확인됨]

- 페이지: `census.gov/housing/hvs/data/rates.html` Table 4 (75대 MSA 분기별, 2015~)
- 형식: .xlsx [추정: 페이지 링크 확장자 미확인]
- 한계: 단독+다세대 합산, MSA 단위 표본 작아 분기 노이즈 큼. **연간 평균**으로만 쓴다
- 용도: IC 심의 자료 인용용 공식 수치. 판정 규칙에는 넣지 않음

### 4.6 Legistar Web API — 시의회 안건 (Phase 3) [확인됨: 직접 호출]

- `https://webapi.legistar.com/v1/seattle/matters?$top=3` → **JSON 정상 응답.** 필드: MatterId, MatterFile, MatterTitle, MatterTypeName, MatterStatusName, MatterBodyName, MatterIntroDate, MatterAgendaDate, MatterPassedDate 등
- `/v1/atlanta/matters`, `/v1/dallas/matters` → **서버 오류.** Legistar 미사용이거나 Web API 비활성 [확인됨: 2026-10-15 호출]
- **함의: 주력 3시장 중 Seattle만 가능.** Atlanta(ATLANTA.legistar? 미확인)·Dallas는 자체 시스템 추정 [추정]. LA는 Council File 시스템 [학습지식]
- 따라서 Legistar는 **Seattle 단일 소스로 Phase 3에 시범 도입**. 수집기 구조상 RSS 소스 하나 추가와 동형(`source="Seattle City Council"`, `sector="Policy"`, summary=MatterTitle). classifier가 그대로 중요도 매김. geo는 Stage 0에서 Seattle 고정
- 양: 조닝·토지이용 키워드 필터 후 일 수 건 [추정]. 뉴스 일 56건과 같은 자릿수

### 4.7 IRS SOI 이주 데이터 (Phase 3 보강) [확인됨]

- `irs.gov/node/136131` 2021~2022 county-to-county inflow/outflow CSV. 신고건수·부양가족·총 AGI
- 2년 지연. 연 1회. 카운티 FIPS → CBSA 집계 필요
- 용도: 마켓워치의 구조 추세 탭. 판정 규칙에는 넣지 않음(지연이 너무 큼)

### 4.8 도입 단계 요약

| Phase | 소스 | 자동화 | 판정 규칙 투입 | 전제 |
|---|---|---|---|---|
| 1 | BPS, SOC | 월간/연간 Actions | **예** | 없음 (geo 무관하게 수집·기저선 가능) |
| 1 | market_flags 부여 | 일간 Actions | — | **geo_tags.csv 존재** |
| 2 | ZORI, Apartment List | 월간 (AL은 미확인) | 예 (Time On Market) | geo_aliases 이름 매칭 |
| 2 | HVS | 분기 | 아니오 (표시만) | — |
| 3 | Legistar Seattle | 일간 (collector 소스) | classifier 경유 | — |
| 3 | IRS SOI | 연간 | 아니오 (표시만) | FIPS→CBSA |

---

## 5. 규칙 설계 초안 — `market_rules.py`

**원칙: 5~6개를 넘기지 않는다.** IC Helper flag_rules가 겪은 "어느 규칙이 왜 발동했는지 모르는" 상태를 피한다. 규칙 ID가 그대로 flag 값이 된다.

| ID | 조건 (Python, 결정론) | flag | 입력 소스 |
|---|---|---|---|
| S1 | `ratio_12m_vs_3y ≥ 1.3` | `supply_surge` | BPS |
| S2 | `ratio_12m_vs_3y ≤ 0.7` | `supply_drought` | BPS |
| S3 | `coverage == "imputed"` 또는 BPS에 CBSA 없음 | `unknown` | BPS rep 비율 |
| S4 | `expected_completion_next_4q / stock_5plus ≥ 임계` | `completion_wave` | BPS+SOC (+ACS stock, Phase 2) |
| T1 | `time_on_market_delta ≥ +10일` (Phase 2) | `absorption_slow` | Apartment List |
| T2 | `zori_yoy ≤ −3%` (Phase 2) | `rent_soft` | ZORI |

- flag는 **복수 가능** (`supply_surge|absorption_slow`). 단일 문자열로 뭉개지 않음 — IC Helper judge_flag() 목록 반환 과제와 같은 교훈
- 임계값(1.3, 0.7, +10일, −3%)은 **초안**. Phase 1에서 전 CBSA 분포를 뽑아 상위/하위 20% 지점으로 보정. Plan에 보정 절차 명시
- 기사와의 결합: `market_flags.csv` 행 = `article_id, cbsa, as_of, flags, ratio_12m_vs_3y, coverage, rule_version`. **rule_version**을 남겨야 규칙 바꿔도 과거 행을 재해석 가능
- LLM `woomi_relevance`와 **합산하지 않는다.** 화면에 "높음 · supply_drought" 로 나란히

**규칙이 아닌 것 (명시적 제외):**
- 기사 건수 기반 편차 — 언론 관심도이지 공급이 아님 (프록시 방향 불일치). 기존 geo Plan의 baseline.py 기사 건수 기저선은 **"커버리지 정직성"(c) 용도로만 유지**하고 공급 판정에는 쓰지 않는다
- 금리·cap rate — IC Helper 영역

---

## 6. 저장 구조 초안

```
data/market/
  bps_cbsa.csv          # 원장. 월×CBSA, 5+ units total/rep, value. append-only
  bps_download_log.csv  # 어느 파일을 언제 받았는지 (재현성)
  soc_lag.csv           # 연×region×bucket
  context_latest.json   # 전 CBSA 최신 market_context 덤프 (화면용)
market_flags.csv        # 렌즈. article_id 키. 루트 (geo_tags.csv와 같은 위치)
market_context.py       # 순수 함수. 조회·계산
market_rules.py         # 규칙 6개. flag 부여
market_collect.py       # BPS/SOC 다운로드·파싱·append
market_tagger.py        # geo_tags.csv × market_context → market_flags.csv + context_latest.json
tests/test_market_rules.py
```

- `articles.csv` 스키마 불변 (I1·I2 계승)
- `bps_cbsa.csv`는 **원본 29열을 다 보관하지 않는다** — 5+ units의 total·rep·value와 1-unit units만. 2~4유닛은 무관. 단 원본 .xls는 `data/market/raw/`에 그대로 둔다 (원장 보존, 재파싱 가능). 용량: 150KB × 84개월 ≈ 13MB — GitHub 허용

---

## 7. geo 태깅 의존성

| 작업 | geo 필요? | 비고 |
|---|---|---|
| BPS·SOC 수집기 + 기저선 계산 | **아니오** | CBSA 코드가 BPS에 이미 있음 |
| context_latest.json + 마켓워치 차트 | **아니오** | 전 CBSA 또는 관심 CBSA 목록 하드코딩으로 시작 |
| 기사별 market_flags | **예** | geo_tags.csv의 `geo_cbsa` 필요 |
| 규칙 임계값 보정 | 아니오 | BPS 전수 분포로 보정 |

**함의:** Phase 1의 80%는 geo 없이 진행 가능하다. geo가 끝나는 날 `market_tagger.py` 한 번 실행으로 기존 5,496건 소급 적용. **geo 백필과 market 백필을 같은 날 돌린다.**

---

## 8. 리스크

| ID | 리스크 | 대응 |
|---|---|---|
| K1 | BPS .xls 파싱이 헤더 2행·병합 셀로 깨짐 | 샘플 파일(ma0401y.txt)로 열 순서 확정. 열 이름이 아닌 **열 위치**로 읽고 테스트 고정 |
| K2 | Census 사이트가 Actions 러너에서 차단 | diagnose_feeds 선례대로 **일회성 진단 워크플로**로 먼저 확인. 차단 시 수동 월 1회 업로드로 전환 |
| K3 | CBSA vintage 불일치(2019~23 파일) | 코드 불일치 행 drop + 로그. 기저선 3년이면 2023-10 이후만 써서 영향 최소 |
| K4 | 임계값을 직관으로 정해 과잉 발동 | Phase 1 실측 분포 기반 보정 절차를 Plan에 고정 |
| K5 | 규칙이 늘어남 | 6개 상한을 Plan 불변조건에 명시 |
| K6 | 화면에 두 열이 나란히 뜨면 사용자가 합쳐서 읽음 | 열 이름을 "기사 중요도" / "시장 맥락"으로 분리. 시장 맥락은 flag 이름 그대로 표시, 점수화 금지 |
| K7 | Apartment List 자동 수집 불가 | Phase 2에서 확인. 불가 시 수동 경로 |

---

## 9. 미해결 질문 (Plan 전 결정 필요)

| ID | 질문 | 기본안 |
|---|---|---|
| Q1 | 기저선 창: 2년 vs 3년 | 3년 (§4.1.5) |
| Q2 | 보고 비율 임계: 70%? | 70%, Phase 1 실측 후 보정 |
| Q3 | 관심 CBSA 목록을 하드코딩할지, BPS 전수를 다 계산할지 | **전수 계산** (약 900 CBSA × 월 1회, 무시 가능한 비용). 화면만 관심 목록 필터 |
| Q4 | 기존 프롬프트의 하드코딩 지역 규칙을 market_flags 도입 후 제거할지 | **유지.** 제거는 재분류를 유발. 별도 결정 |
| Q5 | S4(completion_wave) 분모 stock을 Phase 1에 넣을지 | **Phase 2.** ACS 5+유닛 재고가 필요. Phase 1은 S1~S3만 |
| Q6 | market_flags.csv를 geo_tags.csv에 합칠지 별도로 둘지 | **별도.** 렌즈가 다르면 파일이 다르다. 규칙 재계산 시 geo를 건드리지 않음 |
| Q7 | Actions 스케줄: BPS 월간 수집을 daily_collect에 넣을지 별도 워크플로로 | **별도 `monthly_market.yml`.** 매월 25일(Census 공표 후). daily와 충돌 방지(A1 교훈) |

---

## 10. 공모전 채점 대응 지점

| 항목 | 이 기능이 주는 것 |
|---|---|
| 업무 개선효과 30 | Before: "Atlanta 기사 건수 평소 대비 2배" / After: "Atlanta 5+유닛 허가 12개월 합 평년 대비 0.6배, 보고율 94%" — 지표가 언론 관심도에서 실제 공급으로 바뀜. 산출 근거는 BPS 파일명·행 번호까지 추적 가능 |
| 창의·독창성 30 | 공급 퍼널(허가→준공 예측)과 뉴스 해석을 한 화면에. CoStar는 숫자만, 뉴스 앱은 해석만. 둘을 CBSA 키로 붙인 것 |
| 확산 가능성 30 | 원칙 ③ "LLM은 추출, Python은 판정"의 **두 번째 적용 사례**. IC Helper에서 한 번, The Brief에서 또 한 번 — 원칙이 앱 특수성이 아님을 보임. 체크리스트 항목으로 그대로 들어감 |
| 시스템 구현도 10 | 공공 원출처 자동 수집, 재현 가능 규칙, 테스트 |

---

## 11. 문서 이력

| 버전 | 일자 | 변경 |
|---|---|---|
| v0.1 | 2026-10-15 | 최초 작성. 코드 리서치(classifier·index.html·weekly_report), BPS 파일 구조 확정, SOC URL 확정, Legistar Seattle 응답 확인·Atlanta/Dallas 불응답 확인, 길 B 채택 |

---

## 출처

- Census BPS 월간 CBSA 파일 목록: https://www.census.gov/construction/bps/msamonthly.html
- Census BPS 샘플 파일(열 구조): https://www.census.gov/construction/bps/sample/ma0401y.txt
- Census BPS 방법론 변경(2022 cutoff sample): https://www.census.gov/newsroom/press-releases/2022/construction-monthly-building-permits.html
- Census SOC 소요기간 테이블: https://www.census.gov/construction/nrc/data/time.html
- NAHB 2025 멀티패밀리 공사기간 분석: https://eyeonhousing.org/2026/09/shorter-apartment-construction-time-in-2025/
- Zillow Research Data: https://www.zillow.com/research/data/
- Apartment List Data: https://www.apartmentlist.com/rentonomics/rental-price-data/
- Census HVS 분기 공실률: https://www.census.gov/housing/hvs/data/rates.html
- Legistar Web API (Seattle 응답 확인): https://webapi.legistar.com/v1/seattle/matters
- IRS SOI Migration 2021–2022: https://www.irs.gov/node/136131
