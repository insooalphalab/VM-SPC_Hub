# 3_us_market — 해외(미국) 시장

VM-SPC_Global이 07:00에 받은 미국 일봉 · 예측을 읽어 미국 마감 요약 · 섹터 흐름을 `..\exchange\3_us_market\{미국 거래일}\`에 낸다. 국내 종목 판단은 하지 않는다.
작업 규칙 · 결정은 `CLAUDE.md`.

## 폴더

```
3_us_market/
  export_exchange.py     정리본 내보내기(본체)
  us_themes.py           미국 섹터 흐름 · 국내 연관 테마(KR_LINK)
  backfill_history.py    과거 일봉 백필(한 번 실행함 — 새 종목 더할 때만)
  core/                  Global 복사본: v2_config · v2_datastore
  vm_spc/                Global 복사본: build_index(collect_rows)
```

데이터 · 비밀 폴더가 없다 — 데이터는 `..\..\VM-SPC_Global\data`를 읽기만 한다.

## 파일

| 파일 | 하는 일 | 실행 |
|---|---|---|
| `export_exchange.py` | `summary_am.json · .md` · `us_themes.json` + `latest.json` (key: us_close · us_sectors · us_movers · etf_forecast) | hub_am 07:15 (환경변수 `V2_RESULTS_DIR` · `V2_DATA_DIR` = Global) |
| `us_themes.py` | 섹터 ETF 29개 등락 · 지속 · 큰 움직임, `KR_LINK` → 2_kr 테마 이름 | export가 import |
| `backfill_history.py` | Global 일봉 앞에 2015-10 – 붙이기 (`--only=티커`) | 손으로, 필요할 때만 |

## 입력 · 출력

- 읽음: `..\..\VM-SPC_Global\results\` · `data\` · `basket_watchlist.json`(복사 · 커밋 금지).
- 씀: `..\exchange\3_us_market\`. 백필만 Global `data\`에 쓴다.
- 3_us 정리본 기준일이 hub_am의 "미국 새 거래일" 판정 기준이다.
