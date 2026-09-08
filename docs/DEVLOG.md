<!--
작성 규칙:
- 사실만 쓴다. 커밋 해시, 실측 수치, 실제로 내린 판단만.
- "무엇을 했다"보다 "무엇이 틀렸고 어떻게 알았는지"를 남긴다.
- 추측·평가·미사여구 금지. 근거가 없으면 쓰지 않는다.
- 앞으로 매 작업 후 항목을 추가한다(덮어쓰지 않는다).
-->

# The Brief — 개발 로그

## 2026-09-07~08 : Active Adult 수집 축 신설

### 발단
"South Carolina + Senior Housing" 아카이브 조회가 0건. Senior Housing 88건은
Multifamily 대비 29배 적고, 88건 중 57%는 주 정보도 없었다. 원인은 분류가 아니라
수집이었다 — AA를 겨냥한 축이 아예 없었다. 화면보다 수집을 먼저 한 이유:
수집은 되돌릴 수 없고 화면은 언제든 만들 수 있다.

### 설계 원리
별도 세션의 AA_Universe_Database_v1.xlsx에서 "AA는 CoStar에 property type 분류가
없어 운영 브랜드를 분류키로 쓴다"는 결론이 나왔고, 같은 논리를 뉴스 수집에 적용했다.
대학명이 Student Housing의 키였듯 브랜드명이 AA의 키다.

### 브랜드 쿼리 오탐 실증 (32개 쿼리 실측)
- Calamar = 스페인어 "오징어" (8건 중 7건 오탐)
- Everleigh(bare) = 여아 이름, 부고 기사 (8건 중 6건)
- Amberlin = 한정어를 Sparrow/active adult로 바꿔도 각각 1건씩 오탐 → 채택 불가
- 채택 17종 확정. 섹터 일반어 4종은 오탐 0이면서 실수집의 63%를 차지했다.

### 실측 결과
신규 281건(AA 245 / SH 6 / RSS 30), 중복 0. 17개 소스 전부 1건 이상.

---

## 교훈 : 되돌릴 수 없는 것을 먼저 식별하라

### classifier에 재분류 트리거가 없다
classified != "true" 인 행만 처리하고 lens_version은 읽지 않는다. 즉 한번 붙은
라벨은 영구 고정이다. archive_index.json은 sector를 labels.db에서만 읽으므로,
원장에 "Active Adult"가 정확히 들어가 있어도 라벨이 잘못 붙으면 검색에서 영원히
0건이다. 이 두 사실이 겹쳐, 정기 실행 전에 taxonomy를 고쳐야 하는 시한이 생겼다.
(수집이 되돌릴 수 없어 먼저 했는데, 라벨링도 사실상 되돌릴 수 없었다.)

### 회귀 검증이 사실은 고정 샘플이 아니었다
scripts/snapshot_regression.py가 매번 ORDER BY article_id LIMIT 300으로 재조회하는
구조여서, 신규 ID가 사전순 상위에 들어오면 창이 밀린다. 실제로 diff 15건이 떴고
전부 위양성이었다. 이전의 "변경 0건"은 우연히 상위 300건이 안 밀린 결과였다.
스냅샷의 article_id 집합만 조회하도록 수정(8332ad3).

### tee가 실패 종료코드를 삼켰다
실행 요약을 얻으려고 `python collector.py | tee ...`로 바꿨는데, 셸이
`bash -e {0}`이고 pipefail이 없어 파이프 종료코드가 tee의 것이 됐다.
classifier가 죽어도 워크플로우는 성공으로 진행하고 auto 커밋이 찍히며,
새 가드가 "최근 완료"로 판정해 다음 실행까지 스킵한다 — 실패를 성공으로 기록하고
재시도까지 막는 조합. shell: bash 명시로 수정(f45f107).
관측성을 얻으려다 실패 감지를 잃을 뻔했다.

---

## 프롬프트 한 줄의 무게

AA 라벨의 woomi_relevance 높음 비율이 73.7%로 나왔다(전체 평균 16.1%,
Student Housing 17.8%). 원인은 [개발] 블록의 AA 항목에 조건이 없다는 것이었다 —
같은 줄의 SH는 "500+ beds OR 특정 플랫폼"인데 AA는 착공·준공이면 무조건 높음.
모델이 오독한 게 아니라 프롬프트가 그렇게 지시하고 있었다.
AA 높음의 63%가 개발 카테고리였던 것과 정확히 일치한다. (미해결 — 다음 작업)

