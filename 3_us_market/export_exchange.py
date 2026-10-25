"""VM-SPC_Global 결과(읽기만)를 exchange/3_us_market/{미국 거래일}/summary_am.json · .md 로 내보낸다.

  $env:V2_RESULTS_DIR = "C:\\Users\\USER\\Desktop\\New toy\\VM-SPC_Global\\results"
  $env:V2_DATA_DIR    = "C:\\Users\\USER\\Desktop\\New toy\\VM-SPC_Global\\data"
  python export_exchange.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vm_spc"))
from build_index import collect_rows  # noqa: E402  (core/ 경로도 여기서 잡힘)
from v2_config import KST, load_baskets  # noqa: E402
from v2_datastore import load_bars  # noqa: E402

BASKETS = Path(r"C:\Users\USER\Desktop\New toy\VM-SPC_Global\basket_watchlist.json")
OUT = ROOT.parent / "exchange" / "3_us_market"
# us_close 에 싣는 것 — 지수는 Global에 지수 원자료가 없어 추종 ETF로 대신한다(다우는 없음)
INDEX = {"SPY": "S&P500(SPY)", "QQQ": "나스닥100(QQQ)", "SOXX": "반도체(SOXX)"}
BIGCAPS = ("NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "AVGO", "TSLA")


def last_move(basket: str, code: str):
    """(마지막 거래일 'YYYY-MM-DD', 전일 대비 등락률 %) — 일봉이 없거나 2개 미만이면 None."""
    bars = load_bars(basket, code)
    if bars is None or len(bars) < 2:
        return None
    return bars.index[-1].strftime("%Y-%m-%d"), round((bars["close"].iloc[-1] / bars["close"].iloc[-2] - 1) * 100, 2)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = collect_rows(None, load_baskets(BASKETS))
    dates = [r["etf_pred"]["date"] for r in rows if r["etf_pred"]]
    if not dates:
        print("Global 결과에 ETF 예측이 없습니다 — VM-SPC_Global 07:00 실행을 확인하세요.")
        return 1
    us_date, problems = max(dates), []

    forecast = []
    for r in rows:
        ep, mv = r["etf_pred"], last_move(r["basket"], r["etf_code"])
        if ep is None or ep["date"] != us_date:
            problems.append(f"{r['etf_code']} 예측 기준일 {ep and ep['date']}")
            continue
        forecast.append({
            "basket": r["basket"], "etf": r["etf_code"], "name": r["etf_name"],
            "pred": "상승" if ep["pred_up"] else "하락",
            "hit_rate": None if ep["hit_rate"] is None else round(ep["hit_rate"], 3),
            "usual": None if ep["usual"] is None else round(ep["usual"], 3),
            "last_chg_pct": mv[1] if mv and mv[0] == us_date else None,
        })

    by_etf = {r["etf_code"]: r["basket"] for r in rows}
    close = {}
    for code, label in INDEX.items():
        close[label] = last_move(by_etf[code], code) if code in by_etf else None
    for code in BIGCAPS:  # 나스닥100 바스켓 우선, 없으면 그 종목이 센서로 들어 있는 다른 바스켓
        close[code] = next(filter(None, (last_move(b, code) for b in ["us_nasdaq100", *by_etf.values()])), None)
    for k, v in list(close.items()):
        if v is None or v[0] != us_date:
            problems.append(f"{k} 일봉 기준일 {v and v[0]}")
            close[k] = None
        else:
            close[k] = v[1]

    # 섹터 흐름 — 섹터 ETF 등락 · 지속 · 큰 움직임 · 국내 연관 테마(us_themes.py, 2026-10-10)
    import us_themes
    ut = us_themes.compute(us_date)
    if not ut["sectors"]:
        problems.append(ut["note"])
    sector_txt = us_themes.line(ut)
    mover_txt = " · ".join(f"{m['code']} {m['pct']:+.1f}%" for m in ut["movers"][:8]) or "±5% 이상 없음"

    n_up = sum(f["pred"] == "상승" for f in forecast)
    n60 = sum(1 for f in forecast if f["hit_rate"] is not None and f["hit_rate"] >= 0.6)
    close_txt = " · ".join(f"{k} {v:+.2f}%" for k, v in close.items() if v is not None)
    index_txt = " · ".join(f"{k} {close[k]:+.2f}%" for k in INDEX.values() if close.get(k) is not None)
    notes = ["지수는 추종 ETF(SPY·QQQ·SOXX) 등락으로 대신함 — 다우 원천 없음",
             "night_futures: KOSPI200 야간선물 원천 없음(항목 생략)",
             "etf_forecast 적중률은 과거 같은 방향 예측일의 실제 적중 비율, 평소는 그 방향으로 움직인 날 비율 — 평소보다 높아야 의미 있음"]
    summary = {
        "role": "3_us_market", "date": us_date, "slot": "am",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "status": "partial" if problems else "ok",
        "sources": ["VM-SPC_Global results", "VM-SPC_Global data"],
        "headline": f"미국 {us_date} 마감 — {index_txt} | 강한 섹터 {us_themes.line(ut, 2).split(' | ')[0]}",
        "items": [
            {"key": "us_close", "title": "미국 마감 등락(%)", "text": close_txt, "value": close,
             "grade": "서술", "ref": "", "link": ""},
            {"key": "us_sectors", "title": "미국 섹터 흐름(섹터 ETF 등락 · 지속 · 국내 연관 테마)", "text": sector_txt,
             "value": "us_themes.json", "grade": "참고", "ref": "", "link": ""},
            {"key": "us_movers", "title": f"큰 움직임(구성 종목 ±{us_themes.BIG:.0f}% 이상)", "text": mover_txt,
             "value": ut["movers"][:15], "grade": "서술", "ref": "", "link": ""},
            {"key": "etf_forecast", "title": "미국 ETF 다음 날 방향(VM-SPC Global)",
             "text": f"{len(forecast)}개 중 상승 {n_up} · 하락 {len(forecast) - n_up}, 적중률 60% 이상 {n60}개",
             "value": forecast, "grade": "참고", "ref": "", "link": ""},
        ],
        "notes": "; ".join(notes + problems),
    }

    day = OUT / us_date
    day.mkdir(parents=True, exist_ok=True)
    (day / "summary_am.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (day / "us_themes.json").write_text(json.dumps(ut, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# 해외 시장 — 미국 {us_date} 마감 (생성 {summary['generated_at'][:16].replace('T', ' ')} KST, {summary['status']})", "",
          f"**마감 등락** {close_txt}", "",
          f"**섹터 흐름(참고)** {sector_txt}"]
    md += [f"- {s['theme']}({s['etf']}) {s['chg']:+.1f}% · 5일 {s['r5'] if s['r5'] is not None else '–'} · 지속 {s['streak']}일"
           + (f" · 국내 {s['kr']}" if s["kr"] else "") + " · " + " ".join(f"{x['code']} {x['pct']:+.1f}" for x in s["top"])
           for s in ut["sectors"][:5]]
    md += ["", f"**큰 움직임** {mover_txt}", "",
          f"**ETF 다음 날 방향(본문에 안 씀 — 의미 있는 신호 드묾)** {next(x for x in summary['items'] if x['key'] == 'etf_forecast')['text']} — 적중률 상위 5",
          "| ETF | 예측 | 적중 | 평소 | 당일 등락 |", "|---|---|---|---|---|"]
    for f in forecast[:5]:  # collect_rows 가 적중률 높은 순으로 정렬해 둠
        hr = "–" if f["hit_rate"] is None else f"{f['hit_rate']:.0%}"
        us = "–" if f["usual"] is None else f"{f['usual']:.0%}"
        chg = "–" if f["last_chg_pct"] is None else f"{f['last_chg_pct']:+.2f}%"
        md.append(f"| {f['etf']} {f['name']} | {f['pred']} | {hr} | {us} | {chg} |")
    md += ["", "참고: " + " / ".join(notes + problems)]
    (day / "summary_am.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (OUT / "latest.json").write_text(json.dumps({"date": us_date, "slot": "am"}), encoding="utf-8")
    print(f"완료: {day} ({summary['status']}, ETF {len(forecast)}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
