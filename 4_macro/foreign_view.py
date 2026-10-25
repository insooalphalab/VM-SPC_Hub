"""외국인 시선 — 달러로 셈하는 외국인이 보는 한국 주식(2026-10-15 사용자: "ETF 흐름과 원화 · 달러지수를 연관해 외인 시선 · 자금 유입 · 유출을 매크로 인사이트로").
지금 상태를 보여 주는 동시 지표 칸이다(예측 아님). VM-SPC Core 9.338(2026-10-15): 달러 기준 코스피 · 달러 몫은 동시, 원화 고유 몫은 무관,
외국인 순매수 달러 누적은 지수를 4 – 8개월 뒤따름(역인과), EWY ÷ SPY 3개월만 약한 모멘텀 단서(서술) — 부담 점수에 넣지 않음.

  python foreign_view.py      → data/foreign_view.json (export_exchange.py가 정리본 item `foreign_view`로 싣는다)

1. 달러 기준 코스피 = 코스피 ÷ 원/달러. 1 · 3 · 6개월 달러 수익 = 주가 몫(코스피 원화 수익) + 환율 몫(원화 강약)으로 나눔(로그 분해).
2. 원화 강약 분해(+ = 원화 강세): 전체 = 달러 전체 몫(달러인덱스 주간 변화에 2년 회귀한 기울기 β) + 원화 고유 몫(나머지). 기간은 달력 1 · 3 · 6개월.
3. 외국인 순매수(달러): 코스피 외국인 순매수(백만 원, Core data/_market/investor_kospi.csv — 금요일 갱신) ÷ 그날 원/달러 → 5 · 20 · 60일 누적.
4. 국가 ETF 달러 누적 수익: 한국 EWY · 대만 EWT · 나스닥 QQQ · 브라질 EWZ · 인도 INDA · 일본 EWJ · 신흥국 EEM — 6개월 전 첫 거래일 = 0.
5. ETF 자금 유출입: yfinance가 지금 주식 수만 주므로 etf_shares.csv에 매일 쌓아(collect_ext.py) 주식 수 변화 × 기준가로 자금 유출입을 만든다 — 쌓인 날만큼만.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
INVESTOR = HERE.parent.parent / "VM-SPC_Core" / "data" / "_market" / "investor_kospi.csv"
KST = timezone(timedelta(hours=9))
ETFS = {"y_ewy": "한국 EWY", "y_ewt": "대만 EWT", "y_qqq": "나스닥 QQQ", "y_ewz": "브라질 EWZ", "y_inda": "인도 INDA",
        "y_ewj": "일본 EWJ", "y_eem": "신흥국 EEM"}
WIN = {"1개월": 1, "3개월": 3, "6개월": 6}          # 달력 개월(두 칸이 같은 기간을 보게)


def _r(x, n=2):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), n)


def build() -> dict:
    df = pd.read_csv(DATA / "macro_ext.csv", index_col=0, parse_dates=True)
    krw, dxy = df["y_krw"].dropna(), df["y_dxy"].dropna()
    inv = pd.read_csv(INVESTOR, usecols=["date", "kospi_close", "foreign_amt", "indiv_amt", "inst_amt", "pension_amt", "fin_inv_amt", "etc_corp_amt"], dtype={"date": str})
    inv.index = pd.to_datetime(inv["date"])
    ks = df["y_ks11"].dropna() if "y_ks11" in df else pd.Series(dtype=float)     # 코스피 일별(yfinance, 매일) — 없으면 투자자 표의 종가
    kospi = ks if len(ks) > 200 else inv["kospi_close"].astype(float)
    out = {"made_at": datetime.now(KST).isoformat(timespec="seconds"), "kospi_date": str(kospi.index[-1].date()),
           "fx_date": str(krw.index[-1].date())}

    # 1. 달러 기준 코스피와 분해(코스피 날짜 기준, 그날 원/달러)
    k = pd.DataFrame({"kospi": kospi, "krw": krw.reindex(kospi.index, method="ffill")}).dropna()
    k["usd"] = k.kospi / k.krw
    dec = {}
    for nm, n in WIN.items():
        a = k[k.index <= k.index[-1] - pd.DateOffset(months=n)]
        if len(a):
            a, b = a.iloc[-1], k.iloc[-1]
            loc, fx = np.log(b.kospi / a.kospi), -np.log(b.krw / a.krw)
            dec[nm] = {"usd": _r((np.exp(loc + fx) - 1) * 100), "local": _r((np.exp(loc) - 1) * 100), "fx": _r((np.exp(fx) - 1) * 100)}
    out["usd_kospi"] = {"value": _r(k.usd.iloc[-1], 4), "decomp": dec}

    # 2. 원/달러 변화 = 달러 전체 몫 + 원화 고유 몫 — 두 시세가 찍히는 시각(아시아 · 미국)이 달라 일별이 아닌 주간(금요일) 로그 변화로
    #    최근 2년 회귀한 기울기를 쓰고, 그 기울기로 기간 변화를 나눈다
    wk = pd.DataFrame({"krw": np.log(krw), "dxy": np.log(dxy)}).dropna().resample("W-FRI").last().diff().dropna()
    yr = wk.iloc[-104:]
    beta = float(np.polyfit(yr.dxy, yr.krw, 1)[0]) if len(yr) > 52 else 1.0
    lv = pd.DataFrame({"krw": np.log(krw), "dxy": np.log(dxy.reindex(krw.index, method="ffill"))}).dropna()
    fxs = {}
    for nm, n in WIN.items():          # 원화 기준(+ = 원화 강세): 전체 = −Δlog(원/달러), 달러 몫 = −β·Δlog(달러인덱스), 원화 고유 = 나머지
        a = lv[lv.index <= lv.index[-1] - pd.DateOffset(months=n)]
        if not len(a):
            continue
        tot, usd = -(lv.krw.iloc[-1] - a.krw.iloc[-1]), -beta * (lv.dxy.iloc[-1] - a.dxy.iloc[-1])
        fxs[nm] = {"won": _r((np.exp(tot) - 1) * 100), "dollar": _r((np.exp(usd) - 1) * 100), "won_own": _r((np.exp(tot - usd) - 1) * 100)}
    out["fx_split"] = {"beta": _r(beta, 2), "split": fxs, "krw": _r(krw.iloc[-1]), "dxy": _r(dxy.iloc[-1], 3)}

    # 3. 외국인 순매수(달러)
    f = pd.DataFrame({"amt": inv["foreign_amt"].astype(float) * 1e6, "krw": krw.reindex(inv.index, method="ffill")}).dropna()
    f["usd"] = f.amt / f.krw
    flows = {}
    for n in (5, 20, 60):
        s = f.usd.iloc[-n:].sum()
        hist = f.usd.rolling(n).sum().dropna().iloc[-756:]           # 최근 3년 안 순위
        flows[f"{n}일"] = {"usd_m": _r(s / 1e6, 0), "rank3y": _r(float((hist <= s).mean()), 2)}
    sg = np.sign(f.usd)
    streak = 0
    for v in sg[::-1]:
        if v != sg.iloc[-1] or v == 0:
            break
        streak += 1
    out["foreign"] = {"flows": flows, "streak": int(streak * sg.iloc[-1]), "date": str(f.index[-1].date())}
    grp = {}
    for col, nm in (("foreign_amt", "외국인"), ("indiv_amt", "개인"), ("inst_amt", "기관"), ("pension_amt", "연기금"), ("fin_inv_amt", "금융투자"), ("etc_corp_amt", "기타법인")):
        x = (inv[col].astype(float) * 1e6 / krw.reindex(inv.index, method="ffill")).dropna()
        h = x.rolling(20).sum().dropna().iloc[-756:]
        grp[nm] = {"usd_m": _r(float(x.iloc[-20:].sum()) / 1e6, 0), "rank3y": _r(float((h <= x.iloc[-20:].sum()).mean()), 2)}
    out["groups"] = grp

    # 4. 국가 ETF 달러 누적 수익(6개월, 첫 날 = 0) — 그림용 주 단위 점 + 지금 값
    start = df.index.max() - pd.DateOffset(months=6)
    series, now = {}, {}
    for col, nm in ETFS.items():
        s = df[col].dropna()
        s = s[s.index >= start]
        if len(s) < 20:
            continue
        cum = (s / s.iloc[0] - 1) * 100
        wk = cum.resample("W-FRI").last().dropna()
        series[nm] = {str(d.date()): _r(v, 1) for d, v in wk.items()}
        now[nm] = {"6개월": _r(cum.iloc[-1], 1), "1개월": _r((s.iloc[-1] / s.iloc[-22] - 1) * 100, 1) if len(s) > 22 else None}
    out["etf"] = {"start": str(start.date()), "series": series, "now": now}

    # 5. ETF 자금 유출입(쌓인 만큼)
    sh_path = DATA / "etf_shares.csv"
    fl = {}
    if sh_path.exists():
        sh = pd.read_csv(sh_path, parse_dates=["date"]).sort_values("date")
        for t, g in sh.groupby("ticker"):
            g = g.dropna(subset=["shares"]).drop_duplicates("date", keep="last")
            if len(g) >= 2:
                d = g.shares.diff() * g.nav.fillna(g.price)
                fl[t] = {"days": int(len(g)), "first": str(g.date.iloc[0].date()), "flow_usd_m": _r(d.sum() / 1e6, 0),
                         "flow_20d_usd_m": _r(d.iloc[-20:].sum() / 1e6, 0), "shares": int(g.shares.iloc[-1])}
            elif len(g) == 1:
                fl[t] = {"days": 1, "first": str(g.date.iloc[0].date()), "shares": int(g.shares.iloc[-1])}
    out["etf_flows"] = fl
    out["story"] = story(df, out, lv, beta)
    return out


# ── 해설(2026-10-15 사용자 논리 구조): 지수 → 통화 → 괴리 → 원인 후보 → 돈의 행방 → 감시 조건. 기계 규칙(사람 판단 없음) ──
IDX = {"y_ks11": "코스피", "y_n225": "닛케이", "y_twii": "대만 가권", "y_hsi": "항셍", "y_sse": "상해"}
CCY = {"y_krw": "원", "y_jpy": "엔", "y_twd": "대만달러", "y_cny": "위안"}            # 모두 달러당 → 강세 = 값 하락
USD_ETF = {"y_ewy": "한국", "y_ewt": "대만", "y_ewj": "일본", "y_ewz": "브라질", "y_ewh": "홍콩", "y_inda": "인도", "y_mchi": "중국"}
WATCH_SIGMA = 1.5          # 감시 조건: 원화 고유 몫 1주 변화가 평소 1주 변화폭의 1.5배 넘게 약세


def _chg(s: pd.Series, months=1, weeks=0) -> float | None:
    s = s.dropna()
    if s.empty:
        return None
    d = s.index[-1] - (pd.DateOffset(weeks=weeks) if weeks else pd.DateOffset(months=months))
    a = s[s.index <= d]
    return None if a.empty else float((s.iloc[-1] / a.iloc[-1] - 1) * 100)


def story(df: pd.DataFrame, out: dict, lv: pd.DataFrame, beta: float) -> dict:
    S = lambda c: df[c].dropna() if c in df else pd.Series(dtype=float)
    steps = []
    # 1. 지수 1개월(자국 통화)
    idx = {nm: _chg(S(c)) for c, nm in IDX.items()}
    idx = {k: v for k, v in idx.items() if v is not None}
    others = [v for k, v in idx.items() if k != "코스피"]
    kr = idx.get("코스피")
    weakest = kr is not None and kr <= min(others or [kr])
    gap = None if kr is None or not others else kr - float(np.mean(others))
    t1 = (f"1개월 코스피 {kr:+.1f}% — " + ("아시아 최약" if weakest else "아시아 중") + f", 다른 지수 평균보다 {gap:+.1f}%p"
          if kr is not None else "지수 자료 없음")
    steps.append({"no": 1, "title": "지수(자국 통화, 1개월)", "verdict": "한국 최약세" if weakest and (gap or 0) <= -5 else ("한국 약세" if (gap or 0) < 0 else "한국 양호"),
                  "text": t1, "values": {k: _r(v, 1) for k, v in idx.items()}})
    # 2. 통화 1개월(+ = 달러 대비 강세)
    ccy = {nm: (lambda x: None if x is None else -x)(_chg(S(c))) for c, nm in CCY.items()}
    ccy = {k: _r(v, 2) for k, v in ccy.items() if v is not None}
    sp = out["fx_split"]["split"]
    w1, w3 = sp.get("1개월", {}), sp.get("3개월", {})
    t2 = (f"원화 1개월 {ccy.get('원', 0):+.1f}% · 3개월 {w3.get('won', 0):+.1f}%(원화 고유 몫 {w3.get('won_own', 0):+.1f}%) — "
          + " · ".join(f"{k} {v:+.1f}%" for k, v in ccy.items() if k != "원"))
    steps.append({"no": 2, "title": "통화(달러 대비, + 강세)", "verdict": "원화 강세" if (w3.get("won_own") or 0) > 2 else ("원화 약세" if (w3.get("won_own") or 0) < -2 else "원화 보합"),
                  "text": t2, "values": ccy})
    # 3. 기대 vs 실제 — 외국인이 많이 팔면 원화는 약해져야 함
    f20 = out["foreign"]["flows"].get("20일") or {}
    heavy_sell = (f20.get("rank3y") or 1) <= 0.2
    heavy_buy = (f20.get("rank3y") or 0) >= 0.8
    own = w3.get("won_own") or 0
    if heavy_sell and own > 0:
        v3, t3 = "괴리", f"외국인 20일 {(f20.get('usd_m') or 0) / 100:+,.0f}억 달러(3년 중 매도 상위 {f20.get('rank3y', 0):.0%})인데 원화는 고유 강세 {own:+.1f}% — 파는 만큼 달러로 바뀌지 않거나, 다른 쪽 원화 매수가 더 큼"
    elif heavy_sell:
        v3, t3 = "정상 반응", f"외국인 대량 순매도와 원화 약세가 같이 나옴 — 매도 자금이 달러로 바뀌어 나가는 중"
    elif heavy_buy and own < 0:
        v3, t3 = "괴리(반대)", "외국인이 사는데 원화는 약함 — 거주자 달러 수요(해외 투자 등)가 더 큼"
    else:
        v3, t3 = "특이 없음", f"외국인 20일 {(f20.get('usd_m') or 0) / 100:+,.0f}억 달러 · 원화 고유 3개월 {own:+.1f}% — 뚜렷한 엇갈림 없음"
    steps.append({"no": 3, "title": "기대 vs 실제", "verdict": v3, "text": t3})
    # 4. 원화 괴리의 원인 후보 — 국제수지(월, 1 – 2개월 늦음): ① 미환전(외국인 매도가 아직 달러 유출로 안 잡힘) ② 거주자 달러 매도
    bop = {}
    for c, nm in (("k_bop_fstk", "외국인 국내 주식투자"), ("k_bop_rstk", "내국인 해외 주식투자"), ("k_bop_oia", "기타투자 자산(거주자 해외 예금 등)"), ("k_ca", "경상수지")):
        s = S(c)
        if len(s) >= 3:
            bop[nm] = {"last": _r(float(s.iloc[-1]), 0), "sum3": _r(float(s.iloc[-3:].sum()), 0), "month": str(s.index[-1].date())[:7]}
    ev1, ev2, counter, pending = [], [], [], []
    fs = bop.get("외국인 국내 주식투자")
    sell_from = (pd.Timestamp(out["foreign"]["date"]) - pd.Timedelta(days=28)).strftime("%Y-%m")
    if fs and heavy_sell:
        if fs["month"] < sell_from:      # 국제수지가 아직 대량 매도 기간을 담지 못함
            pending.append(f"국제수지는 {fs['month']}까지 — {sell_from} 이후 매도는 아직 안 잡힘. 다음 발표에서 외국인 주식투자가 매도 규모만큼 크게 음이면 달러로 나간 것, 작으면 ①(미환전) 쪽")
        elif (fs["last"] or 0) > -abs(f20.get("usd_m") or 0) * 0.3:
            ev1.append(f"국제수지 외국인 주식투자 {fs['month']} {fs['last'] / 100:+,.0f}억 달러 — 같은 기간 매도 규모에 비해 작게 잡힘")
    oia = bop.get("기타투자 자산(거주자 해외 예금 등)")
    if oia and (oia["last"] or 0) < 0:
        ev2.append(f"거주자 해외 예금 등(기타투자 자산) {oia['month']} {oia['last'] / 100:+,.0f}억 달러 — 해외에 둔 달러를 들여옴")
    ca = bop.get("경상수지")
    if ca and (ca["sum3"] or 0) > 0:
        ev2.append(f"경상수지 3개월 {ca['sum3'] / 100:+,.0f}억 달러 흑자")
    ex = S("k_exp")
    if len(ex) >= 15:
        e3 = float(ex.iloc[-3:].sum() / ex.iloc[-15:-12].sum() - 1) * 100
        if e3 > 10:
            ev2.append(f"수출 3개월 전년비 {e3:+.0f}% — 수출 기업 달러 매도 여력")
    rs = bop.get("내국인 해외 주식투자")
    if rs and (rs["last"] or 0) > 0:
        counter.append(f"내국인 해외 주식투자 {rs['month']} {rs['last'] / 100:+,.0f}억 달러 — 원화 약세 쪽 압력(어느 후보의 근거도 아님)")
    lean = ("② 거주자 달러 매도 쪽 근거가 더 많음" if len(ev2) > len(ev1) else ("① 미환전 쪽 근거가 더 많음" if len(ev1) > len(ev2) else "근거가 엇갈림"))
    if pending and not ev1:
        lean += "(①은 국제수지로 아직 확인 불가)"
    steps.append({"no": 4, "title": "원화 괴리의 원인 후보(국제수지 · 월)", "verdict": lean if v3.startswith("괴리") else "참고",
                  "text": "① 외국인 매도 자금 미환전 · ② 국내 거주자(기업)가 해외 달러를 팔아 원화 매수", "ev1": ev1, "ev2": ev2,
                  "counter": counter, "pending": pending, "bop": bop})
    # 5. 돈의 행방 — 달러 기준 국가 ETF 1개월
    usd = {nm: _chg(S(c)) for c, nm in USD_ETF.items()}
    usd = {k: _r(v, 1) for k, v in usd.items() if v is not None}
    if usd:
        order = sorted(usd.items(), key=lambda x: x[1])
        kr5 = usd.get("한국")
        rest = [v for k, v in usd.items() if k != "한국"]
        over = kr5 is not None and order[0][0] == "한국" and kr5 - float(np.mean(rest)) <= -5
        t5 = (f"달러 기준 1개월 한국 {kr5:+.1f}% vs " + " · ".join(f"{k} {v:+.1f}%" for k, v in order[::-1] if k != "한국")
              + (" — 한국만 과도하게 팔림" if over else ""))
        steps.append({"no": 5, "title": "돈의 행방(달러 기준 국가 ETF, 1개월)", "verdict": "한국만 과도 매도" if over else ("한국 약세" if kr5 is not None and kr5 < np.mean(rest) else "한국 양호"),
                      "text": t5, "values": usd, "top": [k for k, _ in order[::-1][:2]]})
    # 6. 감시 조건 — 원화 고유 몫이 1주 사이 급하게 약세로 돌면(외국인 대량 매도 중이면 더 주의) → ① 미환전 자금 이탈 시작 가능성
    wk = lv.resample("W-FRI").last().diff().dropna()
    own_w = -(wk.krw - beta * wk.dxy) * 100                       # + = 원화 고유 강세, %
    sd = float(own_w.iloc[-104:].std()) if len(own_w) > 52 else np.nan
    a = lv[lv.index <= lv.index[-1] - pd.Timedelta(days=7)]
    now_w = float(-((lv.krw.iloc[-1] - a.krw.iloc[-1]) - beta * (lv.dxy.iloc[-1] - a.dxy.iloc[-1])) * 100) if len(a) else np.nan
    trig = bool(np.isfinite(sd) and np.isfinite(now_w) and now_w <= -WATCH_SIGMA * sd)
    v6 = ("발동 — 외국인 자금 이탈 가능성" if trig and heavy_sell else "발동" if trig else "아직 아님")
    past = ("과거(9.340): 원화 고유 급약세 뒤 13주 코스피는 평소와 비슷하거나 나았음, 외국인 대량 매도와 겹친 때는 오히려 반등 쪽(사건 적음). "
            "\"괴리 상태에서 발동\"은 2016 – 2번뿐이라 판단 불가 — 조심 신호로 쓰지 않음")
    t6 = (f"원화 고유 몫 1주 {now_w:+.2f}%(평소 1주 변화폭 {sd:.2f}%, 문턱 {-WATCH_SIGMA * sd:+.2f}%) — "
          + ("외국인 대량 매도 중 원화 급약세 전환 = 미환전 자금이 나가기 시작했을 수 있음" if trig and heavy_sell else
             "원화 고유 급약세 전환" if trig else "원화가 아직 버티는 중") + ". " + past)
    steps.append({"no": 6, "title": "감시 조건(원화 고유 급약세 전환)", "verdict": v6, "text": t6, "trigger": trig,
                  "now_w": _r(now_w, 2), "sd_w": _r(sd, 2)})
    # ── 사용자 5단계(2026-10-15): 1 무슨 일 → 2 누가 무엇을 팔거나 샀나 → 3 환율(매크로)에 영향 줄 수준인가
    #    → 4 영향을 줬다면 경고 / 5 안 줬다면 주요로 볼 것. 4 · 5는 3의 판정에 따라 하나만 나온다.
    st1, st2, st3, st4 = steps[0], steps[1], steps[2], steps[3]
    st5 = next((s for s in steps if s["no"] == 5), None)
    kr_usd = (st5 or {}).get("values", {}).get("한국") if st5 else None
    over = bool(st5 and st5["verdict"] == "한국만 과도 매도")
    grp = out.get("groups", {})
    m = lambda k: (grp.get(k) or {}).get("usd_m") or 0
    # 1. 무슨 일
    if st1["verdict"] == "한국 최약세" or over:
        w1, c1 = "한국만 크게 빠졌다", f"코스피 1개월 {kr:+.1f}%로 아시아 최약" + (f", 달러 기준 {kr_usd:+.1f}%" if kr_usd is not None else "")
    elif st1["verdict"] == "한국 약세":
        w1, c1 = "한국이 다른 아시아보다 약했다", f"코스피 1개월 {kr:+.1f}%"
    else:
        w1, c1 = "한국은 다른 아시아만큼 버텼다", f"코스피 1개월 {kr:+.1f}%"
    # 2. 누가 무엇을 — 20일 달러 누적으로 가장 많이 판 쪽 · 받은 쪽
    who = sorted(((k, m(k)) for k in ("외국인", "개인", "기관", "기타법인")), key=lambda x: x[1])
    seller, buyer = who[0], who[-1]
    if heavy_sell:
        w2 = f"외국인이 대량으로 팔고 {buyer[0]}이 받았다" if buyer[1] > 0 else "외국인이 대량으로 팔았다"
    elif heavy_buy:
        w2 = f"외국인이 대량으로 사고 {seller[0]}이 팔았다" if seller[1] < 0 else "외국인이 대량으로 샀다"
    else:
        w2 = f"{seller[0]}이 가장 많이 팔고 {buyer[0]}이 가장 많이 샀다(큰 쏠림은 없음)"
    c2 = " · ".join(f"{k} {v / 100:+,.0f}억 달러" for k, v in sorted(((k, m(k)) for k in ("외국인", "개인", "기관", "기타법인")), key=lambda x: x[1]))
    c2 += f" (기관 중 연기금 {m('연기금') / 100:+,.0f}억) — 코스피 20일 누적, {out['foreign']['date']}까지"
    # 3. 환율(매크로)에 영향 줄 수준인가 — 외국인 대량 매도가 원화 약세로 번졌나
    fx1, fx3 = out["fx_split"]["split"].get("1개월", {}), out["fx_split"]["split"].get("3개월", {})
    won1, won3 = (fx1.get("won") or 0), (fx3.get("won") or 0)
    own1 = fx1.get("won_own") or 0
    if heavy_sell and (trig or own1 <= -2):
        impact, w3_ = True, "원화 약세로 번졌다"
        c3 = f"원화 1개월 {won1:+.1f}%(원화 고유 {own1:+.1f}%)" + (", 1주 급약세" if trig else "")
    elif heavy_sell and own > 0:
        impact, w3_ = False, "환율로는 번지지 않았다 — 원화가 오히려 강하다"
        c3 = f"원화 3개월 {won3:+.1f}%, 그중 원화 고유 몫 {own:+.1f}%. " + (
            "받쳐 주는 힘: " + " · ".join(e.split(" — ")[0] for e in ev2) if ev2 else "받쳐 주는 힘은 아직 근거 부족")
        if pending:
            c3 += ". 외국인이 판 돈이 원화로 남아 있는지는 국제수지로 아직 확인 불가"
    elif heavy_sell:
        impact, w3_ = False, "환율 영향은 아직 작다"
        c3 = f"원화 1개월 {won1:+.1f}% · 3개월 {won3:+.1f}%"
    else:
        impact, w3_ = False, "환율에 영향 줄 규모의 매매는 아니다"
        c3 = f"외국인 20일 {(f20.get('usd_m') or 0) / 100:+,.0f}억 달러 · 원화 3개월 {won3:+.1f}%"
    # 4 / 5
    if impact:
        w45, q45 = "원화 약세가 이어지면 외국인 매도 자금이 달러로 빠져나가는 중일 수 있음", "영향을 줬다면 — 경고"
        c45 = ("볼 것: 원화 약세 지속 · 외국인 매도 지속 · 수입물가. "
               "다만 과거(9.340)엔 원화 급약세와 외국인 대량 매도가 겹친 뒤 13주 코스피가 오히려 반등 쪽이었음(사건 적음) — 판단 신호로 쓰지 않음")
    else:
        watch, short = [], []
        if heavy_sell:
            short.append("원화 급약세 전환")
            watch.append(f"원화가 1주 사이 급하게 약해지는지(문턱 원화 고유 {-WATCH_SIGMA * (sd if np.isfinite(sd) else 0):+.1f}%, 지금 {now_w:+.1f}%)")
        if pending:
            nxt = (pd.Timestamp(bop["외국인 국내 주식투자"]["month"] + "-01") + pd.DateOffset(months=1)).strftime("%Y-%m") if "외국인 국내 주식투자" in bop else "다음 달"
            watch.append(f"{nxt} 국제수지 외국인 주식투자 — 매도 규모만큼 크게 음이면 돈이 실제로 나간 것")
            short.append(f"{nxt[5:].lstrip('0')}월 국제수지 외국인 주식투자")
        if ev2:
            watch.append("원화를 받쳐 준 수출 · 해외 달러 회수가 계속되는지(수출 · 기타투자 자산)")
            short.append("수출 달러 유입 지속")
        if over:
            watch.append("달러 기준 한국 ETF가 다른 나라를 다시 따라잡는지")
        w45, q45 = ("다음에 볼 것: " + " · ".join(short[:3]) if short else "다음에 볼 것: 특이 사항 없음"), "영향이 없다면 — 주요로 볼 것"
        c45 = " · ".join(watch) if watch else "특이 사항 없음"
    parts = [w1, w2, w3_, w45]
    lead_words = " → ".join(parts)
    lead = " → ".join([f"{w1}({c1})", w2, f"{w3_}", w45])
    para = f"{w1}({c1}). {w2}. {w3_}. " + (f"경고: {c45}" if impact else f"주요로 볼 것: {c45}") + "."
    story_steps = [
        {"no": 1, "q": "무슨 일이 있었나?", "verdict": w1, "text": f"{st1['text']}. " + (st5["text"] if st5 else ""), "charts": ["idx", "etf"]},
        {"no": 2, "q": "누가 무엇을 팔거나 샀나?", "verdict": w2, "text": c2 + (f" · 외국인 {'순매수' if out['foreign']['streak'] > 0 else '순매도'} {abs(out['foreign']['streak'])}일째" if out["foreign"].get("streak") else "")},
        {"no": 3, "q": "그래서 환율(매크로)에 영향을 줄 수준인가?", "verdict": w3_, "text": c3, "impact": impact,
         "ev1": ev1, "ev2": ev2, "counter": counter, "pending": pending},
        {"no": 4 if impact else 5, "q": q45, "verdict": w45, "text": c45, "warn": impact},
    ]
    steps = story_steps
    # 그림용: 자국 통화 지수 1개월(일별, 첫날 = 0)
    ser = {}
    for c, nm in IDX.items():
        s = S(c)
        s = s[s.index >= s.index[-1] - pd.DateOffset(months=1)] if len(s) else s
        if len(s) > 3:
            ser[nm] = {str(d.date()): _r(float((v / s.iloc[0] - 1) * 100), 1) for d, v in s.items()}
    return {"steps": steps, "chain": lead, "chain_words": lead_words, "paragraph": para, "idx_series": ser,
            "note": "기계 규칙 해설(사람 판단 없음). 1 – 5단계는 지금 상태 설명, 6단계 감시 조건은 9.340에서 \"조심\" 신호가 아니었음(이후 나쁘지 않음)."}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    r = build()
    (DATA / "foreign_view.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: r[k] for k in ("usd_kospi", "fx_split", "foreign")}, ensure_ascii=False, indent=1))
    print("ETF 6개월:", {k: v["6개월"] for k, v in r["etf"]["now"].items()}, "· 자금 유출입:", r["etf_flows"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
