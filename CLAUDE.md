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

## 파일 구조
- collector.py: RSS 수집, CoStar intake, articles.csv 저장
- classifier.py: Claude API 분류 (Haiku), run_classifier() export
- app.py: Streamlit Article Feed + Market Dashboard
- articles.csv: 단일 output (삭제/스키마 변경 금지)

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

대응: 표시 계층에서 korean_summary가 비면 summary(영문)로 대체한다.

### access_limited 필드의 실제 의미

필드명은 "유료라 접근 불가"를 뜻하지만, collector.py의 _judge_access_limited()가
실제로 판정하는 것은 **"본문/요약을 충분히 확보하지 못했는가"** 다.
173개 소스 중 8개만 특별 처리를 받고 나머지 165개는 len(summary) < 100 으로 결정된다.

따라서 유료 기사뿐 아니라 RSS 요약이 짧게 오는 무료 기사도 True가 된다.
(Multifamily Dive 16건이 이에 해당 — 무료 매체이며 높음 산출률 최상위)

index.html이 이 값을 항상 숨기는 것은 **의도된 동작**이다.
해당 기사는 summary 평균 97자, korean_summary 보유율 23%로 제목만 남아
정보 가치가 없기 때문이다.

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

### 선행 이슈 정리 (issues-plan.md) — geo 착수 전
1. weekly_report.yml과 daily_collect.yml 동시 발화 해소 (일요일 21:00 UTC 충돌)
2. requirements.txt에 pyyaml, openpyxl 추가
3. category 오염 1건 수정 (article_id 8270efb18db5)
4. 제목 중복 167행 정리 (86행 제거) + collector.py 중복 방지 로직
5. korean_summary fallback (index.html, weekly_report.py)
6. _FETCH_SOURCES 확대 (Multifamily Dive 등 5개 추가)

### geo 태깅 (research.md / Plan.md)
7. CBSA 크로스워크 구축 + geo_tags.csv 신설 (articles.csv 스키마 불변)
8. IC Helper 연동 — 딜 지역 공급 파이프라인 조회

### 공모전
9. 2026 AI Innovation Challenge B Track 제출 (10월 초 목표)

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