또 하나: 브랜드 목록을 관련성 기준으로 쓰려는 시도를 기각했다. 채택 브랜드 10종은
"뉴스 쿼리에서 오탐 0"으로 고른 목록이지 시장 중요도로 고른 게 아니다.
수집 정밀도를 관련성 판정의 대리 지표로 쓰면 지표 방향이 어긋난다.
게다가 제외 목록에 CIM Group이 있는데 실제 검토 중인 딜의 상대다.

---

## geo 태깅 : 실패 지점은 추출이 아니라 매핑이었다

AA 213건 중 152건이 미해결이라 Stage A(지명 추출) 문제로 보였으나, 조사 결과
88건은 Stage A가 "Annapolis, MD" "Tucson" 같은 명백한 지명을 정확히 뽑았는데
Stage B(resolver)가 매칭에 실패한 것이었다. 원인 둘:
- 크로스워크가 CBSA 타이틀의 principal city만 인덱싱 — Annapolis 등 소도시는
  구조적으로 매칭 대상이 아님
- Stage A 스키마가 type: state를 정의하는데 resolver에 state 처리 경로가 없음
전 섹터 공통 문제다(Multifamily도 56.7%가 미해결). stage_a_json이 보존돼 있어
resolve-only로 API 재호출 없이 무료 재매핑이 가능하다.

---

## 주요 커밋
- ec5b7d1 collector.py에 AA 축 추가
- 1ff8da4 AA 신규 281건 원장 반영
- 8e2b1c6 sector taxonomy에 Active Adult 추가, 245건 분류
- 8332ad3 회귀 검증 고정 샘플화
- 35e5333 AA 214건 재분류
- b4f311d archive_index 재빌드 (SC+Active Adult 조회 3건 — 0건이었던 것)
- 51a3102 파이프라인에 archive_index 빌드 추가, 가드 롤오버 수정, 실행 요약
- f45f107 pipefail 적용
- 2906314 가드 임계값 12h, *.log gitignore

---

## 2026-09-08 : geo resolver — Stage A는 맞았고 Stage B가 틀렸다

### 발단
AA 213건 중 152건이 geo 미해결이라 Stage A(지명 추출) 문제로 보였다.
조사 결과 152건 중 88건은 Stage A가 "Annapolis, MD"·"Tucson" 같은 지명을
정확히 뽑았는데 Stage B(resolver)가 매칭에 실패한 것이었다. 원인은 둘 —
크로스워크가 CBSA 타이틀의 principal city만 인덱싱해 소도시가 구조적으로
빠지는 것, 그리고 Stage A 스키마가 `type: state`를 정의하는데 resolver에
그 처리 경로 자체가 없는 것. 전 섹터 공통 문제였다(Multifamily도 56.7%
미해결). stage_a_json이 보존돼 있어 resolve-only로 API 재호출 없이
무료 재매핑이 가능했다.

### Austin 33건은 버그가 아니었다
primary로 나온 "Austin"이 33건 실패했는데, 33건 전부 state 필드가 없었다.
Austin, TX(12420)와 Austin, MN 두 후보가 있어 ambiguous로 멈추는 것은
설계대로 작동한 것 — Columbia/Miami/Glendale과 같은 안전장치다. 이건
"실패로 세지 않은 실패"다.

### NYC 110건 — Oklahoma City 오판정을 막으려 되돌린 규칙의 부작용
크로스워크의 실제 키는 CBSA 타이틀 첫 세그먼트인 "New York"뿐이다.
"New York City"가 정확히 추출되고도 안 풀린 건 항목 부재가 아니라 문자열
불일치였다 — geo_norm.norm()이 " city" 접미사를 일괄 제거하지 않는 이유가
"Oklahoma City"/"Kansas City"/"Carson City"를 bare 주 이름·다른 도시와
충돌시키지 않기 위해서였다(2026.09 이전 라운드에 이미 되돌린 규칙).
전역 규칙을 다시 건드리는 대신 "New York City"/"NYC" alias 2개만
추가했다 — 가리키는 대상이 유일해 UW/USC류 통칭 충돌 위험이 없다.
재빌드 전후 diff로 alias_idx 2건 추가 외 전부 동일함을 확인했다
(commit 1de44bf).

