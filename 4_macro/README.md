# 4_macro — 매크로

금리 · 환율 · 유가 · 신용 · 원자재 · 메모리 가격 일별 표와 그 위의 참고 칸(매크로 부담 점수 · 유동성 · 신용 모니터 · 외국인 시선 · 분기 국면)을 `..\exchange\4_macro\{날짜}\`에 낸다. 방향 판단 문구는 쓰지 않는다.
매크로 원자료는 허브에만 있다 — 검증 요청 때 이 폴더 `data\` 경로를 따로 알려 준다. 작업 규칙 · 결정은 `CLAUDE.md`.

## 폴더

```
4_macro/
  export_exchange.py         정리본 내보내기(본체 — 아래를 차례로 부름)
  월간_매크로섹터분석.py      KIS_auto 복사본: 기본 수집 함수(collect_l1 · l2 · l3)
  kis_config.py              KIS_auto 복사본: .env 로더
  collect_ext.py             확장 수집(FRED · yfinance · ECOS · 관세청 약 120 시리즈)
  checklist.py               매크로 체크리스트 · 부담 점수
  liquidity_monitor.py       유동성 · 신용 모니터 · 국내 상태 줄
  foreign_view.py            외국인 시선 6단계
  data/                      원자료(git 제외 — 아래 표)
  .env                       FRED · ECOS · 관세청 키(비밀 — 커밋 금지)
```

## 파일

| 파일 | 하는 일 | 실행 |
|---|---|---|
| `export_exchange.py` | 기본 수집 → `data\macro_daily.csv` · `memory_daily.csv`, 확장 · 체크리스트 · 모니터 · 외국인 시선을 돌려 `summary_am.json · .md` · `checklist.json` · `liquidity_monitor.json` · `foreign_view.json` + `latest.json` (key: rates · fx · oil · credit · memory · quarter · checklist · liquidity · foreign_view) | hub_am 07:15 (약 2분) |
| `월간_매크로섹터분석.py` | `collect_l1_data` · `collect_l2_data` · `collect_l3_dram` (엑셀 · L4는 안 씀) | export · collect_ext가 import |
| `collect_ext.py` | `data\macro_ext.csv`(2000 – 누적, 평소엔 최근 400일) · `data\etf_shares.csv`(매일 한 줄) | export가 부름 (`--full`은 손으로) |
| `checklist.py` | `CARDS` · `SPEC`으로 카드별 체크 · 부담 점수 → `data\checklist.json` | export가 부름 |
| `liquidity_monitor.py` | 12개 지표 · 경보 · 등급별 신용 · `kr_state` · 텔레그램 문안 → `data\liquidity_monitor.json` | export가 부름 |
| `foreign_view.py` | 달러 코스피 · 원화 분해 · 외국인 순매수 달러 · 국가 ETF · `story()` → `data\foreign_view.json` | export가 부름 |

## data\

| 파일 | 내용 |
|---|---|
| `macro_daily.csv` | 기본 매크로 일별(2015-01 – , HY · BBB는 2023-10 – ) |
| `memory_daily.csv` | DRAM · NAND 현물 |
| `macro_ext.csv` | 확장 시리즈(2000 – ) |
| `etf_shares.csv` | 국가 · 지수 ETF 12개 주식 수 스냅샷(2026-10-15 – , 과거 이력 없음 — 지우면 복구 불가) |
| `checklist.json` · `liquidity_monitor.json` · `foreign_view.json` | 그날 계산 결과(정리본 폴더에도 복사) |

## 옮기지 말 것 (다른 곳이 경로로 읽음)

| 경로 | 읽는 곳 |
|---|---|
| `data\macro_daily.csv` · `data\macro_ext.csv` | VM-SPC_Core `research\validate_hub_*.py` · `validate_macro_*.py` · `validate_burden_dynamics.py` 등 |
| `checklist.py`의 `CARDS` 5칸 형식 | Core `research\validate_macro_checklist.py` 등이 import — 형식을 바꾸지 않는다 |
