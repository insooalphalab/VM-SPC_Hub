# 1_core — 판단 · 최종 리포트

2 – 5 정리본(`..\exchange\`)을 읽어 아침 · 마감 리포트 한 편(HTML + 텔레그램)을 만들고 보낸다. 사용자에게 메시지를 보내는 곳은 여기 하나다.
작업 규칙 · 리포트 원칙은 `CLAUDE.md`, 검증(사전 등록 → 백테스트 → 등급)은 VM-SPC_Core 세션이 한다.

## 폴더

```
1_core/
  build_report.py        리포트 만들기 · 전송(본체)
  report_theme.py        디자인(Core GOLDEN_THEME 복사본)
  core_charts.py         종목 차트 칸(Core 페이지에서 잘라 옴)
  signal_log.py          참고 신호 실전 기록
  track_retail_mom.py    9.332 월말 실전 추적
  alert.py               예약 실패 알림 한 줄
  core/                  Core 복사본: secrets_loader · v2_config
  vm_spc/                Core 복사본: notify_telegram(텔레그램 보내기)
  results/               리포트 결과(git 제외)
  .streamlit/secrets.toml  텔레그램 봇 두 줄(비밀 — 커밋 금지)
```

## 파일

| 파일 | 하는 일 | 실행 |
|---|---|---|
| `build_report.py` | exchange 정리본 → `results\report_{날짜}_{am\|pm}[_weekend].html · .txt`, `--send`면 텔레그램(문안 + HTML) · `..\exchange\1_core\{날짜}\summary_*.json` | hub_am 08:00 · hub_pm 16:30 (`--slot am\|pm --send [--weekend] [--warn]`) |
| `report_theme.py` | `GOLDEN_THEME` CSS — 원본 `..\..\VM-SPC_Core\scenario\render_risk.py`와 맞춘다 | build_report가 import |
| `core_charts.py` | Core `results\scenario\risk_scenarios.html`(보유) · `screen.html`(신규)의 종목 칸을 잘라 마감 리포트 탭에 넣음 | build_report가 import |
| `signal_log.py` | 나간 참고 신호 → `results\signal_log.json`, 다음 거래일 결과 채우기(2_kr `themes.py` GROUPS를 import) | build_report `--send` 때 |
| `track_retail_mom.py` | 월말 목록 기록 · 20거래일 뒤 결과 → `results\track_retail_mom.json` (리포트에 안 넣음) | hub_month 18:30 |
| `alert.py` | 텔레그램 한 줄 알림 | 세 예약 스크립트가 실패 때 |

## 입력 · 출력

- 읽음: `..\exchange\{2_kr_market · 3_us_market · 4_macro · 5_news}\latest.json` → 그 날짜 폴더, 2_kr `kr_calendar.json`, Core `results\scenario\*.html`, Core 일봉(실전 기록 채우기).
- 씀: `results\`(리포트 · 실전 기록 두 개), `..\exchange\1_core\{날짜}\`.
- `results\report_*`는 지워도 다시 만들 수 있지만 `signal_log.json` · `track_retail_mom.json`은 쌓인 기록이라 지우지 않는다.
- 9.355 종목 합성 피하기 실전 기록은 허브가 아니라 Core에 쌓인다(`..\..\VM-SPC_Core\results\track_stock_combo.json` · `_universe.csv`, Core `research\track_stock_combo.py`를 hub_month가 실행만). 2027-10 짝 비교용, 리포트에 안 넣음. 스크립트는 Core 저장소에 있지만(b70608d), 쓰는 패널 캐시(Core `results\stock_combo_parts.pkl` · `flow_scan2_parts\base.pkl`)는 커밋되지 않음 — Core를 새로 받으면 `validate_flow_scan2.py` · `validate_stock_combo.py` 등을 다시 돌려 만들어야 월말 기록이 돈다.
