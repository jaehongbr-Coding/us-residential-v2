# research.md — The Brief 지리 태깅(geo tagging) 리서치

> 프로젝트: The Brief (us-residential-v2) × IC Helper 연동
> 작성 목적: 표준 앱 개발 방법론 1단계(리서치) 산출물
> 작성일: 2026-08-24
> 신뢰도 표기: [확인됨] 검색·공개출처 검증 / [학습지식] 검색 미검증 / [추정]

---

## 0. 이 문서가 답하려는 질문

1. 왜 geo 태깅이 필요한가 — 뉴스 누적 데이터가 CoStar·브로커·GP 통화로 대체 불가능한 지점은 어디인가
2. geo 태깅이 기존 분류(category / event_tags / woomi_relevance)를 오염시킬 위험은 실제로 존재하는가
3. 지리 어휘체계(vocabulary)를 무엇으로 삼을 것인가 — 그 선택의 함정은 무엇인가
4. 기저선(base rate) 통계를 성립시키려면 어떤 데이터 조건이 필요한가
5. 지금 당장(구현 전에) 해야 하는 비가역적 조치는 무엇인가

---

## 1. 결론 요약 (먼저 읽을 것)

| # | 결론 | 근거 절 |
|---|---|---|
| C1 | **보관기간 90일 정책을 즉시 연장해야 한다. 이것이 최우선이며 코드 작업보다 앞선다.** 매일 91일차 데이터가 영구 소실되고 있고, 이는 나중에 복구 불가능하다. | §5.1 |
| C2 | geo 태깅은 기존 분류를 오염시키지 **않는다.** 단, `classifier.py`를 수정하지 않고 별도 모듈로 분리한다는 조건 하에서만. | §3 |
| C3 | 어휘체계는 **CBSA 코드(5자리 숫자)를 키로, 명칭은 표시용으로만** 사용한다. 명칭은 vintage마다 바뀌지만 코드는 상대적으로 안정적이다. | §4.2 |
| C4 | 어휘 전체(925개 CBSA)를 프롬프트에 주입하는 방식은 **기각.** LLM은 지명 원문 추출만 하고, CBSA 매핑은 결정론적 Python 조회로 처리하는 2단계 구조를 채택한다. | §6 |
| C5 | MSA 단위는 Atlanta 같은 대형 메트로에서 **너무 거칠다.** 태깅 단계에서는 원문 지명을 그대로 보존하고, submarket 판단은 조회 계층으로 미룬다. | §4.3 |
| C6 | 동명 도시(Columbia MO vs Columbia SC) 등 모호한 경우는 **추정하지 않고 미해결로 남긴다.** 이 "정직한 실패" 설계가 공모전 차별화 지점이기도 하다. | §4.4 |
| C7 | 10월 제출 시점의 기저선은 **얇을 것이다.** 이를 숨기지 말고 표본 수(n)와 관측창 길이를 화면에 명시하는 설계로 간다. | §5.2 |

---

## 2. 현재 시스템 이해

### 2.1 확인된 사실 (업로드된 CLAUDE.md 기준)

| 항목 | 내용 |
|---|---|
| 파일 구조 | `collector.py` (RSS 수집·CoStar intake) / `classifier.py` (Claude 분류) / `app.py` (Streamlit) / `index.html` (GitHub Pages, 메인 화면) / `weekly_report.py` |
| 단일 데이터 저장소 | `articles.csv` — 16개 컬럼 확정, "삭제/스키마 변경 금지" 규칙 존재 |
| 컬럼 16개 | article_id, collected_at, published_at, source, title, url, summary, classified, category, event_tags, signal_type, sector, woomi_relevance, claude_rationale, access_limited, korean_summary |
| 분류 모델 | Sonnet 4.6 (Haiku에서 업그레이드), Batch API 적용 |
| 데이터량 | 5,442건 (CSV 손상 복구 후: 5,576 → 5,442) |
| 보관기간 | 90일 |
| RSS | 30개 피드 + Blue Vista 175개 대학 Student Housing Google News RSS |
| 자동화 | GitHub Actions 매일 06:00 KST 수집·분류 / 매주 월요일 06:00 KST 주간 리포트 |
| 배포 | GitHub Pages `https://jaehongbr-coding.github.io/us-residential-v2/` (메인), Streamlit(보조) |
| category | 개발 / 시장 / GP·자본흐름 — **3개 값만 허용, 배타적** |
| event_tags | construction_start / delivery / permit / land_acquisition / transaction / acquisition / JV / policy / market_data / rent_occupancy / construction_cost / financing — **복수 허용** |
| 특기 규칙 | `financing`은 category 결정에 절대 사용하지 않고 event_tags에만 사용 |
| Known GP | KW / HS / PCCP / Blue Vista / Lionheart / NexMetro / Middleburg / Hillpointe — 항상 woomi_relevance 높음 |

