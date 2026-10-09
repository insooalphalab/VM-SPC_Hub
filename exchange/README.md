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

- 쓰는 역할만 자기 폴더에 쓴다. 다른 역할 폴더는 읽기만 한다.
- 같은 날 두 번(아침 · 마감) 내는 역할은 `summary_am.json` · `summary_pm.json`으로 나눈다(`latest.json`의 slot).
- 내용물은 git에 올리지 않는다(.gitignore). 형식 문서만 올린다.
- 날짜 폴더는 60일 지나면 지워도 된다(원자료는 각 역할의 data/에 있음).

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
| | `flows` | 시장 투자자별 순매수(참고) |
| 3_us_market | `us_close` | 미국 3대 지수 · SOXX · 주요 대형주 등락 |
| | `etf_forecast` | 미국 ETF 다음 날 방향 · 적중률 · 평소 비율(VM-SPC Global 결과) |
| | `night_futures` | KOSPI200 야간선물(있으면) |
| 4_macro | `rates` | 미국 2 · 10 · 30년물, 한국 3년물 |
| | `fx` · `oil` · `credit` · `memory` | 원/달러 · WTI · 신용스프레드 · DRAM/NAND 현물(있는 것만) |
| 5_news | `us_brief` | 미국 모닝 시황 제목 |
| | `kr_close` | 국내 마감 시황 제목 |
| | `issues` | 오늘의 이슈 상위 5(이슈 · 다룬 채널 수 · 대표 제목) |
| | `reports` | 목표가 상향 · 하향 상위 종목 |
| | `holdings_news` | 보유 · 관심 종목 기사(최대 3) |
| 1_core | `report` | 최종 리포트 HTML 경로 · 텔레그램 발송 결과 |
