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

## 2026-09-08(2) : 아카이브 칩 카운트 — 정적 숫자가 만든 혼동

### "MF(2545) + CA(738) = 324건"이 버그처럼 보였다
칩에 archive_index.json의 filters 사전 집계(전 섹터 기준 CA 738건)를
그대로 표시했다. Multifamily를 고르고 CA를 추가로 고르면 결과는 324건 —
738이 아니다. 이건 버그가 아니라 정확한 교집합(MF∩CA=324)이었다. 문제는
칩 숫자 자체가 "지금 이 칩을 고르면 몇 건이 되는지"를 반영하지 않아서,
사용자가 선택 전에는 그 예측을 전혀 할 수 없었다는 것이다. 칩 카운트를
"다른 그룹의 활성 필터는 전부 적용하고 자기 그룹만 제외"한 기준으로
매번 다시 계산하도록 바꿨다(패싯 카운트, `passesArchiveFilters`의
skip 인자를 재사용). 초기 상태(필터 없음)에서 이 방식이 archive_index.json의
사전 집계와 정확히 일치함을 9개 섹터 전부에서 확인했다 — 별도 분기 없이도
같은 값이 나온다.

### "지역 미상"을 경고 문구에서 칩으로
이전엔 결과 헤더에 "(지역 미상 N건은 주 필터에서 제외됨)"이라는 괄호
문구로만 알렸다. 이 문구는 선택할 수 없었다 — 사용자가 "그럼 지역 미상인
것만 보자"고 할 방법이 없었다. 주(State) 그룹 맨 앞에 `지역 미상 (N)`
칩을 추가해 다른 주 칩과 동일하게 다중 선택되도록 했다(`st` Set에
빈 문자열 `""`을 지역 미상의 센티널 값으로 사용). 해시 인코딩에서
빈 문자열이 falsy라 `if (v)` 체크로는 복원이 안 되는 함정이 있었다 —
`if (v !== null)`로 고쳐 "지역 미상만 단독 선택"도 URL 해시로 왕복되게
했다(node로 실측 확인: `st=,CA` → `["", "CA"]` 복원).

### 관련성을 기본 필터로 걸지 않은 이유 둘
정렬 기본값은 관련성순으로 바꿨지만(동률 시 최신순 2차 정렬), 관련성
**필터**는 기본 선택하지 않았다. 이유 둘:
1. 아카이브의 목적 자체가 "일일 화면(핵심 모니터링 등)이 걸러낸 것을
   찾는 것"이다. 기본값으로 높음만 보여주면 정확히 일일 화면이 하는
   일을 반복하는 것이라 아카이브의 존재 이유가 없어진다.
2. 현재 관련성 라벨은 이번 세션 초반 geo/taxonomy 작업에서 확인했듯
   AA 프롬프트 결함(개발 카테고리 조건 부재로 높음 73.7%) 등으로 섹터별
   신뢰도 편차가 있다 — 이 라벨을 기본 필터로 거는 것은 신뢰도가
   확인되지 않은 값에 화면 전체를 맡기는 것이다.

### Workforce Housing 24건 조사 결과 (판단은 보류)
title/source/claude_rationale 전수를 출력해 확인했다 — 전부 실제로
"workforce housing"/"working-class rentals"를 명시한 기사였고
(YieldPro/Connect CRE/Multi-Housing News/Commercial Observer/LA
Urbanize/Multifamily Dive 등 소스 분산), 오분류로 의심되는 사례는
눈에 띄지 않았다. 섹터 신설 여부·taxonomy 편입 여부는 별도 판단
대상으로 남겨둔다.

---

## 2026-09-08(3) : 인텔리전스 탭 제거 — 재는 것과 판정하려는 것이 어긋났다