### 2.2 데이터량 정합성 검증 [추정]

5,442건 ÷ 90일 ≈ **일 60건**. 보관기간과 총량이 정합한다. 즉 90일 이전 데이터는 이미 물리적으로 삭제된 상태로 판단된다. → §5.1의 긴급성 근거.

### 2.3 ⚠️ 구현 전 반드시 확인해야 할 항목 (코드 리서치 공백)

실제 소스 파일 없이 작성된 문서이므로, 아래는 구현 착수 전에 **저장소에서 직접 확인**해야 한다. 확인 결과에 따라 Plan.md의 일부가 달라진다.

| # | 확인 항목 | 왜 중요한가 | 확인 방법 |
|---|---|---|---|
| V1 | `collector.py`가 CSV 헤더를 어디에 하드코딩하는가 (리스트 상수? pandas DataFrame 컬럼?) | 컬럼 추가 시 수집기가 16컬럼으로 덮어쓰면 신규 컬럼이 매일 날아간다 | `grep -n "article_id" collector.py` |
| V2 | `classifier.py`가 articles.csv를 **전체 재작성**하는가, 해당 행만 수정하는가 | 전체 재작성이면 geo 컬럼이 유실된다 | `grep -n "to_csv\|DictWriter" classifier.py` |
| V3 | 90일 pruning 로직의 위치와 조건 | C1(보관기간 연장)을 어디서 바꿔야 하는지 결정 | `grep -rn "90\|timedelta\|retention" *.py` |
| V4 | `index.html`이 CSV를 파싱하는 방식 — 컬럼 **이름** 기준인가 **인덱스** 기준인가 | 인덱스 기준이고 길이 검증이 있으면 컬럼 추가로 화면이 깨진다 | `index.html`에서 CSV 파싱부 확인 |
| V5 | `app.py` Streamlit의 컬럼 참조 방식 | 동일 | `grep -n "columns\|iloc" app.py` |
| V6 | GitHub Actions 워크플로 파일명과 단계 순서 | geo_tagger 단계를 어디에 끼울지 | `.github/workflows/` 확인 |
| V7 | `articles.csv` 실제 최소/최대 published_at | 기저선 관측창 실측 | `python -c "import pandas as pd; d=pd.read_csv('articles.csv'); print(d.published_at.min(), d.published_at.max(), len(d))"` |
| V8 | Columbia MO / Atlanta 관련 기사 실제 건수 | 데모 가능성 사전 판단 | title+summary 문자열 검색 |
| V9 | `requirements.txt` 현재 목록 | 신규 의존성 최소화 판단 | 파일 확인 |

---

## 3. 리스크 분석: geo 태깅이 기존 분류를 오염시키는가

### 3.1 과거 사례의 성격

개발 초기에 "필터링 기준 키워드를 바꾸니 개발 / GP동향 / 시장 분류 결과가 크게 변했다"는 경험이 있었다. 이 현상의 구조적 원인은 다음과 같다.

**category는 배타적 분할(mutually exclusive partition)이다.** 기사 1건은 반드시 3개 값 중 하나만 가진다. 총합이 고정된 파이를 나누는 구조이므로, 한 통의 기준을 넓히면 반드시 다른 통에서 질량이 빠져나간다. `financing`을 category 결정에서 배제한 규칙도 정확히 이 제로섬 성질에 대한 대응으로 해석된다 — financing은 개발·시장·GP 세 카테고리 모두에 자연스럽게 붙는 태그라 category 결정 인자로 쓰면 분류가 불안정해진다.

### 3.2 geo는 구조가 다르다

