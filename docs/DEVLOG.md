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
(이후 작업은 이 아래에 날짜순으로 추가)