### 시장 트렌드 차트를 실데이터 연동 대신 삭제했다
"📈 시장 트렌드 분석"의 월별 카테고리 분포·핵심 모니터링 선별 비율·GP
언급 빈도 차트 3개는 처음부터 하드코딩 데이터였다(articles.csv 실시간
연동 아님, 코드 주석에도 명시돼 있었다). 실데이터로 바꾸는 대신 대체
없이 삭제했다 — 이유는 구현 난이도가 아니라 지표 자체의 문제다. 기사
수는 시장 활동량이 아니라 언론 노출량이다. GP 언급 빈도가 늘어난 게
그 GP의 실제 거래가 늘어난 것인지, 그 GP를 다루는 매체가 늘어난 것인지,
수집 축이 확장된 것인지(Player 축 추가 등) 구분할 수 없다. 실시간
연동은 "틀린 걸 더 자주 보여주는 것"이 될 뿐 지표가 재려는 것(시장
활동)과 실제로 재는 것(보도량)의 불일치를 해결하지 못한다.

이 판단은 조사로 뒷받침된다:
- GP별 원장 건수는 시장 활동이 아니라 쿼리 설계를 반영한다. AA 브랜드
  13개사(Overture/Everleigh/Album/Avenida 등)와 Blue Vista/PeakMade/
  Ascentris는 Player 아닌 일반 RSS·대학 축 title에 **0건** 등장한다 —
  이 회사들의 "언급 빈도"는 전적으로 우리가 그 쿼리를 넣었기 때문에
  존재하는 숫자다.
- 프로젝트 시간축 궤적(land_acquisition→construction_start)을 찾는
  나이브한 클러스터링(같은 CBSA+섹터+태그+30일 이내)은 2건 묶음에서도
  정밀도 약 50%였고, 대형 묶음(NYC+Mixed-use+transaction 111건)은 전혀
  무관한 거래 111건이 체인으로 이어진 아티팩트였다.
- 거래당사자(buyer/seller/lender/broker) 추출 가능성 확인 결과, title
  20건 표본 중 양쪽 당사자가 모두 명시된 것은 **0건**이었다(가장 근접한
  사례도 매수자만 있고 매도자 없음).

세 조사 모두 결론은 같다 — 지금 있는 데이터로 "차트가 재려는 것"(시장의
실제 움직임)을 만들면 겉보기엔 그럴듯해도 속은 노이즈다. 만드는 것보다
없는 게 정직하다.

### 중복 보도와 classifier 판단이 독립적으로 일치했다
매체 수(중복 보도 묶음 소속 여부)와 classifier의 woomi_relevance 판단은
서로 다른 입력으로 서로 다른 시점에 만들어진다 — 하나는 "몇 개 매체가
실었는가"(구조적 사실), 다른 하나는 "Claude가 내용을 보고 관련성이
높다고 판단했는가"(내용 기반 판단). 이 둘이 22.2%(2~3건 묶음) vs 15.3%
(단독 보도)로 방향이 일치했다 — 여러 매체가 실은 기사가 실제로 더 자주
"높음"으로 분류된다. 서로 독립적인 두 판단이 같은 방향을 가리켰다는
점에서, "매체 수가 딜 규모의 대리 지표가 될 수 있다"는 가설은 최소한
기각되지는 않았다(단, 효과 크기는 1.5배 수준으로 크지 않다).

### 작업 B — 지역 미상 3,432건 재집계
511건 해소 이후 기준으로 다시 세었다. (a) place 전혀 못 뽑음 1,563건 /
(b) place는 뽑았으나 크로스워크 매칭 실패 1,865건 / (c) type==state인데
이름 자체가 이미 축약형("NC"/"CT")이라 STATE_ABBR(전체 이름 키) 조회에
안 걸리는 것 3건 / (d) "Washington"이 bare 상태에서 도시로도 해석돼
1차 조회에서 이미 ambiguous로 판정되는 바람에 state 폴백이 개입하지
않은 것 1건(설계대로 — ambiguous는 절대 덮어쓰지 않는다는 원칙 그대로
작동).

