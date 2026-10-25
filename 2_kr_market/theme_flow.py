"""테마 돈의 흐름(2026-10-15 사용자 승인) — theme_map.json 상위군으로 거래대금 가중 등락 · 거래대금 몫 · 확산도 · 지속 · 시총 층.

  python theme_flow.py [YYYY-MM-DD]   → 확인용 출력. 평소에는 export_exchange.py가 themes.json "flow"로 실음

- 그룹 등락 = 직전 20일 평균 거래대금 가중(작은 종목 하나의 급등이 그룹을 끌어올리지 않게). 동일가중 평균도 같이.
- 거래대금 몫 = 그룹 거래대금 ÷ 테마 종목 전체 거래대금. "평소" = 직전 20거래일 몫 평균 → 오늘 몫 ÷ 평소(1보다 크면 돈이 더 몰림).
- 확산도 = 오른 종목 비율 · 상위 5번째 ÷ 1번째 등락(1에 가까울수록 같이 감, 0 근처면 대장만).
- 지속 = 거래대금 가중 등락 상위 TOP_N 안에 든 연속 일수. 히트맵용으로 최근 HEAT_DAYS일 그룹별 등락 · 상위 여부.
- 시총 층: 대형 ≥ 10조 · 중형 1 – 10조 · 소형 < 1조(종가 × 상장주식수, theme_extra.py가 월 1회 받음). 층별 가중 등락 · 거래대금 몫.
방향 판단 없음 — 지금 상태 지도(검증 전 · 참고). 테마 흐름이 다음 방향을 맞히는지는 9.277 – 9.305에서 쓸 만하지 않았다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from theme_extra import price_file, shares

ROOT = Path(__file__).resolve().parent
MAP = ROOT / "theme_map.json"
TOP_N, HEAT_DAYS, W_DAYS, LOOK = 5, 20, 20, 70
TIERS = (("대형", 10e12), ("중형", 1e12), ("소형", 0))


def _tier(cap: float | None) -> str | None:
    if cap is None or np.isnan(cap):
        return None
    return next(n for n, lo in TIERS if cap >= lo)


def compute(day: str) -> dict:
    if not MAP.exists():
        return {"note": "theme_map.json 없음"}
    m = json.loads(MAP.read_text(encoding="utf-8"))
    st = {c: v for c, v in m["stocks"].items() if v["group"] != "기타"}
    cl, tv = {}, {}
    for c in st:
        f = price_file(c)
        if f is None:
            continue
        d = pd.read_csv(f, encoding="utf-8-sig", usecols=["date", "close", "volume"]).tail(LOOK + 30)
        d.index = pd.to_datetime(d["date"].astype(str))
        cl[c], tv[c] = d["close"], d["close"] * d["volume"]
    C = pd.DataFrame(cl).sort_index()
    T = pd.DataFrame(tv).sort_index()
    t0 = pd.Timestamp(day)
    C, T = C[C.index <= t0], T[T.index <= t0]
    if C.empty or C.index[-1] != t0:
        return {"date": day, "note": f"테마 종목 일봉에 {day} 봉 없음"}
    R = C.pct_change(fill_method=None) * 100
    have = R.iloc[-1].notna()
    W = T.shift(1).rolling(W_DAYS, min_periods=10).mean()          # 직전 20일 평균 거래대금(오늘 제외)
    grp = pd.Series({c: st[c]["group"] for c in C.columns})
    groups = list(m["groups"])

    def gret(i: int, g: str) -> float | None:
        cs = [c for c in grp[grp == g].index if not np.isnan(R.iloc[i][c]) and not np.isnan(W.iloc[i][c])]
        if not cs:
            return None
        w = W.iloc[i][cs]
        return float((R.iloc[i][cs] * w).sum() / w.sum())

    n = len(C)
    hist = {g: [] for g in groups}                                  # (날짜, 가중 등락, 상위 여부)
    for i in range(max(1, n - HEAT_DAYS - 15), n):
        v = {g: gret(i, g) for g in groups}
        top = {g for g, _ in sorted(((g, x) for g, x in v.items() if x is not None), key=lambda z: -z[1])[:TOP_N]}
        for g in groups:
            hist[g].append((f"{C.index[i]:%Y-%m-%d}", None if v[g] is None else round(v[g], 2), g in top))
    tot = T.iloc[-1][have].sum()
    share_hist = pd.DataFrame({g: T[grp[grp == g].index].sum(axis=1) for g in groups}).div(T.sum(axis=1), axis=0)
    sh = shares()
    cap = pd.Series({c: C[c].iloc[-1] * sh[c] for c in C.columns if c in sh})
    tier = cap.apply(_tier)
    out = []
    for g in groups:
        cs = [c for c in grp[grp == g].index if have[c]]
        if not cs:
            continue
        r = R.iloc[-1][cs]
        streak = 0
        for _, _, on in reversed(hist[g]):
            if not on:
                break
            streak += 1
        srt = r.sort_values(ascending=False)
        top1, top5 = srt.iloc[0], (srt.iloc[4] if len(srt) >= 5 else np.nan)
        w5 = W.iloc[-6][cs] if n > 6 else None
        r5 = (C[cs].iloc[-1] / C[cs].iloc[-6] - 1) * 100 if n > 6 else None
        sh_now, sh_usual = float(share_hist[g].iloc[-1]), float(share_hist[g].iloc[-W_DAYS - 1:-1].mean())
        tiers = {}
        for tn, _ in TIERS:
            tc = [c for c in cs if tier.get(c) == tn]
            if tc:
                tiers[tn] = {"n": len(tc), "ret": round(float((R.iloc[-1][tc] * W.iloc[-1][tc]).sum() / W.iloc[-1][tc].sum()), 2)}
        out.append({
            "theme": g, "tags": m["groups"][g]["tags"], "n": len(cs),
            "ret": round(gret(n - 1, g), 2), "avg": round(float(r.mean()), 2),
            "r5": round(float((r5[cs] * w5[cs]).sum() / w5[cs].sum()), 2) if r5 is not None else None,
            "up": int((r > 0).sum()), "spread": round(max(float(top5 / top1), 0.0), 2) if top1 > 0 and not np.isnan(top5) else None,
            "share": round(sh_now * 100, 1), "share_x": round(sh_now / sh_usual, 2) if sh_usual > 0 else None,
            "streak": streak, "tiers": tiers,
            "top": [{"code": c, "name": st[c]["name"], "pct": round(float(x), 2), "tier": tier.get(c)} for c, x in srt.head(3).items()],
            "heat": hist[g][-HEAT_DAYS:],
        })
    out.sort(key=lambda x: -x["ret"])
    # 시장 전체 층 — 어느 덩치가 움직였나
    tsum = {}
    for tn, _ in TIERS:
        tc = [c for c in C.columns if tier.get(c) == tn and have[c]]
        if tc:
            w = W.iloc[-1][tc]
            tsum[tn] = {"n": len(tc), "ret": round(float((R.iloc[-1][tc] * w).sum() / w.sum()), 2),
                        "share": round(float(T.iloc[-1][tc].sum() / tot * 100), 1),
                        "share_usual": round(float((T[tc].sum(axis=1) / T[have.index[have]].sum(axis=1)).iloc[-W_DAYS - 1:-1].mean() * 100), 1)}
    return {"date": day, "map_asof": m["asof"], "top_n": TOP_N, "groups": out, "tiers": tsum,
            "n_stocks": int(have.sum()), "tv_total_eok": round(float(tot / 1e8)),
            "note": f"상위군 {len(out)} · 종목 {int(have.sum())} · 거래대금 가중(직전 20일) · 소속표 {m['asof']}"}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    d = sys.argv[1] if len(sys.argv) > 1 else f"{pd.Timestamp.today():%Y-%m-%d}"
    t = compute(d)
    print(t["note"])
    print("층:", t.get("tiers"))
    for g in t.get("groups", []):
        print(f"{g['theme']:12s} 가중 {g['ret']:+6.2f}% 평균 {g['avg']:+6.2f}% 5일 {g['r5']:+6.2f}% · 몫 {g['share']:4.1f}% (평소 {g['share_x']}배) · "
              f"상승 {g['up']}/{g['n']} · 확산 {g['spread']} · 지속 {g['streak']} · 층 {g['tiers']} · " + " ".join(f"{x['name']} {x['pct']:+.1f}" for x in g["top"]))
