"""
4_macro 일별 정리본 — 월간_매크로섹터분석.py 수집 함수를 일별로 불러
  data/macro_daily.csv   (일별 누적, 열 = 지표)
  data/memory_daily.csv  (DRAMeXchange 현물가 스냅샷 누적)
  ../exchange/4_macro/{날짜}/summary_am.json · summary_am.md + latest.json
을 만든다. 방향 판단은 하지 않는다(값 · 전날 대비 · 값의 날짜만).

실행: python export_exchange.py
"""
import os, re, sys, json
from datetime import datetime, timezone, timedelta
import pandas as pd

import 월간_매크로섹터분석 as m

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
EXCH = os.path.join(HERE, "..", "exchange", "4_macro")
KST = timezone(timedelta(hours=9))

# key: (묶음, 표시 이름, 단위) — 단위 "%"는 전날 대비를 bp로, 나머지는 %로 적는다
COLS = {
    "KR_3Y":  ("rates", "한국 국고 3년", "%"),
    "US_2Y":  ("rates", "미국 2년", "%"),   "US_10Y": ("rates", "미국 10년", "%"),
    "US_30Y": ("rates", "미국 30년", "%"),  "JP_10Y": ("rates", "일본 10년(월)", "%"),
    "INVERT_10Y2Y": ("rates", "미국 10년-2년", "%"), "INVERT_10Y3M": ("rates", "미국 10년-3개월", "%"),
    "USDKRW": ("fx", "원/달러", "원"),      "DXY": ("fx", "달러인덱스", ""),
    "WTI":    ("oil", "WTI", "$"),
    "HY":     ("credit", "미국 HY 스프레드", "%"), "BBB": ("credit", "미국 BBB 스프레드", "%"),
    "VIX":    ("other", "VIX", ""), "GOLD": ("other", "금", "$"), "COPPER": ("other", "구리", "$"),
}
GROUP_TITLE = {"rates": "금리", "fx": "환율", "oil": "유가", "credit": "신용스프레드",
               "memory": "메모리 현물가(DRAMeXchange)", "other": "기타(VIX · 금 · 구리)"}
MEMORY_PICK = {"DRAM Spot Price": 3, "Wafer Spot Price": 2}   # 섹션별 앞쪽 몇 품목을 요약에 올릴지


def collect_ecos_kr3y(years=2):
    """한국은행 ECOS 817Y002(시장금리 일별) · 010200000(국고채 3년). 키가 없거나 실패하면 빈 시리즈."""
    key = os.environ.get("ECOS_API_KEY", "").strip()
    if not key:
        print("  ⚠️  ECOS_API_KEY 없음 → 한국 3년물 건너뜀")
        return pd.Series(dtype=float)
    end = datetime.now(KST)
    start = end - timedelta(days=365 * years)
    url = (f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/2000/817Y002/D/"
           f"{start:%Y%m%d}/{end:%Y%m%d}/010200000")
    try:
        r = m.requests.get(url, timeout=20)
        r.encoding = "utf-8"
        rows = r.json()["StatisticSearch"]["row"]
        s = pd.Series({pd.Timestamp(x["TIME"]): float(x["DATA_VALUE"]) for x in rows})
        print(f"  ✅ ECOS 국고채 3년: {len(s)}일")
        return s
    except Exception as e:
        print(f"  ❌ ECOS 국고채 3년: {type(e).__name__}")   # URL에 키가 있어 메시지 원문은 찍지 않음
        return pd.Series(dtype=float)


