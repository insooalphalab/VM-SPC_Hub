"""코스피200 선물 투자자별 순매수(그날 값) — KIS 시장별 투자자매매동향(시세, FHPTJ04030000, 시장 K2I · 업종 F001).
2026-10-21 사용자 가설("선물 · 현물의 외인 · 기관 · 개인 흐름이 크로스하거나 같이 갈 때")용. KIS는 이 TR로 **그날 값만** 주고
과거 일별은 주지 않아 오늘부터 하루 한 줄씩 쌓는다(과거분은 KRX 등 다른 원천 — CLAUDE.md "할 일").

  python futures_investor.py           → data/futures_investor.csv (date · 투자자별 순매수 계약 수 *_qty · 대금 *_amt(백만 원), 누적)
  python futures_investor.py --force   장 마감 전 · 휴장일에도 기록(시험용)

- hub_pm 16:00 단계(선물 정규장 15:45 마감 뒤)에서 실행. 15:50 전이면 장중 값이라 기록하지 않는다. 같은 날 다시 돌면 덮어씀.
- 국내 휴장일(exchange/2_kr_market/kr_calendar.json)이거나 값이 모두 0이면 기록하지 않는다. 실패해도 0으로 끝난다.
- 방향 판단 없음. 검증은 VM-core(현물 · 프로그램 차익 대리 검증 요청 2026-10-21, 선물 자료가 쌓이거나 과거분을 구하면 같은 정의로 재검증).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "core"))
OUT = ROOT / "data" / "futures_investor.csv"
CAL = ROOT.parent / "exchange" / "2_kr_market" / "kr_calendar.json"
KST = timezone(timedelta(hours=9))
PATH, TR = "/uapi/domestic-stock/v1/quotations/inquire-investor-time-by-market", "FHPTJ04030000"
WHO = {"frgn": "외국인", "prsn": "개인", "orgn": "기관계", "scrt": "금융투자", "ivtr": "투신", "bank": "은행",
       "insu": "보험", "mrbn": "종금", "fund": "기금", "etc_corp": "기타법인"}


def is_open(day: str) -> bool | None:
    try:
        return json.loads(CAL.read_text(encoding="utf-8")).get("days", {}).get(day)
    except Exception:  # noqa: BLE001
        return None


def fetch() -> dict:
    from kis_client import RateLimitedCaller
    out = RateLimitedCaller(min_interval=1.0).get(PATH, TR, {"FID_INPUT_ISCD": "K2I", "FID_INPUT_ISCD_2": "F001"}).get("output") or []
    r = out[0] if isinstance(out, list) and out else {}
    row = {}
    for k in WHO:
        q, a = r.get(f"{k}_ntby_qty"), r.get(f"{k}_ntby_tr_pbmn")
        row[f"{k}_qty"] = float(q) if q not in (None, "") else None
        row[f"{k}_amt"] = float(a) if a not in (None, "") else None
    return row


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    now = datetime.now(KST)
    day = now.strftime("%Y-%m-%d")
    force = "--force" in sys.argv
    if not force and (now.hour, now.minute) < (15, 50):
        print("[futures_investor] 15:50 전 — 장중 값이라 기록 안 함")
        return 0
    if not force and is_open(day) is False:
        print(f"[futures_investor] {day} 휴장 — 기록 안 함")
        return 0
    try:
        row = fetch()
    except Exception as e:  # noqa: BLE001
        print(f"[futures_investor] KIS 실패: {type(e).__name__}: {e}")
        return 0
    if not any(v for v in row.values()):
        print("[futures_investor] 값이 모두 0 — 기록 안 함")
        return 0
    old = pd.read_csv(OUT, index_col=0) if OUT.exists() else pd.DataFrame()
    new = pd.DataFrame([row], index=pd.Index([day], name="date"))
    df = pd.concat([old[old.index != day], new]).sort_index()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, encoding="utf-8")
    print(f"[futures_investor] {day} 기록 · {len(df)}일 누적 — 순매수(백만 원) "
          + " · ".join(f"{WHO[k]} {row[k + '_amt']:+,.0f}" for k in ("frgn", "prsn", "orgn") if row[k + "_amt"] is not None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
