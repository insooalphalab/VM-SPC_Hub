# 2_kr_market — 국내 시장 데이터

국내 시장 데이터와 그 위의 기계적 상태(장세 · 대량 복귀일 · 규칙 충족 종목 · 보유 상태 · 테마 흐름 · 수급 표시)를 `..\exchange\2_kr_market\{거래일}\`에 낸다. 방향 판단 문구는 1_core가 쓴다.
작업 규칙 · 결정은 `CLAUDE.md`.

## 폴더

```
2_kr_market/
  export_exchange.py     정리본 내보내기(본체)
  themes.py              테마 흐름(22개 GROUPS — 다른 역할도 이 이름을 씀)
  theme_map.py           테마 돈의 흐름 상위군 소속표 만들기(분기마다)
  theme_map.json         그 결과(커밋 대상 — VM-SPC_Core 검증 스크립트도 읽음)
  theme_flow.py          테마 돈의 흐름 계산
  theme_extra.py         넓힘 종목 일봉 · 상장주식수(KIS)
  flow_flags.py          보유 · 관심 수급 표시
  holding_facts.py       보유 · 관심 사실 값 · 묶음
  kr_calendar.py         국내 개장일 달력(KIS)
  vkospi.py              VKOSPI 일별(KIS)
  retail_etf.py          개인 쏠림 ETF 일봉 · 좌수(KIS)
  core/                  Core 복사본: kis_auth · kis_client · secrets_loader · v2_config
  data/                  theme_extra/ · theme_shares.csv · retail_etf/ (git 제외)
  state/                 KIS 토큰 캐시(git 제외)
  .streamlit/secrets.toml  KIS 앱 키 두 줄(비밀 — 커밋 금지, BOM 없는 UTF-8)
```

## 파일

| 파일 | 하는 일 | 실행 |
|---|---|---|
| `export_exchange.py` | Core `results\scenario\*.json` · 일봉을 읽어 `summary_pm.json · .md` · `candidates.json` · `holdings.json` · `themes.json` + `latest.json` | hub_pm (16:00 단계 끝) |
| `themes.py` | 바스켓 39개 → 테마 22개 하루 강도 · 지속 | export가 import (1_core signal_log · 3_us · 5_news도 이름 · 키워드를 씀) |
| `theme_map.py` → `theme_map.json` | 상관으로 묶은 상위군 소속표 | hub_month 분기 말 |
| `theme_flow.py` | `themes.json` `flow`(거래대금 가중 등락 · 몫 · 시총 층 · 히트맵) | export가 import |
| `theme_extra.py` | 넓힘 종목 일봉 → `data\theme_extra\`, 상장주식수 → `data\theme_shares.csv`(30일마다) | hub_pm |
| `flow_flags.py` | `holdings.json` 종목별 `flow`(연기금 · 기관 · 공매도 · 매물대) | export가 import |
| `holding_facts.py` | `holdings.json` `facts` · `groups` | export가 import |
| `kr_calendar.py` | `..\exchange\2_kr_market\kr_calendar.json` | hub_am 07:20 뒤 |
| `vkospi.py` | `..\exchange\2_kr_market\vkospi.csv`(2003 – 누적) | hub_pm |
| `retail_etf.py` | `data\retail_etf\{code}.csv` · `shares.csv` | hub_pm |

## 입력 · 출력

- 읽음(읽기만): `..\..\VM-SPC_Core\data\`(바스켓 일봉 · `_scenario` · `_investor_detail` · `_short` · `_dart` · `_market`), `..\..\VM-SPC_Core\results\scenario\`(market · screen · mass_days · summary), `..\..\VM-SPC_Core\scenario_targets.json`(비밀).
- 씀: `..\exchange\2_kr_market\`, `data\`, `state\`.

## 옮기지 말 것 (다른 곳이 경로로 읽음)

| 경로 | 읽는 곳 |
|---|---|
| `..\exchange\2_kr_market\vkospi.csv` | 4_macro `liquidity_monitor.py`, Core `research\validate_vkospi.py` 등 |
| `..\exchange\2_kr_market\kr_calendar.json` | 1_core `build_report.py`, `scripts\hub_month.ps1`, 4_macro `liquidity_monitor.py` |
| `theme_map.json` | Core `research\validate_theme_rotation.py` |
| `data\retail_etf\` | 4_macro `liquidity_monitor.py`, Core 검증 스크립트 |
| `themes.py`의 `GROUPS` 이름 | 1_core · 3_us · 5_news (바꾸면 같이 바뀜) |
