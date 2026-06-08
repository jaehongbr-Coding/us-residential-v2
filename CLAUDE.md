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

## 다음 작업
1. Student Housing 첫 수집 결과 확인 (기사 수집률 검증)
2. Phase 2: 가설 검증 화면 (기사 500건 이상 후)
3. CoStar 수동 intake 테스트

## Bash 자동 허용 명령어
다음 명령어는 항상 자동으로 허용한다:
- git add
- git commit
- git pull
- git push
- git status
- git log

## 자율 진행 허용
- 함수 rename, 키워드 수정, 우선순위 변경
- 문법 확인, 분포 집계

## 반드시 확인 후 진행
- articles.csv 스키마 변경
- 두 파일 이상 동시 수정
- 신규 함수 50줄 이상
- API 키·외부 서비스 연동