def collect_daily():
    l1 = m.collect_l1_data(freq=None)
    l2 = m.collect_l2_data(freq=None, skip=("KOSPI", "SPX", "USDKRW"))  # 지수는 2 · 3 역할, 환율은 L1에서
    series = {**l1["rates"], **l1["credit"], **l2}
    cols = {k: v["weekly"] for k, v in series.items() if k in COLS}
    kr3y = collect_ecos_kr3y()
    if not kr3y.empty:
        cols["KR_3Y"] = kr3y
    df = pd.DataFrame(cols)
    df.index = pd.to_datetime(df.index).date
    df.index.name = "date"
    path = os.path.join(DATA, "macro_daily.csv")
    if os.path.exists(path):  # 누적: 새로 받은 값이 우선, 받지 못한 옛 값은 유지
        old = pd.read_csv(path, index_col=0, parse_dates=True)
        old.index = old.index.date
        df = df.combine_first(old)
    df = df.sort_index()[[c for c in COLS if c in df.columns]]
    df.index.name = "date"   # combine_first 뒤에 이름이 빠지므로 다시 붙인다
    df.round(4).to_csv(path, encoding="utf-8")
    return df


def collect_memory(run_date):
    rows = []
    for section, d in m.collect_l3_dram().items():
        for _, r in d["df"].iterrows():
            chg_col = next((c for c in r.index if "Change" in str(c)), None)
            rows.append({"run_date": run_date, "section": section, "last_update": d["last_update"],
                         "item": r["Item"], "average": pd.to_numeric(r.get("Session Average"), errors="coerce"),
                         "change_pct": pd.to_numeric(str(r.get(chg_col, "")).replace("%", ""), errors="coerce")})
    new = pd.DataFrame(rows)
    path = os.path.join(DATA, "memory_daily.csv")
    if not new.empty:
        allm = pd.concat([pd.read_csv(path), new]) if os.path.exists(path) else new
        allm.drop_duplicates(["section", "item", "last_update"], keep="last").to_csv(path, index=False, encoding="utf-8")
    return new


def mem_date(txt):
    """'Last Update: Oct.9 2026    18:10 (GMT+8)<>' → '2026-10-09 18:10'(대만 시각)"""
    mt = re.search(r"([A-Z][a-z]{2})\.?\s*(\d{1,2})\s+(\d{4})\s+(\d{1,2}:\d{2})", txt)
    if not mt:
        return txt.strip()
    return datetime.strptime(" ".join(mt.groups()), "%b %d %Y %H:%M").strftime("%Y-%m-%d %H:%M")


def latest_point(s):
    s = s.dropna()
    if s.empty:
        return None
    v, d = float(s.iloc[-1]), s.index[-1]
    prev = float(s.iloc[-2]) if len(s) > 1 else None
    return v, d, prev


def fmt_item(key, v, d, prev):
    _, name, unit = COLS[key]
    if prev is None:
        chg, chg_txt = None, ""
    elif unit == "%":
        chg = round((v - prev) * 100, 1)
        chg_txt = f" ({chg:+.1f}bp)"
    else:
        chg = round((v / prev - 1) * 100, 2) if prev else None
        chg_txt = f" ({chg:+.2f}%)" if chg is not None else ""
    val_txt = f"{v:.2f}%" if unit == "%" else (f"{v:,.1f}원" if unit == "원" else f"{v:,.2f}")
    return ({"name": name, "value": round(v, 4), "unit": unit, "chg": chg,
             "chg_unit": "bp" if unit == "%" else "%", "date": str(d)},
            f"{name} {val_txt}{chg_txt}, {d:%m-%d}")


def quarter_regime(df: pd.DataFrame, now: datetime) -> dict | None:
    """분기 국면(VM-SPC Core 9.294 · 9.296, 2026-10-10) — 지난 월말 기준, 직전 63거래일 평균 vs 그 앞 63거래일 평균.
    WTI는 % 변화, 10Y-2Y 금리차는 %p 변화. 부호만 리포트에 쓴다(유가 상승 · 금리차 가팔라짐)."""
    me = (pd.Timestamp(now.date()).replace(day=1) - pd.Timedelta(days=1)).date()   # 지난달 말일
    out = {"asof": str(me)}
    for col, key, pct in (("WTI", "wti_q_pct", True), ("INVERT_10Y2Y", "curve_q_pp", False)):
        if col not in df.columns:
            continue
        s = df[col].dropna()
        s = s[[d <= me for d in s.index]]
        if len(s) < 126:
            continue
        a, b = s.iloc[-63:].mean(), s.iloc[-126:-63].mean()
        out[key] = float(round((a / b - 1) * 100, 2) if pct else round(a - b, 3))
    return out if len(out) > 1 else None


