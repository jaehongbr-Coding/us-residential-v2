# US Residential Intelligence v2

## 프로젝트
US Residential Intelligence v2
우미글로벌 해외사업팀 미국 주거시장 뉴스 수집·분류 앱

## 설계 원칙 (2026.08 확립 — 변경 시 반드시 근거를 남길 것)

### 3계층 분리: 원장 / 렌즈 / 화면

| 계층 | 파일 | 역할 | 성격 |
|---|---|---|---|
| 원장(raw ledger) | collector.py | 판단 없이 담는다 | 되돌릴 수 없음 → 넓게 |
| 렌즈(lens) | classifier.py | 무엇이 중요한지 결정 | 언제든 교체 가능 → 좁게 |
| 화면 | index.html / app.py | 렌즈 결과를 보여준다 | 즉시 변경 가능 |

**collector.py에 "무엇을 볼지 판단하는" 필터를 넣지 않는다.**
단, 동일 기사의 물리적 중복 제거는 판단이 아니므로 허용한다.

### 왜 낮음 67.8%를 방치하는가 — 의도된 설계

수집분의 약 68%가 woomi_relevance=낮음이고, 그중 Mixed-use(오피스·물류·리테일)가
1,090건이다. 수집 단계에서 주거 키워드 필터로 걸러내면 API 비용과 노이즈가 줄지만,
2026.08 검토 결과 **하지 않기로 결정**했다.

이유는 비대칭성이다.
- 지금 안 거르면 → 나중에 언제든 거를 수 있다 (데이터가 남아 있다)
- 지금 거르면 → 되돌릴 수 없다 (RSS는 과거 기사를 주지 않는다)

우미글로벌은 현재 주거에 집중하지만 오피스·물류 섹터 전환 가능성을 열어둔다.
현 구조에서는 classifier.py의 SYSTEM_PROMPT 한 블록만 교체하면 Office Intelligence로
전환되며, 이미 쌓인 Mixed-use 1,260건이 그날 바로 과거 데이터가 된다.
수집 단계에 주거 필터를 박으면 이 전환이 불가능해진다.

**낮음 68%는 결함이 아니라 원장을 유지하는 비용이다.**

재검토 조건: API 월 청구액이 감당 범위를 넘을 때. 단 그때도 답은 수집 필터가 아니라
"Haiku 1차 선별 → Sonnet 정밀 분류" 방향이다. 원장은 유지하고 렌즈 비용만 줄인다.

### 확산 가능성

이 3계층 구조는 도메인 무관하다. 수집은 넓게, 판단은 프롬프트로 좁게 —
미국 주거 → 오피스뿐 아니라 국내 주택사업 인허가 동향, 자재비, 경쟁사 수주
모니터링에도 같은 원리로 이식된다.

### 원장의 물리 분리 (2026.09)

3계층 원칙이 파일 구조로 실현됐다. `archive/YYYY-MM.csv`가 원장, `articles.csv`가
작업본, `seen_index.db`가 인덱스다.

**articles.csv의 지위가 바뀌었다.** "단일 output"에서 "원장에서 파생되는 작업본"으로.
경로·파일명·CSV_COLUMNS(16개)는 여전히 고정이며 화면 계층(index.html/app.py/
weekly_report.py)은 이 파일만 읽으므로 그대로 동작한다. 다만 이제 내용을 삭제해도
`rebuild_working_set()`으로 원장에서 재생성 가능하다 — 예전처럼 "복구 불가능한
유일본"이 아니다.

**작업본 포함 기준**: published_at이 최근 90일 이내 **또는** source가
`"Player — "`로 시작(Player는 기간 무관 전량 유지). 임계치는
`WORKING_SET_MAX_ROWS` 초과 시에만 collector.py가 자동 재생성한다 —
매일 재생성하지 않는 이유는 파티션 분리의 의미(일상 실행은 append만) 유지.

**원장은 append-only다.** 한 번 쓴 과거 월 파티션은 다시 수정하지 않는다.
`.gitattributes`에 `archive/*.csv merge=union`으로 선언돼 있다.

