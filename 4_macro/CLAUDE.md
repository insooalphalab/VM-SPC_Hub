# 4 매크로 — 역할 지침 (hub-macro)

상위 `..\CLAUDE.md`(공통) · `..\README.md`(설계) · `..\exchange\README.md`(형식)를 먼저 읽는다.

## 맡은 일
금리 · 환율 · 유가 · 신용스프레드 · 메모리(DRAM/NAND) 현물가 같은 매크로 일별 표를 만들고, 전날 대비 변화를 `..\exchange\4_macro\{날짜}\`에 낸다.
방향 판단은 하지 않는다. 매크로가 국내 판단에 쓸모 있는지는 1 코어가 사전 등록해 검증한다(VM-SPC Core 로드맵에서 "해외 · 매크로"는 보류 항목이었다).

## 입력 · 출발점
- `..\..\KIS_auto\월간_매크로섹터분석.py` — FRED 금리 · 신용스프레드, DRAM/NAND 현물, 섹터 bottom-up(수동 실행용). 필요한 키는 KIS_auto의 `.env` 항목 이름만 참고하고, 이 폴더의 `.env`에 사용자가 직접 넣는다(키 값을 옮겨 적지 않는다).
- `..\..\VM-SPC_Core\data\_market\usdkrw_yahoo.csv` — 원/달러(2015 – ).
- KIS는 쓰지 않는다(무료 공개 원천 위주).

## 첫 작업 (5단계)
1. 어떤 지표를 매일 받을지 사용자와 정한다(후보: 미국 2 · 10 · 30년물, 한국 3년물, 원/달러, WTI, 미 하이일드 스프레드, DRAM 현물).
2. 일별 표(`data\macro_daily.csv`, 2016 – )와 `summary.json` · `summary.md`(key: rates · fx · oil · credit · memory).
3. 원천마다 갱신 시각이 달라 07:20 아침 실행 기준으로 "가장 최근 값 + 날짜"를 함께 적는다.