def main():
    os.makedirs(DATA, exist_ok=True)
    now = datetime.now(KST)
    date = now.strftime("%Y-%m-%d")
    df = collect_daily()
    mem = collect_memory(date)

    groups = {g: {"values": {}, "texts": []} for g in GROUP_TITLE}
    missing = []
    for key, (g, _, _) in COLS.items():
        p = latest_point(df[key]) if key in df.columns else None
        if p is None:
            missing.append(key)
            continue
        val, txt = fmt_item(key, *p)
        groups[g]["values"][key] = val
        groups[g]["texts"].append(txt)
    for section, n in MEMORY_PICK.items():
        sub = mem[mem["section"] == section].head(n) if not mem.empty else mem
        for _, r in sub.iterrows():
            upd = mem_date(r["last_update"])
            groups["memory"]["values"][r["item"]] = {"section": section, "value": r["average"], "unit": "$",
                                                    "chg": r["change_pct"], "chg_unit": "%", "date": upd}
            groups["memory"]["texts"].append(f"{r['item']} ${r['average']:g} ({r['change_pct']:+.2f}%), {upd}")
    if mem.empty:
        missing.append("memory")

    items = [{"key": g, "title": GROUP_TITLE[g], "text": " · ".join(v["texts"]),
              "value": v["values"] or None, "grade": "서술", "ref": "", "link": ""}
             for g, v in groups.items() if v["values"]]
    qr = quarter_regime(df, now)
    if qr:
        qt = [f"{qr['asof']} 기준 지난 3개월 평균 대비"]
        if "wti_q_pct" in qr:
            qt.append(f"WTI {qr['wti_q_pct']:+.1f}%")
        if "curve_q_pp" in qr:
            qt.append(f"10Y-2Y {qr['curve_q_pp']:+.2f}%p")
        items.append({"key": "quarter", "title": "분기 국면(월말 기준)", "text": " · ".join(qt), "value": qr,
                      "grade": "서술", "ref": "9.294 · 9.296", "link": ""})
    # 체크리스트(2026-10-15) — 확장 수집(collect_ext.py, 최근 400일 합침) → checklist.py 기계 규칙. 실패해도 정리본은 낸다
    ck = None
    try:
        import collect_ext as ce
        import checklist as ckl
        sys.argv = [sys.argv[0]]                     # collect_ext.main()이 --full을 보지 않게
        ce.main()
        try:                                         # 외국인 원화 채권 순매수(FreeSIS 장외, 2026-10-23) — 마지막 날 − 10일부터
            import bond_foreign as bf
            sys.argv = [sys.argv[0]]
            bf.main()
        except Exception as e:  # noqa: BLE001
            missing.append(f"bond_foreign({type(e).__name__})")
        ck = ckl.build()
        ckl.record(ck)                               # 직전 대비 변화 · 사건 표시용 이력(2026-10-20)
        cnt = ck["count"]
        items.append({"key": "checklist", "title": "매크로 체크리스트(흐름 방식 · 카드 10 · 보조 1)",
                      "text": (f"매크로 부담 점수 {ck['burden']}/100(낮을수록 좋음, {ck['level']}, 문턱 {ck['cut']}) · 카드 높음 {cnt['R']} · 높은 편 {cnt['A']} · 낮음 {cnt['G']}"
                               + (f" · 자료 부족 {cnt['B']}" if cnt["B"] else "") + " — "
                               + " · ".join(f"{b['name']} {b['summary']}" for b in ck["board"])),
                      "value": "checklist.json", "grade": "참고", "ref": "", "link": ""})
    except Exception as e:  # noqa: BLE001
        missing.append(f"checklist({type(e).__name__}: {e})")
    # 외국인 시선(2026-10-15) — 달러 기준 코스피 · 원화 강약 분해 · 외국인 순매수(달러) · 국가 ETF 달러 누적 · ETF 자금 유출입(쌓는 중). 동시 지표
    fv = None
    try:
        import foreign_view as fvm
        fv = fvm.build()
        d1 = (fv["usd_kospi"]["decomp"] or {}).get("1개월") or {}
        f20 = fv["foreign"]["flows"].get("20일") or {}
        items.append({"key": "foreign_view", "title": "외국인 시선(달러 기준, 동시 지표)",
                      "text": (f"달러 코스피 1개월 {d1.get('usd')}%(주가 {d1.get('local')} · 환율 {d1.get('fx')}) · "
                               f"외국인 20일 {(f20.get('usd_m') or 0) / 100:+,.0f}억 달러({fv['foreign']['date']} 기준) — 지수를 뒤따르는 동시 지표(9.338)"),
                      "value": "foreign_view.json", "grade": "참고", "ref": "9.338", "link": ""})
    except Exception as e:  # noqa: BLE001
        missing.append(f"foreign_view({type(e).__name__}: {e})")
    # 유동성 · 신용 모니터(2026-10-15 사용자) — 12개 지표 · 경보 · 미국 신용 등급별 · 한 줄 요약 · 주요 이슈. 참고(검증 전)
    lq = None
    try:
        import liquidity_monitor as lqm
        lq = lqm.build()
        n_al = sum(i.get("alert", False) for i in lq["items"])
        items.append({"key": "liquidity", "title": "유동성 · 신용 모니터", "text": f"경보 {n_al}개 — {lq['headline']}",
                      "value": "liquidity_monitor.json", "grade": "참고", "ref": "", "link": ""})
    except Exception as e:  # noqa: BLE001
        missing.append(f"liquidity({type(e).__name__}: {e})")
    pick = lambda g, k: next((t for t in groups[g]["texts"] if t.startswith(COLS[k][1] + " ")), None)
    head = [t.rsplit(",", 1)[0] for t in (pick("rates", "US_10Y"), pick("fx", "USDKRW"),
                                          pick("oil", "WTI"), pick("credit", "HY")) if t]
    summary = {
        "role": "4_macro", "date": date, "slot": "am",
        "generated_at": now.isoformat(timespec="seconds"),
        "status": "ok" if not missing else ("failed" if not items else "partial"),
        "sources": ["yfinance", "FRED", "ECOS", "DRAMeXchange"],
        "headline": " · ".join(head),
        "items": items,
        "notes": "; ".join(filter(None, [
            f"수집 실패: {', '.join(missing)}" if missing else "",
            "원천마다 갱신 시각이 달라 항목마다 값의 날짜를 함께 적음. 전날 대비 = 그 원천의 직전 관측치 대비"])),
    }

    out = os.path.join(EXCH, date)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "summary_am.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    if ck:
        with open(os.path.join(out, "checklist.json"), "w", encoding="utf-8") as f:
            json.dump(ck, f, ensure_ascii=False, indent=1, default=str)
    if fv:
        with open(os.path.join(out, "foreign_view.json"), "w", encoding="utf-8") as f:
            json.dump(fv, f, ensure_ascii=False, indent=1, default=str)
    if lq:
        with open(os.path.join(out, "liquidity_monitor.json"), "w", encoding="utf-8") as f:
            json.dump(lq, f, ensure_ascii=False, indent=1, default=str)
    md = [f"# 매크로 {date} (아침)", "", f"**{summary['headline']}**", ""]
    md += [f"- **{it['title']}**: {it['text']}" for it in items]
    md += ["", f"상태: {summary['status']} · {summary['notes']}",
           f"일별 표: `4_macro/data/macro_daily.csv` · `memory_daily.csv`"]
    with open(os.path.join(out, "summary_am.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    with open(os.path.join(EXCH, "latest.json"), "w", encoding="utf-8") as f:
        json.dump({"date": date, "slot": "am"}, f)
    print(f"\n→ {out}  (status={summary['status']})")
    return 0 if items else 1


if __name__ == "__main__":
    sys.exit(main())