**(a)를 다시 갈랐다.** 소스 필드·제목 접미사("- 매체명")·요약 중복
문구를 제거한 뒤 주 이름 패턴 매칭(휴리스틱, 완벽하지 않음 — 최초
시도는 "Washington Times" 같은 매체명 자체에 낀 주 이름을 지명으로
오판해 33~38건으로 부풀렸다가 소스 텍스트 제거로 21건까지 좁혔다)한
결과: (a-1) 지명 자체가 없음 1,542건(98.7%), (a-2) 지명이 있는데 놓친
것으로 의심 21건(1.3%). (a-1)이 압도적이다 — 정상 상태에 해당한다.
(a-2) 21건을 육안 재검토하니 실제 부동산 관련 지명 누락으로 보이는
건 6건 안팎(Tennessee/Wisconsin/Florida 대학 뉴스, Puerto Rico 호텔
인수, Alabama 아파트 딜, California 주택법 소송)이고 나머지는 부고·
사건사고·연준 집행조치에 우연히 낀 주 이름이거나 회사명·거래소 이름
(뉴욕증권거래소 등)이었다.

(b) 1,865건 상위 지명: Miami(48)·Austin(36)·Portland(10)는 크로스워크에
후보가 복수라 주 없이는 여전히 ambiguous로 남는다(alias 문제 아님,
state 필요). Los Angeles(22)·Boston(10)은 **bare로는 이미 고유하게
풀리는데도**(`_lookup_one` 직접 호출로 확인) secondary 위치에서 맥락
없이는 시도 자체를 안 하는 지난 라운드의 보수적 규칙 때문에 여전히
빠진다 — 안전장치가 필요 이상으로 넓게 걸린 사례다. UW/USC/OSU/Pitt/
Texas A&M/UConn/CU Boulder는 기존에 충돌 위험으로 제외한 대학 약칭,
Illinois State/Kennesaw State/Purdue Fort Wayne/Stony Brook/Clemson은
기존 "미해결 대학" 목록 그대로, Midtown/East Village/Midtown Manhattan은
NYC 서브마켓 중 자치구 이상 세분화하지 않기로 한 기존 결정 그대로,
Sun Belt/Bay Area/South Florida/Southern California/Midwest는 CBSA로
매핑하지 않기로 한 광역 통칭 그대로다. D.C./Washington, D.C.(합쳐서
61건)는 아직 별도 alias가 없다.

복수 지역(st에 "|") 레코드는 1,058건이지만 이는 **해결된** 레코드가
CBSA 자체의 다주(多州) 구성(뉴욕 메트로=NY+NJ 등) 때문에 여러 주에
걸치는 것이지, "여러 지역이 거론돼서 빠지는" 것과는 다른 현상이다.
그 가설을 직접 보려면 **미해결** 3,432건의 stage_a_json place 개수를
봐야 한다 — 2개 이상 언급된 것은 732건(21.3%)뿐이고, 나머지 78.7%는
place가 0개(1,563건)이거나 정확히 1개(1,137건)인데도 실패한다. "여러
지역 언급"은 실패의 소수 요인이지 주된 원인이 아니다.

섹터별 미해결 비율: Workforce Housing 66.7%, Active Adult 62.9%,
Senior Housing 54.5%가 상위 — AA·Workforce·Senior는 전용 해결 경로
(대학 alias 같은)가 없어 계속 불리하다는 이전 진단과 일치한다. source
상위는 Bisnow(487)·Commercial Observer(363)·Connect CRE(315) 순으로,
전체 기사량이 큰 소스가 그대로 상위를 차지한다 — 특정 매체가
불균형하게 지명을 안 쓰는 패턴은 보이지 않았다. Federal Reserve(53)는
전국 단위 통화정책 보도라 (a-1) 성격(원래 지명이 없는 콘텐츠)에
해당한다.

### 커밋
- (Task A) 인텔리전스 탭 제거, 주간·월간 리포트를 뉴스 탭으로 이동,
  하드코딩 차트 삭제, Chart.js CDN 로드 제거

---

## 2026-09-08(4) : AA 관련성 기준 1차 수정 — 조여보니 다른 구멍이 보였다

### 73.7%의 원인은 모델이 아니라 프롬프트였다
[개발] 블록의 AA "높음" 줄에는 조건이 없었다. 같은 줄의 Student Housing은
"500+ beds OR Core Spaces/Landmark/Greystar"로 조건이 붙는데, AA는
"groundbreaking or completion"만 있으면 규모·자본·지역 무관하게 무조건
높음이었다. 착공·준공 기사이면 그것으로 끝이었다. 모델이 프롬프트를
잘못 읽은 게 아니라, 프롬프트가 정확히 그렇게 쓰여 있었다.

