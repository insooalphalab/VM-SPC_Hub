"""테마 흐름 보조 수집(2026-10-15) — theme_map.json "넓힘" 종목 일봉 + 테마 종목 상장주식수(시총 층용).

  python theme_extra.py            → 넓힘 종목 일봉 갱신(KIS 일봉, 마지막 저장일 이후) · 상장주식수가 30일 넘었으면 다시 받기
  python theme_extra.py --shares   → 상장주식수 지금 다시 받기(테마 종목 약 230개, 1초 간격 약 4분)

- 일봉: data/theme_extra/{code}.csv(date YYYYMMDD · open · high · low · close · volume, 수정주가) — 바스켓 · Core _scenario에 이미 있는
  종목은 받지 않는다(price_file()이 그쪽을 먼저 읽음). 처음엔 400일치.
- 상장주식수: data/theme_shares.csv(code · shares · asof) — KIS 현재가(FHKST01010100) lstn_stcn. 시총 = 종가 × 주식수.
- KIS 코드는 core\\ 복사본(수정 없음). hub_pm 16:00 VKOSPI 다음에 실행(같은 토큰 캐시). 실패해도 0으로 끝남 — 테마 흐름은 있는 값으로.
"""
from __future__ import annotations

import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "core"))
from themes import DATA, GROUPS  # noqa: E402

EXTRA = ROOT / "data" / "theme_extra"
SHARES = ROOT / "data" / "theme_shares.csv"
MAP = ROOT / "theme_map.json"
SHARES_DAYS, FIRST_DAYS = 30, 400
PRICE_PATH, PRICE_TR = "/uapi/domestic-stock/v1/quotations/inquire-price", "FHKST01010100"


def price_file(code: str) -> Path | None:
    """테마 묶음 바스켓 → Core _scenario → 이 폴더 data/theme_extra 순."""
    for _, bs, _ in GROUPS:
        for b in bs:
            f = DATA / b / f"{code}.csv"
            if f.exists():
                return f
    for f in (DATA / "_scenario" / f"{code}.csv", EXTRA / f"{code}.csv"):
        if f.exists():
            return f
    return None


def _map() -> dict:
    import json
    return json.loads(MAP.read_text(encoding="utf-8")) if MAP.exists() else {}


def _last_date(f: Path) -> str | None:
    with f.open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    return rows[-1]["date"] if rows else None


def update_bars(caller, codes: list[str]) -> list[str]:
    from kis_client import fetch_daily_bars
    EXTRA.mkdir(parents=True, exist_ok=True)
    today, done = date.today(), []
    for c in codes:
        f = price_file(c)
        if f is not None and f.parent != EXTRA:
            continue                                   # 바스켓 · _scenario가 매일 갱신
        f = EXTRA / f"{c}.csv"
        last = _last_date(f) if f.exists() else None
        start = (datetime.strptime(last, "%Y%m%d").date() - timedelta(days=7)) if last else today - timedelta(days=FIRST_DAYS * 1.5)
        rows = fetch_daily_bars(caller, c, start, today)
        if not rows:
            continue
        new = pd.DataFrame(rows).set_index("date")
        if f.exists():
            old = pd.read_csv(f, dtype={"date": str}, encoding="utf-8-sig").set_index("date")
            new = new.combine_first(old)
        new.sort_index().to_csv(f, encoding="utf-8")
        done.append(c)
    return done


def update_shares(caller, codes: list[str]) -> int:
    rows = []
    for c in codes:
        b = caller.get(PRICE_PATH, PRICE_TR, {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": c})
        o = b.get("output") or {}
        try:
            n = float(o.get("lstn_stcn") or 0)
        except ValueError:
            n = 0
        if n > 0:
            rows.append({"code": c, "shares": n, "asof": f"{date.today():%Y-%m-%d}"})
    if rows:
        SHARES.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(SHARES, index=False, encoding="utf-8")
    return len(rows)


def shares() -> dict[str, float]:
    if not SHARES.exists():
        return {}
    d = pd.read_csv(SHARES, dtype={"code": str})
    return dict(zip(d["code"], d["shares"]))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    m = _map()
    if not m:
        print("[theme_extra] theme_map.json 없음 — theme_map.py 먼저")
        return 0
    from kis_client import RateLimitedCaller
    caller = RateLimitedCaller(min_interval=1.0)
    st = m["stocks"]
    try:
        extra = [c for c, v in st.items() if v["src"] == "extra"]
        done = update_bars(caller, extra)
        print(f"[theme_extra] 넓힘 {len(extra)}종목 중 일봉 갱신 {len(done)}")
        old = (datetime.now() - datetime.fromtimestamp(SHARES.stat().st_mtime)).days if SHARES.exists() else 999
        if "--shares" in sys.argv or old > SHARES_DAYS:
            n = update_shares(caller, [c for c, v in st.items() if v["group"] != "기타"])
            print(f"[theme_extra] 상장주식수 {n}종목")
    except Exception as e:  # noqa: BLE001
        print(f"[theme_extra] KIS 실패: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