| 성질 | category | geo |
|---|---|---|
| 유형 | 분류(classification) — 판단 | 추출(extraction) — 사실 |
| 배타성 | 배타적 3분할 | 배타 아님, 경쟁 통 없음 |
| 총합 제약 | 있음 (제로섬) | 없음 |
| 정답 존재 | 해석 여지 큼 | 기사에 명시되거나 아니거나 |
| 기준 변경 영향 | 전체 분포 재배열 | 해당 필드만 변화 |

기사가 "Columbia, MO"를 언급하면 언급한 것이고, 안 하면 안 한 것이다. geo 값이 채워진다고 해서 category가 바뀔 **구조적 경로가 존재하지 않는다.**

### 3.3 다만 실재하는 위험 하나: 프롬프트 간섭

구조적 제로섬은 없지만, **동일 프롬프트에 geo 지시문을 추가하면 category 출력이 흔들릴 수 있다.** LLM은 프롬프트 전체를 하나의 맥락으로 읽으므로 지시문이 늘어나면 기존 판단의 가중치가 미세하게 달라진다. 이것은 구조가 아니라 구현의 문제이며, **완전히 회피 가능하다.**

**회피 설계:**
- `classifier.py`를 **동결(freeze)** 한다. 이번 작업에서 단 한 줄도 수정하지 않는다.
- `geo_tagger.py`를 신규 생성한다. 별도 API 호출, 별도 프롬프트.
- geo 프롬프트는 category / event_tags / sector / woomi_relevance를 **언급조차 하지 않는다.**
- geo_tagger가 쓰는 컬럼은 `geo_*` 접두 컬럼으로만 제한한다. 기존 16컬럼은 읽기 전용.

### 3.4 추가 안전장치

**(a) 회귀 테스트 세트** — 작업 착수 전 고정 샘플(권장 300건)의 `category / event_tags / woomi_relevance` 스냅샷을 저장하고, geo 작업 후 재측정하여 **변화율 0%** 를 확인한다. 구조상 당연히 0이어야 하며, 0이 아니면 파이프라인이 섞인 것이므로 즉시 탐지된다. 이 스냅샷은 공모전 제안서의 "시스템 구현도" 근거 자료로도 사용한다.

**(b) geo를 The Brief UI 필터로 승격하지 않는다 (이번 라운드 한정)** — 핵심 모니터링·전략 신호 모니터에 geo 필터를 넣으면 커버리지 공백이 있는 기사가 화면에서 사라진다. 그러면 본 기능이 실제로 열화된다. geo는 IC Helper 쪽 조회용 인덱스로만 사용하고 The Brief 화면은 현행 유지.

**(c) `woomi_relevance` 산식에 geo를 절대 넣지 않는다** — "우리 딜 지역이면 높음" 규칙은 매력적으로 보이지만, 딜 파이프라인이 바뀔 때마다 과거 기사의 relevance가 바뀐다. **재현 불가능한(non-reproducible) 시스템**이 된다. 딜과의 매칭은 IC Helper 조회 시점에 수행한다.

---

## 4. 지리 어휘체계(vocabulary) 리서치

### 4.1 CBSA 개요 [확인됨]

- **CBSA(Core Based Statistical Area)** = Metropolitan Statistical Area(MSA) + Micropolitan Statistical Area(μSA). OMB가 정의하고 Census Bureau가 파일로 배포한다. CBSA는 **항상 카운티(또는 카운티 등가 단위)의 집합**으로 구성된다.
  - 출처: https://www.census.gov/geographies/reference-files/time-series/demo/metro-micro/delineation-files.html
- 기준: 도시 핵심부 인구 5만 이상 → MSA, 1만 이상 5만 미만 → μSA. 인접 카운티는 통근 비율(25% 기준)로 편입.
- 현행 vintage는 **2020 Census 기반, 2023년 7월 OMB Bulletin No. 23-01**로 발표된 delineation이다.
  - 출처: OMB Bulletin 23-01 / https://www.ruralhealthinfo.org/resources/21528
- 규모: CRS(의회조사국) 보고서 IF12704는 393개 MSA(1,186개 카운티), 542개 μSA(658개 카운티), 37개 Metropolitan Division, 184개 CSA, CBSA 미분류 카운티 1,300개로 집계한다.
  - 출처: https://www.congress.gov/crs-product/IF12704
  - ⚠️ **상충 데이터 병기**: 일부 2차 출처는 387 MSA / 538 μSA로 기재한다. vintage 및 집계 시점 차이로 보이나 확인되지 않았다. **구현 시 숫자를 문서에서 가져오지 말고 delineation 파일을 직접 파싱해 카운트할 것.**

