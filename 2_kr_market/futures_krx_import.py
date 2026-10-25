"""KRX [15007] 투자자별 거래실적(코스피200 선물 · 일별추이 · 거래대금 · 순매수 · 백만원) CSV를 data/futures_investor.csv에 합친다.
2026-10-21 사용자가 KRX에서 2년씩 내려받은 과거분(KIS는 그날 값만 줌 — futures_investor.py).

  python futures_krx_import.py 파일1.csv 파일2.csv ...

- KRX 파일: EUC-KR, 열 = 일자 · 기관 합계 · 기타법인 · 개인 · 외국인 합계 · 전체 → orgn_amt · etc_corp_amt · prsn_amt · frgn_amt(백만 원), source = krx.
- 같은 날짜가 이미 있으면 KIS 기록(source = kis, 마감 뒤 값)을 남기고 KRX 줄은 넣지 않는다. 오늘 날짜 줄은 장중일 수 있어 넣지 않는다.
- 네 주체 합이 0(±2)이 아닌 줄은 넣지 않고 알린다.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "futures_investor.csv"
KST = timezone(timedelta(hours=9))
COLS = {"기관 합계": "orgn_amt", "기타법인": "etc_corp_amt", "개인": "prsn_amt", "외국인 합계": "frgn_amt"}


def read_krx(path: str) -> pd.DataFrame:
    d = pd.read_csv(path, encoding="euc-kr")
    miss = [c for c in ["일자", *COLS] if c not in d.columns]
    if miss:
        raise ValueError(f"{path}: 열 없음 {miss}")
    d["date"] = pd.to_datetime(d["일자"]).dt.strftime("%Y-%m-%d")
    d = d.rename(columns=COLS).set_index("date")[list(COLS.values())].astype(float)
    bad = d.sum(axis=1).abs() > 2
    if bad.any():
        print(f"  {Path(path).name}: 합이 0이 아닌 줄 {bad.sum()}개 뺌 — {list(d.index[bad])[:5]}")
    return d[~bad]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    today = datetime.now(KST).strftime("%Y-%m-%d")
    new = pd.concat([read_krx(p) for p in sys.argv[1:]])
    new = new[~new.index.duplicated(keep="first")]
    new = new[new.index != today]
    new["source"] = "krx"
    old = pd.read_csv(OUT, index_col=0) if OUT.exists() else pd.DataFrame()
    if not old.empty and "source" not in old.columns:
        old["source"] = "kis"
    keep_old = old if old.empty else old[old["source"] == "kis"]
    new = new[~new.index.isin(keep_old.index)]
    rest = old if old.empty else old[(old["source"] != "kis") & ~old.index.isin(new.index)]
    df = pd.concat([keep_old, rest, new]).sort_index()
    df.index.name = "date"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, encoding="utf-8")
    yrs = pd.Series(pd.to_datetime(df.index).year).value_counts().sort_index()
    print(f"[futures_krx_import] {len(df)}일 · {df.index.min()} – {df.index.max()} · 해마다 " + " · ".join(f"{y}:{n}" for y, n in yrs.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
