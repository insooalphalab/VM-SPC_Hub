# exchange — 역할 간 정리본 형식

```
exchange/
  {역할}/                 2_kr_market · 3_us_market · 4_macro · 5_news · 1_core
    {YYYY-MM-DD}/         정리본을 만든 기준일(국내 거래일, 해외는 미국 현지 거래일)
      summary.json        필수 — 아래 공통 형식
      summary.md          필수 — 사람이 읽는 같은 내용(10 – 20줄)
      *.csv · *.json      선택 — 원자료 일부나 표
    latest.json           가장 최근 날짜 폴더를 가리키는 한 줄: {"date": "YYYY-MM-DD", "slot": "am|pm"}
```

역할 폴더 바로 아래에 날짜 없이 두는 고정 파일(지우지 않는다 — 다른 역할 · VM-SPC_Core 검증이 경로로 읽음):

| 파일 | 쓰는 곳 | 내용 |
|---|---|---|
| `2_kr_market\kr_calendar.json` | 2_kr `kr_calendar.py` | 국내 날짜 → 개장 여부(KIS 휴장일조회 캐시) |
| `2_kr_market\vkospi.csv` | 2_kr `vkospi.py` | VKOSPI 일별(2003 – 누적, 원자료 — 날짜 폴더처럼 지우면 안 됨) |

날짜 폴더 안 파일 이름(지금 실제로 나오는 것):

| 역할 | 파일 |
|---|---|
| 1_core | `summary_am.json · .md` · `summary_pm.json · .md` · 월요일 `summary_am_weekend.json · .md` |
| 2_kr_market | `summary_pm.json · .md` · `candidates.json` · `holdings.json` · `themes.json` |
| 3_us_market | `summary_am.json · .md` · `us_themes.json` |
| 4_macro | `summary_am.json · .md` · `checklist.json` · `liquidity_monitor.json` · `foreign_view.json` |
| 5_news | `summary_am.json · .md`(월요일은 `weekend` 표시) · `summary_pm.json · .md` |

- 쓰는 역할만 자기 폴더에 쓴다. 다른 역할 폴더는 읽기만 한다.
- 같은 날 두 번(아침 · 마감) 내는 역할은 `summary_am.json` · `summary_pm.json`으로 나눈다(`latest.json`의 slot).
- 내용물은 git에 올리지 않는다(.gitignore). 형식 문서만 올린다.
- 날짜 폴더는 60일 지나면 지워도 된다(원자료는 각 역할의 data/에 있음). 위 고정 파일은 지우지 않는다.

## summary.json 공통 형식 (`//` 주석은 설명용 — 실제 파일에는 넣지 않는다)

```json
{
  "role": "5_news",
  "date": "2026-10-08",
  "slot": "pm",
  "generated_at": "2026-10-08T15:52:10+09:00",
  "status": "ok",                       // ok · partial(일부 원천 실패) · failed
  "sources": ["aicorporateanalysisdeepdive", "shmstory"],
  "headline": "한 줄 요약(사실만, 방향 판단 없음)",
  "items": [
    {
      "key": "us_brief",                // 역할 안에서 고정된 항목 이름
      "title": "미국 시황",
      "text": "장기금리 2002년 이후 최고 급등에 3대 지수 하락",
      "value": null,                    // 숫자면 숫자
      "grade": "서술",                  // 검증됨 · 최근경향 · 약함 · 참고 · 서술 (1 코어만 검증됨 · 최근경향 · 약함을 붙인다)
      "ref": "",                        // 검증 절 번호(있으면, 예 "9.269")
      "link": "https://t.me/..."
    }
  ],
  "notes": "실패 원천 · 지연 등"
}
```

## 역할별 필수 항목(key)