### 4.2 vintage 문제 — 명칭은 바뀐다, 코드는 상대적으로 안정적이다

이것이 어휘체계 설계에서 가장 실무적으로 중요한 함정이다.

**사례 A — Atlanta** [확인됨]
- CBSA 코드: **12060** (불변)
- 2018 vintage 명칭: Atlanta-Sandy Springs-**Alpharetta**, GA
- 2023 vintage 명칭: Atlanta-Sandy Springs-**Roswell**, GA
- 출처: https://33n.atlantaregional.com/data-diversions/definitions-understand / FHFA Technical Note https://www.fhfa.gov/document/11-5a-technical_note_pt1_text.pdf
- 문제: FRED 등 주요 데이터 소스에 **두 명칭이 모두 살아 있다.** 명칭을 키로 삼으면 동일 지역이 두 개로 쪼개진다.

**사례 B — Columbia, MO** [확인됨]
- CBSA 코드: **17860** (불변)
- 2018 vintage(OMB 18-04): Boone, Audrain, Randolph, Cooper, Howard — **5개 카운티**
- 2023 vintage: Boone, Cooper, Howard — **3개 카운티** (Audrain·Randolph 제외)
- 출처: https://en.wikipedia.org/wiki/Columbia_metropolitan_area_(Missouri) / Census CBSA-EST2022 데이터셋 https://www2.census.gov/programs-surveys/popest/datasets/2020-2022/metro/totals/cbsa-est2022.csv
- 문제: 카운티 구성이 바뀌면 **기저선의 분모가 바뀐다.** vintage를 하나로 고정하지 않으면 시계열 비교가 무의미해진다.

**→ 설계 결정 (C3):**
- 저장 키는 **`geo_cbsa_code` (5자리 문자열)**. 조인·집계는 전부 코드 기준.
- 명칭은 `geo_cbsa_title`에 표시용으로만 저장.
- **vintage는 2023(OMB 23-01)으로 고정**하고, 크로스워크 파일 상단에 vintage를 명시한다.
- 구 명칭(Alpharetta 버전 등)은 alias 테이블에 넣어 같은 코드로 흡수한다.

### 4.3 MSA 단위의 해상도 한계 (C5)