착공/준공 확정, 기관자본 참여, Sun Belt(Atlanta/Dallas/Houston/Phoenix/
Charlotte) 또는 LA/West Coast 위치 — 이미 관찰 가능한 세 조건 중 하나를
만족할 때로 좁혔다. 새 수치나 임계치를 만들지 않았다 — AA 단지 규모의
근거가 없고, classifier에 재분류 트리거가 없어 근거 없는 임계치는
영구화되기 때문이다(예: "300세대 이상"을 만들었다면 그 300이라는
숫자의 근거를 댈 수 없었을 것이고, 한번 박히면 못 바꾼다). 목표 비율도
정하지 않았다 — 특정 %를 겨냥해 문구를 조정하는 것 자체가 임의 기준이기
때문이다. 결과: 개발 카테고리 높음 100건 → 53건, AA 전체 높음
75.6%(161/213) → 49.8%(105/211).

### 미해결 결함 3건 — 이번 라운드에서 고치지 않았다

**(1) 위치 단독 승급 23건(21.9%).** 사용자가 수정 전에 경고한 그대로
확인됐다 — "같은 줄의 Multifamily는 Sun Belt에 200+ units 조건이
붙는데 AA는 위치만으로 통과한다"는 우려가 실제로 재현됐다. 착공 확정도
기관자본도 없이 "Texas City approves... after 2-year pause"(시의회
승인 단계)나 "3,500-Home Margaritaville... Coming To Texas City"(계획
발표 단계)처럼 확정되지 않은 단계의 기사가 Sun Belt 언급만으로 높음이
됐다. 조건을 하나 좁히니 다른 조건이 그 빈자리를 메웠다.

**(2) OR가 AND처럼 오적용 — 착공 확정 기사 8건이 부당 강등됐다.**
프롬프트는 "다음 중 하나(OR)"라고 명시했는데, 강등된 56건 중 8건은
rationale이 스스로 "건설 착공이 확인되었으나(Elk Township)" 라고
인정하면서도 기관자본이나 Sun Belt/LA가 없다는 이유로 보통으로
낮췄다 — 모델이 조건 하나로는 부족하다는 듯 다른 조건과의 결합을
요구했다. 이번 수정의 목적은 부풀림 제거이지 AA 전체를 억제하는 게
아니었으므로, 이 8건은 목적에 어긋나는 부작용이다.

**(3) Known GP 오귀속 5건.** Greystar/Album을 "Known GP 계열"이라고
rationale이 명시한 경우가 여전히 5건 있다 — Greystar는 PRIORITY 4의
Known GP 목록(Kennedy Wilson/Harrison Street/PCCP/Blue Vista/
Lionheart/NexMetro/Middleburg/Hillpointe)에 없다. AA/SH 경계 정의
문단에 "Operating brands include: Overture, Album, Avenida..."라고
브랜드명을 이미 명시해 둔 것이, 모델에게 이 브랜드들을 "주요 플레이어"
급으로 각인시켜 Known GP와 혼동하게 만드는 것으로 보인다. 이번 라운드는
PRIORITY 4·경계 정의 문단을 건드리지 않았으므로 그대로 남았다.

### "부당 강등을 지적하라"는 검증 항목이 실제로 뭔가를 잡아냈다
STEP 3 검증에 "새로 강등된 건 중 부당한 것이 있으면 지적하라"는 항목이
없었다면 (2)는 발견되지 못했을 것이다 — 표본 확인 중 강등 사유
rationale 자체가 착공 확정을 인정하면서 다른 조건을 추가로 요구하는
모순을 담고 있어서 드러났다. 결과 숫자(75.6%→49.8%)만 봤다면 "성공"으로
끝났을 검증이었다.

### 다음 세션
프롬프트를 추가 조정해 (1)(2)(3)을 다룰 예정이다. tmp_aa_before2.json/
tmp_aa_after2.json/labels.db.bak4_*를 지우지 않고 남겨 다음 라운드의
before/after 비교 기준으로 쓴다.

