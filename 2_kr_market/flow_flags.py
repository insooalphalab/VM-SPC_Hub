"""보유 · 관심 종목 수급 표시(2026-10-14, VM-SPC_Core 9.322 · 9.325 · 9.326 정의 그대로) — 데이터만, 문구는 1_core.

  python flow_flags.py 005930 000660 …   → 종목별 값 출력(확인용)

- pension_streak: 연기금 연속 순매수 일수(마지막 날부터 거꾸로). 5 이상이면 경고 조건(9.322 · 9.326).
- inst_days20 · inst_sum20: 기관합계 최근 20일 중 순매수 일수 · 20일 합(백만 원). 15일 이상 ∧ 합 > 0이면 경고 조건(9.325 ③).
- short_pct20 · short_rank: 공매도 거래대금 비중 20일 평균(%)과 그날 전 종목 중 순위(0 – 1, 1 = 가장 높음). 0.9 이상이면 참고(9.325 ① 약함).
- overhang · overhang_rank: 매물대 비중(현재가 위 0 – 20%에 쌓인 지난 250일 거래량 비중)과 바스켓 종목 안 순위. 0.9 초과면 참고(9.328 ⑮ · 9.329 약함).
자료: VM-SPC_Core data/_investor_detail(보유 · 관심은 hub_pm의 render_risk.py가 매일 갱신) · data/_short(주기 갱신, 기준일을 같이 냄). 읽기만.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

CORE_DATA = Path(__file__).resolve().parent.parent.parent / "VM-SPC_Core" / "data"
INV, SHORT = CORE_DATA / "_investor_detail", CORE_DATA / "_short"
PENSION_MIN, INST_DAYS, INST_WIN, SHORT_WIN, SHORT_TOP = 5, 15, 20, 20, 0.9
SHORT_MIN_N = 100          # 그날 공매도 비중이 있는 종목이 이보다 적으면(금지 기간 등) 순위를 내지 않음
OVH_WIN, OVH_TOP, OVH_MIN_N = 250, 0.9, 100   # 매물대: 250거래일 · 상위 10% · 바스켓 안 값 있는 종목이 100 미만이면 순위 안 냄


def _ymd(s) -> str:
    s = str(s)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def investor(code: str) -> dict | None:
    f = INV / f"{code}.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f, dtype={"date": str}, encoding="utf-8").sort_values("date").tail(60)
    if d.empty or "연기금" not in d or "기관합계" not in d:
        return None
    pen = d["연기금"].tolist()
    streak = 0
    for v in reversed(pen):
        if v > 0:
            streak += 1
        else:
            break
    inst = d["기관합계"].tail(INST_WIN)
    return {"flow_date": _ymd(d["date"].iloc[-1]), "pension_streak": streak,
            "inst_days20": int((inst > 0).sum()), "inst_sum20": float(inst.sum()), "inst_n": len(inst),
            "pension_flag": streak >= PENSION_MIN,
            "inst_flag": bool(len(inst) == INST_WIN and (inst > 0).sum() >= INST_DAYS and inst.sum() > 0)}


def short_table() -> tuple[str | None, pd.Series]:
    """전 종목 공매도 거래대금 비중 20일 평균 — 가장 많은 종목이 가진 마지막 날짜 기준. (기준일, 종목 → 값)"""
    rows = {}
    for f in SHORT.glob("*.csv"):
        try:
            d = pd.read_csv(f, usecols=["date", "ssts_amt_pct"], dtype={"date": str}).sort_values("date").tail(SHORT_WIN + 5)
        except (ValueError, OSError):
            continue
        if len(d):
            rows[f.stem] = d
    if not rows:
        return None, pd.Series(dtype=float)
    last = pd.Series({k: v["date"].iloc[-1] for k, v in rows.items()}).value_counts().idxmax()
    vals = {}
    for k, d in rows.items():
        d = d[d["date"] <= last].tail(SHORT_WIN)
        if len(d) == SHORT_WIN and d["date"].iloc[-1] == last:
            vals[k] = d["ssts_amt_pct"].mean()
    s = pd.Series(vals, dtype=float)
    if (s > 0).sum() < SHORT_MIN_N:
        return _ymd(last), pd.Series(dtype=float)
    return _ymd(last), s


def overhang(f: Path, day: str) -> float | None:
    """매물대 비중(9.329 정의) — 직전 250거래일(당일 제외, 거래량 0 · 가격 0 이하 제외) 거래량 중 종가가 (C, 1.2C]였던 날의 비중.
    마지막 봉이 day가 아니거나 250일이 안 차면 None."""
    d = pd.read_csv(f, usecols=["date", "close", "volume"], dtype={"date": str}).sort_values("date").drop_duplicates("date")
    if d.empty or d["date"].iloc[-1] != day.replace("-", ""):
        return None
    C = d["close"].iloc[-1]
    p = d.iloc[:-1]
    p = p[(p["volume"] > 0) & (p["close"] > 0)].tail(OVH_WIN)
    if len(p) < OVH_WIN or C <= 0:
        return None
    tot = p["volume"].sum()
    return float(p.loc[(p["close"] > C) & (p["close"] <= 1.2 * C), "volume"].sum() / tot) if tot > 0 else None


def overhang_table(day: str) -> pd.Series:
    """테마 묶음(바스켓) 종목 — hub_pm이 매일 받는 일봉 — 의 매물대 비중. 전 종목 _long_history는 매일 갱신되지 않아 바스켓 안 순위로 씀(9.329 보조: 같은 방향)."""
    import json
    wl = json.loads((CORE_DATA.parent / "basket_watchlist.json").read_text(encoding="utf-8"))
    baskets = {v["basket_name"] for v in wl["themes"].values()}
    files = {}
    for b in sorted(baskets):
        for f in (CORE_DATA / b).glob("*.csv"):
            files.setdefault(f.stem, f)
    vals = {}
    for c, f in files.items():
        try:
            v = overhang(f, day)
        except (ValueError, OSError, KeyError):
            v = None
        if v is not None:
            vals[c] = v
    return pd.Series(vals, dtype=float)


def compute(codes: list[str], day: str | None = None) -> dict:
    """{code: {...}} + 공통 기준일. 자료가 없는 종목은 값 없이 note만. day가 있으면 매물대도 계산."""
    sdate, s = short_table()
    rank = s.rank(pct=True) if len(s) else s
    o = overhang_table(day) if day else pd.Series(dtype=float)
    orank = o.rank(pct=True) if len(o) >= OVH_MIN_N else pd.Series(dtype=float)
    out = {}
    for c in codes:
        r = investor(c) or {"note": "투자자별 자료 없음"}
        if c in s.index:
            r.update({"short_pct20": round(float(s[c]), 2), "short_rank": round(float(rank[c]), 3),
                      "short_flag": bool(rank[c] >= SHORT_TOP)})
        if c in orank.index:
            r.update({"overhang": round(float(o[c]), 3), "overhang_rank": round(float(orank[c]), 3),
                      "overhang_flag": bool(orank[c] > OVH_TOP)})
        out[c] = r
    return {"short_date": sdate, "short_n": int(len(s)), "overhang_n": int(len(orank)), "codes": out}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import json
    a = sys.argv[1:]
    day = a.pop(0) if a and "-" in a[0] else None      # 첫 인자가 YYYY-MM-DD면 매물대까지
    print(json.dumps(compute(a or ["005930"], day), ensure_ascii=False, indent=1))