**Atlanta MSA는 29개 카운티, 면적 약 8,376 sq mi다** [확인됨: https://en.wikipedia.org/wiki/Metro_Atlanta]. 또한 2023 vintage에서 두 개의 Metropolitan Division으로 분할된다 — Marietta, GA MD (Bartow·Cherokee·Cobb·Haralson·Paulding)와 Atlanta-Sandy Springs-Roswell, GA MD (나머지 24개 카운티) [확인됨: https://33n.atlantaregional.com/data-diversions/definitions-understand].

실무적 함의: **Cartersville(Bartow County)의 MF 착공과 Buckhead의 MF 착공은 같은 "Atlanta MSA"지만 경쟁 공급으로서는 무관하다.** MSA 단위 기저선만으로는 우리 딜의 경쟁 공급을 판정할 수 없다.

**→ 설계 결정:** 태깅 단계에서 submarket을 판정하려 들지 않는다. 대신 **LLM이 추출한 원문 지명을 그대로 `geo_place_raw`에 보존**하고, submarket 그룹핑은 IC Helper 조회 계층에서 딜별로 수행한다.

원칙: **태깅 계층은 사실만 기록하고, 판단은 조회 계층으로 미룬다.** 판단을 태깅에 넣는 순간 §3.1의 제로섬 불안정성이 geo에도 도입된다.

### 4.4 동명 도시 — 모호성 처리 (C6)

가장 명확한 사례가 하필 우리 딜에 있다.

| 명칭 | CBSA 코드 | 유형 |
|---|---|---|
| Columbia, MO | 17860 | MSA |
| Columbia, SC | 17900 | MSA |

출처: Census CBSA-EST2022 데이터셋 (위 4.2와 동일)

기사 제목에 "Columbia"만 있고 주(state)가 없으면 **판정 불가**다. 이때 어느 한쪽으로 추정하면 기저선이 오염된다. Student Housing 기사라면 MO일 확률이 높지만, 그런 추론을 태깅에 넣으면 그 순간 geo가 "판단"이 되어 §4.3의 원칙을 위반한다.

**→ 설계 결정:** 주 정보가 없어 다중 매칭되면 `geo_confidence = "none"`, `geo_cbsa_code`는 비움. 원문 지명은 `geo_place_raw`에 남긴다. **추정하지 않는다.**

기타 주의 대상 동명 지명 [학습지식 — 크로스워크 빌드 시 실측 필요]: Springfield(MO/IL/MA/OH), Columbus(OH/GA/IN), Portland(OR/ME), Kansas City(MO/KS 동일 MSA), Charleston(SC/WV), Jackson(MS/TN/MI), Aurora(CO/IL), Athens(GA/OH/TN).

### 4.5 대학도시 / Student Housing 특수성

Blue Vista 175개 대학 RSS를 운영 중이므로, Student Housing 기사에는 **CBSA 명칭이 아니라 대학명이 등장**하는 경우가 많다.

- "Mizzou" / "University of Missouri" → Columbia, MO (17860)
- "UGA" / "University of Georgia" → Athens-Clarke County, GA (별도 MSA. Atlanta MSA가 **아니다.** Atlanta CSA에는 포함) [확인됨: https://33n.atlantaregional.com/data-diversions/definitions-understand]
- "Georgia Tech" → Atlanta MSA (12060) 내

**→ 설계 결정:** `geo_aliases.yaml`에 **대학명 → CBSA 코드** 매핑을 별도 섹션으로 둔다. Blue Vista 175개 대학 목록이 이미 collector.py에 존재하므로, 그 목록을 시드로 삼으면 수작업이 크게 줄어든다 [추정 — V1 확인 필요].

⚠️ 방향성 검증: 대학 소재지를 CBSA의 프록시로 쓰는 것은 타당하다 — 대학은 물리적 위치가 고정되어 있고, 학생주택 공급은 캠퍼스 반경 내에서 발생하므로 측정하려는 개념(지역 공급)과 지표(대학 소재 CBSA)의 방향이 일치한다.

### 4.6 어휘 소스 목록 (구현 시 사용)

| 소스 | 내용 | 위계 | URL |
|---|---|---|---|
| Census Delineation Files | CBSA ↔ 카운티, CSA, Metro Division (2023 vintage) | ① 원출처 | https://www.census.gov/geographies/reference-files/time-series/demo/metro-micro/delineation-files.html |
| Census Principal Cities File | CBSA별 principal city 목록 — **city→CBSA 시드로 결정적** | ① 원출처 | 위 페이지 내 "Principal cities of metropolitan and micropolitan statistical areas" |
| Census CBSA Population Estimates | CBSA 코드·명칭·카운티 검증용 | ① 원출처 | https://www2.census.gov/programs-surveys/popest/datasets/2020-2022/metro/totals/cbsa-est2022.csv |
| NBER CBSA↔FIPS Crosswalk | 대안/검증용 크로스워크 (2026년 5월 확장 업데이트) | ② 기관 | https://www.nber.org/research/data/census-core-based-statistical-area-cbsa-federal-information-processing-series-fips-county-crosswalk |
| OMB Bulletin 23-01 | 현행 delineation 원문 | ① 원출처 | https://www.ruralhealthinfo.org/resources/21528 |

⚠️ **네트워크 제약**: 현재 개발 환경의 허용 도메인에 `census.gov`가 포함되지 않을 수 있다. 파일은 **로컬에서 수동 다운로드 후 저장소에 커밋**하는 방식으로 간다. 어차피 런타임 네트워크 의존을 없애는 것이 옳다.

---

## 5. 기저선(base rate) 통계 설계

### 5.1 🚨 최우선 조치: 보관기간 90일 정책 (C1)

**이것이 이 문서 전체에서 가장 시급하며, 코드 작업보다 앞선다.**

- 현재 보관기간 90일. 매일 자동화가 돌면서 91일차 기사가 **영구 삭제**되고 있다.
- 삭제된 데이터는 복구 불가능하다. RSS는 과거 기사를 다시 주지 않는다.
- 오늘(8/24) 보관기간을 연장하면 10월 초 제출 시점에 약 **135~140일** 관측창을 확보한다.
- 9월 중순으로 미루면 **약 110일**에 그친다. 하루 지연 = 하루 영구 손실.

**권고: Plan.md 승인을 기다리지 말고, 보관기간 상한을 제거하거나 최소 730일로 변경하는 단일 커밋을 오늘 실행할 것.** 이 변경은 기존 로직에 영향이 없고(삭제를 안 할 뿐), 되돌리기도 쉽다.

⚠️ 부작용 검토: 보관기간 연장 시 (a) articles.csv 파일 크기 증가 — 5,442건 CSV가 수 MB 수준이라면 GitHub 100MB 제한까지 여유 충분 [추정, V7 확인 필요], (b) `index.html` 로딩 속도 저하 가능 — 다만 UI는 이미 30일 기본 필터를 쓰므로 표시량은 불변, (c) 재분류 스크립트 실행 비용 증가.

### 5.2 관측창과 표본 (C7)

기저선이 성립하려면 **분모가 있어야 한다.** "이번 주 Columbia MO 기사 4건"은 "평소 주당 0.3건"이라는 기준선이 있을 때만 의미를 갖는다.

현실 판단:
- 제출 시점 관측창 ≈ 135일 (보관기간을 오늘 연장한다는 전제)
- 착공·인허가는 계절성이 있다. 135일은 계절성을 흡수하기에 **짧다.**
- Sun Belt 주요 MSA(Atlanta, Dallas, Phoenix 등)는 표본이 충분할 가능성이 높다 [추정]
- Columbia MO 같은 tertiary 시장은 표본이 한 자릿수일 가능성이 높다 [추정 — V8로 실측 필요]

**→ 설계 결정:**
- 기저선을 제시할 때 **관측창 길이(일)와 표본 수(n)를 항상 함께 표시**한다.
- 임계치 미만이면 수치를 내지 않고 "커버리지 부족" 상태를 명시적으로 반환한다.
- 임계치 제안 (초기값, 실측 후 조정): 관측창 내 해당 CBSA 기사 **12건 미만이면 커버리지 부족**. 근거: 주당 최소 1건 × 12주 — 주 단위 편차를 논하려면 최소한의 주별 관측점이 필요하다. [추정 — 통계적 엄밀성보다 실무적 보수성 기준]

### 5.3 편차 지표 설계

단순 비율보다 **관측창 대비 최근 구간의 상대 빈도**를 쓴다.

```
baseline_weekly = (관측창 내 해당 CBSA 기사 수) / (관측창 주 수)
recent_weekly   = (최근 4주 해당 CBSA 기사 수) / 4
ratio           = recent_weekly / baseline_weekly
```

표본이 작을 때 비율은 폭주한다(0.3 → 4면 13배). 그래서:
- ratio는 **표시하되 단독 판단 근거로 쓰지 않는다.**
- 항상 원자료(최근 4주 실제 건수, 기저선 건수, n, 관측창)를 병기한다.
- 특정 배수 이상에서 "이상치"라고 단정하는 자동 판정은 **이번 라운드에서 구현하지 않는다.** 표본이 그 수준의 주장을 지탱하지 못한다.

### 5.4 scope 필터의 필요성

전국 단위 기사(NMHC 센티먼트 조사, 전국 착공 통계 등)가 본문에서 Atlanta를 스쳐 언급하면, 그것이 Atlanta 기저선에 잡힌다. 이는 **오탐의 주요 원천**이다.

**→ 설계 결정:** `geo_scope` 컬럼을 두어 `national / regional / metro / local` 을 구분하고, 기저선 산출 시 `metro` + `local`만 카운트한다. `national`은 배제.

---

## 6. 추출 방식 대안 비교 (C4)

| 대안 | 방식 | 장점 | 단점 | 판정 |
|---|---|---|---|---|
| A | CBSA 925개 명칭을 프롬프트에 전량 주입, LLM이 그중 선택 | 출력이 어휘 내로 강제됨 | 프롬프트 토큰 폭증(수만 토큰 × 5,442건), 비용·지연 심각, 긴 목록에서 LLM 선택 정확도 저하, 프롬프트 비대화로 §3.3 간섭 위험 증가 | **기각** |
| B | LLM이 자유롭게 지역명 생성 | 구현 단순 | "Columbia, MO" / "Columbia Missouri" / "Boone County" / "mid-Missouri"가 모두 다른 값으로 쌓임 → 집계 불가. 과거 겪은 불안정성의 재현 | **기각** |
| C | **2단계: LLM은 원문 지명 추출만 → Python 결정론적 크로스워크 조회** | 프롬프트 최소(간섭 위험 최소), 매핑이 100% 재현 가능·감사 가능, 크로스워크 수정 시 LLM 재호출 없이 재매핑 가능, 비용 최저 | 크로스워크 구축 초기 작업 필요, alias 관리 필요 | **채택** |
| D | 순수 규칙기반(정규식으로 지명 매칭) | LLM 호출 0 | "the metro area" 같은 문맥 지시어 처리 불가, 오탐 다수(Jackson이 인명인지 지명인지), 대학명 처리 취약 | **부분 채택** — C의 보조로 사용 |

### 6.1 채택안(C) 상세

**Stage A — LLM 추출 (Haiku)**
- 입력: title + summary
- 출력: 원문에 등장한 지명 문자열 배열 + 주(state) + 유형 + scope
- 프롬프트에 CBSA 목록 없음. category/event_tags/sector 언급 없음.
- 모델: **Haiku 4.5** — 개체명 추출은 Haiku급 과제이며, classifier(Sonnet 4.6)와 모델을 분리함으로써 구조적 독립성도 확보

**Stage B — Python 결정론적 해석**
- `data/geo/cbsa_crosswalk.json` 조회
- 정규화 → 매칭 → 다중 매칭 시 미해결 처리
- LLM 호출 없음. 100% 재현 가능. 크로스워크만 고쳐서 언제든 재실행 가능

**이 분리의 핵심 이점:** alias를 추가하거나 임계치를 바꿔도 **API 재호출이 필요 없다.** Stage A 출력을 원본 그대로 `geo_place_raw`에 보존하기 때문이다. 5,442건 재태깅을 반복해야 하는 상황이 원천적으로 사라진다.

---

## 7. 미해결 질문 (Plan.md 승인 전 결정 필요)

| # | 질문 | 선택지 | 초안 권고 |
|---|---|---|---|
| Q1 | 백필 범위 | (a) 전량 5,442건 (b) category=개발 + 공급 관련 event_tags 우선 | (b)로 시작, 여유 시 (a). 단 Stage A 비용이 낮으므로 전량도 현실적 |
| Q2 | 기사 1건에 여러 CBSA가 등장하면? | (a) 대표 1개만 (b) 복수 저장 | (b) 파이프 구분 복수 저장 + 대표 1개 별도 표기. 기저선은 복수 전부 카운트 |
| Q3 | 커버리지 임계치 | 12건 / 20건 / 실측 후 결정 | V8 실측 후 확정 |
| Q4 | Metropolitan Division 사용 여부 | (a) CBSA만 (b) MD도 별도 컬럼 | (a). MD는 37개뿐이고 복잡도만 늘린다. 해상도는 `geo_place_raw`로 해결 |
| Q5 | The Brief UI에 geo 노출 여부 | (a) 미노출 (b) 검색 보조로만 | (a) 이번 라운드 미노출 — §3.4(b) |

---

## 8. 참고: 이 리서치가 공모전 채점에 대응하는 지점

| 채점 항목 | 배점 | 이 문서의 대응 |
|---|---|---|
| 업무 개선효과 | 30 | §5 기저선 — 언더라이팅 가정에 대한 독립 검증 절차 신설 |
| 창의·독창성 | 30 | §4.4, §5.2 "모르면 모른다고 출력하는" 설계 |
| 확산 가능성 | 30 | §6 2단계 구조는 도메인 무관 — 어휘체계만 교체하면 국내 지자체·자재·경쟁사 동향에 이식 |
| 시스템 구현도 | 10 | §3.4(a) 회귀 테스트로 기존 기능 무영향 입증 |

출처: 2026 AI Innovation Challenge 안내문 (2026.8.5) — 평가항목 업무 개선효과 30 / 창의·독창성 30 / 확산 가능성 30 / 시스템 구현도 10

---

## 9. 문서 이력

| 버전 | 일자 | 내용 |
|---|---|---|
| v0.1 | 2026-08-24 | 초안. 코드 리서치 공백(§2.3 V1~V9) 미해소 상태 |