### 커밋
- 9b9beb6 classifier.py AA 관련성 기준 조건부화(1차)
- 6cef00a labels.db/articles.csv/archive_index.json AA 211건 재분류 반영

---
(이후 작업은 이 아래에 날짜순으로 추가)

## 2026-09-09 : 크레딧 소진 원인 진단 — 모델 교체 가설 기각, geo_tagger 캐싱 적용

### 발단
9/9 오전 daily_collect가 API 크레딧 소진으로 실패했다. Console 사용량 CSV 분석
결과 9/3~9/8 6일간 $16.4로 전체의 89%가 개발 과정 소진이었고, 9/7 하루가
$7.19(geo Stage A 백필 $4.10 일회성 포함)였다. 그런데 이걸 측정할 수단이
코드에 없었다 — classifier.py/geo_tagger.py는 캐시 hit/miss만 로그하고
토큰·비용을 기록하지 않아, 위 분석 자체가 Console CSV 역산이었다. 토큰
로깅(input/output/cache_creation_input/cache_read_input, 커밋 3d3d986)을
먼저 추가했다.

### "8/31 모델 교체" 가설 — 기각
classifier.py의 MODEL 상수는 커밋 `a749108`(2026-06-12) 이후 `claude-sonnet-4-6`
고정이며 변경 이력이 없다. `claude-sonnet-4-5` 문자열이 classifier.py에 존재한
적 자체가 없다(`git log -S` 확인). 8월 초 Sonnet 4.5는 weekly_report.py였다 —
커밋 `2a46574`(2026-08-25)에서 weekly_report.py만 4.5→4.6으로 바뀌었고,
weekly_report.py는 주 1회 실행이라 일일 비용 급증의 원인이 될 수 없다.
8/25~9/2 구간 classifier.py·geo_tagger.py 커밋은 전무했다.

### 재분류 3회가 비용의 상당 부분
AA sector 도입 후 245건(9/7, 커밋 `8e2b1c6`) → 211건(9/8, 커밋 `9b9beb6`) 재분류가
있었고, 3차가 예정돼 있다(213건). 세 번 모두 전체 재분류가 필요했던 이유는
prompt(woomi_relevance 조건)를 한 번에 못 고쳤기 때문이다 — DEVLOG
2026-09-08(4) "미해결 결함 3건" 참조.

### "규칙 기반 1차 필터"가 원리적으로 불가능
sector·event_tags·category는 classifier.py 호출의 **결과물**이라 호출 전에는
존재하지 않는다. 호출 전에 알 수 있는 신호는 source뿐이다.

### 소스 기반 필터는 채택하지 않음
labels.db(7,427건) 기준 Bisnow 79.5%/Connect CRE 82.1%/Commercial Observer
76.5%가 woomi_relevance=낮음이었다. 세 소스 합계 2,396건(전체 분류량의
32.3%)을 필터링하면 낮음이 아닌 나머지 18~24%, 약 480건도 함께 버리게 된다.
"수집은 넓게, 판단은 렌즈에서" 원칙(CLAUDE.md)에 어긋나 채택하지 않았다.

### geo_tagger.py 캐싱 적용
classifier.py는 이미 SYSTEM_PROMPT에 `cache_control: {ephemeral, ttl: 1h}`가
적용돼 있었다(2026-08-24, 커밋 `5b228bd`). geo_tagger.py는 캐싱 인프라
자체가 없었고, few-shot 예시 4개(858자)가 system이 아니라 user 메시지 안에
있어 구조적으로 캐시 대상이 될 수 없었다. GEO_SYSTEM_PROMPT(2,018자)와
few-shot을 하나의 system 블록(`GEO_SYSTEM_FULL`, 2,878자)으로 합치고
classifier.py와 동일한 `cache_control: {ephemeral, ttl: 1h}`을 붙였다.
build_geo_prompt()는 기사 본문만 담게 됐다(user 메시지 1,124자 → 264자).
프롬프트 내용은 이동만 했을 뿐 변경하지 않았다 — 이동 전후 system+user
합산 문자수가 3,142자로 정확히 일치함을 코드로 조립해 확인했다(API 호출
없이 dict만 구성해 검증, 크레딧 소진 상태라 실행 불가).