### secondary 폴백이 Manhattan,KS류 위험의 노출 범위를 넓혔다
primary가 실패했을 때 버려졌던 secondary를 조회하는 폴백을 추가했는데,
1차 구현(secondary를 무주로 그대로 조회)이 두 건의 확정 오판정을 냈다:
- Evesham(NJ) 기사의 secondary "Medford"가 크로스워크에 유일 등재된
  Medford, OR로 확정됨(article_id 64d164856186)
- 워싱턴 D.C. 기사의 secondary "Georgetown"이 Georgetown, TX(Austin)로
  확정됨(article_id 0a3a645b5660)

둘 다 CLAUDE.md가 이미 기록한 유형이다 — 크로스워크에 후보가 여럿이면
모호성 체크가 잡지만, 후보가 하나뿐인데 그게 틀리면 원리적으로 못 잡는다
(Manhattan,KS 116건 오판정과 같은 계열). 대도시 목록 같은 임의 기준으로
"확인된 것만" 막는 방법은 기각했다 — 못 본 오판정이 남기 때문이다.

해법은 기사 내 주 맥락 상속이었다: secondary에 state가 없으면 같은
stage_a_json의 다른 place가 명시한 state로만 조회하고, 맥락이 아예
없으면 조회 자체를 하지 않고 미해결로 남긴다. 두 사례 모두 stage_a_json
전체에 state 단서가 없어서(Evesham/Evesboro/Medford, D.C./Georgetown
전부 state=null) 이 폴백을 적용해도 정답을 맞히지는 못한다 — 하지만
목표는 Medford를 오리건으로 보내지 않는 것이었지 뉴저지로 맞히는 것이
아니었다. 틀린 답을 빈칸으로 바꾸는 것이 이번 수정이 달성한 것이다.

### 오차율 수치가 세 번 정정됐다 — 매번 위로 올라갔다
처음엔 확정 오판정 2건을 627건(신규 해결 전체) 대비로 계산해 0.32%라고
보고했다. 사용자가 정정했다 — 위험 모집단은 627이 아니라 "주 없는
secondary 매칭" 194건이고, 표본 검토였으므로 2건은 하한값이다(194건
기준 최소 1.0%).

실제로 하한이었다. 맥락 상속 적용 전, "다른 place에 명시 state가 있는"
81건(애초엔 안전하다고 가정한 그룹)을 맥락 검증으로 재조회했더니 그중
최소 8건이 이미 틀린 답이었다는 게 드러났다 — Wellington, FL 기사가
Seattle로, Falls Church, VA 기사가 Los Angeles로, Northern Virginia
기사가 Boston으로, Bal Harbour, FL 기사가 New York City로, Kennesaw, GA
기사가 Dallas로 확정돼 있었다. 명시 state가 "존재한다"는 것과 그 state가
"실제로 사용됐다"는 것은 다른 얘기였다 — 예전 무주 조회는 기사에 state
정보가 있어도 그걸 안 쓰고 크로스워크에서 유일하게 걸리는 아무 후보나
집었다. 확정 오판정은 최소 2+8=10건 — **194건 기준 5.2%**이며, 전수
감사가 아니므로 이 역시 하한이다.

0.32% → 1.0% → 5.2%, 세 번 다 위로만 움직였다. 표본 검토로 잡은 숫자는
과소평가 쪽으로만 틀린다는 뜻이고, "확인된 것만 고친다"는 접근이 왜
위험한지를 그 자체로 보여주는 기록이다.

### 맥락 상속 커버리지 측정 — (a)+(b)는 과반에 못 미쳤다
"주 없는 secondary 매칭" 194건을 세 갈래로 나눴다: (a) 다른 place에
명시 state 있음 81건(42.1%), (b) 명시는 없으나 다른 place가 크로스워크로
해결돼 주를 역산 가능 3건(1.5%), (c) 기사 전체에 주 단서 전혀 없음
110건(56.7%). (a)+(b)=84건(43.3%)로 과반에 못 미쳤고, (c)가 과반이었다.
구현은 (a)만 커버한다(STEP 2 스펙이 "다른 place의 state 필드"만 수집하도록
명시했고, (b)는 크로스워크 역산이라는 별도 메커니즘이 필요해 이번
라운드 범위 밖으로 남겼다).

