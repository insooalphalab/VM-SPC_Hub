"""미국 섹터 흐름(하루치) — VM-SPC_Global 바스켓(섹터 ETF + 구성 대형주) 일봉을 읽어 섹터별 그날 강도 · 지속 · 국내 연관 테마(2026-10-10).

  python us_themes.py [YYYY-MM-DD]      # 확인용 출력. 평소에는 export_exchange.py 가 불러 us_themes.json 으로 저장

- 섹터 = Global basket_watchlist.json 의 테마(지수 성격인 '대형주 전체' · '나스닥100'은 뺌). 등락은 섹터 ETF 기준, 구성 종목 평균도 같이.
- 지속 = ETF 등락 상위 TOP_N 안에 든 날이 며칠째 이어지는지. 큰 움직임 = 구성 종목 중 ±BIG% 이상.
- KR_LINK = 같은 성격의 국내 테마(2_kr_market themes.py GROUPS 이름). 미국 → 국내 이어짐은 검증 전 — 참고로만.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

GLOBAL = Path(__file__).resolve().parent.parent.parent / "VM-SPC_Global"
DATA = GLOBAL / "data"
TOP_N, BIG, LOOKBACK = 5, 5.0, 25
SIG_N, SIG_Z, SIG_PCT = 60, 1.5, 2.0   # 검증 9.277 · 9.286 신호: ETF 등락이 직전 60일 표준편차의 ±1.5배 이상(또는 ±2%)
SKIP = {"대형주 전체", "나스닥100"}
KR_LINK = {"반도체": "반도체", "원자력": "원전", "방산": "방산", "2차전지·리튬": "2차전지", "로봇·AI": "로봇", "자동차": "자동차",
           "바이오": "바이오", "헬스케어": "바이오", "철강": "철강", "에너지": "에너지화학", "소재": "에너지화학", "인터넷": "인터넷",
           "소프트웨어": "인터넷", "게임": "게임", "은행": "금융(은행 · 보험)", "보험": "금융(은행 · 보험)", "금융": "금융(은행 · 보험)",
           "증권": "증권", "건설·주택": "건설", "인프라": "건설", "유틸리티": "전력기기", "운송": "운송", "필수소비재": "필수소비재"}


def _closes(path: Path, n: int) -> dict[str, float]:
    with path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))[-n:]
    return {f"{r['date'][:4]}-{r['date'][4:6]}-{r['date'][6:8]}": float(r["close"]) for r in rows if r.get("close")}


def compute(day: str | None = None) -> dict:
    wl = json.loads((GLOBAL / "basket_watchlist.json").read_text(encoding="utf-8"))
    names = {s["code"]: s.get("name", s["code"]) for s in wl.get("stocks", [])}
    secs = []
    for theme, t in wl["themes"].items():
        if theme in SKIP:
            continue
        d, etf = DATA / t["basket_name"], t["target"]["code"]
        if not (d / f"{etf}.csv").exists():
            continue
        secs.append({"theme": theme, "etf": etf, "etf_name": t["target"]["name"],
                     "closes": {p.stem: _closes(p, max(LOOKBACK, SIG_N) + 15) for p in d.glob("*.csv")}})
    all_days = sorted({x for s in secs for x in s["closes"][s["etf"]]})
    day = day or (all_days[-1] if all_days else "")
    days = [x for x in all_days if x <= day][-(LOOKBACK + 6):]
    if not days or days[-1] != day:
        return {"date": day, "sectors": [], "movers": [], "note": f"Global 섹터 일봉에 {day} 봉 없음"}

    def ret(cl: dict, i: int, k: int = 1) -> float | None:
        a, b = cl.get(days[i - k]) if i - k >= 0 else None, cl.get(days[i])
        return (b / a - 1) * 100 if a and b else None

    hist = {s["theme"]: [] for s in secs}
    for i in range(1, len(days)):
        rs = sorted(((ret(s["closes"][s["etf"]], i), s["theme"]) for s in secs), key=lambda x: -(x[0] if x[0] is not None else -1e9))
        top = {t for v, t in rs[:TOP_N] if v is not None}
        for t in hist:
            hist[t].append(t in top)

    last, out, movers = len(days) - 1, [], {}
    for s in secs:
        e = ret(s["closes"][s["etf"]], last)
        if e is None:
            continue
        cons = [(c, ret(cl, last)) for c, cl in s["closes"].items() if c != s["etf"]]
        cons = [(c, r) for c, r in cons if r is not None]
        streak = 0
        for on in reversed(hist[s["theme"]]):
            if not on:
                break
            streak += 1
        for c, r in cons:
            if abs(r) >= BIG:
                movers[c] = {"code": c, "name": names.get(c, c), "pct": round(r, 2), "sector": s["theme"]}
        ecl = s["closes"][s["etf"]]                       # 직전 60거래일 일간 등락의 표준편차(오늘 제외)
        past = [x for x in sorted(ecl) if x < day][-(SIG_N + 1):]
        rs = [(ecl[b] / ecl[a] - 1) * 100 for a, b in zip(past, past[1:]) if ecl.get(a) and ecl.get(b)]
        sd = statistics.pstdev(rs) if len(rs) >= SIG_N // 2 else None
        z = round(e / sd, 2) if sd else None
        out.append({"theme": s["theme"], "etf": s["etf"], "chg": round(e, 2), "z": z,
                    "signal": bool((z is not None and abs(z) >= SIG_Z) or abs(e) >= SIG_PCT),
                    "avg": round(sum(r for _, r in cons) / len(cons), 2) if cons else None,
                    "r5": None if ret(s["closes"][s["etf"]], last, 5) is None else round(ret(s["closes"][s["etf"]], last, 5), 2),
                    "streak": streak, "kr": KR_LINK.get(s["theme"], ""),
                    "top": [{"code": c, "name": names.get(c, c), "pct": round(r, 2)} for c, r in sorted(cons, key=lambda x: -abs(x[1]))[:3]]})
    out.sort(key=lambda x: -x["chg"])
    mv = sorted(movers.values(), key=lambda x: -abs(x["pct"]))
    return {"date": day, "top_n": TOP_N, "big_pct": BIG, "sectors": out, "movers": mv,
            "note": f"미국 섹터 {len(out)}개 · 섹터 ETF 등락 기준 · 지속 = ETF 등락 상위 {TOP_N} 연속 일수 · 큰 움직임 = 구성 종목 ±{BIG:.0f}% 이상"}


def line(t: dict, k: int = 3) -> str:
    ss = t.get("sectors") or []
    if not ss:
        return t.get("note", "미국 섹터 자료 없음")
    f = lambda s: f"{s['theme']} {s['chg']:+.1f}%" + (f"({s['streak']}일째)" if s["streak"] >= 2 else "")
    return " · ".join(f(s) for s in ss[:k]) + " | 약함: " + " · ".join(f(s) for s in ss[::-1][:2])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    t = compute(sys.argv[1] if len(sys.argv) > 1 else None)
    print(t["date"], t["note"])
    for s in t["sectors"]:
        print(f"{s['theme']:10s} {s['etf']:5s} {s['chg']:+6.2f}% 구성평균 {s['avg'] if s['avg'] is not None else '–':>6} 5일 {s['r5'] if s['r5'] is not None else '–':>6} "
              f"지속 {s['streak']} → {s['kr'] or '–':10s} " + " ".join(f"{x['name']} {x['pct']:+.1f}" for x in s["top"]))
    print("큰 움직임:", " · ".join(f"{m['name']} {m['pct']:+.1f}%" for m in t["movers"][:12]))
