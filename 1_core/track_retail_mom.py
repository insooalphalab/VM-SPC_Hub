"""실전 추적 — "최근 20일 상승 상위 1/3 ∧ 개인 20일 누적 상위 1/3 사기"(VM-SPC Core 9.332 2단계 검증됨, 결과 본 뒤 고른 칸).
2026-10-15 사용자 결정: 리포트에는 넣지 않고 월말마다 목록을 기록 · 다음 20거래일 성과를 쌓아 3 – 6개월 뒤 반영 여부를 정한다.

  python track_retail_mom.py --date 2026-09-30   # 그 월말 신호 목록 기록(이미 있으면 덮어씀)
  python track_retail_mom.py                     # 결과만 채우기 + 누적 요약 출력
정의(9.332): ROC 20 = 종가 t ÷ t−20 − 1, 개인 20일 누적 ÷ ADV = 개인 순매수 20일 합 ÷ 직전 20일 평균 거래대금.
  둘 다 그날 값이 있는 종목 안 순위 상위 1/3. 성과 = D+1 시가 → 20거래일 뒤 종가, 같은 기간 순위를 매긴 전 종목 평균 대비(비용 전).
자료(읽기만): VM-SPC_Core data/_scenario(후보 화면 일봉, hub_pm이 매일 갱신 · 검증 종목 중 상장 보통주) ·
  data/_investor_detail(월말 hub_month.ps1이 --validation으로 갱신) · data/_program value(거래대금, 없으면 종가 × 거래량).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

CORE = Path(__file__).resolve().parent.parent.parent / "VM-SPC_Core" / "data"
BARS, INV, PROG = CORE / "_scenario", CORE / "_investor_detail", CORE / "_program"
OUT = Path(__file__).resolve().parent / "results" / "track_retail_mom.json"
KST = timezone(timedelta(hours=9))
WIN, HOLD, TOP = 20, 20, 2 / 3
MIN_N = 300            # 그날 두 값이 다 있는 종목이 이보다 적으면 기록하지 않음(수집 실패 의심)


def _bars(code: str) -> pd.DataFrame | None:
    f = BARS / f"{code}.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f, dtype={"date": str}).drop_duplicates("date").set_index("date").sort_index()
    p = PROG / f"{code}.csv"
    if p.exists():
        v = pd.read_csv(p, usecols=["date", "value"], dtype={"date": str}).drop_duplicates("date").set_index("date")["value"]
        d["tv"] = v.reindex(d.index)
    else:
        d["tv"] = float("nan")
    d["tv"] = d["tv"].where(d["tv"] > 0, d["close"] * d["volume"])
    return d


def signal(day: str) -> dict:
    ymd = day.replace("-", "")
    rows = []
    for f in BARS.glob("*.csv"):
        c = f.stem
        b = _bars(c)
        if b is None or ymd not in b.index:
            continue
        i = b.index.get_loc(ymd)
        if i < WIN:
            continue
        roc = b["close"].iloc[i] / b["close"].iloc[i - WIN] - 1
        adv = b["tv"].iloc[i - WIN:i].mean()
        fi = INV / f"{c}.csv"
        if not fi.exists() or not adv > 0:
            continue
        inv = pd.read_csv(fi, usecols=["date", "개인"], dtype={"date": str}).drop_duplicates("date").set_index("date").sort_index()["개인"]
        inv = inv[inv.index <= ymd]
        if len(inv) < WIN or inv.index[-1] != ymd:
            continue
        rows.append({"code": c, "roc20": roc, "ind20": inv.tail(WIN).sum() * 1e6 / adv})   # 개인은 백만 원
    df = pd.DataFrame(rows)
    if len(df) < MIN_N:
        raise SystemExit(f"[track] {day}: 두 값이 다 있는 종목 {len(df)}개(< {MIN_N}) — 투자자별 수집을 먼저 확인")
    df["r_roc"], df["r_ind"] = df.roc20.rank(pct=True), df.ind20.rank(pct=True)
    pick = df[(df.r_roc > TOP) & (df.r_ind > TOP)].sort_values("ind20", ascending=False)
    names = json.loads((BARS / "names.json").read_text(encoding="utf-8")) if (BARS / "names.json").exists() else {}
    return {"signal_date": day, "made_at": datetime.now(KST).isoformat(timespec="seconds"), "universe": df.code.tolist(),
            "n_universe": len(df),
            "picks": [{"code": r.code, "name": names.get(r.code, ""), "roc20": round(r.roc20, 4), "ind20": round(r.ind20, 4)}
                      for r in pick.itertuples()],
            "result": None}


def _ret(code: str, ymd: str) -> float | None:
    """신호일 다음 거래일 시가 → 그로부터 HOLD거래일째 종가(9.325 방식: 진입일 포함 20거래일)."""
    b = _bars(code)
    if b is None:
        return None
    after = b.index[b.index > ymd]
    if len(after) < HOLD:
        return None
    o, c = b.at[after[0], "open"], b.at[after[HOLD - 1], "close"]
    return float(c / o - 1) if o > 0 else None


def evaluate(rec: dict) -> dict | None:
    ymd = rec["signal_date"].replace("-", "")
    uni = {c: _ret(c, ymd) for c in rec["universe"]}
    if sum(v is not None for v in uni.values()) < len(uni) * 0.9:      # 대부분 20거래일이 안 찼으면 아직
        return None
    u = [v for v in uni.values() if v is not None]
    p = [uni.get(x["code"]) for x in rec["picks"]]
    p = [v for v in p if v is not None]
    if not p:
        return None
    mu, mp = sum(u) / len(u), sum(p) / len(p)
    return {"picks_ret": round(mp * 100, 2), "universe_ret": round(mu * 100, 2), "excess": round((mp - mu) * 100, 2),
            "n_picks": len(p), "filled_at": datetime.now(KST).isoformat(timespec="seconds")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="월말 신호일 YYYY-MM-DD — 주면 그날 목록을 기록")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    recs = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    if a.date:
        recs = [r for r in recs if r["signal_date"] != a.date] + [signal(a.date)]
        recs.sort(key=lambda r: r["signal_date"])
        print(f"[track] {a.date} 기록: {len(recs[-1]['picks'])}종목 / {recs[-1]['n_universe']}종목 중 — "
              + " · ".join(x["name"] or x["code"] for x in recs[-1]["picks"][:15]))
    for r in recs:
        if r["result"] is None:
            r["result"] = evaluate(r)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
    done = [r for r in recs if r["result"]]
    for r in recs:
        s = r["result"]
        print(f"  {r['signal_date']} {len(r['picks'])}종목 → " + (f"초과 {s['excess']:+.2f}%p (목록 {s['picks_ret']:+.2f}% · 전체 {s['universe_ret']:+.2f}%)" if s else "결과 대기"))
    if done:
        ex = [r["result"]["excess"] for r in done]
        print(f"[track] 누적 {len(done)}달: 평균 초과 {sum(ex) / len(ex):+.2f}%p · 이긴 달 {sum(e > 0 for e in ex)}/{len(ex)} "
              f"(백테스트 월 +0.86 / 최근 +1.16%p · 이긴 달 57%, 9.332)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
