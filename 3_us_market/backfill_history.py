"""미국 일봉 과거분 백필 — VM-SPC_Global 일봉 파일 앞에 START 부터 붙인다(2026-10-10 사용자 결정, 한 번만 실행).

  python backfill_history.py            # 전부(섹터 ETF + 구성 대형주)
  python backfill_history.py --dry      # 받을 목록 · 예상 호출 수만

- 왜: 검증 분할 기준(2016 – 2021-05 / 2021-06 – )의 앞 기간이 없어 미국 → 국내 칸이 "최근경향"까지만 나옴(9.277 · 9.281 – 9.285).
- Global 수집기는 저장분이 있으면 최근 것만 덧붙여 과거로 늘지 않는다 — 그래서 Global 의 KIS 함수(fetch_daily_bars)를
  그대로 불러 [START, 가장 오래된 날 + 겹침] 을 받고 Global save_bars(merge=True)로 합친다. Global 코드는 고치지 않음.
- 이음매 점검: 겹치는 날 종가가 0.5% 넘게 다르면(그 사이 분할 등 수정주가 소급) 그 종목은 [START, 오늘] 전체를 다시 받아 통째로 쓴다.
- 같은 티커가 여러 바스켓 폴더에 있으면 한 번만 받아 모든 폴더에 쓴다.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

GLOBAL = Path(__file__).resolve().parent.parent.parent / "VM-SPC_Global"
for p in (GLOBAL, GLOBAL / "core", GLOBAL / "vm_predict"):
    sys.path.insert(0, str(p))
import os  # noqa: E402

os.environ.setdefault("V2_DATA_DIR", str(GLOBAL / "data"))
from kis_client import RateLimitedCaller, fetch_daily_bars  # noqa: E402
from v2_config import basket_codes, basket_excd, load_baskets  # noqa: E402
from v2_datastore import load_bars, save_bars  # noqa: E402

START = date(2015, 10, 1)
OVERLAP_DAYS, TOL = 20, 0.005


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    dry = "--dry" in sys.argv
    where: dict[str, list[str]] = {}
    excd: dict[str, str] = {}
    for b in load_baskets(GLOBAL / "basket_watchlist.json"):
        ex = basket_excd(b)
        for code in basket_codes(b):
            where.setdefault(code, []).append(b["name"])
            excd[code] = ex.get(code) or excd.get(code)
    only = {a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")}   # 시험용: --only=SOXX
    todo = []
    for code, bs in sorted(where.items()):
        if only and code not in only:
            continue
        old = load_bars(bs[0], code)
        first = old.index.min().date() if old is not None and not old.empty else None
        if first is None or first > START + timedelta(days=10):
            todo.append((code, bs, first))
    calls = sum(((f or date.today()) - START).days * 252 // 365 // 100 + 2 for _, _, f in todo)
    print(f"티커 {len(where)}개 중 백필 대상 {len(todo)}개 · 예상 KIS 호출 약 {calls}번(0.35초 간격 → 약 {calls * 0.35 / 60:.0f}분)")
    if dry:
        for code, bs, f in todo[:15]:
            print(f"  {code} ({excd[code]}) 지금 시작 {f} · 폴더 {len(bs)}개")
        return 0
    caller = RateLimitedCaller()
    done = 0
    for i, (code, bs, first) in enumerate(todo, 1):
        try:
            end = (first + timedelta(days=OVERLAP_DAYS)) if first else date.today()
            rows = fetch_daily_bars(caller, code, START, end, excd[code])
            if not rows:
                print(f"[{i}/{len(todo)}] {code}: 받은 봉 없음(상장 전 등)")
                continue
            mode = "앞에 붙임"
            old = load_bars(bs[0], code)
            if old is not None and not old.empty:
                bad = 0
                for r in rows:
                    ts = datetime.strptime(r["date"], "%Y%m%d")
                    if ts in old.index and old.at[ts, "close"] > 0 and abs(r["close"] - old.at[ts, "close"]) / old.at[ts, "close"] > TOL:
                        bad += 1
                if bad:
                    rows = fetch_daily_bars(caller, code, START, date.today(), excd[code])
                    mode = f"이음매 {bad}일 어긋남 → 전체 다시 받음"
            for b in bs:
                save_bars(b, code, rows, merge=(mode == "앞에 붙임"))
            done += 1
            print(f"[{i}/{len(todo)}] {code}: {rows[0]['date']} – {rows[-1]['date']} {len(rows)}봉 · {mode} · 폴더 {len(bs)}개", flush=True)
        except Exception as e:  # 한 종목 실패로 전체를 멈추지 않는다
            print(f"[{i}/{len(todo)}] {code}: 실패 {type(e).__name__}: {e}", flush=True)
    print(f"끝: {done}/{len(todo)}개 백필")
    return 0


if __name__ == "__main__":
    sys.exit(main())
