# US Residential Intelligence v2

우미글로벌 해외사업팀 미국 주거시장 뉴스 수집·분류 앱

RSS 피드(26개)와 Yardi Matrix 등에서 미국 주거용 부동산 기사를 자동 수집하고,
Claude AI(Haiku)로 카테고리·이벤트 태그를 분류해 Streamlit 대시보드로 제공합니다.

## 기능

- **자동 수집**: 26개 RSS 피드에서 최신 기사 수집 (`collector.py`)
- **AI 분류**: Claude Haiku로 카테고리·이벤트 태그·시장 신호 분류 (`classifier.py`)
- **대시보드**: Streamlit 기반 기사 피드 + 시장 분포 시각화 (`app.py`)

### 분류 체계

| 필드 | 값 |
|---|---|
| category | 개발 / 시장 / GP·자본흐름 |
| event_tags | construction_start, delivery, permit, land_acquisition, transaction, JV, policy, market_data, rent_occupancy, construction_cost, financing |

## 실행 방법

**1. 패키지 설치**
```bash
pip install -r requirements.txt
```

**2. 환경변수 설정**
```bash
cp .env.example .env
# .env 파일에 실제 ANTHROPIC_API_KEY 값 입력
```

**3. 앱 실행**
```bash
# 기사 수집
python collector.py

# AI 분류
python classifier.py

# 대시보드 실행
streamlit run app.py
```

## 환경변수

| 변수명 | 설명 |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API 키 ([발급](https://console.anthropic.com/)) |

로컬 실행 시 `.env` 파일에 설정하거나 터미널에서 직접 export합니다.

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # macOS/Linux
$env:ANTHROPIC_API_KEY="sk-ant-..."   # Windows PowerShell
```

## Streamlit Cloud 배포

1. 이 레포를 GitHub에 push
2. [share.streamlit.io](https://share.streamlit.io) 접속 → New app → 레포 선택
3. **Settings → Secrets**에 아래 내용 입력

```toml
ANTHROPIC_API_KEY = "sk-ant-여기에-실제-키-입력"
```

4. Deploy 클릭

> `articles.csv`는 헤더만 있는 빈 파일로 포함되어 있습니다.  
> 앱 사이드바의 ▶ Claude 분류 실행 버튼으로 수집과 분류를 순서대로 실행할 수 있습니다.

## 파일 구조

```
us-residential-v2/
├── app.py            # Streamlit 대시보드
├── collector.py      # RSS 수집
├── classifier.py     # Claude AI 분류
├── requirements.txt  # 패키지 목록
├── .env.example      # 환경변수 형식 예시
└── articles.csv      # 수집 데이터 (빈 파일로 포함, 로컬에서 채워짐)
```
