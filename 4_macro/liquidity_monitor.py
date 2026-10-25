"""유동성 · 신용 모니터(일별) — 12개 지표의 지금 값 · 1주 · 1개월 변화 · 1년 백분위 · 경보, 미국 신용 등급별(IG · BBB · HY · CCC) 3년 흐름,
그리고 기계 규칙으로 만든 한 줄 요약 · 주요 이슈. 2026-10-15 사용자 요청(받은 예시 두 장의 형태). 지금 상태를 보는 참고 모니터 — 검증 전.

  python liquidity_monitor.py      → data/liquidity_monitor.json (export_exchange.py가 정리본 item `liquidity`로 싣는다)

경보(예시와 같은 세 가지):
 ① 1개월 위험 방향 급변 = 1개월 변화가 위험 쪽이고 그 크기가 최근 3년 1개월 변화 표준편차의 1.5배 이상
 ② 1년 백분위 90% 이상(위험 쪽 — 낮을수록 위험인 지표는 10% 이하)
 ③ 변동성 절대 수준 초과(VIX 25 · VIX ÷ VIX3M 1.0 · MOVE 130 · 국내 변동성 30)
VKOSPI는 2_kr_market vkospi.py가 KIS(업종 0503)로 받아 exchange/2_kr_market/vkospi.csv에 쌓는다(2026-10-15 – , 2003 – 백필).
그 파일이 없거나 5일 넘게 오래되면 코스피 20일 실현 변동성(연율)으로 대신한다.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
KST = timezone(timedelta(hours=9))


def _s(df, c):
    s = df[c].dropna() if c in df else pd.Series(dtype=float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _bp(a, b):
    return lambda df: ((_s(df, a) - _s(df, b)).dropna() * 100)


def _net_liq(df):
    w, t = _s(df, "f_walcl") / 1000, _s(df, "f_tga") / 1000          # 백만 → 십억 달러
    r = _s(df, "f_rrp").reindex(w.index, method="ffill")
    return (w - t.reindex(w.index, method="ffill") - r).dropna()


def _rv20(df):
    k = _s(df, "y_ks11")
    return (np.log(k).diff().rolling(20).std() * np.sqrt(252) * 100).dropna()


VK_PATH = HERE.parent / "exchange" / "2_kr_market" / "vkospi.csv"


def _vkospi(df):
    try:
        v = pd.read_csv(VK_PATH, index_col=0, parse_dates=True)["close"].dropna().sort_index()
        if len(v) > 250 and (pd.Timestamp(datetime.now(KST).date()) - v.index[-1]).days <= 5:
            return v
    except (OSError, KeyError, ValueError):
        pass
    return pd.Series(dtype=float)


# (키, 이름, 설명, 단위, 위험 방향 +1 = 클수록 위험, 절대 경보선, 묶음, 값 함수)
ITEMS = [
    ("aa", "회사채 AA− − 국고채(3년)", "한국 우량 신용 스프레드", "bp", 1, None, "국내 신용", _bp("k_aa", "k_ktb3")),
    ("bbb", "회사채 BBB− − 국고채(3년)", "한국 비우량 신용 스프레드", "bp", 1, None, "국내 신용", _bp("k_bbb", "k_ktb3")),
    ("cpcd", "CP 91일 − CD 91일", "한국 단기자금 경색", "bp", 1, None, "국내 단기자금", _bp("k_cp91", "k_cd91")),
    ("kr_curve", "국고채 10년 − 3년", "한국 장단기 금리차", "bp", -1, None, "금리 곡선", _bp("k_ktb10", "k_ktb3")),
    ("hy", "미국 하이일드 스프레드", "ICE BofA HY OAS", "bp", 1, None, "미국 신용", lambda df: _s(df, "f_hy") * 100),
    ("ig", "미국 투자등급 스프레드", "ICE BofA IG OAS", "bp", 1, None, "미국 신용", lambda df: _s(df, "f_ig") * 100),
    ("netliq", "미국 순유동성", "연준 자산 − TGA − 역레포($B)", "", -1, None, "유동성", _net_liq),
    ("us_curve", "미국 10년 − 2년", "미국 장단기 금리차", "bp", -1, None, "금리 곡선", lambda df: _s(df, "f_t10y2y") * 100),
    ("vix", "VIX", "S&P500 30일 내재변동성", "", 1, 25.0, "변동성", lambda df: _s(df, "y_vix")),
    ("vixterm", "VIX ÷ VIX3M", "1 초과 = 단기 공포 > 장기(역전)", "x", 1, 1.0, "변동성", lambda df: (_s(df, "y_vix") / _s(df, "y_vix3m")).dropna()),
    ("move", "MOVE", "미국 국채 내재변동성", "", 1, 130.0, "변동성", lambda df: _s(df, "y_move")),
    ("vkospi", "VKOSPI", "코스피200 30일 내재변동성(KIS)", "", 1, 30.0, "변동성", _vkospi),
]
TIERS = [("ig", "투자등급(IG) 전체", "f_ig"), ("bbb_us", "BBB(투자등급 하단)", "f_bbb"), ("hy", "하이일드(HY) 전체", "f_hy"),
         ("ccc", "CCC 이하(정크 최하단)", "f_ccc")]


def _r(x, n=1):
    return None if x is None or not np.isfinite(x) else round(float(x), n)


def item(df, key, name, desc, unit, rdir, absline, grp, fn) -> dict:
    s = fn(df).dropna()
    if s.empty:
        return {"key": key, "name": name, "desc": desc, "unit": unit, "group": grp, "missing": True}
    v, dt = float(s.iloc[-1]), s.index[-1]
    y1 = s[s.index > dt - pd.DateOffset(years=1)]
    y3 = s[s.index > dt - pd.DateOffset(years=3)]
    asof = lambda d: s[s.index <= d].iloc[-1] if (s.index <= d).any() else np.nan
    c1w, c1m = v - asof(dt - pd.Timedelta(days=7)), v - asof(dt - pd.DateOffset(months=1))
    m1 = (s - s.reindex(s.index - pd.DateOffset(months=1), method="ffill").to_numpy()).dropna()
    sd = float(m1[m1.index > dt - pd.DateOffset(years=3)].std()) if len(m1) > 60 else np.nan
    pct = float((y1 <= v).mean())
    risk_pct = pct if rdir > 0 else 1 - pct
    why = []
    if np.isfinite(c1m) and np.isfinite(sd) and sd > 0 and c1m * rdir > 0 and abs(c1m) >= 1.5 * sd:
        why.append("1개월 급변")
    if risk_pct >= 0.9:
        why.append("1년 " + ("상위" if rdir > 0 else "하위") + " 10%")
    if absline is not None and v >= absline:
        why.append(f"절대 수준 {absline:g} 초과")
    pts = y1.resample("W-FRI").last().dropna()
    return {"key": key, "name": name, "desc": desc, "unit": unit, "group": grp, "dir": rdir, "value": _r(v, 2), "date": str(dt.date()),
            "chg_1w": _r(c1w, 2), "chg_1m": _r(c1m, 2), "sd_1m": _r(sd, 2), "pct_1y": _r(pct, 2), "risk_pct": _r(risk_pct, 2),
            "median_1y": _r(float(y1.median()), 2), "pct_3y": _r(float((y3 <= v).mean()), 2),
            "range_3y": [_r(float(y3.min()), 1), _r(float(y3.max()), 1)], "abs": absline,
            "alert": bool(why), "why": why, "series_1y": {str(d.date()): _r(x, 2) for d, x in pts.items()}}


def tiers(df) -> list[dict]:
    out = []
    for key, name, col in TIERS:
        s = _s(df, col) * 100
        if s.empty:
            continue
        dt = s.index[-1]
        y3 = s[s.index > dt - pd.DateOffset(years=3)]
        pts = y3.resample("W-FRI").last().dropna()
        out.append({"key": key, "name": name, "value": _r(float(s.iloc[-1]), 0), "date": str(dt.date()),
                    "range_3y": [_r(float(y3.min()), 0), _r(float(y3.max()), 0)], "pct_3y": _r(float((y3 <= s.iloc[-1]).mean()), 2),
                    "chg_1m": _r(float(s.iloc[-1] - s[s.index <= dt - pd.DateOffset(months=1)].iloc[-1]), 0) if (s.index <= dt - pd.DateOffset(months=1)).any() else None,
                    "series_3y": {str(d.date()): _r(x, 0) for d, x in pts.items()}})
    return out


def _fmt(it, v):
    u = it["unit"]
    if v is None:
        return "–"
    if u == "bp":
        return f"{v:,.0f}bp"
    if u == "x":
        return f"{v:.2f}x"
    if u == "%":
        return f"{v:.1f}"
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:,.1f}"


def _fchg(it, v):
    if v is None:
        return "–"
    u = it["unit"]
    return f"{v:+,.0f}bp" if u == "bp" else (f"{v:+.2f}" if u == "x" else (f"{v:+,.0f}" if abs(v) >= 100 else f"{v:+.1f}"))


def narrate(items: list[dict], tier: list[dict]) -> tuple[str, list[str]]:
    """한 줄 요약 · 주요 이슈 — 기계 규칙(사람 판단 없음)."""
    al = [i for i in items if i.get("alert")]
    by = {i["key"]: i for i in items if not i.get("missing")}
    grp = []
    for g in ("국내 단기자금", "국내 신용", "미국 신용", "유동성", "금리 곡선", "변동성"):
        if any(i["group"] == g for i in al):
            grp.append(g)
    calm = [g for g in ("국내 신용", "미국 신용", "유동성", "변동성") if g not in grp]
    head = (" · ".join(grp) + " 쪽에서 위험 신호" + (f", {' · '.join(calm)}은 잠잠" if calm else "")) if al else \
        "신용 · 유동성 · 변동성 모두 평소 범위"
    issues = []
    t = {x["key"]: x for x in tier}
    if "ccc" in t and "ig" in t and (t["ccc"]["pct_3y"] or 0) >= 0.95 and (t["ig"]["pct_3y"] or 1) < 0.6:
        issues.append(f"미국 정크 최하단(CCC)만 3년 최고권({t['ccc']['value']:,.0f}bp, 3년 범위 {t['ccc']['range_3y'][0]:,.0f} – {t['ccc']['range_3y'][1]:,.0f}) — "
                      f"투자등급({t['ig']['value']:.0f}bp)은 안정, 스트레스가 가장 약한 고리에 몰림")
    if "cpcd" in by and by["cpcd"].get("alert"):
        x = by["cpcd"]
        issues.append(f"국내 단기자금: CP − CD {x['value']:.0f}bp, 1개월 {x['chg_1m']:+.0f}bp — 기업어음 쪽 자금 경색 조짐")
    if "hy" in by and by["hy"].get("alert"):
        x = by["hy"]
        issues.append(f"미국 하이일드 스프레드 {x['value']:.0f}bp, 1개월 {x['chg_1m']:+.0f}bp(1년 {x['pct_1y']:.0%} 위치)")
    if "vix" in by and "move" in by and by["move"].get("alert") and not by["vix"].get("alert"):
        issues.append(f"주식 변동성은 잠잠(VIX {by['vix']['value']:.1f}), 채권 변동성만 높음(MOVE {by['move']['value']:.1f}) — 금리발 불안")
    if "vixterm" in by and (by["vixterm"]["value"] or 0) >= 1:
        issues.append(f"VIX 기간구조 역전(VIX ÷ VIX3M {by['vixterm']['value']:.2f}) — 단기 공포가 장기보다 큼")
    if "vkospi" in by and by["vkospi"].get("alert"):
        issues.append(f"국내 공포 구간: VKOSPI {by['vkospi']['value']:.1f}(1개월 {by['vkospi']['chg_1m']:+.1f}, 1년 {by['vkospi']['pct_1y']:.0%} 위치) — "
                      "과거엔 이런 경보 뒤 3 – 6개월 코스피가 평소보다 나았음(9.339, 세 구간 같은 방향 · 통계 미달)")
    elif "krvol" in by and by["krvol"].get("alert"):
        issues.append(f"국내 변동성 높음: 코스피 20일 실현 변동성 {by['krvol']['value']:.0f}%(연율, VKOSPI 대신)")
    for x in al:                                             # 위에서 다루지 않은 경보
        if x["key"] not in ("cpcd", "hy", "move", "krvol", "vkospi") and not any(x["name"] in s for s in issues):
            issues.append(f"{x['name']} {_fmt(x, x['value'])} — {', '.join(x['why'])}")
    if "netliq" in by:
        x = by["netliq"]
        issues.append(f"미국 순유동성 {x['value']:,.0f}십억 달러, 1개월 {x['chg_1m']:+,.0f} — 1년 {x['pct_1y']:.0%} 위치" + (" (넉넉한 편)" if x["pct_1y"] >= 0.7 else " (빠듯한 편)" if x["pct_1y"] <= 0.3 else ""))
    return head, issues[:6]


# ── 국내 상태 지도(2026-10-17 사용자 — VM-core 9.344 · 9.348 · 9.349 권고: 방향 신호 아님, 지금 상태 설명만) ──────────────
RETAIL = HERE.parent / "2_kr_market" / "data" / "retail_etf"
KR_CAL = HERE.parent / "exchange" / "2_kr_market" / "kr_calendar.json"


def _etf_tv(code: str) -> pd.Series:
    d = pd.read_csv(RETAIL / f"{code}.csv", dtype={"date": str})
    d.index = pd.to_datetime(d["date"], format="%Y%m%d")
    return (d["close"] * d["volume"]).sort_index()


def _lev_tilt(lev: str, invs: list[str], label: str) -> dict | None:
    """레버리지 ÷ 인버스 거래대금 20일 평균과 1년 순위(9.344: 쏠림 클 때 다음 20일 변동성 큼 — 최근 기간만, 방향 신호 아님)."""
    try:
        L = _etf_tv(lev)
        inv = sum(_etf_tv(c).reindex(L.index).fillna(0) for c in invs)
    except (OSError, KeyError, ValueError):
        return None
    r = (L.rolling(20).mean() / inv.rolling(20).mean()).replace([np.inf, -np.inf], np.nan).dropna()
    if len(r) < 260:
        return None
    v, dt = float(r.iloc[-1]), r.index[-1]
    pct = float((r[r.index > dt - pd.DateOffset(years=1)] <= v).mean())
    note = ("쏠림 1년 상위 10% — 최근 몇 년은 이런 때 다음 20일 출렁임이 컸음" if pct >= 0.9 else
            "인버스 쪽으로 쏠림(1년 하위 10%)" if pct <= 0.1 else "평소 범위")
    return {"key": "lev_" + lev, "name": f"{label} 레버리지 ÷ 인버스 거래대금(20일)", "value": round(v, 2), "pct_1y": round(pct, 2),
            "date": str(dt.date()), "flag": pct >= 0.9, "text": f"{label} 개인 레버리지 쏠림 {v:.2f}배(1년 {pct:.0%} 위치) — {note}"}


def _margin_pos(df) -> list[dict]:
    """공식 신용융자 잔고 ÷ 시가총액 · ÷ 투자자 예탁금의 10년 위치(9.344 · 9.348: 높을 때 이후 약했던 기록, 판정 못 함)."""
    out = []
    m = _s(df, "s_credit") * 1e6                                      # 2026-10-22: 금투협 FreeSIS 일별(백만 원 → 원) — 없으면 한국은행 월 단위
    if len(m) >= 2500:
        cap = _s(df, "k_kospi_cap") * 1e8                              # 억 원 → 원(유가증권시장만 — 신용은 코스닥 포함이라 비율은 근사, 9.344와 같은 정의)
        dep = _s(df, "s_deposit") * 1e6
        daily = True
    else:
        m = _s(df, "k_margin")
        if m.empty:
            return out
        cap = _s(df, "k_kospi_cap").resample("MS").mean() * 1e8           # 억 원 → 원(월평균, 유가증권시장만 — 신용은 코스닥 포함이라 비율은 근사)
        dep = _s(df, "k_deposit")
        daily = False
    for key, name, den in (("margin_cap", "신용융자 ÷ 코스피 시가총액", cap), ("margin_dep", "신용융자 ÷ 투자자 예탁금", dep)):
        s = (m / den.reindex(m.index)).dropna()
        if len(s) < 60:
            continue
        v, dt = float(s.iloc[-1]), s.index[-1]
        p10 = float((s[s.index > dt - pd.DateOffset(years=10)] <= v).mean())
        note = "빚투 많은 구간 — 이런 때 이후 6개월이 약했던 기록(판정 못 함)" if p10 >= 0.8 else ("빚투 적은 구간" if p10 <= 0.2 else "평소 범위")
        unit = f"{v * 100:.2f}%" if key == "margin_cap" else f"{v * 100:.0f}%"
        ds = dt.strftime("%m/%d") if daily else dt.strftime("%Y-%m")
        out.append({"key": key, "name": name, "value": round(v * 100, 3), "pct_10y": round(p10, 2), "date": dt.strftime("%Y-%m-%d" if daily else "%Y-%m"),
                    "flag": p10 >= 0.8, "text": f"{name} {unit}({ds}, 10년 {p10:.0%} 위치) — {note}"})
    return out


def _open_days(start: pd.Timestamp, n: int) -> list[pd.Timestamp]:
    cal = {}
    try:
        cal = json.loads(KR_CAL.read_text(encoding="utf-8")).get("days", {})
    except (OSError, ValueError):
        pass
    out, d = [], start
    while len(out) < n and (d - start).days < 40:
        k = d.strftime("%Y-%m-%d")
        fixed_off = (d.month, d.day) in ((1, 1), (12, 25), (12, 31))      # 달력 밖 날짜용 고정 휴장(신정 · 성탄 · 연말 휴장)
        if cal.get(k, d.weekday() < 5 and not fixed_off):
            out.append(d)
        d += pd.Timedelta(days=1)
    return out


def _calendar(today: pd.Timestamp) -> list[dict]:
    """앞으로 5거래일 안 수급 달력(9.344 서술: MSCI 정기변경일 외국인 대량 매도가 흔함 · 연말 연초 강한 편(2016 – ) · 만기일)."""
    days = _open_days(today + pd.Timedelta(days=1), 5)
    if not days:
        return []
    allm = _open_days(today.replace(day=1) - pd.Timedelta(days=5), 30) + days
    out = []
    for d in days:
        month_days = sorted({x for x in allm + _open_days(d.replace(day=1), 25) if x.month == d.month and x.year == d.year})
        thu = [x for x in pd.date_range(d.replace(day=1), periods=31, freq="D") if x.month == d.month and x.weekday() == 3]
        exp = thu[1] if len(thu) > 1 else None
        if exp is not None and exp not in month_days:            # 휴장이면 앞 거래일로 당김
            prev = [x for x in month_days if x < exp]
            exp = prev[-1] if prev else None
        tag = []
        if exp is not None and d == exp:
            tag.append("선물 · 옵션 동시만기" if d.month in (3, 6, 9, 12) else "옵션 만기")
        if d.month in (2, 5, 8, 11) and month_days and d == month_days[-1]:
            tag.append("MSCI 정기변경 반영일 — 외국인 대량 매도가 흔한 날(평소의 약 5배)")
        if d.month == 12 and month_days and d in month_days[-5:]:
            tag.append("연말 마지막 5거래일 — 2016년 뒤로는 강한 편")
        if d.month == 1 and month_days and d in month_days[:5]:
            tag.append("연초 첫 5거래일 — 2016년 뒤로는 강한 편")
        for t in tag:
            out.append({"date": str(d.date()), "tag": t})
    merged = []                                                  # 같은 메모가 이어지면 한 줄로(연말 · 연초 5거래일)
    for x in out:
        if merged and merged[-1]["tag"] == x["tag"]:
            merged[-1]["end"] = x["date"]
        else:
            merged.append({**x, "end": x["date"]})
    md = lambda s: f"{int(s[5:7])}/{int(s[8:])}"
    return [{"date": m["date"], "text": (md(m["date"]) + (f" – {md(m['end'])}" if m["end"] != m["date"] else "")) + " " + m["tag"]} for m in merged]


def kr_state(df) -> list[dict]:
    out = [x for x in (_lev_tilt("122630", ["114800", "252670"], "코스피"), _lev_tilt("233740", ["251340"], "코스닥")) if x]
    out += _margin_pos(df)
    out += [{"key": "cal", **c, "flag": False} for c in _calendar(pd.Timestamp(datetime.now(KST).date()))]
    return out


def telegram(r: dict) -> str:
    """예시 형태 그대로(숫자 포함) — 사용자 요청."""
    al = [i for i in r["items"] if i.get("alert")]
    L = [f"유동성·신용 모니터 {r['date'][5:].replace('-', '/')}",
         (f"🔴 경보 {len(al)}개 · " + ", ".join(i["name"] for i in al)) if al else "🟢 경보 없음",
         f"— {r['headline']}"]
    for i in r["items"]:
        if i.get("missing"):
            continue
        L.append(f"{'🔴' if i['alert'] else '▫️'} {i['name']}: {_fmt(i, i['value'])} (1M {_fchg(i, i['chg_1m'])})")
    if r["issues"]:
        L.append("■ 주요 이슈")
        L += [f"· {s}" for s in r["issues"][:5]]
    if r.get("kr_state"):
        L.append("■ 국내 상태(참고 — 방향 신호 아님)")
        L += [f"· {x['text']}" for x in r["kr_state"]]
    return "\n".join(L)


def build() -> dict:
    df = pd.read_csv(DATA / "macro_ext.csv", index_col=0, parse_dates=True)
    items = [item(df, *x) for x in ITEMS]
    if items[-1].get("missing"):                    # VKOSPI 파일이 없거나 오래됨 → 실현 변동성으로 대신
        items[-1] = item(df, "krvol", "코스피 실현 변동성(20일)", "VKOSPI 대신 — 코스피 일간 수익 20일 표준편차 × √252", "%", 1, 30.0, "변동성", _rv20)
    tier = tiers(df)
    head, issues = narrate(items, tier)
    r = {"made_at": datetime.now(KST).isoformat(timespec="seconds"), "date": datetime.now(KST).strftime("%Y-%m-%d"),
         "headline": head, "issues": issues, "items": items, "tiers": tier,
         "rule": "경보 = ① 1개월 위험 방향 변화가 3년 1개월 변화 표준편차의 1.5배 이상 ② 1년 위험 쪽 상위 10% ③ 변동성 절대 수준 초과. 기계 규칙 · 검증 전(참고)"}
    try:
        r["kr_state"] = kr_state(df)
    except Exception as e:  # noqa: BLE001 — 상태 줄이 빠질 뿐 모니터는 낸다
        r["kr_state"], r["kr_state_error"] = [], f"{type(e).__name__}: {e}"
    r["telegram"] = telegram(r)
    return r


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    r = build()
    (DATA / "liquidity_monitor.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(r["telegram"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
