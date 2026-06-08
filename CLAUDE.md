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
url, summary, classified, market_region, category,
event_tags, sector, woomi_relevance, claude_rationale,
access_limited

## 분류 체계
category (1개): 개발 / 시장 / GP·자본흐름
event_tags (복수): construction_start / delivery / permit /
  land_acquisition / transaction / acquisition /
  JV / policy / market_data / rent_occupancy /
  construction_cost / financing
financing 규칙: category 결정에 절대 사용 안 함, event_tags에만
woomi_relevance: CSV 저장만, UI 미노출

## 현재 완료 상태 (2026.06)
- 170건 수집·분류 완료
- 26개 RSS 피드 + Yardi Matrix 추가
- Claude API JSON 파싱 버그 수정 완료 (코드펜스 strip)
- Windows UTF-8 인코딩 처리 완료 (sys.stdout.reconfigure)

## 다음 작업
1. Policy/Other category 프롬프트 보강
2. CoStar 수동 intake 테스트
3. 개발 기사 비중 확대 (현재 12.9%)
4. Phase 2: 가설 검증 화면 (기사 500건 이상 후)

## 자율 진행 허용
- 함수 rename, 키워드 수정, 우선순위 변경
- 문법 확인, 분포 집계

## 반드시 확인 후 진행
- articles.csv 스키마 변경
- 두 파일 이상 동시 수정
- 신규 함수 50줄 이상
- API 키·외부 서비스 연동