| 역할 | key | 내용 |
|---|---|---|
| 2_kr_market | `regime` | 코스피 장세(상승장 · 횡보·전환 · 하락장)와 며칠째, 60일선 대비 · 기울기 |
| | `mass_recovery` | 오늘 대량 복귀일 여부(복귀 섹터 수 / 20) |
| | `candidates` | 오늘 규칙 충족 종목(코드 · 이름 · 셋업 · 손절 · 목표) — 값은 `candidates.json` |
| | `holdings` | 보유 종목 상태(추세 강도 순위 · 이탈일 외인 · 기관 수급 · 셋업 추적) — 값은 `holdings.json` |
| | `flow_flags` | 보유 · 관심 종목 수급 표시 요약(2026-10-14) — 종목별 값은 `holdings.json` 각 종목 `flow`: `flow_date` · `pension_streak`(연기금 연속 순매수 일수) · `inst_days20` · `inst_sum20`(기관합계 20일 중 순매수 일수 · 합, 백만 원) · `pension_flag` · `inst_flag` · `short_pct20` · `short_rank` · `short_flag`(공매도 거래대금 비중 20일 평균 · 전 종목 순위) · `overhang` · `overhang_rank` · `overhang_flag`(매물대 비중 · 테마 묶음 안 순위). 문구는 1_core |
| | `holdings.json` `facts` · `groups` | 보유 코멘트 값(2026-10-15, `holding_facts.py`) — `facts`: `px_date` · `close` · `today` · `r20` · `bm20` · `dd250` · `gap250` · `slope120` · `r250` · `vol20` · `vol_rank` · `vol_ratio` · `theme` · `events` · `prelim_ly`(%는 퍼센트 값). `groups`: `theme` · `codes` · `names` · `n_hold` · `corr_in` · `corr_out` · `today`. 문구는 1_core |
| | `themes.json` `flow` | 테마 돈의 흐름(2026-10-15, `theme_flow.py` · `theme_map.json`) — `groups[]`: `theme` · `tags` · `n` · `ret`(거래대금 가중 %) · `avg` · `r5` · `up` · `spread` · `share`(%) · `share_x`(평소 대비 배) · `streak` · `tiers{대형 · 중형 · 소형: n · ret}` · `top[]` · `heat[[날짜, 등락, 상위5]]`, `tiers{층: n · ret · share · share_usual}`, `map_asof` · `top_n` · `n_stocks`. 방향 판단 없음 |
| | `flows` | 시장 투자자별 순매수(참고) |
| | `themes` | 테마 흐름(참고) — 테마별 평균 등락 · +5% 종목 수 · 5일 · 지속 · 상위 종목 · 키워드, 값은 `themes.json`(2026-10-10) |
| 3_us_market | `us_close` | 미국 3대 지수 · SOXX · 주요 대형주 등락 |
| | `us_sectors` | 미국 섹터 흐름(참고) — 섹터 ETF 29개 등락 · 5일 · 지속 · 많이 움직인 구성 종목 · 국내 연관 테마, 값은 `us_themes.json`(2026-10-10) |
| | `us_movers` | 큰 움직임 — 섹터 구성 종목 중 ±5% 이상(2026-10-10) |
| | `etf_forecast` | 미국 ETF 다음 날 방향 · 적중률 · 평소 비율(VM-SPC Global 결과) — 리포트 본문에는 안 씀(2026-10-10) |
| | `night_futures` | KOSPI200 야간선물(있으면) |
| 4_macro | `rates` | 미국 2 · 10 · 30년물, 한국 3년물 |
| | `fx` · `oil` · `credit` · `memory` | 원/달러 · WTI · 신용스프레드 · DRAM/NAND 현물(있는 것만) |
| | `liquidity` | 유동성 · 신용 모니터(2026-10-15, 참고) — 같은 폴더 `liquidity_monitor.json`: `headline` · `issues` · `items`(12개: value · date · chg_1w · chg_1m · pct_1y · median_1y · alert · why · series_1y) · `tiers`(미국 IG · BBB · HY · CCC 3년) · `telegram`(문안) |
| | `foreign_view` | 외국인 시선(2026-10-15, 참고 · 동시 지표) — 같은 폴더 `foreign_view.json`: `usd_kospi`(달러 코스피 · `decomp` 1 · 3 · 6개월 usd · local · fx) · `fx_split`(원화 강약 won · dollar · won_own, β) · `foreign`(외국인 순매수 달러 5 · 20 · 60일 · 3년 순위 · 연속) · `etf`(국가 ETF 달러 누적) · `etf_flows`(쌓인 주식 수로 자금 유출입) |
| | `quarter` | 분기 국면 — 지난 월말 기준 WTI 3개월 평균 % 변화 · 10Y-2Y %p 변화(VM-SPC Core 9.294 · 9.296 검증 신호, 문구는 1_core) |
| | `checklist` | 매크로 체크리스트 요약(2026-10-15, 참고) — 전체는 같은 폴더 `checklist.json`: `burden`(흐름 부담 0 – 100) · `level`(높음 · 중간 · 낮음) · `cut`(2016 – 월말 1/3 · 2/3) · `burden_6m_ago` · `hist` · `count` · `board`(가격 반응 1주 — `매크로` · `AI` 두 묶음) · `cards` · `aux` · `sync`(동시 지표) · `ref_cards`(AI 투자 · 인프라 참고 카드, 점수 밖, 2026-10-20) · `strands`(같은 줄기 묶음) · `plain`(`changed` · `risk` · `ok` · `watch` — 쉬운 말 문장 목록) · `credit_alert`(`on` · `hot` · `broad` · `text` — AI · 저신용 신용 압박 경보, 참고) · `change`(`prev_date` · `d_burden` · `cards[]` · `checks[]`, 직전 기록 대비) · `events`(카드 등급 · 구간이 바뀐 날) · `divergence`(상태 vs 가격 한 줄). 카드마다 `grade` · `mean`, 체크마다 `form` · `role`(score · sync · off · aux) · `signal` · `rank` 또는 `chg` · `z` · `streak`(6개월 흐름 몇 개월째, + 상승) |
| 5_news | `us_brief` | 미국 모닝 시황 제목 |
| | `kr_close` | 국내 마감 시황 제목 |
| | `issues` | 오늘의 이슈 상위 5(이슈 · 다룬 채널 수 · 대표 제목) |
| | `reports` | 목표가 상향 · 하향 상위 종목 |
| | `holdings_news` | 보유 · 관심 종목 기사(최대 3) |
| | `theme_news` | 테마별 뉴스 언급(참고) — 2_kr `themes.json`의 종목 · 키워드를 다룬 채널 수 · 글 수 · 대표 제목(2026-10-10) |
| 1_core | `report` | 최종 리포트 HTML 경로 · 텔레그램 발송 결과 |