### "정답을 못 찾는 것"과 "틀린 답을 내는 것"은 다른 문제다
(c) 110건은 이번 수정으로 구제되지 않는다 — 근거가 없으므로 미해결로
남는 것이 맞다. 이건 실패가 아니라 설계다: 기사에 주 단서가 없으면
맞힐 방법이 없고, 없는 근거로 확정하는 것 자체가 Manhattan,KS류 사고의
원인이었다. 검색 화면 관점에서도 누락(빈칸)은 설명 가능하지만 오답은
설명되지 않는다 — "SC + Active Adult" 조회에 틀린 지역의 기사가 섞이면
화면 전체의 신뢰가 무너진다. (c) 110건은 미해결 부채로 남는다.

### source_inferred — 진단만 하고 이번 라운드에 쓰지 않았다
geo_confidence=='source_inferred' 66건이 이미 있다. `geo_store.
derive_source_hint()`가 "Student Housing — <대학명> (<주>)" 형식 소스에서
`geo_aliases.yaml`의 universities 섹션(154개 대학)을 조회해 (CBSA, 주)
힌트를 주는 기존 메커니즘이다. (c) 110건 중 이 형식 소스는 18건뿐이고
나머지 92건(Connect CRE/Bisnow/LA Urbanize/YieldPro 등)은 애초에 이
정규식에 안 걸려 힌트를 받을 수 없다. Evesham(64d164856186)의 source는
"Player — Active Adult — age-restricted", Georgetown(0a3a645b5660)의
source는 "Bisnow"다 — 즉 이번에 문제가 된 두 사례는 이 메커니즘이 있어도
구제되지 않았을 것이다. 또한 source_inferred 승격 코드(geo_resolver.py)는
`overall == "ambiguous"`일 때만 발동하는데, 맥락 상속이 실패하면 결과는
"ambiguous"가 아니라 "none"이라 이 승격 경로 자체가 지금 구조로는
적용되지 않는다. 이번 라운드에 구현하지 않았다 — 다음 라운드 판단 대상.

### 부수 발견 — Stage A가 가끔 주 이름을 2자리 코드가 아닌 전체 이름으로 낸다
맥락 상속 검증 중 발견: 일부 stage_a_json이 `"state": "Illinois"`처럼
전체 이름을 쓴다(정상은 `"IL"`). 크로스워크의 모든 state 비교는 2자리
코드 기준이라 이런 place는 자기 state로도, 맥락으로도 매칭되지 않는다.
Skokie(IL)/Sheboygan(WI)/Arvada(CO) 3건이 이 문제로 이전엔 우연히 맞는
답(무주 secondary가 크로스워크에서 유일하게 걸린 게 하필 정답)을 냈다가
이번엔 보수적으로 미해결 처리됐다 — 틀린 게 아니라 이번 라운드가 검증을
못 통과시킨 것이다. 손대지 않았다. 별건으로 남긴다.

### 결과
resolve-only 재실행(API 호출 없음), 실질 미해결 3,943 → 3,432건(511건
해소). 기여분: state 폴백 217 / NYC alias(primary) 102 / NYC alias
(secondary) 5 / secondary 폴백(맥락 상속) 187. 퇴화 검증 0건.
tests/test_geo_resolver.py 51 baseline + 4 신규 = 55/55.
"SC"+"Active Adult" 조회 3건(무변화 — 신규 해결 25건 중 SC 없음).

### 커밋
- a1a05da geo resolver state/secondary 폴백 + 회귀 테스트 4건
- 1de44bf New York City/NYC alias 추가
- 8af5dc9 resolve-only 재매핑 (실질 미해결 511건 해소)

---

## 2026-09-08 : 아카이브 검색 화면 — 이 프로젝트가 원래 하려던 것

### 왜 여기 도달하는 데 이렇게 오래 걸렸나
아카이브 검색이 이 프로젝트의 원래 목적이었다. 그런데 순서는 수집(AA 축
신설) → taxonomy 재분류(brand 기준 제거) → geo 매핑(state/secondary 폴백)
순으로 왔다. 이유는 되돌릴 수 없는 것부터 처리해야 했기 때문이다 —
수집 축이 없으면 AA 기사 자체가 원장에 없고, taxonomy가 틀리면 labels.db에
영구히 잘못된 sector가 박히고(classifier에 재분류 트리거 없음), geo가
없으면 "SC + Active Adult" 같은 지역 조합 조회가 애초에 불가능하다.
화면은 이 셋 중 어느 것도 아니다 — 데이터가 옳으면 언제든 다시 만들 수
있다. 그래서 마지막까지 미뤄졌다.