Batch API에서 배치 내 여러 요청이 캐시를 공유하는지는 설치된 anthropic
SDK(0.107.1)의 타입 정의·문서로는 확인 불가였다 — usage.py에
cache_creation_input_tokens/cache_read_input_tokens 필드는 있으나 배치
간 공유 여부는 명시돼 있지 않다. 실제 값은 다음 정상 실행의 [USAGE] 로그가
알려줄 것이다.

classifier.py의 MODEL·ttl·SYSTEM_PROMPT, index.html/app.py/weekly_report.py는
이번 작업에서 변경하지 않았다.

### 커밋
- 3d3d986 classifier·geo_tagger 토큰 사용량 로깅 추가
- (본 커밋) geo_tagger 프롬프트 캐싱 적용, few-shot을 system 블록으로 이동

---

## 2026-09-09(2) : 프롬프트 캐싱 제거 — 문서 권장이 실측으로 뒤집힌 사례

### 실측: 캐싱이 이득이 아니라 손실이었다
전날 추가한 [USAGE] 로깅이 다음 정상 실행(108건 배치, `logs/last_run.md`
2026-09-09 01:09 UTC)에서 바로 답을 줬다. classifier.py 토큰:
input 10,900 / output 40,855 / cache_write 242,496 / cache_read 30,312.
cache_write ≈101회분, cache_read ≈12회분 — 히트율 12%.

계산: 1시간 캐시 쓰기는 기본 입력의 2배 요금이다(cache read는 약 0.1배).
93%(101/113)가 2배 요금을 내고 12%만 0.1배 할인을 받는 구조라, 캐싱 있음
$1.05 vs 캐싱 없음 $0.73 — **캐싱이 44% 더 비쌌다**. 5분 TTL(1.25배)로
낮춰도 $0.78로 여전히 캐싱 없는 쪽이 쌌다.

### 원인
배치 요청은 정의상 동시 처리된다. 캐시 항목은 첫 응답이 시작된 뒤에야
읽기 가능해지는데, 동시에 출발하는 요청들은 그 시점에 이미 출발한
상태라 캐시를 못 받는다. Anthropic 문서가 배치 처리에 1시간 TTL을
권장하는 것은 사실이지만, 그 권장은 "히트가 실제로 난다"는 것을
전제로 한 상대 비교(1시간 vs 5분 중 어느 쪽이 나은가)이지, "배치에서
캐싱이 이득"이라는 뜻이 아니었다. 어제 이 권장 문구만 보고 "1h 유지"로
판단한 것이 틀렸다.

### geo는 애초에 구조적으로 불가능했다
geo_tagger.py의 system 블록(GEO_SYSTEM_FULL)은 2,878자(약 720토큰)다.
Claude API 레퍼런스 확인 결과 Haiku 4.5의 최소 캐시 가능 길이는
**4,096토큰**이다 — 미달 시 오류 없이 그냥 캐싱 없이 처리된다. 실측도
cache_write 0 / cache_read 0으로 일치했다. 전날 few-shot을 system으로
옮기고 cache_control을 붙인 작업은 캐싱 관점에서는 하루 종일 효과가
0이었다 — 다만 few-shot을 system 블록으로 옮긴 구조 변경 자체는
품질 저하 없이(108/108 성공) 그대로 유지했다.

### 문서 권장 → 실측 뒤집힘
"문서가 권장하니 맞다"는 판단이 실측 데이터로 뒤집힌 사례다. 전날
[USAGE] 로깅을 먼저 넣지 않았으면 캐싱이 이득이라 믿고 계속 44% 더 비싼
방식으로 돌렸을 것이다 — 비용 측정 수단을 먼저 갖추는 것이 판단보다
선행해야 하는 이유가 이번에 실증됐다.

### 조치
classifier.py·geo_tagger.py 두 곳 모두 system 블록에서 `cache_control`을
제거했다. system 필드는 리스트 형태를 유지했고(구조 변경 없음),
MODEL·SYSTEM_PROMPT·max_tokens·BATCH_SIZE는 손대지 않았다. geo_tagger의
few-shot-in-system 구조 변경도 유지했다. [USAGE] 로깅은 그대로 남겨
다음 실행에서 cache_write/read가 0이 되고 input이 늘어나는지 확인한다.

