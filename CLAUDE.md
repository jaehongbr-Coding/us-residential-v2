# US Residential Intelligence v2

## 프로젝트
US Residential Intelligence v2
우미글로벌 해외사업팀 미국 주거시장 뉴스 수집·분류 앱

## 파일 구조
- collector.py: RSS 수집, CoStar intake, articles.csv 저장
- classifier.py: Claude API 분류 (Haiku), run_classifier() export
- app.py: Streamlit Article Feed + Market Dashboard
- articles.csv: 단일 output (삭제/스키마 변경 금지)

## articles.csv 컬럼 (15개 확정)
article_id, collected_at, published_at, source, title,
url, summary, classified, category, event_tags,
signal_type, sector, woomi_relevance, claude_rationale,
access_limited

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

## 현재 완료 상태 (2026.06)
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

## 다음 작업
1. 06-29(월) GitHub Actions 자동 실행 확인 — md+docx 동시 생성 여부
2. 모바일 환경 리포트 렌더링 정상 동작 확인 (marked.js fallback 검증)
3. 국문 요약(korean_summary) 팝업 품질 확인
4. 리포트 고도화: 월간 → 분기 → 반기 순차 확장
5. Phase 3: 리포트 품질 고도화 (프롬프트 튜닝, 섹터별 심화 분석)

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