### Player 제외 로직이 화면 계층에 있어 AA가 수집되고도 안 보였다
핵심 모니터링·전략 신호 모니터는 `PLAYER_SOURCE_PREFIX`로 Player 소스를
제외한다(일상 브리핑에서 아카이브 시점 데이터를 걸러내기 위한 설계,
CLAUDE.md "Player 소스는 표시·리포트 계층에서 제외" 참조). AA 213건은
전량이 Player 소스다(브랜드 쿼리로 수집). 즉 AA를 아무리 잘 수집하고
분류하고 geo 태깅해도, 이 제외 로직을 그대로 물려받는 화면이라면 결과는
여전히 0건이었을 것이다. 아카이브 검색에는 이 제외를 적용하지 않기로
했다 — "전체 기사" 섹션이 같은 이유(Deal Ledger 검색의 전신)로 이미
Player를 포함하고 있어 판단 기준이 이미 있었다. 핵심 모니터링·전략 신호의
제외 로직 자체는 건드리지 않았다 — 그 둘은 여전히 "최근 동향"이 목적이고
아카이브는 "과거 전체 조회"가 목적이라 기준이 다르다.

### 지역 미상 1,441건을 숨기지 않기로 했다
주(state) 필터를 걸면 `st` 필드가 빈 값인 기사는 자동으로 빠진다 —
아무 코드도 짜지 않아도 "조용히" 사라진다. 이걸 그대로 두면 사용자는
"이 조합은 원래 이 정도 건수구나"라고 오해하게 된다. 실제로는 geo
resolver가 못 푼 것과 애초에 지명이 없는 것이 섞여 빠진 것이다. 결과
헤더에 "N건 (지역 미상 M건은 주 필터에서 제외됨)"을 항상 표기하기로
했다 — 근거 없이 넘어가는 화면보다 무엇을 모르는지 아는 화면이 낫다는
판단이다(geo resolver 라운드에서 "틀린 답보다 빈칸이 낫다"고 판단한 것과
같은 원칙의 화면 버전).

### PWA Cache-First 때문에 아카이브가 굳을 뻔했다
`service-worker.js`는 `articles.csv`에만 Network First를 적용하고 나머지는
전부 Cache First다. `archive_index.json`을 그냥 fetch()로 불러왔다면 첫
방문 이후 캐시된 채로 굳어, PWA 설치 사용자에게는 다음 `index.html` 변경
(CACHE_NAME을 갱신하는 유일한 트리거, `update_sw_version.yml`이
`index.html`/`app.py`/`manifest.json`/아이콘 변경에만 반응)까지 매일 밤
갱신되는 아카이브가 전혀 반영되지 않았을 것이다. archive_index.json을
articles.csv와 같은 Network First 경로에 추가해서 막았다.

### 성능 우려는 실측으로 기각됐다
"6MB짜리 JSON을 브라우저가 받는 게 느리지 않을까"를 부채로 잡아뒀었다.
실측: GitHub Pages·raw.githubusercontent.com 둘 다 gzip으로 서빙하고
(`curl -H "Accept-Encoding: gzip"` 응답 헤더에 `Content-Encoding: gzip`
확인), archive_index.json의 실제 전송 크기는 2.2MB다. 이미 매일 로드하는
articles.csv(원본 7.63MB, 전송 2.8MB)보다 오히려 작다. 근거 없이 쌓아둔
부채였다.

### 검증의 한계
이번 세션 환경에는 실행 가능한 브라우저(Chrome 확장 미설치, 로컬 바이너리
없음, Node.js 없음)가 없어 실제 클릭·렌더링·콘솔 에러를 직접 확인하지
못했다. 대신 archive_index.json 실 데이터에 대해 필터 로직을 Python으로
동일하게 재구현해 요구된 시나리오(전체 7,427 / AA 213 / SC+AA 3 /
SC+AA+transaction 0 및 0건 진단 값)를 검증했고, 코드 정독으로 구조적
정합성(중복 ID·함수 없음, 브레이스 균형, 기존 switchPage()/buildTable
패턴 그대로 확장)을 확인했다. 실제 브라우저에서의 시각적·상호작용
확인은 하지 못한 채로 남아 있다.

---
(이후 작업은 이 아래에 날짜순으로 추가)