### 커밋
- (본 커밋) classifier·geo_tagger cache_control 제거

---

## 2026-09-09(3) : AA 관련성 3차 수정 — 판단의 비결정성을 잡아냈다

### 세 라운드 추이
| | 1차 (n=214) | 2차 (n=213) | 3차 (n=215) |
|---|---|---|---|
| 높음/보통/낮음 | 162/43/9 (75.7%) | 105/89/19 (49.3%) | 84/118/13 (39.1%) |
| 개발-높음 | 100 | 53 | 37 |

1차는 AA "높음" 줄에 조건이 아예 없었다(무조건 승급). 2차는 착공/기관자본/
Sun Belt·LA-West Coast 위치 중 하나를 요구했으나 위치가 단독 트리거로
작동해 23건이 위치만으로 승급했다. 3차는 위치를 "둘 중 하나가 이미 충족된
경우의 가중 요소"로 낮추고, 착공·완공 또는 기관자본 참여만 남겼다.

### 결함 1의 변형 재발 — "위치 단독"이 "플랫폼 딜"로 옷을 갈아입었다
개발-높음 37건 중 33건(89%)은 착공/완공/기관자본을 rationale에서 언급했으나,
4건은 둘 다 언급하지 않았다. 원문 헤드라인과 대조한 결과:

```
13ca58b7f9a4 | "3,500-Home Margaritaville Active Adult Community Coming To Texas
              City" (Bisnow, 헤드라인 자체가 미확정 계획 발표)
  → rationale: "...Sun Belt 지역 대규모 액티브 어덜트 플랫폼 딜에 해당한다."

db2387e4da9b | "Taylor Morrison plotting first active-adult community in Atlanta
              market" ("plotting"=구상 중 단계)
  → rationale: "...선벨트 지역 액티브 어덜트 섹터 확장 신호로... 주목할 만한
              개발 동향이다."

cda1948ea6a7 | "Luxury apartment complex in Phoenix's CityNorth now accepting
              pre-lease applications" (헤드라인에 Active Adult 언급조차 없음)
  → rationale: "...BTR/Active Adult 섹터 주요 운영사의 Sun Belt 시장 진입
              이벤트에 해당함."

802f73c8158b | "King of Prussia office building to be razed for 205-unit
              apartment project" (헤드라인에 Active Adult 언급 없음)
  → rationale: "...Greystar라는 주요 플랫폼이 참여한 점에서 높은 관련성을
              가진다."
```

"플랫폼 딜"·"주요 운영사 진입"·"주요 플랫폼 참여"는 프롬프트가 정한 두 조건
(착공/완공 확인, 기관자본 확인) 어디에도 없다. 조건을 좁히면 모델이 그 자리를
프롬프트에 없는 제3의 근거로 메운다는 패턴이 2차에 이어 3차에도 반복됐다.

### 날조 사례
```
c9b4754d5112 | "Canadian builder to bring 650-home 'active adult' community to
              Sarasota County" (헤드라인은 미래형 "to bring")
  → rationale: "...대규모 프로젝트 착공이 확인되는 기사로 높음에 해당."
```
원문에 없는 사실("착공이 확인되는")을 rationale이 만들어냈다.

### explicitly의 역방향 부작용 — 같은 사건, 정반대 판정
```
1bf4c84cba1a (citybiz, 1/21) | "CF Evans Construction Selected to Build Album
              Dorchester, an Active-Adult Community in North Charleston..."
  → 높음: "시공사를 선정하며 착공을 공식화한 개발 기사로... 착공 확인 조건을
         충족하여 높음으로 분류."

9d013562156f (Construction Owners, 1/25, 동일 프로젝트 재보도) | "CF Evans
              Construction Selected for Album Dorchester Active-Adult
              Community in North Charleston..."
  → 보통: "시공사 선정 단계이나, 착공 확인이나 기관 자본 참여가... 명시되지
         않아 '보통'으로 분류."
```
같은 프로젝트, 같은 사실(시공사 선정)을 다룬 두 기사가 같은 배치 안에서
정반대로 판정됐다. 이것이 이번 라운드의 핵심 발견이다 — **프롬프트 문구의
한계가 아니라 판단 자체의 비결정성**이다. "explicitly confirmed"라는 문구를
아무리 다듬어도, 모델이 같은 사실에 대해 매번 같은 결론을 내린다는 보장은
프롬프트만으로 만들 수 없다.

