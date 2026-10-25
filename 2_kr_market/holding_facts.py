"""보유 · 관심 종목 사실 · 위험 값(2026-10-15 사용자 승인 — 보유 코멘트 세 층 중 ② 추세 · ③ 사실) — 데이터만, 문구는 1_core.

  python holding_facts.py 005930 000660 …   → 종목별 값 출력(확인용)

예측이 아니라 지금 상태: 오늘 · 20일 수익(코스피200 대비), 1년 고점 대비, 250일선 이격 · 120일선 방향 · 1년 수익(긴 추세 — 9.330 · 9.342에서
"이어지는 쪽"은 있으나 끝은 모름), 20일 변동성과 1년 안 순위, 거래량 ÷ 20일 평균, 최근 30일 공시 · 지분 변동 보고, 작년 같은 때 잠정실적 날.
groups: 보유 종목을 테마(themes.GROUPS 순서로 처음 걸리는 것)로 묶어 2종목 이상인 묶음의 60일 상관 평균 · 오늘 평균 수익.
자료: VM-SPC_Core data/{바스켓} · _scenario · _benchmarks 일봉, data/_dart(events · prelim · insider). 읽기만.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from themes import GROUPS

CORE_DATA = Path(__file__).resolve().parent.parent.parent / "VM-SPC_Core" / "data"
DART = CORE_DATA / "_dart"
BENCH = CORE_DATA / "_benchmarks" / "069500.csv"
SKIP = ("_investor_detail", "_credit", "_program", "_long_history", "investor")
CORR_WIN, EVENT_DAYS = 60, 30


def _px_file(code: str) -> Path | None:
    fs = [f for f in CORE_DATA.glob(f"*/{code}.csv") if not any(s in f.parts for s in SKIP)]
    return max(fs, key=lambda f: f.stat().st_mtime) if fs else None


def _px(f: Path) -> pd.DataFrame:
    d = pd.read_csv(f, encoding="utf-8-sig")
    d["date"] = pd.to_datetime(d["date"].astype(str))
    return d.set_index("date").sort_index()


def theme_of(code: str) -> str:
    for theme, baskets, _ in GROUPS:
        if any((CORE_DATA / b / f"{code}.csv").exists() for b in baskets):
            return theme
    return ""


def _dart(code: str, day: pd.Timestamp) -> tuple[list[str], str]:
    ev: list[str] = []
    lo = day - pd.Timedelta(days=EVENT_DAYS)
    last_prelim = ""
    for name in ("events.csv", "prelim.csv"):
        f = DART / name
        if not f.exists():
            continue
        d = pd.read_csv(f, dtype=str)
        d = d[d["stock_code"] == code].copy()
        d["d"] = pd.to_datetime(d["rcept_dt"], errors="coerce")
        ev += [f"{r.d:%m/%d} {r.report_nm}" for r in d[(d.d >= lo) & (d.d <= day)].itertuples()]
        if name == "prelim.csv":            # 작년 같은 때(330 – 380일 전) 잠정실적 — 올해 발표 예상 시기
            ly = d[(d.d >= day - pd.Timedelta(days=380)) & (d.d <= day - pd.Timedelta(days=330))]
            if len(ly):
                last_prelim = f"{ly.d.min():%m/%d}"
    f = DART / "insider.csv"
    if f.exists():
        d = pd.read_csv(f, dtype=str, usecols=["stock_code", "rcept_dt"])
        n = int(((d["stock_code"] == code) & (pd.to_datetime(d["rcept_dt"], errors="coerce").between(lo, day))).sum())
        if n:
            ev.append(f"임원 · 주요주주 지분 변동 보고 {n}건")
    return ev, last_prelim


def compute(codes: list[str], day: str, hold_codes: set[str] | None = None, names: dict | None = None) -> dict:
    t0 = pd.Timestamp(day)
    bm = _px(BENCH)["close"] if BENCH.exists() else None
    out: dict = {"codes": {}, "groups": []}
    rets: dict[str, pd.Series] = {}
    for c in codes:
        f = _px_file(c)
        if f is None:
            continue
        d = _px(f)
        d = d[d.index <= t0]
        if len(d) < 260:
            continue
        cl = d["close"]
        r = cl.pct_change()
        rets[c] = r
        ma120, ma250 = cl.rolling(120).mean(), cl.rolling(250).mean()
        vol20 = float(r.tail(20).std() * 100)
        vh = (r.rolling(20).std() * 100).tail(250)
        x = {
            "px_date": f"{d.index[-1]:%Y-%m-%d}", "close": float(cl.iloc[-1]),
            "today": round(float(r.iloc[-1] * 100), 2),
            "r20": round(float((cl.iloc[-1] / cl.iloc[-21] - 1) * 100), 2),
            "dd250": round(float((cl.iloc[-1] / cl.tail(250).max() - 1) * 100), 2),
            "gap250": round(float((cl.iloc[-1] / ma250.iloc[-1] - 1) * 100), 2),
            "slope120": round(float((ma120.iloc[-1] / ma120.iloc[-21] - 1) * 100), 2),
            "r250": round(float((cl.iloc[-1] / cl.iloc[-251] - 1) * 100), 2),
            "vol20": round(vol20, 2), "vol_rank": round(float((vh < vol20).mean()), 2),
            "vol_ratio": round(float(d["volume"].iloc[-1] / d["volume"].iloc[-21:-1].mean()), 2),
            "theme": theme_of(c),
        }
        if bm is not None:
            b = bm[bm.index <= t0]
            x["bm20"] = round(float((b.iloc[-1] / b.iloc[-21] - 1) * 100), 2)
        x["events"], x["prelim_ly"] = _dart(c, t0)
        out["codes"][c] = x
    # 묶음 — 보유 종목만, 같은 테마 2종목 이상
    hc = [c for c in codes if c in out["codes"] and (hold_codes is None or c in hold_codes)]
    R = pd.DataFrame({c: rets[c] for c in hc}).tail(CORR_WIN)
    by: dict[str, list[str]] = {}
    for c in hc:
        by.setdefault(out["codes"][c]["theme"] or "기타", []).append(c)
    for theme, cs in by.items():
        if len(cs) < 2 or theme == "기타":
            continue
        cm = R[cs].corr().values
        rest = [c for c in hc if c not in cs]
        out["groups"].append({
            "theme": theme, "codes": cs, "names": [(names or {}).get(c, c) for c in cs], "n_hold": len(hc),
            "corr_in": round(float(cm[np.triu_indices(len(cs), 1)].mean()), 2),
            "corr_out": round(float(R.corr().loc[cs, rest].values.mean()), 2) if rest else None,
            "today": round(float(np.mean([out["codes"][c]["today"] for c in cs])), 2),
        })
    return out


if __name__ == "__main__":
    import json
    day = f"{pd.Timestamp.today():%Y-%m-%d}"
    print(json.dumps(compute(sys.argv[1:], day), ensure_ascii=False, indent=1))
