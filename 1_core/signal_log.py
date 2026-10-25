"""참고 신호 실전 기록 — 리포트에 나간 신호를 쌓고, 다음 국내 거래일 결과를 이미 있는 일봉으로 채운다(2026-10-11 사용자 결정).

  python signal_log.py            # 결과 채우기 + 누적 성과 출력(확인용)

- 기록: build_report.py --send 때 record(r) — 같은 날짜 · 슬롯 · 신호는 덮어씀(다시 보내도 두 번 쌓이지 않음).
- 결과: evaluate() — 새 데이터를 받지 않고 VM-SPC_Core 테마 묶음 일봉(2_kr themes.GROUPS와 같은 종목) · KODEX 200(_benchmarks\\069500)만 읽는다.
  · 미국 섹터 → 국내 테마(9.277 · 9.286): 발송일 이후 첫 국내 거래일, 테마 시가 → 종가 평균 − 나머지 테마 평균. 맞음 = 부호가 신호 방향과 같음.
  · SOXX → 지수 갭(9.282): 같은 날 KODEX 200 시가 갭. 맞음 = SOXX와 같은 방향.
  · 추격 주의(9.283): 마감 기준일 다음 거래일, 테마 시가 → 종가 − 나머지 테마. 맞음 = 0 미만.
  · 분기 국면(9.294 · 9.296): 기준 월말 뒤 63거래일. 유가 = 에너지화학 · 운송 평균 − 나머지 테마, 금리차 = KODEX 200 등락. 맞음 = 0 초과.
- 백테스트 값(평균 +0.18%p · 같은 방향 54% 등)과 비교하려는 것 — 판단 규칙을 바꾸는 근거는 VM-core 재검증으로만.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "results" / "signal_log.json"
CORE_DATA = ROOT.parent.parent / "VM-SPC_Core" / "data"
BENCH = CORE_DATA / "_benchmarks" / "069500.csv"
QDAYS = 63
KST = timezone(timedelta(hours=9))

sys.path.insert(0, str(ROOT.parent / "2_kr_market"))
from themes import GROUPS, _watchlist  # noqa: E402


# ── 기록 ────────────────────────────────────────────────────────────────

def _load() -> list[dict]:
    try:
        return json.loads(LOG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save(rows: list[dict]) -> None:
    LOG.parent.mkdir(exist_ok=True)
    rows.sort(key=lambda x: (x["made"], x["id"]))
    LOG.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def _next_day(d: str) -> str:
    return (_date.fromisoformat(d) + timedelta(days=1)).isoformat()


def record(r: dict) -> int:
    """리포트 r(build_report.build 결과)에 나간 신호를 기록. 돌려주는 값 = 이번에 쓴 건수."""
    import build_report as B
    slot = r["slot"]
    made = (r.get("send") or _next_day(r["date"])) if slot == "am" else r["date"]   # am 기준일 = 미국 현지 거래일 → 국내 발송일(평소 다음 날, 주말판 월요일)
    new = []
    if slot == "am":
        for s in B.us_signals(r):
            new.append({"kind": "us_theme", "key": s["kr"], "dir": 1 if s["up"] else -1, "already": s["already"],
                        "src": f"{s['theme']} {s['etf']} {s['chg']:+.1f}%"})
        sx = B._soxx(r)
        if sx:
            new.append({"kind": "soxx", "key": "KODEX 200", "dir": 1 if sx["chg"] > 0 else -1, "src": f"SOXX {sx['chg']:+.1f}%"})
    else:
        gs = (r.get("themes") or {}).get("groups") or []
        if gs:
            for i, g in enumerate(gs):
                if i == 0 or B._hot_share(g) >= B.HOT_SHARE:
                    new.append({"kind": "chase", "key": g["theme"], "dir": -1, "src": f"평균 {g['avg']:+.1f}% · +5% {g['hot']}/{g['n']}"})
    q = r.get("quarter") or {}
    if q.get("asof"):
        if (q.get("wti_q_pct") or 0) > 0:
            new.append({"kind": "q_oil", "key": "에너지화학 · 운송", "dir": 1, "src": f"WTI {q['wti_q_pct']:+.1f}%", "asof": q["asof"]})
        if (q.get("curve_q_pp") or 0) > 0:
            new.append({"kind": "q_curve", "key": "KODEX 200", "dir": 1, "src": f"10Y-2Y {q['curve_q_pp']:+.2f}%p", "asof": q["asof"]})
    rows = _load()
    if slot == "am":   # 같은 미국 기준일 신호가 토요일판 · 월요일 주말판에 두 번 나오면 먼저 기록한 것만(결과 날짜가 같음)
        seen = {(o["kind"], o["key"]) for o in rows if o["slot"] == "am" and _next_day(r["date"]) <= o["made"] < made}
        new = [x for x in new if x["kind"].startswith("q_") or (x["kind"], x["key"]) not in seen]
    ids = set()
    for x in new:
        # 분기 신호는 기준 월말마다 한 번(매일 같은 신호가 쌓이지 않게)
        x["id"] = f"{x['asof']}|{x['kind']}" if x["kind"].startswith("q_") else f"{made}|{slot}|{x['kind']}|{x['key']}"
        x.update({"made": x.get("asof", made), "slot": slot, "eval_day": None, "res": None, "hit": None})
        ids.add(x["id"])
    keep = [o for o in rows if o["id"] not in ids and not (o["made"] == made and o["slot"] == slot and not o["kind"].startswith("q_"))]
    old_q = {o["id"]: o for o in rows if o["kind"].startswith("q_")}
    new = [old_q.get(x["id"], x) for x in new]                     # 이미 있는 분기 기록은 결과까지 그대로 둠
    _save(keep + new)
    return len(new)


# ── 결과 채우기 ──────────────────────────────────────────────────────────

def _bars(path: Path) -> dict[str, tuple[float, float]]:
    with path.open(encoding="utf-8-sig") as f:
        return {f"{r['date'][:4]}-{r['date'][4:6]}-{r['date'][6:8]}": (float(r["open"]), float(r["close"]))
                for r in csv.DictReader(f) if r.get("open") and r.get("close")}


def _theme_bars() -> dict[str, dict[str, dict]]:
    """테마 → {종목: 일봉} — themes.compute와 같은 종목(바스켓 대상 종목 뺌)."""
    targets = {t["target"]["code"] for t in _watchlist()["themes"].values()}
    out, cache = {}, {}
    for g, baskets, _ in GROUPS:
        m = {}
        for b in baskets:
            d = CORE_DATA / b
            if not d.exists():
                continue
            for p in d.glob("*.csv"):
                if p.stem.isdigit() and p.stem not in targets and p.stem not in m:
                    if p.stem not in cache:
                        cache[p.stem] = _bars(p)
                    m[p.stem] = cache[p.stem]
        out[g] = m
    return out


def _days(tb: dict) -> list[str]:
    return sorted({d for m in tb.values() for b in m.values() for d in b})


def _oc(tb: dict, theme: str, day: str) -> float | None:
    rs = [(b[day][1] / b[day][0] - 1) * 100 for b in tb.get(theme, {}).values() if day in b and b[day][0]]
    return sum(rs) / len(rs) if rs else None


def _rel_oc(tb: dict, themes: list[str], day: str) -> float | None:
    """themes 평균 시가→종가 − 나머지 테마 평균(테마마다 한 표)."""
    v = {t: _oc(tb, t, day) for t in tb}
    a = [v[t] for t in themes if v.get(t) is not None]
    o = [x for t, x in v.items() if t not in themes and x is not None]
    return sum(a) / len(a) - sum(o) / len(o) if a and o else None


def _cc(bars: dict, d0: str, d1: str) -> float | None:
    return (bars[d1][1] / bars[d0][1] - 1) * 100 if d0 in bars and d1 in bars else None


def _rel_cc(tb: dict, themes: list[str], d0: str, d1: str) -> float | None:
    def avg(t):
        rs = [x for x in (_cc(b, d0, d1) for b in tb.get(t, {}).values()) if x is not None]
        return sum(rs) / len(rs) if rs else None
    v = {t: avg(t) for t in tb}
    a = [v[t] for t in themes if v.get(t) is not None]
    o = [x for t, x in v.items() if t not in themes and x is not None]
    return sum(a) / len(a) - sum(o) / len(o) if a and o else None


def evaluate() -> int:
    rows = _load()
    todo = [x for x in rows if x["res"] is None]
    if not todo:
        return 0
    tb = _theme_bars()
    days = _days(tb)
    bench = _bars(BENCH) if BENCH.exists() else {}
    bdays = sorted(bench)
    n = 0
    for x in todo:
        k = x["kind"]
        if k.startswith("q_"):
            after = [d for d in days if d > x["asof"]]
            if len(after) < QDAYS + 1:
                continue
            d0 = [d for d in days if d <= x["asof"]][-1]
            d1 = after[QDAYS - 1]
            res = _rel_cc(tb, ["에너지화학", "운송"], d0, d1) if k == "q_oil" else _cc(bench, d0, d1)
        else:
            first = [d for d in days if (d > x["made"] if k == "chase" else d >= x["made"])]
            if not first:
                continue
            d1 = first[0]
            if k == "soxx":
                prev = [d for d in bdays if d < d1]
                if d1 not in bench or not prev:
                    continue
                res = (bench[d1][0] / bench[prev[-1]][1] - 1) * 100
            else:
                res = _rel_oc(tb, [x["key"]], d1)
        if res is None:
            continue
        x["eval_day"], x["res"] = d1, round(res, 3)
        x["hit"] = (res * x["dir"]) > 0
        n += 1
    _save(rows)
    return n


# ── 누적 성과 ────────────────────────────────────────────────────────────

KINDS = {  # 종류: (이름, 백테스트 값 — 비교용)
    "us_theme": ("미국 섹터 → 국내 테마", "다른 테마보다 +0.18%p · 같은 방향 54%(평소 50%)"),
    "soxx": ("SOXX → 지수 갭", "갭 같은 방향 85 – 91%"),
    "chase": ("1위 · 무더기 급등 테마 추격", "다른 테마보다 −0.2%p · 이긴 비율 42%(평소 47%)"),
    "q_oil": ("유가↑ 분기 → 에너지화학 · 운송", "+8.6 – 10.4%p · 10번 중 8번"),
    "q_curve": ("금리차 가팔라짐 → 코스피", "+12.3% · 7번 중 5번"),
}


def stats() -> list[dict]:
    """종류별 실전 성과 — 결과가 채워진 것만('이미 반영'은 뺌). avg: 미국 → 국내 테마는 신호 방향으로 맞춘 값(맞는 쪽 +),
    추격 · 분기는 그대로(백테스트 값과 같은 부호), SOXX는 맞음 비율만."""
    rows = [x for x in _load() if x["res"] is not None]
    out = []
    for k, (name, bt) in KINDS.items():
        xs = [x for x in rows if x["kind"] == k and not x.get("already")]
        if not xs:
            continue
        vals = None if k == "soxx" else [x["res"] * (x["dir"] if k == "us_theme" else 1) for x in xs]
        out.append({"kind": k, "name": name, "n": len(xs), "hit": sum(x["hit"] for x in xs) / len(xs),
                    "avg": sum(vals) / len(vals) if vals else None, "since": min(x["made"] for x in xs), "bt": bt})
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"결과 채움 {evaluate()}건 · 기록 {len(_load())}건 ({LOG})")
    for s in stats():
        a = "" if s["avg"] is None else f" · 평균 {s['avg']:+.2f}%p"
        print(f"{s['name']}: {s['n']}건(since {s['since']}) · 맞음 {s['hit']:.0%}{a} | 백테스트 {s['bt']}")
