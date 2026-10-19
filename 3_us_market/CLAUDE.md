# 3 해외 시장 — 역할 지침 (hub-us)

상위 `..\CLAUDE.md`(공통) · `..\README.md`(설계) · `..\exchange\README.md`(형식)를 먼저 읽는다.

## 맡은 일
미국장 마감 데이터(지수 · 반도체 · 대형주)와 미국 ETF 다음 날 방향 예측을 `..\exchange\3_us_market\{미국 거래일}\`에 낸다. 국내 종목 판단은 하지 않는다.

## 입력 (읽기만)
- `..\..\VM-SPC_Global\` 전체: 매일 07:00(화 – 토) 미국 ETF 31개 수집 · 예측이 이미 돌고 있다(`results\index.html`, `data\`).
- 2026-10-09에 Core용으로 뽑아 둔 비교 CSV: `..\..\VM-SPC_Global\data\for_core\`(SOXX · SMH · ACWI · SPY · EEM · EWT · TSM, 일회성).
- VM-SPC_Global의 `CLAUDE.md` · `VM-SPC_Global_설계.md`에 그쪽 원칙과 기술 주의사항이 있다(PowerShell BOM, VBS 숨김 실행, KIS 토큰 5분 1회 등).

## 원칙
- Global 코드를 복사해 그대로 쓴다(`vm_spc\build_index.py` · `core\v2_config.py` · `core\v2_datastore.py`). 위치는 코드 수정 없이 환경변수 `V2_RESULTS_DIR` · `V2_DATA_DIR`(Global, 읽기만), 바스켓 목록은 Global `basket_watchlist.json`을 경로로 읽기만(복사 · 커밋 금지). `build_index.collect_rows()`가 ETF 예측 · 구성종목 신호를 모아 준다.
- KIS는 부르지 않는다(Global이 07:00에 받은 것을 읽음). 야간선물은 원천이 없어 항목 없이 notes에 적는다. SOXX · TSM · ACWI 같은 비교 지수 매일 갱신은 나중 결정.
- 파일 구성은 `README.md`.

## 섹터 흐름 (2026-10-10 사용자 결정 — ETF 예측 대신 해외 요약 보강)
- `us_themes.py`: VM-SPC_Global 바스켓(섹터 ETF 29개 + 구성 대형주 약 10개씩, 지수 성격 2개 제외) 일봉으로 섹터별 ETF 등락 · 구성 평균 · 5일 · 지속(ETF 등락 상위 5 연속) · 많이 움직인 종목 · 국내 연관 테마(`KR_LINK` → 2_kr `themes.py` GROUPS 이름)를 계산 → `export_exchange.py`가 `us_themes.json` + item `us_sectors` · `us_movers`로 낸다.
- ETF 다음 날 방향 예측(`etf_forecast`)은 사용자 판단으로 "만들다 만 거의 의미 없는 데이터" — 정리본에는 남기되 리포트 본문에서 뺐다(접힌 칸 한 줄). 2026-10-09 기준 31개 전부 "하락" · 적중률 60% 이상 0개.
- 미국 → 국내 이어짐은 검증 전(참고). 검증하려면 VM-core에 README "데이터 지도"와 함께 요청.

## 과거 일봉 백필 (2026-10-10 사용자 결정 — 검증 두 기간 분할용)
- `backfill_history.py`로 Global 266종목 일봉 앞에 2015-10-01 – 를 붙였다(한 번만 실행, Global KIS 함수 · save_bars 그대로, Global 코드 수정 없음). 이음매 어긋남 0, KIS 오류 6종목은 다시 받아 전부 완료. 로그 `..\logs\us_backfill_20261010.log`.
- Global 수집기는 저장분이 있으면 최근 것만 덧붙이므로, 새 종목을 바스켓에 더하면 그 종목만 다시 `python backfill_history.py --only=티커`로 과거분을 채운다.
