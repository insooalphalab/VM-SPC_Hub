"""개인 쏠림 ETF — 코스피 레버리지 · 인버스 일봉 + 상장좌수 스냅샷(2026-10-15 사용자: "국장 흐름에 도움 될 아이템 전부 살펴봐 줘").

  python retail_etf.py          → 일봉 갱신(마지막 저장일 이후) + 오늘 상장좌수 한 줄 추가
  python retail_etf.py --full   → 일봉 2010 – 처음부터

- 일봉: data/retail_etf/{code}.csv(date YYYYMMDD · open · high · low · close · volume, KIS 일봉). 레버리지 ÷ 인버스 거래대금 비 등은 검증 쪽에서 계산.
- 상장좌수: data/retail_etf/shares.csv(date · code · shares) — KIS에 과거 이력 API가 없어 오늘부터 매일 쌓는다(설정 · 환매 = 개인 자금 방향).
- hub_pm 16:00 theme_extra 다음(같은 토큰 캐시). 실패해도 0.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "core"))
OUT = ROOT / "data" / "retail_etf"
ETFS = {"122630": "KODEX 레버리지", "252670": "KODEX 200선물인버스2X", "114800": "KODEX 인버스",
        "233740": "KODEX 코스닥150레버리지", "251340": "KODEX 코스닥150선물인버스", "069500": "KODEX 200"}
START = date(2010, 1, 1)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    from kis_client import RateLimitedCaller, fetch_daily_bars, fetch_etf_listed_shares
    c = RateLimitedCaller(min_interval=1.0)
    OUT.mkdir(parents=True, exist_ok=True)
    today = date.today()
    try:
        for code in ETFS:
            f = OUT / f"{code}.csv"
            old = pd.read_csv(f, dtype={"date": str}).set_index("date") if f.exists() and "--full" not in sys.argv else None
            start = (datetime.strptime(old.index.max(), "%Y%m%d").date() - timedelta(days=7)) if old is not None and len(old) else START
            rows = fetch_daily_bars(c, code, start, today)
            if rows:
                new = pd.DataFrame(rows).set_index("date")
                new = new if old is None else new.combine_first(old)
                new.sort_index().to_csv(f, encoding="utf-8")
        sf = OUT / "shares.csv"
        snap = pd.DataFrame([{"date": f"{today:%Y-%m-%d}", "code": k, "shares": fetch_etf_listed_shares(c, k)} for k in ETFS])
        if sf.exists():
            snap = pd.concat([pd.read_csv(sf, dtype={"code": str}), snap]).drop_duplicates(["date", "code"], keep="last")
        snap.to_csv(sf, index=False, encoding="utf-8")
        print(f"[retail_etf] 일봉 {len(ETFS)}종 · 상장좌수 {today}")
    except Exception as e:  # noqa: BLE001
        print(f"[retail_etf] KIS 실패: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