**⚠️ merge=union의 알려진 한계**: union은 양쪽 변경을 모두 남기므로, 두 프로세스가
같은 기사를 각자 append하면 중복 행이 그대로 병합되어 남는다. 2026-09-03
article_id 142건 사고가 이 유형이었다(TODO #9, 2026.09 정리 완료 — 아래 참조).
archive/ 도입으로 새로 생긴 문제는 아니지만 파티션에도 동일하게 적용되므로,
TODO #8(이중 실행 원인)이 해결되기 전까지는 재발할 수 있다.

**article_id 완전 중복 142건 정리 완료 (TODO #9, 2026.09)**: 2026-09-03 daily_collect.yml
이중 실행으로 생긴 중복 중, collected_at 외 수집 필드(published_at/source/title/
url/summary/access_limited)가 전부 동일한 119건만 정리했다 — 같은 article_id 중
collected_at이 가장 이른 행을 남기고 나머지를 archive/articles.csv 양쪽에서
제거했다. 나머지 23건은 title/summary/source 등이 달라(같은 URL이지만 RSS
재수집 시 메타데이터가 미세하게 달라진 경우) 서로 다른 상황일 수 있어 손대지
않았다 — `removed_duplicates.log`에 제거 내역이 남아있다.

이 정리는 **append-only 원칙의 명시적 예외**다. 원장은 원칙적으로 과거 파티션을
다시 쓰지 않지만, "동일 기사의 물리적 중복 제거는 판단이 아니므로 허용한다"는
설계 원칙(위 "3계층 분리" 절)에 따라 `dedupe_duplicates.py`가 파티션을 통째로
rewrite했다. 재발 시(TODO #8 미해결) 같은 스크립트로 같은 방식으로 정리하면 된다.

**정합성 검증 기준선은 이제 0이다.** 이 정리 전까지는 archive↔labels.db
dry-run 비교에서 142건 불일치가 "알려진 노이즈"로 허용됐으나, 정리 후에는
0건이 정상이다. 향후 dry-run 비교에서 불일치가 1건이라도 나오면 노이즈로
넘기지 말고 즉시 실제 문제로 판정할 것.

**쓰기 순서 규칙**: 원장 → 작업본 → seen_index.db commit (수집 시), labels.db →
작업본 (분류 시). collector.py의 `save_articles()`가
`archive_manager.append_to_archive()`를 먼저 호출한 뒤 articles.csv에 append하고,
`main()`은 그 다음에만 `conn.commit()`한다. classifier.py는 `label_store.upsert_labels()`로
labels.db에 먼저 쓰고 commit한 뒤에만 articles.csv를 덮어쓴다. 두 경우 모두
영속 저장소(원장/labels.db)가 source of truth이므로 가장 먼저 확정해야 한다 —
반대 순서면 저장 실패 시 "이미 처리됨"만 기록되고 실제 내용은 영영 잃는다.

**🟢 classifier.py 쓰기가 원장에 반영되지 않는 문제 — labels.db 분리로 해결 (2026.09).**
과거에는 classifier.py가 articles.csv(작업본)만 갱신해, archive/ 파티션은 수집
시점의 미분류 원본 그대로 남았다. `rebuild_working_set()`이 발동하면 원장의
미분류 원본이 분류 결과를 덮어써 소실되는 구조적 위험이 있었다 (임시로
"현재 작업본 classified=True 우선" 응급 가드를 넣었으나 근본 해법은 아니었다).

**근본 해법 — 렌즈 산출물을 labels.db(SQLite)로 물리 분리했다.** 필드를 두
부류로 나눈다:

| 구분 | 필드 | 저장 위치 |
|---|---|---|
| 수집 사실 (8개) | article_id, collected_at, published_at, source, title, url, summary, access_limited | archive/ (원장) |
| 렌즈 산출물 (8개) | classified, category, event_tags, signal_type, sector, woomi_relevance, claude_rationale, korean_summary | labels.db |

articles.csv(CSV_COLUMNS 16개, 화면 계층 호환을 위해 불변)는 이제 **원장 +
labels.db의 조인 뷰**다. `rebuild_working_set()`이 원장에서 수집 8필드를 읽고
`label_store.get_labels()`로 렌즈 8필드를 조회해 병합한다 — labels.db에 없는
article_id는 렌즈 필드가 빈 값(classified='False')으로 채워진다. 위 응급
가드는 이 함수에서 제거했다 — labels.db가 렌즈 산출물의 유일한 source of
truth가 되면서 가드가 대체됐다.

**이 분리로 "SYSTEM_PROMPT 한 블록 교체 → Office Intelligence 전환"이 실제로
가능해졌다.** labels.db를 비우고 재분류하면 되며, 원장(archive/)은 전혀 손대지
않는다 — 위 "3계층 분리" 절이 말하던 렌즈 교체가 파일 구조로 실현된 것이다.

`lens_version` 필드는 향후 렌즈를 교체하거나 2단 스크리닝(Haiku 1차 선별 →
Sonnet 정밀 분류)을 도입할 때 어느 버전으로 분류됐는지 구분하기 위한 자리다.
현재는 `'v1'`로 고정.

**archive/ 축소는 아직 보류 중.** 원장 파티션에는 여전히 렌즈 8필드가 남아있다
(labels.db 이관 시 삭제하지 않았다). labels.db가 몇 주 운영 검증된 뒤 축소할
것 — TODO 참조.

**참고 — weekly_report.py semi-annual 폴백 영향**: quarterly·semi-annual 리포트는
평소 weekly `.md` 재요약 경로를 쓰지만, 폴백 경로(주간 리포트 3개 미만일 때
articles.csv 직접 분석)는 이제 90일보다 먼 데이터를 가져올 수 없다 — semi-annual
(180일) 폴백이 불완전한 데이터로 리포트를 생성할 위험이 있다.

## 파일 구조
- collector.py: RSS 수집 → 원장(archive/) + 작업본(articles.csv) 동시 append
- archive_manager.py: 원장 읽기·쓰기 모듈 (append_to_archive / read_archive /
  list_partitions / rebuild_working_set). CSV_COLUMNS는 collector.py에서 import.
  rebuild_working_set()은 원장 + labels.db를 조인해 작업본을 만든다
- label_store.py: 렌즈 산출물(분류 8필드) 저장소 모듈 (open_labels / get_labels /
  upsert_labels / count_labels). LABEL_FIELDS 상수로 8필드 목록 정의
- migrate_to_archive.py: 일회성 마이그레이션 스크립트 (재실행 가능, 이미 완료됨).
  articles.csv → archive/ 파티션
- migrate_to_labels.py: 일회성 마이그레이션 스크립트 (재실행 가능, 이미 완료됨).
  articles.csv + archive/ → labels.db. 하드코딩된 검증 임계치가 있어 CI 자동화에는
  부적합 — 수동 실행 전용
- dedupe_duplicates.py: article_id 완전 중복 정리 도구 (재실행 가능). append-only
  예외로 archive/ 파티션을 rewrite한다 — TODO #8 재발 시 재사용
- classifier.py: Claude API 분류 (Haiku/Sonnet), run_classifier() export.
  분류 결과를 labels.db에 먼저 쓰고(upsert_labels) articles.csv를 그 다음 덮어쓴다
- app.py: Streamlit Article Feed + Market Dashboard
- archive/YYYY-MM.csv: 원장 — 월별 파티션, append-only(물리적 중복 제거는 예외),
  영구 보존, 절대 삭제 금지
- articles.csv: 작업본 — 원장 + labels.db의 조인 뷰, 삭제·스키마 변경은 여전히
  금지되나 이제 rebuild_working_set()으로 재생성 가능
- seen_index.db: 중복 체크 인덱스, articles.csv/archive에서 파생되는 캐시
- labels.db: 렌즈 산출물(분류 8필드) 저장소, articles.csv/archive에서 파생되되
  이제 이쪽이 분류 결과의 유일한 source of truth. article_id PRIMARY KEY

## 데이터 현황 (2026.08.24 실측)

| 항목 | 값 |
|---|---|
| 총 행 수 | 5,501건 (중복 article_id 0, 미분류 0) |
| 파일 크기 | 6.22MB (GitHub 100MB 제한 대비 여유) |
| published_at 범위 | 2026-03-13 ~ 2026-08-23 (명목 163일) |
| collected_at 범위 | 2026-06-08 ~ (앱 최초 가동일 = 2026-06-08) |
| **기저선 유효 관측창** | **2026-06-01 이후 (약 85일)** |
| 고유 소스 | 173개 (대학 SH 154 + 일반 피드 19) |
| Student Housing 소스 비중 | 24.5% (균질구간 기준) |

### ⚠️ 관측창 불균질 — 통계 산출 시 반드시 주의

3~5월 기사(614건)는 2026-06-08 최초 가동 시 대학 Google News RSS가 소급 반환한
백필분이다. 일반 RSS 피드는 최근 20~50건만 노출하므로 그 구간에 일반 피드 기사가
3월 4건 / 4월 3건뿐이다.

**이 구간을 기저선·트렌드 통계에 포함하면 "과거엔 조용했는데 최근 급증"이
모든 지역·모든 주제에서 나타나는 착시가 생긴다.**
통계 산출 시 published_at >= 2026-06-01 하한을 반드시 적용할 것.

semi-annual(180일) 리포트는 이 구간을 포함하므로, 기사 건수의 시계열 변화를
시장 신호로 해석하지 않도록 프롬프트에 주의 문구를 넣을 것.

### 소스별 woomi_relevance=높음 산출률 (균질구간)

| 소스 | 기사 수 | 높음 | 산출률 |
|---|---|---|---|
| Multifamily Dive | 147 | 47 | 32.0% |
| Multi-Housing News | 100 | 32 | 32.0% |
| Yardi Matrix Blog | 42 | 12 | 28.6% |
| LA Urbanize | 188 | 53 | 28.2% |
| YieldPro | 515 | 116 | 22.5% |
| Bisnow | 665 | 47 | 7.1% |
| Commercial Observer | 714 | 45 | 6.3% |
| Connect CRE | 669 | 28 | 4.2% |

참고용 지표다. 산출률이 낮다고 소스를 제거하지 않는다 — 위 "설계 원칙" 참조.
또한 woomi_relevance 기준 자체가 주거 개발에 맞춰져 있으므로
CRE 종합지가 구조적으로 낮게 나오는 순환논리 요소가 있다.

### korean_summary 결측 1,339건 — 의도된 상태

korean_summary 기능 도입(2026.06 중순) 이전 수집분에는 값이 없다.
2026-06-22 이후 수집분은 결측 0%다.

**이 결측을 채우기 위해 재분류하지 않는다.** classifier.py는
article_map[aid].update(result)로 7개 필드를 통째로 덮어쓰므로,
korean_summary만 채우는 것이 구조적으로 불가능하고 기존 분류가 함께 바뀐다.
결측분의 46%는 2026-06-01 이전 발행이라 기저선에서도 제외되며,
woomi_relevance=높음이면서 6/1 이후 발행인 것은 79건뿐이다.

weekly_report.py는 korean_summary를 참조하지 않고 영문 summary를 Claude에 넘겨
새로 요약하므로 리포트에는 영향이 없다. 대응은 index.html 표시 계층에서
korean_summary가 비면 summary(영문)로 대체하는 것으로 충분하다.

### access_limited 필드의 실제 의미

필드명은 "유료라 접근 불가"를 뜻하지만, collector.py의 _judge_access_limited()가
실제로 판정하는 것은 **"본문/요약을 충분히 확보하지 못했는가"** 다.
173개 소스 중 8개만 특별 처리를 받고 나머지 165개는 len(summary) < 100 으로 결정된다.

따라서 유료 기사뿐 아니라 RSS 요약이 짧게 오는 무료 기사도 True가 된다.
(Multifamily Dive 16건이 이에 해당 — 무료 매체이며 높음 산출률 최상위)

index.html이 이 값을 항상 숨기는 것은 **의도된 동작**이다.
해당 기사는 summary 평균 97자, korean_summary 보유율 23%로 제목만 남아
정보 가치가 없기 때문이다.

### 수집 구조 정정 (2026.09 확인)

**"기사 보관기간 90일"은 삭제 주기가 아니라 수집 창(intake window)이다.**
collector.py 296행/363행(대학·RSS)과 fetch_industry_player_feed 내 동일 cutoff가
`datetime.now() - timedelta(days=90)`로 "발행 후 90일 지난 기사는 수집 자체를 하지
않는다"는 뜻이며, 이미 저장된 기사를 지우는 로직이 아니다. **published_at 기준
삭제 로직은 코드 어디에도 없다 — 수집된 기사는 영구 보존된다.**

2026-09 진단(대학 3곳 Google News RSS 비교) 결과, Google News는 현재 쿼리로도
2006~2013년까지 기사를 반환한다. 즉 90일 컷오프는 Google 측 한계가 아니라
collector.py가 사후 폐기하는 값이며, 늘릴 여지가 있다는 뜻이다. 다만 관측창
불균질(위 "관측창 불균질" 절 참조)과 분류 API 비용 문제가 있어 값은 유지 중.

**fetch_student_housing_feed의 `[:5]` 상한은 구조적 수집 상한이다.**
같은 진단에서 대학당 실제 반환량은 76~100건이었으나 코드는 앞 5건만 취한다.
Google News 정렬은 관련도순이라 발행일 최신순이 보장되지 않으므로, 상한 5건이
최신 기사를 놓칠 수 있다. 기업명 피드(fetch_industry_player_feed)는 이 문제를
반영해 상한을 [:12]로 넓혔다.

**수집 축이 대학(175) + 기업(38) 2원 구조로 확대되었다.**
BLUE_VISTA_UNIVERSITIES(대학 로컬 뉴스)만으로는 스폰서·운영사·기관자본 기업명
기반 뉴스플로우를 구조적으로 놓친다는 문제(Blue Vista·PeakMade·Ascentris SH
섹터 0건 확인)로 INDUSTRY_PLAYERS 38개사(Tier1 딜 직접 관계자 4 / Tier2 SH
전업 개발사·운영사 18 / Tier3 기관자본 10 / Tier4 중개·자문 6)를 추가했다.
초회 실행 기준 Player 소스 신규 64건, 그중 Tier1 4개사는 0건 — 쿼리 튜닝은
결과를 보고 별도 결정.

**기업명 피드는 tier별 lookback_days를 사용한다 (2026.09 확인)**

`fetch_industry_player_feed()`는 대학·일반 RSS 피드의 90일 cutoff와 달리 Tier별로
서로 다른 수집 창을 쓴다: Tier1(딜 직접 관계자) 730일, Tier2·3(SH 개발사·운영사·기관자본)
365일, Tier4(중개·자문) 180일. 대학 피드의 90일은 의도적으로 그대로 유지했다.

이 예외가 정당한 이유는 Player 피드의 source 값이 `"Player — "` 접두사로 완전히
분리되어 있어, 기존 대학·RSS 기저선 시계열을 오염시키지 않기 때문이다. 대학 피드에
같은 예외를 주면 "관측창 불균질" 절의 착시 문제가 재발한다. **따라서 published_at
기준 통계를 낼 때는 Player 소스를 분리하거나 제외할 것.**

Tier1 4개사(Blue Vista·PeakMade·Ascentris·Dinerstein)가 90일 창에서 전원 0건이던
원인은 쿼리 문제가 아니라 사모 운용사 특유의 낮은 뉴스 빈도(연 5~15건 수준)에 90일
창이 구조적으로 안 맞았기 때문으로 진단됐다. 창을 730일로 넓히자 Blue Vista 14 /
PeakMade 5 / Ascentris 8 / Dinerstein 10건으로 즉시 해소됐다.

같은 진단에서 Blue Vista는 쿼리를 좁혀야 하는 소스임이 드러났다. `"Blue Vista" real
estate`는 동명 지명·단지명 오탐(호주 부동산 매물 "47 Blue Vista, Hopetoun" 등)이
섞여 `"Blue Vista Capital Management"`로 교체했다. 반면 PeakMade·Ascentris·
Dinerstein은 동명 충돌 위험이 낮아 오히려 한정어(`student housing` 등)를 제거하거나
정식 법인명으로 넓혀 커버리지를 늘렸다.

**Player 소스는 표시·리포트 계층에서 제외된다 (2026.09 확인)**

원장(articles.csv)에는 Player 소스가 그대로 남지만, weekly_report.py의
`filter_by_period()`와 index.html·app.py의 핵심 모니터링/전략 신호 모니터에서는
`source`가 `"Player — "`로 시작하는 행을 제외한다. 판정 기준은 각 파일에
`PLAYER_SOURCE_PREFIX` 상수 하나로 정의해 재사용하며, 세 파일에 흩어 하드코딩하지
않는다.

예외 두 곳은 의도된 포함이다: ① 누적 지표 헤더(archiveState 등 축적량 표시)는
Player를 포함해야 원장 규모를 정확히 반영한다. ② 전체 기사 섹션의 검색 기능은
Deal Ledger 검색의 전신이므로 Player 기사가 검색 대상에 남아 있어야 한다.

이 분리는 3계층 원칙(원장/렌즈/화면)의 실제 적용 사례다. 수집은 넓게(원장에 lookback
최대 730일까지 보존), 판단은 렌즈에서(classifier.py는 변경 없음), 노출은 화면에서
좁게(일상 브리핑에서 아카이브 시점 제외). 향후 원장과 브리핑용 작업본을 물리적으로
분리할 때 이 소스-접두사 기반 분리 규칙이 그 전신이 된다.

**중복 체크가 CSV 전량 로드에서 SQLite 인덱스로 이관됐다 (2026.09)**

collector.py의 중복 판정은 매 실행마다 articles.csv 전체를 메모리에 올리던 방식에서
`seen_index.db`(SQLite) 조회로 바뀌었다. 판정 규칙(article_id 일치 OR (정규화제목,
발행일 앞 10자) 일치)은 구버전과 완전히 동일하며, 6,884건 실측 검증에서 100% 일치를
확인했다.

`seen_index.db`는 **articles.csv에서 파생되는 캐시**다. 원본이 아니다 — 손상되거나
삭제돼도 `python build_seen_index.py`로 언제든 재생성할 수 있다. articles.csv가
유일한 원장(source of truth)이라는 원칙은 변하지 않는다.

**CSV 저장 후 DB commit** 순서를 반드시 지킨다. collector.py의 `main()`은
`save_articles()`가 끝난 뒤에만 `conn.commit()`을 호출하며, 예외 발생 시 try/finally로
commit 없이 종료된다. 반대 순서(DB commit 먼저)면 CSV 저장 실패 시 DB에만 "이미 봤음"
기록이 남아 해당 기사를 영영 재수집하지 못하는 실패 모드가 생긴다.

`seen_index.db`는 `.gitattributes`에 `binary merge=ours`로 선언되어 있다. 단, 이는
순차 실행 중 발생하는 통상적 병합 충돌 회피용이며, **여러 워크플로우 실행이 동시에
겹쳐 각자 다른 스냅샷으로 독립 판단하는 상황은 막지 못한다** — 그 경우 daily_collect.yml의
커밋 단계가 병합 실패를 감지하면 `build_seen_index.py`로 articles.csv 기준 전체
재생성 후 재커밋하는 폴백이 실행된다. 단 이 폴백은 병합이 실제로 일어날 때만
작동하며, 아래 2026-09-03 사고처럼 두 프로세스가 각자 다른 스냅샷으로 독립
실행되는 경우는 병합 자체가 발생하지 않으므로 방어되지 않는다.

**articles.csv 정합성 참고 — 알려진 손상 행 1건**: article_id·published_at·source
필드가 밀려 깨진 행이 정확히 1건 존재한다 (원문 추정: 웨비나 홍보 요약 텍스트 내
이스케이프되지 않은 따옴표로 인한 CSV 파싱 어긋남). `build_seen_index.py`는 이 행을
자동으로 skip하며 인덱스에 포함하지 않는다. article_id가 sha256(url)[:12] 형식(12자
hex)이 아니므로 정상 기사와 충돌할 위험은 없다. articles.csv 정합성 점검 시 이 행을
참조할 것 — 위치는 build_seen_index.py 실행 시 skip 목록에서 확인 가능하다.

**2026-09-03 article_id 142건 중복 — 원인 미규명, 재발 가능**:
같은 URL의 기사가 25분 간격 두 daily_collect.yml 실행(23:28:41 / 23:53:48 UTC,
둘 다 github-actions[bot])에서 각각 신규로 판단되어 두 번 저장됐다.

⚠️ concurrency 그룹(daily-collect, cancel-in-progress: false)이 2026-07-13부터
이미 존재했음에도 발생했다. 즉 동시 실행 방지 설정으로는 막히지 않는 사고이며,
SQLite 이관으로도 막히지 않는다. 두 방어선 모두 무력했다.

미확인 가설(다음 사고 시 이 순서로 확인할 것):
 ① 큐 대기 중인 두 번째 job이 첫 실행의 push 이전 시점 ref를 체크아웃했을 가능성
 ② concurrency group이 weekly_report.yml과 분리되어 있어 두 워크플로우가
    각자 그룹으로 동시 실행됐을 가능성 (일요일 21:00 UTC 충돌 = TODO #1)
 ③ 트리거가 복수(schedule + 외부 cron-job.org 등)여서 서로 다른 이벤트로 발화했을 가능성

이번 조사에서는 gh CLI 부재로 트리거 소스를 확인하지 못했다. 다음 실행 로그에서
run 시작 시각·트리거 이벤트·체크아웃 SHA를 대조해 판정할 것.

영향 범위: seen_index.db는 article_id가 PRIMARY KEY라 중복 쌍 중 하나만 인덱싱하며,
재수집 시도는 정상적으로 걸러진다. 따라서 향후 중복 판정 자체에는 문제가 없다.
articles.csv의 142건 잔여 행 정리는 미해결(TODO). CLAUDE.md TODO #4
"제목 중복 167행 정리"와는 판정 기준이 다른 별건이다.

## articles.csv 컬럼 (16개 확정)
article_id, collected_at, published_at, source, title,
url, summary, classified, category, event_tags,
signal_type, sector, woomi_relevance, claude_rationale,
access_limited, korean_summary

## 분류 체계
category (1개): 개발 / 시장 / GP·자본흐름
event_tags (복수): construction_start / delivery / permit /
  land_acquisition / transaction / acquisition /
  JV / policy / market_data / rent_occupancy /
  construction_cost / financing
financing 규칙: category 결정에 절대 사용 안 함, event_tags에만
woomi_relevance: CSV 저장만, UI 미노출

## 작업 시작 전 필수 규칙
- 모든 작업 시작 전 반드시 `git pull --no-rebase` 먼저 실행
- articles.csv는 GitHub Actions(Daily Collect & Classify)가 수시로 업데이트하므로,
  로컬에서 분류/재분류 작업 시작 전 항상 원격 최신본 확인 필수
- classifier.py 또는 reclassify 스크립트 실행 전: git pull로 최신 articles.csv 확보
- 동일 스크립트(classifier.py 등) 중복 실행 금지 — Batch API 특성상 중복 배치가
  Anthropic 서버에 쌓여 처리 지연 발생 가능
- 백그라운드 실행 시 출력이 안 보이면 즉시 중단하고 터미널에서 직접 실행 확인
  (PowerShell 백그라운드 셸은 출력 버퍼링 문제 있음)
- GitHub Actions 실행 시각(21:00 UTC = 06:00 KST) 전후로는 articles.csv를
  직접 수정하는 스크립트를 실행하지 말 것 (충돌 위험)
- articles.csv를 직접 수정하는 스크립트는 실행 전 반드시 articles.csv.bak 백업 생성
- classifier.py의 SYSTEM_PROMPT와 CSV_COLUMNS는 수정 전 반드시 영향 범위를 검토할 것
  (CSV_COLUMNS는 csv.DictWriter의 fieldnames로 쓰이며 extrasaction 기본값이 raise라,
   articles.csv에 컬럼이 추가되면 ValueError로 파이프라인 전체가 중단된다)
- 모델 상수는 classifier.py와 weekly_report.py 두 곳에 있다. 업그레이드 시 양쪽 모두 확인할 것

## 개발 이력 (~2026.08)
- 220건 수집·분류 완료
- RSS 피드 30개 + Blue Vista 175개 대학 Student Housing Google News RSS 추가
- Policy/Other category 제거 완료 (category 3개 값만 허용: 개발/시장/GP·자본흐름)
- sector에서 Policy 제거 완료
- woomi_relevance category별 세분화 완료 (개발/시장/GP·자본흐름 기준 상이)
- Claude API JSON 파싱 버그 수정 완료 (코드펜스 strip)
- Windows UTF-8 인코딩 처리 완료 (sys.stdout.reconfigure)
- python-dotenv 적용 완료 (.env 자동 로드)
- GitHub Actions 매일 오전 6시(KST) 자동 수집·분류 설정 완료
- Streamlit 대시보드 Student Housing 모니터 섹션 추가 완료
- LinkColumn으로 원문 링크 클릭 가능하도록 수정 완료
- 핵심 모니터링 리브랜딩 (⭐ 우미 관련 높음 → 🎯 핵심 모니터링)
- woomi_relevance 기준 강화 (대형 개발/플랫폼 인수 Weight 상향, Student Housing 기준 상향)
- 전략 신호 모니터 필터 개선 (시장·금리 / GP 거래동향 로직 분리)
- weekly_report.py 구현 완료 (주간/월간/분기/반기, docx 우미글로벌 양식 적용)
- 주간 리포트 자동 생성 GitHub Actions 추가 (매주 월요일 06:00 KST)
- 기사 보관기간 90일로 확장
- 분기/반기 리포트: weekly .md 재요약 방식 설계 완료
- 핵심 모니터링 SH 캡 5건 + 중복 제거 로직 (isDuplicate) 적용
- 기존 SH 높음 기사 룰베이스 재분류 (77건→23건 높음 유지, reclassify_sh.py)
- classifier.py woomi_relevance 기준 보완:
  BTR/SFR 착공·완공 규모 무관 높음 / Sun Belt MF 200+ units 개발 높음
  건설비·캡레이트·기관센티먼트 시장 높음
  Known GP (KW/HS/PCCP/Blue Vista/Lionheart/NexMetro/Middleburg/Hillpointe) 항상 높음
- classifier.py 모델 Haiku → Sonnet 4.6 업그레이드
- Batch API 적용 (건당 개별 호출 → 배치 1회 전송, 비용 50% 절감)
- 핵심 모니터링·전략 신호 모니터 날짜 기준 변경:
  고정 날짜 필터 → articles.csv 최신 날짜 기준 자동 2일치 (getLatestDateRange)
- getLatestDateRange() 버그 수정 (latest-1일 고정)
- 전체 기사 섹션 검색 기능 추가 (title·summary·분류근거 실시간 검색)
- 사이드바 기본 날짜 3일 → 30일 (전체 기사 탐색용)
- weekly_report.yml GitHub Actions 생성 완료 (매주 월요일 06:00 KST 자동 실행)
- weekly_report.yml permissions: contents: write + git config 설정 추가
- woomi_relevance 기준 보완: MF 추가 + Student Housing 500beds 명시
- 인텔리전스 리포트 Word 다운로드 버튼 항상 표시 (docx 존재 여부 확인 후 활성/비활성)
- 국문 요약 기능 추가: korean_summary 필드 (classifier.py) + 기사 클릭 팝업 (index.html)
- articles.csv korean_summary 컬럼 추가 (신규 기사부터 생성, 기존 기사 빈값 유지)
- classifier.py max_tokens 500 → 1500 상향 (korean_summary 추가로 인한 JSON 파싱 실패 수정)
- 06-16 기사 101건 전체 재분류 완료 (높음 17 / 보통 14 / 낮음 70)
- getLatestDateRange 정상 동작 확인, 핵심 모니터링 06-16 기사 16건 정상 표시
- requirements.txt python-docx 누락 수정 (매주 Actions에서 docx 생성 실패하던 근본 원인)
- marked.js 로딩 실패 대비 fallback 처리 추가 (모바일 CDN 이슈 대응, onerror 핸들러 + typeof 체크)
- loadReportList GitHub API 방식으로 변경 (raw.githubusercontent.com CORS 실패 수정, docx 존재 여부 즉시 판단)
- 06-23 주간 리포트 수동 생성 (md+docx, requirements.txt 수정 전 누락분 보완)
- 앱 리브랜딩: "US Residential Intelligence v2" → "The Brief — Woomi Global"
- 신문 헤더 스타일 적용 (THE + Brief 타이포그래피, 날짜 표시)
- PWA 변환 완료 (manifest.json, service-worker.js, 앱 아이콘 192/512px)
- 홈 화면 앱 설치 가능 (Android 삼성 인터넷/크롬 확인)
- 사이드바 필터 전면 제거 (카테고리/섹터/날짜/유료기사 체크박스)
- 유료 기사 항상 숨김으로 하드코딩
- 아이콘 컬러: #1B3A5C 네이비 배경 + 신문 텍스처 + THE/Brief 워드마크
- CSV 손상 복구: 잔해 행 삭제 + 중복 134건 정리 (5576→5442건)
- classifier.py 중복 article_id dict 병합 버그 수정
- 2026 Q2 분기 인텔리전스 리포트 생성 (6~8월, 12주간)
- 📈 시장 트렌드 분석 섹션 추가 (차트 3개: 월별 카테고리/높음비율/GP언급 빈도)
- Service Worker 캐시 버전 v1→v2 (모바일 캐시 강제 갱신)
- Chart.js CDN jsdelivr로 교체 + window.load 렌더링 타이밍 보정

## 다음 작업

### 선행 이슈 정리 (geo 착수 전)
1. weekly_report.yml과 daily_collect.yml 동시 발화 해소 (일요일 21:00 UTC 충돌)
2. requirements.txt에 pyyaml, openpyxl 추가
3. category 오염 1건 수정 (article_id 8270efb18db5)
4. 제목 중복 167행 정리(86행 제거) + collector.py 중복 방지 로직
5. index.html korean_summary fallback 한 줄
6. collector.py _FETCH_SOURCES 확대 (Multifamily Dive 등 5개)
7. weekly_report.py 모델 claude-sonnet-4-5 → claude-sonnet-4-6
8. daily_collect.yml 중복 실행 원인 규명 (2026-09-03 142건 사고,
   concurrency·SQLite 양쪽 모두 무력. 다음 실행 로그로 트리거 소스 확인)
9. ✅ 완료 (2026.09) — articles.csv/archive의 article_id 완전 중복 정리.
   142건 중 119건(collected_at만 다른 안전한 쌍) 정리, 23건은 title/summary/source가
   달라 제외(removed_duplicates.log 참조). TODO #4(제목 유사도 기준 167행)와는
   별건으로 그대로 남아있음. TODO #8이 재발하면 dedupe_duplicates.py 재사용
10. ✅ 완료 (2026.09) — classifier.py가 archive/ 파티션에 분류 결과를 쓰지
    않아 rebuild_working_set 발동 시 분류가 소실되던 문제. 렌즈 산출물을
    labels.db(SQLite)로 물리 분리해 해결 — 원장은 수집 8필드만, labels.db가
    분류 8필드의 유일한 source of truth. rebuild_working_set()이 원장+labels.db를
    조인해 작업본을 생성한다. 2026.09 응급 가드("작업본 classified=True 우선")는
    제거됨 — labels.db가 대체. 자세한 내용은 위 "원장의 물리 분리" 절 참조
11. weekly_report.py semi-annual 폴백 경로가 90일 이상 데이터를 못 읽는 문제
    (평소엔 weekly .md 재요약 경로라 영향 적음, 폴백 시에만 발생)
12. archive/ 파티션에서 렌즈 8필드 제거 (원장 축소) — labels.db 운영 검증
    후 진행. 지금은 파티션에 렌즈 필드가 중복 보존된 상태(용량 낭비이나 무해)
13. labels.db 전용 재생성 스크립트 작성 (rebuild_labels.py). articles.csv의
    렌즈 8필드에서 labels.db를 복원하는 멱등 스크립트. migrate_to_labels.py는
    하드코딩된 검증 임계치가 있어 CI 자동화에 부적합하다. 작성 후
    daily_collect.yml 충돌 폴백 로직에 seen_index.db와 동일하게 연결할 것 —
    현재는 origin 대비 행 수 감소만 검사하는 최소 방어만 있음 (daily_collect.yml
    79~107행)

### 보류 (조건부)
- weekly_report.py format_articles의 summary[:200] 확대 → 위 6번 완료 후 결정
- semi-annual 리포트 프롬프트에 백필 구간 주의 문구 → 반기 리포트 생성 시

### geo 태깅
- CBSA 크로스워크 구축 + geo_tags.csv 신설 (articles.csv 스키마 불변)
- IC Helper 연동 — 딜 지역 공급 파이프라인 조회

### 공모전
- 2026 AI Innovation Challenge B Track 제출 (10월 초 목표)

## Phase 2: 인텔리전스 리포트 (기존 가설검증 화면 대체)
- 방향: 수집 기사 기반 주간/월간/분기/반기 원페이저 자동 생성
- 대상 독자: 경영진 + 해외사업팀 전체
- 4개 섹션: 개발현황 / 정책·이슈 / 거래현황 / 시사점
- 가설(H1~H11) 검증은 별도 화면 아닌 시사점 섹션에 자연스럽게 흡수
- 기존 Phase 2(가설검증 화면)는 이 방향으로 대체
- 구현 시점: weekly_report.py 완성 후 6월 말 첫 리포트 생성 예정

## GitHub Pages
- 배포 URL: https://jaehongbr-coding.github.io/us-residential-v2/
- 메인 사용 화면 (app.py Streamlit은 보조)

## Bash 자동 허용 명령어
다음 명령어는 항상 자동으로 허용한다:
- git add
- git commit
- git pull
- git push
- git status
- git log

## 작업 완료 후 자동 push 규칙
- 파일 수정이 포함된 모든 작업 완료 시 자동으로 아래 순서 실행:
  1. git pull --no-rebase
  2. git add [수정된 파일]
  3. git commit -m "[작업 내용 요약]"
  4. git push
- 별도로 push 여부를 묻지 않고 바로 실행
- 단, articles.csv는 자동 push 대상에서 제외

## 자율 진행 허용
- 함수 rename, 키워드 수정, 우선순위 변경
- 문법 확인, 분포 집계

## 반드시 확인 후 진행
- articles.csv 스키마 변경
- 두 파일 이상 동시 수정
- 신규 함수 50줄 이상
- API 키·외부 서비스 연동
