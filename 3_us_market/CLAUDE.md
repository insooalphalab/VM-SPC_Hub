# 3 해외 시장 — 역할 지침 (hub-us)

상위 `..\CLAUDE.md`(공통) · `..\README.md`(설계) · `..\exchange\README.md`(형식)를 먼저 읽는다.

## 맡은 일
미국장 마감 데이터(지수 · 반도체 · 대형주)와 미국 ETF 다음 날 방향 예측을 `..\exchange\3_us_market\{미국 거래일}\`에 낸다. 국내 종목 판단은 하지 않는다.

## 입력 (전환 기간 — 읽기만)
- `..\..\VM-SPC_Global\` 전체: 매일 07:00(화 – 토) 미국 ETF 31개 수집 · 예측이 이미 돌고 있다(`results\index.html`, `data\`).
- 2026-10-09에 Core용으로 뽑아 둔 비교 CSV: `..\..\VM-SPC_Global\data\for_core\`(SOXX · SMH · ACWI · SPY · EEM · EWT · TSM, 일회성).
- VM-SPC_Global의 `CLAUDE.md` · `VM-SPC_Global_설계.md`에 그쪽 원칙과 기술 주의사항이 있다(PowerShell BOM, VBS 숨김 실행, KIS 토큰 5분 1회 등).

## 첫 작업 (3단계)
1. VM-SPC_Global 결과(예측 · 적중률 · 평소 비율)를 읽어 `summary.json` · `summary.md`로 바꾸는 작은 내보내기 스크립트(key: us_close · etf_forecast · night_futures).
2. 반도체 비교에 쓴 SOXX · TSM · ACWI 같은 지수는 매일 갱신되도록(지금은 일회성 추출) — KIS 해외 일봉, 수정주가.
3. KIS 호출은 07:00 VM-SPC_Global 실행과 겹치지 않게. 처음에는 Global이 받은 데이터를 읽기만 하고, 새 수집은 그 뒤 시각에.
