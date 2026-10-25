"""VKOSPI 일별 — KIS 국내업종 일자별지수(FHPUP02120000, 업종 코드 0503 = VKOSPI). 2026-10-15 사용자: "브이코스피도 받아서 검증".

  python vkospi.py            → ../exchange/2_kr_market/vkospi.csv (date · open · high · low · close, 누적)
  python vkospi.py --full     처음부터(한 번에 100거래일씩 과거로, 자료가 끝날 때까지)

- 평소엔 마지막 저장일 이후만 받는다(hub_pm 16:00 — 장 마감 뒤). 4_macro 유동성 · 신용 모니터가 이 파일을 읽는다(KIS는 2_kr만 부름).
- KIS 코드는 VM-SPC_Core core\\ 4개 파일 복사본(수정 없음), 키는 이 폴더 .streamlit\\secrets.toml, 토큰 캐시 state\\.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "core"))
OUT = ROOT.parent / "exchange" / "2_kr_market" / "vkospi.csv"
KST = timezone(timedelta(hours=9))
PATH, TR, CODE = "/uapi/domestic-stock/v1/quotations/inquire-index-daily-price", "FHPUP02120000", "0503"
MAX_CALLS = 80


def fetch(stop_after: str | None) -> pd.DataFrame:
    from kis_client import RateLimitedCaller
    c = RateLimitedCaller(min_interval=1.0)
    cur, rows = datetime.now(KST).strftime("%Y%m%d"), {}
    for _ in range(MAX_CALLS):
        b = c.get(PATH, TR, {"FID_PERIOD_DIV_CODE": "D", "FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": CODE, "FID_INPUT_DATE_1": cur})
        out = b.get("output2") or []
        got = [x for x in out if x.get("stck_bsop_date") and x.get("bstp_nmix_prpr") not in (None, "", "0", "0.00")]
        if not got:
            break
        for x in got:
            rows[x["stck_bsop_date"]] = {"open": float(x["bstp_nmix_oprc"]), "high": float(x["bstp_nmix_hgpr"]),
                                         "low": float(x["bstp_nmix_lwpr"]), "close": float(x["bstp_nmix_prpr"])}
        oldest = min(x["stck_bsop_date"] for x in got)
        if stop_after and oldest <= stop_after:
            break
        nxt = (datetime.strptime(oldest, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
        if nxt >= cur:
            break
        cur = nxt
    df = pd.DataFrame.from_dict(rows, orient="index")
    if df.empty:
        return df
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df.index.name = "date"
    return df.sort_index()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    full = "--full" in sys.argv or not OUT.exists()
    old = None if full else pd.read_csv(OUT, index_col=0, parse_dates=True)
    stop = None if old is None or old.empty else old.index.max().strftime("%Y%m%d")
    try:
        new = fetch(stop)
    except Exception as e:  # noqa: BLE001 — 실패해도 리포트는 돈다(모니터가 이전 값 · 대체값으로)
        print(f"[vkospi] KIS 실패: {type(e).__name__}: {e}")
        return 0
    df = new if old is None else new.combine_first(old)          # 새로 받은 값 우선(장중 값 → 마감 값 덮어씀)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.sort_index().to_csv(OUT, encoding="utf-8")
    print(f"[vkospi] {len(df)}일 · {df.index.min().date()} – {df.index.max().date()} · 마지막 {df['close'].iloc[-1]:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