같은 패턴이 Elk Township 기사에서도 나타났다:
```
161a7099c549 | "See construction underway on Elk Township active adult
              housing" (헤드라인에 "construction underway" 명시, 모델 자신이
              매긴 event_tags도 construction_start)
  → rationale: "...기관 자본 참여나 착공 확인 외 구체적 정보가 부족하여
              '보통'으로 분류."
```
이 기사는 2차에서도 같은 이유로 강등됐다 — 3차도 고치지 못했다. 같은 패턴이
`d7674d0834b2`("Apartments Under Construction At Growing Shopping Hub", 헤드라인에
"Under Construction" 명시)에서도 나타났다.

### 미해결 후보 처방 — 기록만, 구현하지 않음
event_tags에 construction_start를 붙여놓고 rationale에서는 "착공 불명확"이라고
쓰는 것은 같은 API 응답 안에서의 자기모순이다. woomi_relevance의 착공 조건을
산문 판단이 아니라 모델 자신의 event_tags 출력 값에 프로그램적으로 묶는 것이
후보 처방이 될 수 있으나, 이는 프롬프트 패치가 아니라 파이프라인 설계
변경이라 이번에 구현하지 않았다. 로드맵의 2단 스크리닝(Haiku 1차 선별 →
Sonnet 정밀 분류) 논의와 함께 다룰 항목이다.

### 결함 3(Known GP 오귀속)은 해결
2차 5건 → 3차 0건(애매 1건). PRIORITY 4번에 추가한 폐쇄성 문장이 의도대로
작동한 사례:
```
10b25b07506c | "Active Adult 단일 자산 거래로 기관 자본 참여 여부가 불명확하여
              '보통'으로 분류되며, Inland은 Known GP 목록에 포함되지 않음."
8be2c732766d | "...Known GP 개입 없이 단일 운영사의 서비스 확장에 해당하여
              '보통'으로 분류."
```

### 미해결 규모
215건 중 확정 규칙 위반 4건 + 날조성 1건 + 과도 강등 2~3건(중복 집계 없이
약 7건, 3%). 세 라운드 평균 높음 비율 75.7 → 49.3 → 39.1%(labels.db
전체 평균은 15.2%). regression_snapshot 300건 mismatch 0, articles.csv/
labels.db AA 건수 211=211 일치.

### 캐싱 제거 검증 (재확인)
```
[USAGE] input_tokens 573413 / output_tokens 108232 /
        cache_creation_input_tokens 0 / cache_read_input_tokens 0
```
215건 배치, cache_creation·cache_read 모두 0 — 어제 제거한 cache_control이
실제로 반영됐음을 재확인. 건당 입력 약 2,667토큰(SYSTEM_PROMPT가 AA 조건
추가로 늘어난 만큼 반영된 수치).

### 4차 재분류는 하지 않는다
CF Evans/Album Dorchester 사례는 프롬프트 문구를 더 다듬어서 없앨 수 있는
종류의 문제가 아니라고 판단했다 — 문구를 좁히면 2차→3차처럼 또 다른 변종이
나타날 뿐이다. 이번 라운드는 결함3을 해결하고 결함1·2의 규모를 축소했으나,
남은 약 3%는 프롬프트 튜닝이 아니라 다른 접근(event_tags 연계, 또는 다중
샘플링 후 합의 판정 같은 구조적 방법)이 필요하다는 것이 이번 라운드의
결론이다.

### 커밋
- f224248 classifier.py AA 위치 단독 승급 제거·OR 명시·Known GP 폐쇄성 명시
- 6f62f4a labels.db/articles.csv/archive_index.json AA 3차 재분류 반영
