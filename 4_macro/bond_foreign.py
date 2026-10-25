"""외국인 원화 채권 순매수(장외, 일별) — 금융투자협회 FreeSIS "투자자별거래현황 장외"(STATBND0100000270, 단위 억 원).
2026-10-23 사용자("받을 수 있는 데이터가 있으면 받아서 검증"). 외국인 시선 칸의 "원화 강세가 채권 자금 때문인가"를 월간 국제수지 대신 일별로.

  python bond_foreign.py           → data/bond_foreign.csv (마지막 날 − 10일부터 다시 받아 합침)
  python bond_foreign.py --full    → 2010-01 – 전부(하루 한 번 조회, 약 4천 번 · 몇 분)

- 화면이 쓰는 JSON 주소(인증 없음, 화면을 한 번 열어 세션 쿠키를 받아야 함). 하루씩 조회(기간 조회는 합계만 줘서).
- 칸: date · 외국인 순매수 국채 · 통안증권 · 합계(억 원), 외국인 총거래 합계. 다음 영업일 공표.
- 거래일은 macro_ext.csv의 s_kospi_mcap 날짜(FreeSIS 시장 표)를 쓴다. 방향 판단 없음.
"""
from __future__ import annotations

import os
import sys
import time

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "bond_foreign.csv")
EXT = os.path.join(HERE, "data", "macro_ext.csv")
BASE = "https://freesis.kofia.or.kr"
PAGE = BASE + "/stat/FreeSIS.do?parentDivId=MSIS20000000000000&serviceId=STATBND0100000270"
FRGN = "TMPV11"          # 열 순서: 전체 · 증권사간 · 은행 · 자산운용(공모) · 자산운용(사모) · 보험 · 종금/상호 · 기금공제 · 외국인 · 국가/지자체 · 기타법인 · 개인
START = "2010-01-01"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Referer": PAGE})
    s.get(PAGE, timeout=30)
    return s


def _day(s: requests.Session, d: str) -> dict | None:
    body = {"dmSearch": {"tmpV40": "100000000", "tmpV41": "1", "tmpV1": "D", "tmpV45": d, "tmpV46": d, "tmpV76": "00",
                         "tmpV92": "00", "tmpV77": "00", "tmpV93": "00", "tmpV67": "1", "OBJ_NM": "STATBND0100000270BO"}}
    rows = s.post(BASE + "/meta/getMetaDataList.do", json=body, timeout=30).json().get("ds1") or []
    pick = {(r["TMPV1"], r["TMPV2"]): r.get(FRGN) for r in rows}
    if not pick:
        return None
    f = lambda k: float(pick.get(k) or 0)
    return {"f_net_ktb": f(("순매수", "국채")), "f_net_msb": f(("순매수", "통안증권")), "f_net_all": f(("순매수", "합계")),
            "f_total_all": f(("총거래", "합계"))}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    full = "--full" in sys.argv or not os.path.exists(OUT)
    old = None if full else pd.read_csv(OUT, index_col=0)
    days = pd.read_csv(EXT, index_col=0, usecols=["date", "s_kospi_mcap"], parse_dates=True)["s_kospi_mcap"].dropna().index
    start = pd.Timestamp(START) if full or old is None or old.empty else pd.Timestamp(old.index.max()) - pd.Timedelta(days=10)
    want = [d.strftime("%Y%m%d") for d in days if d >= start]
    try:
        s = _session()
        rows = {}
        for i, d in enumerate(want):
            r = _day(s, d)
            if r and r["f_total_all"] > 0:
                rows[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = r
            if i % 500 == 499:
                print(f"  {d} …", flush=True)
            time.sleep(0.05)
    except Exception as e:  # noqa: BLE001 — 실패해도 옛 값은 남김
        print(f"[bond_foreign] 실패: {type(e).__name__}: {e}")
        return 0
    new = pd.DataFrame.from_dict(rows, orient="index")
    df = new if old is None else new.combine_first(old)
    df.index.name = "date"
    df.sort_index().to_csv(OUT, encoding="utf-8")
    print(f"[bond_foreign] {len(df)}일 · {df.index.min()} – {df.index.max()} · 마지막 외국인 순매수 합계 {df['f_net_all'].iloc[-1]:+,.0f}억")
    return 0


if __name__ == "__main__":
    sys.exit(main())
