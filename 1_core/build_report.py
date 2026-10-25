"""exchange 정리본(2 국내 · 3 해외 · 4 매크로 · 5 뉴스)을 읽어 코어 리포트 한 편(HTML + 텔레그램 문안)을 만든다.

판단 문장 = 장세 줄 · 보유 판단 · 검증된 참고 신호 줄(VM-SPC Core 검증 규칙만).
검증 전 자료(해외 · 매크로 · 뉴스 · 테마 숫자)는 아래 "자세히"에 서술로만 둔다.

  python build_report.py --date 2026-10-08 --slot pm          # HTML · 텔레그램 문안 만들기(전송 없음)
  python build_report.py --date 2026-10-08 --slot pm --send   # 만든 뒤 텔레그램 전송(시범본 확인 뒤에만)
  python build_report.py --slot am [--send]                   # 글로벌 아침 리포트 — 기준일 = 3_us latest(미국 현지 거래일)
  python build_report.py --slot am --weekend [--send]         # 월요일 주말 정리판(2026-10-12) — 금요일 미국 마감 + 토 – 월 아침 뉴스 묶음

  ... --warn "core: screen candidates · 2_kr_market export"   # 예약 스크립트가 실패한 단계를 넘김 → 맨 위 ⚠ 줄

--send는 전송이 실패해도 0으로 끝난다(예약 스크립트가 멈추지 않게 · 실패는 stderr와 exchange 정리본에 남김).
--send 때 나간 참고 신호를 signal_log.py로 기록하고, 앞선 신호의 결과를 채워 접힌 칸 "참고 신호 근거"에 실전 성과를 붙인다.

결과: results/report_{date}_{slot}.html · results/report_{date}_{slot}.txt
      ../exchange/1_core/{date}/summary_{slot}.json(+ .md) · ../exchange/1_core/latest.json
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXCHANGE = ROOT.parent / "exchange"
RESULTS = ROOT / "results"
KST = timezone(timedelta(hours=9))
ROLES = ("2_kr_market", "3_us_market", "4_macro", "5_news")
ROLE_NAME = {"2_kr_market": "국내 시장", "3_us_market": "해외 시장", "4_macro": "매크로", "5_news": "뉴스"}

sys.path.insert(0, str(ROOT))
from report_theme import GOLDEN_THEME  # noqa: E402
from core_charts import charts_html  # noqa: E402


# ── 정리본 읽기 ──────────────────────────────────────────────────────────

def _dates(role: str) -> list[str]:
    d = EXCHANGE / role
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir() and len(p.name) == 10 and p.name[4] == "-")


def _summary_file(folder: Path, slot: str) -> Path | None:
    for name in (f"summary_{slot}.json", "summary_pm.json", "summary_am.json", "summary.json"):
        if (folder / name).exists():
            return folder / name
    return None


def _next_day(d: str) -> str:
    return (_date.fromisoformat(d) + timedelta(days=1)).isoformat()


def role_cutoff(role: str, target: str, slot: str, send: str | None = None) -> tuple[str, bool]:
    """역할별로 쓸 수 있는 가장 늦은 날짜(포함 여부)를 돌려준다.

    pm(국내 마감, 기준일 D = 한국 거래일): 국내 · 뉴스 · 매크로는 D 이하, 해외는 D 미만
      (D 날짜 미국 마감은 D 밤에 끝남).
    am(글로벌 아침, 기준일 D = 미국 현지 거래일): 해외는 D 이하, 국내는 D 이하(어제 국내 마감),
      뉴스 · 매크로는 리포트를 보내는 한국 날짜(send — 평소 D 다음 날, 주말판은 월요일) 이하.
    """
    if slot == "pm":
        return target, role != "3_us_market"
    if role in ("5_news", "4_macro"):
        return send or _next_day(target), True
    return target, True


def load_role(role: str, target: str, slot: str, send: str | None = None) -> dict | None:
    """기준일에 맞는 정리본을 고른다(role_cutoff 이하 가장 최근 날짜).
    맞는 날짜가 없으면 latest.json을 쓰되 `late`(기준일보다 늦은 자료) 표시를 붙인다.
    """
    ds = _dates(role)
    if not ds:
        return None
    cut, incl = role_cutoff(role, target, slot, send)
    ok = [d for d in ds if (d <= cut if incl else d < cut)]
    late = False
    if ok:
        pick = ok[-1]
    else:
        lj = EXCHANGE / role / "latest.json"
        pick = json.loads(lj.read_text(encoding="utf-8"))["date"] if lj.exists() else ds[-1]
        late = True
    f = _summary_file(EXCHANGE / role / pick, slot)
    if f is None:
        return None
    s = json.loads(f.read_text(encoding="utf-8"))
    s["_file"] = f
    s["_late"] = late
    s["_items"] = {it["key"]: it for it in s.get("items", [])}
    return s


def _side(s: dict, name: str):
    p = s["_file"].parent / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# ── 문구 만들기 ──────────────────────────────────────────────────────────

def _r(t: str) -> str:
    return (t or "").replace("~", "–")      # 범위는 "–"로(공통 지침)


def _md(d: str) -> str:
    return d[5:].replace("-", "/") if d and len(d) >= 10 else d


TITLE = {"pm": "국내 마감 리포트", "am": "글로벌 아침 리포트"}
# 판단 안내는 맨 위 한 줄만(2026-10-10 사용자: "판단은 개별로 알아서 한 줄만 가장 위에 — 너무 자주 반복") — 칸마다 붙이지 않는다
TOP_LINE = "※ 판단은 검증된 규칙만 · 매매 결정은 각자"   # 2026-10-11 VM-core 점검(사용자 승인) — 본문의 판단 줄과 맞춤

ETF_MIN_HIT = 0.60   # VM-SPC Core 텔레그램 요약과 같은 문턱 — 이 이상이면서 평소 비율보다 높을 때만 한 줄


def data_warning(r: dict) -> str:
    """맨 위 ⚠ 한 줄(없으면 "") — 예약 스크립트가 넘긴 실패 단계 + 기준일과 다른 정리본(2026-10-11: 실패해도 정상처럼 나가지 않게)."""
    W = []
    exp = ({"2_kr_market": r["date"], "5_news": r["date"]} if r["slot"] == "pm"
           else {"3_us_market": r["date"], "2_kr_market": None})
    for role, want in exp.items():
        s = r["srcs"].get(role)
        if s is None:
            W.append(f"{ROLE_NAME[role]} 정리본 없음")
        elif want and s["date"] != want:
            W.append(f"{ROLE_NAME[role]} {_md(s['date'])} 기준")
    t = r.get("themes") or {}
    if r.get("regime") is not None and not t.get("groups"):
        W.append("테마 표 없음")
    msg = []
    if r.get("warn"):
        msg.append(f"오늘 실패: {r['warn']}")
    if W:
        msg.append(" · ".join(W))
    return ("⚠ " + " — ".join(msg) + " (일부 내용이 전날 기준일 수 있음)") if msg else ""


def build(target: str, slot: str, weekend: bool = False, send: str | None = None) -> dict:
    """weekend = 월요일 주말 정리판 — send(발송일, 기본 오늘)까지의 뉴스 · 매크로를 읽는다."""
    send = send or (_date.today().isoformat() if weekend else (_next_day(target) if slot == "am" else target))
    kr = load_role("2_kr_market", target, slot)
    us = load_role("3_us_market", target, slot)
    mc = load_role("4_macro", target, slot, send)
    nw = load_role("5_news", target, slot, send)
    srcs = {"2_kr_market": kr, "3_us_market": us, "4_macro": mc, "5_news": nw}

    out: dict = {"date": target, "slot": slot, "srcs": srcs, "weekend": weekend, "send": send}

    # 1. 장세 · 전략(판단 문장은 여기서만)
    if kr is None:
        out["regime"] = None
    else:
        reg = kr["_items"].get("regime", {})
        rv = reg.get("value") or {}
        mr = kr["_items"].get("mass_recovery", {})
        mv = mr.get("value") or {}
        cand = _side(kr, "candidates.json") or {}
        out["regime"] = {
            "state": rv.get("state", "?"), "days": rv.get("days"),
            "strategy": cand.get("strategy") or rv.get("favor", ""),
            "favor": _r(rv.get("favor", "")), "nums": _r(rv.get("nums", "")),
            "text": reg.get("text", ""), "why": _r(cand.get("why", "")),
            "mass_today": bool(mv.get("today")), "mass_text": mr.get("text", ""), "mass_ref": mr.get("ref", ""),
        }
        out["candidates"] = cand.get("candidates", [])
        hold_codes = {h.get("code") for h in (_side(kr, "holdings.json") or {}).get("holdings", []) if h.get("hold")}
        out["observe"] = [o for o in cand.get("observe", []) if o.get("code") not in hold_codes]   # 보유와 관찰에 두 번 나오지 않게
        hj = _side(kr, "holdings.json") or {}
        hs = hj.get("holdings", [])
        out["holdings"] = [h for h in hs if h.get("hold")]
        out["watch"] = [h for h in hs if not h.get("hold")]
        out["hold_groups"] = hj.get("groups", [])
        fl = kr["_items"].get("flows")
        out["flows"] = fl["text"] if fl else ""
    # 테마 흐름(참고) — 가격은 2 국내 themes.json, 뉴스 언급은 5 뉴스 theme_news
    out["themes"] = (_side(kr, "themes.json") or {}) if kr else {}
    out["theme_news"] = {x["theme"]: x for x in ((nw["_items"].get("theme_news") or {}).get("value") or [])} if nw else {}

    # 3. 참고
    ref: list[dict] = []
    if us:
        uc = us["_items"].get("us_close", {})
        uv = uc.get("value") or {}
        idx = " · ".join(f"{k.split('(')[-1].rstrip(')')} {v:+.2f}%" for k, v in uv.items() if "(" in k)
        # ETF 다음 날 방향 예측은 본문에서 뺌(2026-10-10 사용자: "만들다 만 거의 의미 없는 데이터") — 접힌 칸에 한 줄만
        etf = us["_items"].get("etf_forecast", {}).get("value") or []
        good = [e for e in etf if e.get("hit_rate") is not None and e["hit_rate"] >= ETF_MIN_HIT
                and e["hit_rate"] > (e.get("usual") or 0)]
        out["etf_note"] = ("ETF 예측(VM-SPC Global): " + (" · ".join(
            f"{e['etf']} {e['pred']}(적중 {e['hit_rate']:.0%} · 평소 {e['usual']:.0%})" for e in good) if good else "의미 있는 신호 없음"))
        out["us_themes"] = _side(us, "us_themes.json") or {}
        out["us_close"] = uv
        sec = us["_items"].get("us_sectors", {}).get("text", "")
        mov = us["_items"].get("us_movers", {}).get("text", "")
        ref.append({"k": "해외", "d": us["date"], "late": us["_late"],
                    "t": f"미국 {_md(us['date'])} 마감 {idx}", "t2": f"섹터: {sec}" if sec else "",
                    "t3": f"큰 움직임: {mov}" if mov else "", "full": uc.get("text", "")})
    if mc:
        out["quarter"] = (mc["_items"].get("quarter") or {}).get("value") or {}
        out["macro"] = {k: v for it in mc.get("items", []) if it.get("key") != "quarter" and isinstance(it.get("value"), dict)
                        for k, v in it["value"].items()}
        ref.append({"k": "매크로", "d": mc["date"], "late": mc["_late"], "t": mc.get("headline", ""), "t2": "", "full": ""})
        out["checklist"] = _side(mc, "checklist.json") if "checklist" in mc["_items"] else None
        out["foreign_view"] = _side(mc, "foreign_view.json") if "foreign_view" in mc["_items"] else None
        out["liquidity"] = _side(mc, "liquidity_monitor.json") if "liquidity" in mc["_items"] else None
    if nw:
        it = nw["_items"]
        iss = (it.get("issues", {}).get("value") or [])[:3]
        ub = it.get("us_brief")
        # 아침: 모닝 시황은 발송일(D+1) 아침 정리본에 있을 때만 — 토요일 · 늦게 올라온 날 전날 시황이 실리지 않게
        if slot == "am" and not (nw["date"] == send and nw["_file"].name == "summary_am.json"):
            ub = None
        if ub and not ub.get("text"):                       # 5_news는 시황이 없어도 빈 항목을 낸다 — 빈칸 대신 "아직 없음"
            ub = None
        out["issues_all"] = it.get("issues", {}).get("value") or []          # 주말판 "주말 뉴스" 칸(상위 10)
        out["holdings_news"] = it.get("holdings_news", {}).get("value") or []
        out["reports"] = it.get("reports", {})
        ref.append({"k": "뉴스", "d": nw["date"], "late": nw["_late"],
                    "t": "이슈 " + " · ".join(f"{x['issue']}({x['channels']})" for x in iss),
                    "t2": "", "issues": iss,
                    "us_brief": ub, "kr_close": it.get("kr_close"),
                    "reports": it.get("reports", {}).get("text", ""),
                    "holdings_news": it.get("holdings_news", {}).get("text", "")})
    out["ref"] = ref
    nf = (us["_items"].get("night_futures") if us else None) or (nw["_items"].get("night_futures") if nw else None)
    out["night_futures"] = nf["text"] if nf else ""
    return out


def _holding_line(h: dict) -> tuple[str, str]:
    head = _r(h.get("head", ""))
    body = head.split("→", 1)[1].strip() if "→" in head else head
    body = body.replace("(검증됨)", "").strip()
    return body, h.get("verdict", "")


def _holding_split(r: dict) -> tuple[list, list]:
    """보유 종목을 (판단이 있는 것, 판단 없음)으로 나눈다 — [(이름, 판단 문구, 등급)]."""
    acts, rest = [], []
    for h in r.get("holdings", []):
        body, v = _holding_line(h)
        (acts if v == "검증됨" or "판단 없음" not in body else rest).append((h["name"], body, v))
    return acts, rest


# ── 보유 · 관심 수급 경고(VM-SPC Core 9.322 · 9.325 · 9.326, 2026-10-14 사용자 승인) ──────────────────────
# 연기금 연속 순매수 5일+ · 기관합계 20일 중 15일+ 순매수 = 경고(검증됨, 이후 1년까지 시장보다 약함). 공매도 비중 상위 10% = 참고(9.325 약함).
# 값은 2_kr holdings.json 종목별 flow(flow_flags.py). 투자자별 기준일이 리포트 기준일과 다르면 쓰지 않음.
FLOW_WARN_TAIL = "이후 시장보다 약한 경향"


def flow_warn(h: dict, day: str) -> tuple[list[str], list[str]]:
    """(경고 문구, 참고 문구) — 해당 없으면 빈 목록."""
    f = h.get("flow") or {}
    W, R = [], []
    if f.get("flow_date") == day:
        if f.get("pension_flag"):
            W.append(f"연기금 {f['pension_streak']}일 연속 순매수")
        if f.get("inst_flag"):
            W.append(f"기관 20일 중 {f['inst_days20']}일 순매수")
    if f.get("short_flag"):
        R.append(f"공매도 비중 상위 {max(1, round((1 - f['short_rank']) * 100))}%")
    if f.get("overhang_flag"):
        R.append(f"현재가 바로 위 매물대 두꺼움(지난 1년 거래량 {f['overhang']:.0%})")
    return W, R


def _flow_kind(h: dict, day: str) -> str:
    """텔레그램용 단어(숫자 없음)."""
    f = h.get("flow") or {}
    if f.get("flow_date") != day:
        return ""
    return " · ".join(w for w, ok in (("연기금 연속 매수", f.get("pension_flag")), ("기관 꾸준 매수", f.get("inst_flag"))) if ok)


def flow_evidence_html(r: dict) -> str:
    """접힌 칸 '수급 경고 근거' — 해당 종목이 하나라도 있을 때만."""
    hs = r.get("holdings", []) + r.get("watch", [])
    rows = [(h, *flow_warn(h, r["date"])) for h in hs]
    rows = [x for x in rows if x[1] or x[2]]
    if not rows:
        return ""
    kr = r["srcs"].get("2_kr_market") or {}
    sd = ((kr.get("_items") or {}).get("flow_flags") or {}).get("value", {}).get("short_date")
    P = ['<details class="fold"><summary>수급 경고 근거</summary><table><tr><th>종목</th><th>연기금 연속</th><th>기관 20일 중 순매수</th><th>공매도 비중 20일</th><th>매물대</th></tr>']
    for h, _, _ in rows:
        f = h["flow"]
        sp = f"{f['short_pct20']}% · 상위 {max(1, round((1 - f['short_rank']) * 100))}%" if "short_pct20" in f else "–"
        ov = f"{f['overhang']:.0%} · 상위 {max(1, round((1 - f['overhang_rank']) * 100))}%" if "overhang" in f else "–"
        P.append(f"<tr><td>{_e(h['name'])}{'' if h.get('hold') else ' (관심)'}</td><td>{_e(f.get('pension_streak', '–'))}일</td>"
                 f"<td>{_e(f.get('inst_days20', '–'))}일 · 합 {f.get('inst_sum20', 0) / 100:+,.0f}억</td><td>{_e(sp)}</td><td>{_e(ov)}</td></tr>")
    P.append("</table>")
    P.append("<p>경고 = 연기금 연속 순매수 5일 이상 · 기관합계 20일 중 15일 이상 순매수(20일 합 > 0) — 보유 · 관찰 주의용, 매수 신호 아님.</p>")
    P.append(f"<p>참고 = 공매도 거래대금 비중 20일 평균 상위 10%(기준일 {_e(sd or '–')}) · 매물대 = 250일 거래량 중 현재가 위 0 – 20% 구간 비중 상위 10%.</p>"
             "<p>투자자별 값은 16:00 기준 KRX 잠정치일 수 있음.</p></details>")
    return "".join(P)


def _kr_brief(r: dict) -> tuple[str, str]:
    """아침 리포트용 어제 국내 두 줄(장세 · 전략 / 보유 판단)."""
    g = r.get("regime")
    kr = r["srcs"].get("2_kr_market")
    if g is None or kr is None:
        return "국내 시장 정리본 없음 — 장세 판단 못 함", ""
    late = " ※기준일 뒤 자료" if kr["_late"] else ""
    l1 = f"코스피 {g['state']} {g['days']}일째 — {g['strategy']} ({_md(kr['date'])} 마감{late})"
    acts, rest = _holding_split(r)
    parts = [f"{n} {b}" + (f" [{v}]" if v else "") for n, b, v in acts]
    if rest:
        parts.append(f"그 밖의 {len(rest)}종목 판단 없음")
    return l1, "보유: " + " · ".join(parts) if parts else "보유 종목 없음"


THEME_ROWS, THEME_NEWS_EXTRA, THEME_NEWS_MIN = 6, 2, 2   # 표: 평균 등락 상위 6 + 뉴스 많은 테마(채널 2 이상) 최대 2 더


def _theme_pick(r: dict) -> tuple[list, list]:
    """(표에 넣을 테마, 약한 테마 2) — 가격 상위 + 뉴스 언급이 많은데 상위에 없는 테마."""
    gs = (r.get("themes") or {}).get("groups") or []
    if not gs:
        return [], []
    rows = gs[:THEME_ROWS]
    seen = {g["theme"] for g in rows}
    news = sorted((x for x in r.get("theme_news", {}).values() if x["channels"] >= THEME_NEWS_MIN and x["theme"] not in seen),
                  key=lambda x: (-x["channels"], -x["msgs"]))[:THEME_NEWS_EXTRA]
    by = {g["theme"]: g for g in gs}
    rows += [by[x["theme"]] for x in news if x["theme"] in by]
    weak = [g for g in gs[::-1][:2] if g["theme"] not in {x["theme"] for x in rows}]
    return rows, weak


# ── 핵심 요약 문장(2026-10-10 사용자: "첫 요약은 간단한 문장으로, 숫자 나열은 아래로") ─────────────────
# 숫자는 괄호 안에 한두 개만. 기준값은 화면 문구용 — 판단 규칙 아님.
MKT_FLAT, SEMI_GAP = 0.3, 1.0                       # 지수 ±0.3% 안 = 보합, 반도체가 시장과 1%p 이상 벌어지면 따로 언급
MACRO_MOVE = {"US_10Y": 5.0, "USDKRW": 0.5, "WTI": 2.0, "VIX": 10.0}   # 이만큼 움직이면 문장에 넣음(bp · % · % · %)


def _names(xs: list, k: str = "theme", n: int = 3) -> str:
    return " · ".join(x[k] for x in xs[:n])


def _josa(word: str, a: str, b: str) -> str:
    """받침 있으면 a, 없으면 b(이/가 · 은/는). 한글이 아니면 b."""
    c = word.rstrip()[-1:] if word else ""
    return a if c and "가" <= c <= "힣" and (ord(c) - 0xAC00) % 28 else b


def _core_us(r: dict) -> list[str]:
    S = []
    uv = r.get("us_close") or {}
    spy, qqq, soxx = uv.get("S&P500(SPY)"), uv.get("나스닥100(QQQ)"), uv.get("반도체(SOXX)")
    if spy is not None and qqq is not None:
        m = (spy + qqq) / 2
        d = 1 if m >= MKT_FLAT else -1 if m <= -MKT_FLAT else 0
        idx = f"(S&P500 {spy:+.1f}% · 나스닥100 {qqq:+.1f}%)"
        if soxx is not None and abs(soxx - m) >= SEMI_GAP:
            semi_up = soxx > m
            stem = {1: "올랐", -1: "내렸", 0: "보합이었"}[d]
            joint = "지만" if (d == 1 and not semi_up) or (d == -1 and semi_up) else "고"
            semi = ("강했습니다" if semi_up else "약했습니다") if d == 0 else (
                "더 강했습니다" if semi_up and d > 0 else "강했습니다" if semi_up else "더 약했습니다" if d < 0 else "약했습니다")
            S.append(f"미국 증시는 {stem}{joint}{idx} 반도체는 {semi}(SOXX {soxx:+.1f}%).")
        else:
            S.append(f"미국 증시는 {({1: '올랐습니다', -1: '내렸습니다', 0: '보합이었습니다'})[d]}{idx}.")
    ss = (r.get("us_themes") or {}).get("sectors") or []
    if ss:
        weak = ss[::-1][:2]
        sw, ww = _names(ss), _names(weak, n=2)
        S.append(f"{sw}{_josa(sw, '이', '가')} 강했고, {ww}{_josa(ww, '은', '는')} 약했습니다.")   # 국내 연관은 아래 신호 줄(us_signal_lines)이 맡음
    return S


# ── 매크로 체크리스트(4_macro checklist.json, 2026-10-15 사용자 결정 · 참고) ──────────────────────
# 흐름 방식(VM-SPC Core 9.334 · 9.335, 약함 개선안): 흐름 부담 0 – 100(50 중립)과 2016 – 월말 상위 · 하위 1/3로 높음 · 중간 · 낮음.
# 검증 전이라 판단 문장에 섞지 않고 참고로만. 아침 리포트(주말판 포함)에만.
CK_COLOR = {"G": "var(--up)", "A": "var(--warn)", "R": "var(--dn)", "B": "var(--dim)"}
CK_SHORT = {"1": "물가", "2": "정책 · 장기금리", "3": "신용", "4": "금융여건", "5": "유동성", "6": "해외국채",
            "7": "에너지", "8": "환율", "9": "위험 온도", "10": "반도체 · AI", "11": "한국 금리 · 신용", "12": "경기 · 불확실성", "15": "AI 투자 · 인프라", "16": "AI · 저신용 신용"}


def _ck_high(ck: dict) -> list[str]:
    return [CK_SHORT.get(k["no"], k["title"]) for k in ck["cards"] if k["grade"] == "R"]


def _ck_level(ck: dict) -> str:
    lv = ck.get("level")
    return {"높음": "부담 높음", "낮음": "부담 낮음", "중간": "부담 중간"}.get(lv, "")


# 2026-10-15 사용자: "매크로 부담 점수를 중심으로" — 점수(0 – 100, 50 중립, 낮을수록 좋음) · 구간 · 6개월 흐름(9.336) · 카드별 기여(점)
def _ck_contrib(ck: dict) -> list[tuple[str, float]]:
    """카드별 기여 = 50 ÷ (점수 체크 수) × 그 카드 신호 합 × 척도(scale_k) — 모두 더하면 점수 − 중립(0 · 100에 붙은 날은 조금 어긋남)."""
    sc = [(k["no"], c["signal"]) for k in ck["cards"] for c in k["checks"] if c.get("role") == "score" and "signal" in c]
    if not sc:
        return []
    w = 50 / len(sc) * ck.get("scale_k", 1)
    out = {}
    for no, s in sc:
        out[no] = out.get(no, 0) + w * s
    return sorted(((CK_SHORT.get(no, no), round(v, 1)) for no, v in out.items()), key=lambda x: -x[1])


def _ck_move(ck: dict) -> str:
    p3 = ck.get("burden_6m_ago")
    if p3 is None:
        return ""
    d = ck["burden"] - p3
    return "올라가는 중" if d >= 7 else ("내려가는 중" if d <= -7 else "제자리")


def _core_checklist(r: dict) -> str:
    ck = r.get("checklist")
    if not ck or ck.get("burden") is None:
        return ""
    cb = _ck_contrib(ck)
    up = [f"{n} {v:+.0f}" for n, v in cb if v >= 1][:3]
    dn = [f"{n} {v:+.0f}" for n, v in cb[::-1] if v <= -1][:2]
    p3 = ck.get("burden_6m_ago")
    ch = ck.get("change") or {}
    db = ch.get("d_burden")
    ai = next((k for k in ck.get("ref_cards", []) if k["grade"] in "GAR"), None)
    return (f"매크로 부담 점수 {ck['burden']:.0f}/100 — {_ck_level(ck)} 구간"
            + (f"(6개월 전 {p3:.0f}, {_ck_move(ck)}" + (f" · 직전 대비 {db:+.0f}" if db is not None else "") + ")" if p3 is not None else "")
            + ", 낮을수록 좋음."
            + (f" 올린 쪽: {' · '.join(up)}" if up else "") + (f" / 내린 쪽: {' · '.join(dn)}" if dn else "") + "."
            + (f" AI 투자 · 인프라(참고) {ai['word']}." if ai else "")
            + (f" {(ck.get('credit_alert') or {}).get('text')}." if (ck.get("credit_alert") or {}).get("on") else "")
            + (f" {ck['divergence'].split(' — ')[0]}: 상태와 1주 가격 반응 비교." if ck.get("divergence", "").startswith("괴리") else ""))


def _tg_checklist(r: dict) -> str:
    """텔레그램 — 단어만(숫자 없음): 구간 · 흐름 · 가장 올린 카드."""
    ck = r.get("checklist")
    if not ck or not ck.get("level"):
        return ""
    up = [n for n, v in _ck_contrib(ck) if v >= 1][:3]
    mv = _ck_move(ck)
    worse = [CK_SHORT.get(c["no"], c["title"]) for c in (ck.get("change") or {}).get("cards", []) if c["arrow"] == "▲"][:2]
    ai = next((k for k in ck.get("ref_cards", []) if k["grade"] in "GAR"), None)
    return (f"· 매크로 부담 점수 {ck['level']}" + (f"({mv})" if mv else "") + (f" — {', '.join(up)}" if up else "")
            + (f" · 직전보다 나빠짐: {', '.join(worse)}" if worse else "")
            + (f" · AI 투자 · 인프라(참고) {ai['word']}" if ai else "")
            + (" · AI · 저신용 쪽 신용 압박(참고)" if (ck.get("credit_alert") or {}).get("on") else ""))


def _ck_gauge(ck: dict) -> str:
    """0 – 100 막대(낮음 · 중간 · 높음 구간)와 지금 위치, 최근 24개월 월말 점수 선."""
    b, (lo, hi), nu = ck["burden"], (ck.get("cut") or (None, None)), ck.get("neutral", 50)
    W = 320
    x = lambda v: max(0, min(W, v / 100 * W))
    zone = "" if lo is None else (f'<rect x="0" y="8" width="{x(lo):.0f}" height="10" fill="var(--up)" opacity=".35"/>'
                                  f'<rect x="{x(lo):.0f}" y="8" width="{x(hi) - x(lo):.0f}" height="10" fill="var(--warn)" opacity=".35"/>'
                                  f'<rect x="{x(hi):.0f}" y="8" width="{W - x(hi):.0f}" height="10" fill="var(--dn)" opacity=".35"/>')
    g = (f'<svg viewBox="0 0 {W} 34" width="100%" style="max-width:{W}px;display:block" role="img" aria-label="부담 점수 {b:.0f}">'
         f'{zone}<line x1="{x(nu):.0f}" y1="4" x2="{x(nu):.0f}" y2="22" stroke="var(--dim)" stroke-dasharray="2 2"/>'
         f'<polygon points="{x(b) - 5:.0f},2 {x(b) + 5:.0f},2 {x(b):.0f},9" fill="var(--tx)"/>'
         f'<text x="0" y="32" font-size="9" fill="var(--dim)">0 좋음</text><text x="{x(nu) - 14:.0f}" y="32" font-size="9" fill="var(--dim)">중립 {nu:.0f}</text>'
         f'<text x="{W - 40}" y="32" font-size="9" fill="var(--dim)">100 부담</text></svg>')
    h = list((ck.get("hist") or {}).values())[-12:]   # 최근 1년 월말(2026-10-21 사용자: 2년 → 1년)
    if len(h) >= 6:
        hh = h + [b]
        mn, mx = min(hh + [lo or 50]) - 2, max(hh + [hi or 50]) + 2
        X = lambda i: i / (len(hh) - 1) * W
        Y = lambda v: 40 - (v - mn) / (mx - mn) * 36
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(hh))
        cut = "" if lo is None else (f'<line x1="0" x2="{W}" y1="{Y(hi):.1f}" y2="{Y(hi):.1f}" stroke="var(--dn)" stroke-dasharray="3 3" opacity=".6"/>'
                                     f'<line x1="0" x2="{W}" y1="{Y(lo):.1f}" y2="{Y(lo):.1f}" stroke="var(--up)" stroke-dasharray="3 3" opacity=".6"/>')
        g += (f'<svg viewBox="0 0 {W} 44" width="100%" style="max-width:{W}px;display:block;margin-top:4px" role="img" aria-label="최근 1년 월말 부담 점수">'
              f'{cut}<polyline points="{pts}" fill="none" stroke="var(--tx)" stroke-width="1.5"/>'
              f'<circle cx="{X(len(hh) - 1):.1f}" cy="{Y(b):.1f}" r="2.5" fill="var(--tx)"/></svg>'
              f'<p class="sub" style="margin:0">최근 1년 월말 점수(점선 = 높음 · 낮음 문턱)</p>')
    return g


def _ck_badge(g: str, word: str) -> str:
    return f'<span class="badge" style="color:{CK_COLOR.get(g, "var(--dim)")};border-color:{CK_COLOR.get(g, "var(--line)")}">{_e(word)}</span>'


def _ck_state(c: dict) -> str:
    """형태별 지금 상태 한 줄."""
    f = c.get("form", "")
    if f.startswith("L") and "rank" in c:
        return f"{f[1:]}년 중 {c['rank']:.0%} 위치"
    if f.startswith("F") and "chg" in c:
        u = "%" if c.get("pct") else ("%p" if c["unit"] in ("%", "%p") else "")
        return f"{f[1:]}개월 {c['chg']:+.2f}{u} (평소 대비 {c['z']:+.1f}σ)"
    if f == "Q" and "q" in c:
        return f"5년 {'상단' if c['rank5'] >= 0.5 else '하단'} · 6개월 {'상승' if c['chg6'] > 0 else '하락'}"
    return ""


def _ck_row(c: dict) -> str:
    g = c.get("grade")
    role = c.get("role")
    word = {"G": "낮음", "A": "높은 편", "R": "높음", "B": "자료 부족"}.get(g, "")
    unit = c["unit"] if c["unit"] in ("%", "%p", "원", "엔", "$") else ""
    st = c.get("streak")
    streak = "" if not st else f"{'상승' if st > 0 else '하락'} {abs(st)}개월째"
    if role == "sync":
        tag = '<span class="sub">동시 지표</span>'
    elif role == "off":
        tag = f'<span class="sub">기록만 — {_e(c.get("why", ""))}</span>'
    elif role == "new":
        tag = '<span class="sub">검증 대기</span>' if g != "B" else f'<span class="sub">{_e(c.get("why", "자료 부족"))}</span>'
    else:
        tag = _ck_badge(g or "B", word)
    return (f"<tr><td>{_e(c['label'])}</td><td>{_e(c.get('value_txt', '–'))}{_e(unit)} <span class='sub'>{_e((c.get('date') or '')[5:])}</span></td>"
            f"<td class='sub'>{_e(c.get('form_txt', ''))} · {'클수록 부담' if c['dir'] > 0 else '작을수록 부담' if c['dir'] < 0 else '방향 없음'}</td>"
            f"<td>{_e(_ck_state(c))}</td><td>{tag}</td><td class='sub'>{_e(streak)}</td></tr>")


def _ck_plain_html(ck: dict) -> list[str]:
    """쉬운 말로 — 무엇이 바뀌었나 · 지금 위험한 지점 · 아직 번지지 않은 곳 · 다음에 볼 것(4_macro `plain`, 2026-10-20 사용자). 방향 판단 없음."""
    pl = ck.get("plain") or {}
    if not pl.get("risk") and not pl.get("changed"):
        return []
    P = ['<div style="border-left:3px solid var(--warn);padding:4px 10px;margin:8px 0">', '<p style="margin:0 0 4px"><b>쉬운 말로 — 지금 어디가 위험한가</b></p>']
    for head, key in (("바뀐 것", "changed"), ("위험한 지점", "risk"), ("아직 번지지 않은 곳", "ok"), ("다음에 볼 것", "watch")):
        if pl.get(key):
            P.append(f'<p class="sub" style="margin:4px 0 0">{head}</p><ul style="margin:2px 0 0 18px;padding:0">'
                     + "".join(f"<li>{_e(x)}</li>" for x in pl[key]) + "</ul>")
    P.append("</div>")
    return P


def _ck_change_html(ck: dict) -> list[str]:
    """직전 대비 · 괴리 · 카드 칩 · 최근 바뀐 날(2026-10-20 사용자 — 급변 때 변화부터)."""
    P = []
    ch = ck.get("change") or {}
    arrow = {c["no"]: c["arrow"] for c in ch.get("cards", [])}
    chips = []
    for k in ck["cards"] + ck.get("ref_cards", []):
        if k["grade"] not in "GAR":
            continue
        a = arrow.get(k["no"], "")
        chips.append(f'<span class="badge" style="color:{CK_COLOR[k["grade"]]};border-color:{CK_COLOR[k["grade"]]};margin:2px">'
                     f'{_e(CK_SHORT.get(k["no"], k["title"]))}{(" " + a) if a else ""}</span>')
    if chips:
        P.append('<p class="sub" style="margin:8px 0 2px">카드 한눈에(초록 낮음 · 노랑 높은 편 · 빨강 높음, ▲▼ = 직전보다 나빠짐 · 나아짐)</p>'
                 f'<div style="display:flex;flex-wrap:wrap">{"".join(chips)}</div>')
    if ch:
        db = ch.get("d_burden")
        moved = " · ".join(f"{c['label']} {c['arrow']}" for c in ch.get("checks", [])[:4])
        cards = " · ".join(f"{CK_SHORT.get(c['no'], c['title'])} {c['from']}→{c['to']}" for c in ch.get("cards", []) if c["from"] != c["to"])
        P.append(f'<p style="margin:6px 0 2px">직전({_e(ch["prev_date"][5:])}) 대비: 점수 {db:+.1f}' if db is not None else f'<p style="margin:6px 0 2px">직전({_e(ch["prev_date"][5:])}) 대비:')
        P[-1] += (f" · 카드 {_e(cards)}" if cards else " · 카드 등급 변화 없음") + (f' <span class="sub">· 많이 움직인 체크: {_e(moved)}</span>' if moved else "") + "</p>"
    if ck.get("divergence"):
        P.append(f'<p style="margin:2px 0"><b>상태 vs 가격</b> — {_e(ck["divergence"])}</p>')
    ca = ck.get("credit_alert") or {}
    if ca.get("on"):
        P.append(f'<p style="margin:2px 0;color:var(--dn)">⚠ {_e(ca["text"])} <span class="sub">(참고 — 점수 밖, 아래 "AI · 저신용 신용" 표)</span></p>')
    ev = ck.get("events") or []
    if ev:
        P.append('<p class="sub" style="margin:4px 0 0">최근 바뀐 날: ' + " / ".join(f"{_e(e['date'][5:])} {_e(e['text'])}" for e in ev[-5:]) + "</p>")
    return P


def _html_checklist(r: dict) -> list[str]:
    ck = r.get("checklist")
    if not ck or ck.get("burden") is None:
        return []
    lo, hi = ck.get("cut") or (None, None)
    P = ["<h2>매크로 부담 점수</h2>", '<div class="card tm">']
    col = {"높음": "var(--dn)", "낮음": "var(--up)"}.get(ck.get("level"), "var(--warn)")
    p3 = ck.get("burden_6m_ago")
    P.append(f'<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap"><span style="font-size:2rem;font-weight:700;color:{col}">{ck["burden"]:.0f}</span>'
             f'<span class="muted">/ 100 · <b>{_e(_ck_level(ck))}</b> 구간'
             + (f' · 6개월 전 {p3:.0f} → {_e(_ck_move(ck))}' if p3 is not None else "") + '</span></div>')
    P.append(f'<p class="sub" style="margin:2px 0 6px">낮을수록 좋음.'
             + (f' 낮음 {lo:.0f} 이하 · 높음 {hi:.0f} 이상.' if lo is not None else "")
             + f' 자료 {_e(ck["data_to"])}까지.</p>')
    P += _ck_plain_html(ck)
    P.append(_ck_gauge(ck))
    P += _ck_change_html(ck)
    cb = _ck_contrib(ck)
    if cb:
        mx = max(abs(v) for _, v in cb) or 1
        P.append(f'<p class="sub" style="margin:10px 0 2px">점수를 올리고 내린 카드(점, 합 ≈ 점수 − 중립 {ck.get("neutral", 50):.0f})</p><table>')
        for n, v in cb:
            w = abs(v) / mx * 100
            bar = (f'<span style="display:inline-block;height:8px;width:{w:.0f}%;max-width:120px;background:{"var(--dn)" if v > 0 else "var(--up)"};opacity:.7"></span>')
            P.append(f"<tr><td>{_e(n)}</td><td style='text-align:right'>{v:+.1f}</td><td style='width:50%'>{bar}</td></tr>")
        P.append("</table>")
    for b in ck["board"]:     # 가격 반응 보드
        P.append(f'<p class="sub" style="margin:4px 0 2px">가격 반응(1주) — {_e(b["name"])}: <b>{_e(b["summary"])}</b></p><table>')
        for x in b["rows"]:
            u = "bp" if x["unit"] == "bp" else "%"
            P.append(f"<tr><td>{_e(x['label'])}</td><td>{x['from']:.4g} → {x['to']:.4g}</td><td>{x['chg']:+.1f}{u}</td>"
                     f"<td>{_e(x['arrow'])} {'악화' if x['arrow'] == '▲' else '완화' if x['arrow'] == '▼' else ''}</td></tr>")
        P.append("</table>")
    P.append('<table style="margin-top:8px"><tr><th>#</th><th>카드</th><th>흐름</th><th>가장 부담 쪽 체크</th></tr>')
    for k in ck["cards"] + ck["aux"]:
        top = max((c for c in k["checks"] if "signal" in c), key=lambda c: c["signal"], default=None)
        tt = f"{top['label']} — {_ck_state(top)}" if top else "–"
        P.append(f"<tr><td>{_e(k['no'])}</td><td>{_e(k['title'])}</td><td>{_ck_badge(k['grade'], k['word'])}</td><td class='top'>{_e(tt)}</td></tr>")
    P.append("</table>")
    for k in ck.get("ref_cards", []):     # AI 투자 · 인프라 참고 카드(2026-10-20, 점수 밖)
        P.append(f'<p style="margin:10px 0 2px"><b>{_e(k["title"])}</b> {_ck_badge(k["grade"], k["word"])} '
                 f'<span class="sub">— {_e(k["desc"])}</span></p><table><tr><th>체크</th><th>값</th><th>지금 상태</th><th>등급</th></tr>')
        for c in k["checks"]:
            g = c.get("grade") or "B"
            word = {"G": "낮음", "A": "높은 편", "R": "높음"}.get(g, _trim(c.get("why", "자료 부족")))
            P.append(f"<tr><td>{_e(c['label'])}</td><td>{_e(c.get('value_txt', '–'))}</td><td>{_e(_ck_state(c))}</td><td>{_ck_badge(g, word)}</td></tr>")
        P.append("</table>")
    if ck.get("strands"):
        P.append('<p class="sub" style="margin:8px 0 2px">같은 줄기 — 같이 움직이는 점수 체크 묶음(2016 – 상관 0.7 이상). 묶어서 다시 계산해도 점수는 거의 같음</p><table>')
        for x in ck["strands"]:
            P.append(f"<tr><td>{_e(x['name'])}</td><td class='sub'>체크 {x['n']}개</td><td>{_ck_badge(x['grade'], {'G': '낮음', 'A': '높은 편', 'R': '높음'}[x['grade']])}</td>"
                     f"<td class='sub'>{_e(' · '.join(x['labels'][:4]) + (' …' if x['n'] > 4 else ''))}</td></tr>")
        P.append("</table>")
    if ck.get("sync"):
        P.append('<p class="sub" style="margin:8px 0 2px">동시 지표 — 지금 시장 상태(예측 아님)</p><table>')
        for c in ck["sync"]:
            P.append(f"<tr><td>{_e(c['label'])}</td><td>{_e(c.get('value_txt', '–'))}</td><td>{_e(_ck_state(c))}</td></tr>")
        P.append("</table>")
    P.append("</div>")
    P.append('<details class="fold"><summary>체크리스트 전체 — 체크 · 값 · 형태 · 지금 상태 · 등급 · 흐름 지속</summary>')
    pend = ck.get("pending", [])
    for k in ck["cards"] + ck.get("ref_cards", []) + ck["aux"] + pend:
        badge = "" if k in pend else _ck_badge(k["grade"], k["word"])
        P.append(f"<p><b>{_e(k['no'])}. {_e(k['title'])}</b> {badge} — {_e(_trim(k['desc']))}</p>")
        P.append("<table><tr><th>체크</th><th>값 · 날짜</th><th>형태 · 방향</th><th>지금 상태</th><th>등급</th><th>6개월 흐름</th></tr>"
                 + "".join(_ck_row(c) for c in k["checks"]) + "</table>")
    P.append("<p>점수 = 체크 신호 평균을 2016년 이후 하위 · 상위 5%가 0 · 100이 되게 늘린 값. n년 순위 = 최근 n년 중 위치 · "
             "n개월 흐름 = n개월 변화 ÷ 평소 변화폭(σ) · 국면 = 5년 수준 상 · 하 × 6개월 상승 · 하락. 원천: FRED · yfinance.</p></details>")
    return P


# ── 유동성 · 신용 모니터(4_macro liquidity_monitor.json, 2026-10-15 사용자) — 12개 지표 · 경보 · 미국 신용 등급별 · 한 줄 요약 · 주요 이슈. 참고 ──
def _core_liquidity(r: dict) -> str:
    lq = r.get("liquidity")
    if not lq:
        return ""
    n = sum(i.get("alert", False) for i in lq["items"])
    return f"유동성 · 신용 모니터: 경보 {n}개 — {lq['headline']}."


def _tg_liquidity(r: dict) -> list[str]:
    """예시 형태 그대로 숫자 포함(사용자 요청 — 텔레그램 숫자 없음 원칙의 예외)."""
    lq = r.get("liquidity")
    return ["", *lq["telegram"].split("\n")] if lq and lq.get("telegram") else []


def _lq_spark(it: dict, W=200, H=64) -> str:
    pts = [(d, v) for d, v in sorted((it.get("series_1y") or {}).items()) if v is not None]
    if len(pts) < 4:
        return ""
    vals = [v for _, v in pts] + [it["value"]]
    med, ab = it.get("median_1y"), it.get("abs")
    extra = [x for x in (med, ab) if x is not None and (ab is None or x != ab or min(vals) * 0.5 <= x <= max(vals) * 1.5)]
    lo, hi = min(vals + extra), max(vals + extra)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    X = lambda i: i / (len(pts) - 1) * (W - 4) + 2
    Y = lambda v: 4 + (hi - v) / (hi - lo) * (H - 8)
    col = "var(--dn)" if it.get("alert") else "var(--tx)"
    line = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(pts))
    g = f'<svg viewBox="0 0 {W} {H}" width="100%" style="display:block" role="img" aria-label="{_e(it["name"])} 1년">'
    if med is not None:
        g += f'<line x1="0" x2="{W}" y1="{Y(med):.1f}" y2="{Y(med):.1f}" stroke="var(--dim)" stroke-dasharray="3 3" opacity=".7"/>'
    if ab is not None and lo <= ab <= hi:
        g += f'<line x1="0" x2="{W}" y1="{Y(ab):.1f}" y2="{Y(ab):.1f}" stroke="var(--dn)" stroke-dasharray="1 3" opacity=".8"/>'
    g += (f'<polyline points="{line}" fill="none" stroke="{col}" stroke-width="1.4"/>'
          f'<circle cx="{X(len(pts) - 1):.1f}" cy="{Y(pts[-1][1]):.1f}" r="2.5" fill="{col}"/></svg>')
    return g


def _lq_val(it, v, chg=False):
    if v is None:
        return "–"
    u = it["unit"]
    if u == "bp":
        return f"{v:+,.0f}bp" if chg else f"{v:,.0f}bp"
    if u == "x":
        return f"{v:+.2f}" if chg else f"{v:.2f}x"
    if chg:
        return f"{v:+,.0f}" if abs(v) >= 100 else f"{v:+.1f}"
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.1f}"


def _tier_chart(t: dict, color: str, W=360, H=70) -> str:
    pts = [(d, v) for d, v in sorted(t["series_3y"].items()) if v is not None]
    if len(pts) < 4:
        return ""
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    X = lambda i: i / (len(pts) - 1) * (W - 4) + 2
    Y = lambda v: 4 + (hi - v) / (hi - lo) * (H - 8)
    line = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(pts))
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" style="display:block" role="img" aria-label="{_e(t["name"])} 3년">'
            f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.6"/></svg>')


def _html_liquidity(r: dict) -> list[str]:
    lq = r.get("liquidity")
    if not lq:
        return []
    al = [i for i in lq["items"] if i.get("alert")]
    P = ["<h2>유동성 · 신용 모니터</h2>", '<div class="card tm">']
    P.append(f'<p style="margin:0 0 4px"><b style="color:{"var(--dn)" if al else "var(--up)"}">{"● 경보 " + str(len(al)) + "개" if al else "● 경보 없음"}</b> — {_e(lq["headline"])}</p>')
    if lq.get("issues"):
        P.append('<ul style="margin:4px 0 8px;padding-left:18px">' + "".join(f'<li style="font-size:0.85rem;line-height:1.6">{_e(s)}</li>' for s in lq["issues"]) + "</ul>")
    P.append('<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px">')
    for it in lq["items"]:
        if it.get("missing"):
            continue
        col = "var(--dn)" if it.get("alert") else "var(--tx)"
        why = f'<div class="sub" style="color:var(--dn)">{_e(" · ".join(it["why"]))}</div>' if it.get("why") else ""
        P.append(f'<div style="border:1px solid var(--line);padding:6px 8px">'
                 f'<div style="font-size:0.78rem;font-weight:600">{_e(it["name"])}</div><div class="sub">{_e(it["desc"])}</div>'
                 f'<div style="display:flex;justify-content:space-between;align-items:baseline;gap:6px">'
                 f'<span style="font-size:1.1rem;font-weight:700;color:{col}">{_lq_val(it, it["value"])}</span>'
                 f'<span class="sub">1주 {_lq_val(it, it["chg_1w"], True)} · 1개월 {_lq_val(it, it["chg_1m"], True)} · 백분위 {it["pct_1y"]:.0%}</span></div>'
                 f'{_lq_spark(it)}{why}<div class="sub" style="text-align:right">기준일 {_e(it["date"][5:])}</div></div>')
    P.append("</div>")
    P.append('<p class="sub" style="margin:4px 0 0">회색 점선 = 1년 중앙값 · 빨간 점선 = 절대 경보선 · 빨간 선 = 경보. '
             'VKOSPI는 KIS 지수 시세(2_kr, 장 마감 뒤 갱신 — 파일이 없으면 코스피 20일 실현 변동성으로 대신).</p>')
    tiers = lq.get("tiers") or []
    if tiers:
        TC = {"ig": "#3e63dd", "bbb_us": "#30a46c", "hy": "#8e4ec6", "ccc": "#e5484d"}
        P.append('<p style="margin:12px 0 2px;font-size:0.85rem"><b>미국 회사채 신용 스프레드</b> <span class="sub">(일별, 국채 대비 가산금리, 3년)</span> — '
                 + " · ".join(f'<span style="color:{TC.get(t["key"])}">{_e(t["name"].split("(")[0].strip())}</span> {t["value"]:,.0f}bp' for t in tiers) + "</p>")
        for t in tiers:
            P.append(f'<div style="display:flex;justify-content:space-between;font-size:0.78rem;margin-top:6px"><b style="color:{TC.get(t["key"])}">{_e(t["name"])}</b>'
                     f'<span class="sub">최근 {t["value"]:,.0f}bp({_e(t["date"][5:])}) · 3년 범위 {t["range_3y"][0]:,.0f} – {t["range_3y"][1]:,.0f}bp · 1개월 {t["chg_1m"]:+,.0f}bp</span></div>'
                     + _tier_chart(t, TC.get(t["key"], "var(--tx)")))
    ks = lq.get("kr_state") or []
    if ks:      # 국내 상태 지도(2026-10-17 사용자 — 레버리지 쏠림 · 신용 위치 · 수급 달력, 방향 신호 아님)
        P.append('<p style="margin:12px 0 2px;font-size:0.85rem"><b>국내 상태</b> <span class="sub">(지금 상태 설명 — 방향 신호 아님)</span></p>'
                 '<ul style="margin:2px 0 0;padding-left:18px">' + "".join(
                     f'<li style="font-size:0.84rem;line-height:1.6{";color:var(--warn)" if x.get("flag") else ""}">{_e(_trim(x["text"]))}</li>' for x in ks) + "</ul>")
    P.append(f'<p class="sub" style="margin:8px 0 0">{_e(_trim(lq["rule"]))}. 원천: ECOS · FRED · Yahoo.</p></div>')
    return P


# ── 외국인 시선(4_macro foreign_view.json, 2026-10-15 사용자) — 달러로 셈하는 외국인 쪽에서 본 한국. 동시 지표(예측 아님), 아침판만 ──
FV_COLOR = {"한국 EWY": "#e5484d", "대만 EWT": "#30a46c", "나스닥 QQQ": "#3e63dd", "브라질 EWZ": "#f76b15",
            "인도 INDA": "#8b8d98", "일본 EWJ": "#ab4aba", "신흥국 EEM": "#ffc53d",
            "코스피": "#e5484d", "닛케이": "#ab4aba", "대만 가권": "#30a46c", "항셍": "#8b8d98", "상해": "#ffc53d"}
FV_VERDICT_COLOR = {"한국 최약세": "var(--dn)", "괴리": "var(--warn)", "한국만 과도 매도": "var(--dn)", "발동 — 외국인 자금 이탈 가능성": "var(--warn)",
                    "발동": "var(--warn)", "아직 아님": "var(--up)", "원화 강세": "var(--tx)", "원화 약세": "var(--dn)"}


def _fmt_usd(m) -> str:
    """백만 달러 → '−212억 달러' 꼴."""
    if m is None:
        return "–"
    return f"{m / 100:+,.0f}억 달러"


def _core_foreign(r: dict) -> str:
    fv = r.get("foreign_view")
    st = (fv or {}).get("story")
    if not st:
        return ""
    return "외국인 시선: " + st.get("chain_words", st["chain"]) + "."


def _tg_foreign(r: dict) -> str:
    """텔레그램 — 단어로 흐름만(숫자 없음): 단계별 판정을 화살표로."""
    st = ((r.get("foreign_view") or {}).get("story")) or {}
    return ("· 외국인 시선: " + st.get("chain_words", st["chain"])) if st.get("chain") else ""


def _lines_chart(ser: dict, now_label: dict | None = None, W=360, H=170) -> str:
    """{이름: {날짜: 값}} 여러 선 — 첫날 = 0 누적 % 그림."""
    if not ser:
        return ""
    L, B = 30, 20
    dates = sorted({d for s in ser.values() for d in s})
    vals = [v for s in ser.values() for v in s.values() if v is not None]
    lo, hi = min(vals + [0]) - 2, max(vals + [0]) + 2
    X = lambda d: L + dates.index(d) / max(1, len(dates) - 1) * (W - L - 6)
    Y = lambda v: 6 + (hi - v) / (hi - lo) * (H - B - 6)
    g = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W * 1.6:.0f}px;display:block" role="img" aria-label="누적 수익 비교">']
    rng = hi - lo
    step = 20 if rng > 60 else (10 if rng > 25 else 5)
    for t in range(int(lo // step) * step, int(hi) + 1, step):
        if lo <= t <= hi:
            g.append(f'<line x1="{L}" x2="{W - 6}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" stroke="var(--line)" stroke-width="{1.2 if t == 0 else 0.6}"/>'
                     f'<text x="{L - 4}" y="{Y(t) + 3:.1f}" font-size="8" fill="var(--dim)" text-anchor="end">{t}</text>')
    for i in (0, len(dates) // 2, len(dates) - 1):
        g.append(f'<text x="{X(dates[i]):.1f}" y="{H - 6}" font-size="8" fill="var(--dim)" text-anchor="middle">{dates[i][5:].replace("-", "/")}</text>')
    for nm, s in ser.items():
        pts = " ".join(f"{X(d):.1f},{Y(v):.1f}" for d, v in sorted(s.items()) if v is not None)
        w = 2.6 if nm in ("한국 EWY", "코스피") else 1.4
        dash = ' stroke-dasharray="3 3"' if nm in ("인도 INDA", "항셍") else ""
        g.append(f'<polyline points="{pts}" fill="none" stroke="{FV_COLOR.get(nm, "var(--tx)")}" stroke-width="{w}"{dash}/>')
    g.append("</svg>")
    last = {nm: [v for _, v in sorted(s.items()) if v is not None][-1] for nm, s in ser.items()}
    leg = " ".join(f'<span style="white-space:nowrap;margin-right:8px"><span style="display:inline-block;width:10px;height:3px;background:{FV_COLOR.get(nm)};vertical-align:middle"></span> {_e(nm)} {(now_label or last)[nm]:+.1f}%</span>'
                   for nm in ser)
    return "".join(g) + f'<p class="sub" style="margin:2px 0 0">{leg}</p>'


def _html_foreign(r: dict) -> list[str]:
    fv = r.get("foreign_view")
    if not fv:
        return []
    st = fv.get("story") or {}
    P = ["<h2>외국인 시선 — 국장 · 원화 · 외인 자금</h2>", '<div class="card tm">']
    if st:
        P.append(f'<p style="margin:0 0 4px;font-size:0.9rem;line-height:1.6"><b>{_e(st.get("chain_words", st["chain"]))}</b></p>'
                 f'<p class="muted" style="margin:0 0 8px;line-height:1.65">{_e(st["paragraph"])}</p>')
        for s in st["steps"]:
            col = ("var(--dn)" if s.get("warn") or any(k in s["verdict"] for k in ("크게 빠졌다", "대량으로 팔", "번졌다", "빠져나가는")) else
                   "var(--warn)" if any(k in s["verdict"] for k in ("번지지 않았다", "아직 작다", "약했다")) else
                   "var(--up)" if any(k in s["verdict"] for k in ("버텼다", "대량으로 사", "규모의 매매는 아니다")) else "var(--tx)")
            body = f'<div style="font-size:0.82rem;line-height:1.6">{_e(s["text"])}</div>'
            if s.get("ev2") is not None or s.get("ev1") is not None:
                lst = lambda xs, h: (f'<div class="sub" style="margin-top:3px">{h}</div><ul style="margin:0;padding-left:18px">'
                                     + "".join(f'<li style="font-size:0.8rem">{_e(x)}</li>' for x in xs) + "</ul>") if xs else ""
                body += lst(s.get("ev2"), "② 쪽 근거") + lst(s.get("ev1"), "① 쪽 근거") + lst(s.get("pending"), "아직 확인 불가") + lst(s.get("counter"), "반대 방향 압력")
            if "idx" in s.get("charts", []) and st.get("idx_series"):
                body += '<div class="sub" style="margin-top:4px">자국 통화 지수 1개월</div>' + _lines_chart(st["idx_series"])
            if "etf" in s.get("charts", []) and fv["etf"]["series"]:
                body += ('<div class="sub" style="margin-top:4px">달러 기준 국가 ETF 누적(6개월)</div>'
                         + _lines_chart(fv["etf"]["series"], {k: v["6개월"] for k, v in fv["etf"]["now"].items()}))
            P.append(f'<div style="border-left:3px solid {col};padding:4px 0 6px 10px;margin:6px 0">'
                     f'<div class="sub">{s["no"]}. {_e(s.get("q", s.get("title", "")))}</div>'
                     f'<div style="font-size:0.9rem;font-weight:700;color:{col};margin:1px 0 3px">{_e(s["verdict"])}</div>{body}</div>')
        P.append(f'<p class="sub" style="margin:6px 0 0">지금 상황 설명 · 방향 판단 아님.</p>')
    # 숫자 표(접힘)
    dec, sp, fl = fv["usd_kospi"]["decomp"], fv["fx_split"]["split"], fv["foreign"]["flows"]
    rows = "".join(f"<tr><td>{nm}</td><td>{dec[nm]['usd']:+.1f}%</td><td>{dec[nm]['local']:+.1f}%</td><td>{dec[nm]['fx']:+.1f}%</td>"
                   f"<td>{sp.get(nm, {}).get('won_own', 0):+.1f}%</td></tr>" for nm in ("1개월", "3개월", "6개월") if nm in dec)
    fr = "".join(f"<tr><td>{nm}</td><td>{_fmt_usd(fl[nm]['usd_m'])}</td><td class='sub'>3년 중 {fl[nm]['rank3y']:.0%} 위치</td></tr>" for nm in ("5일", "20일", "60일") if nm in fl)
    ef = fv.get("etf_flows") or {}
    n = (ef.get("EWY") or {}).get("days", 0)
    etf = (f"ETF 자금 유출입: {_e((ef.get('EWY') or {}).get('first', ''))}부터 주식 수를 매일 쌓는 중 — 이틀째부터 표시." if n < 2 else
           "".join(f"{_e(t)} {_fmt_usd(v.get('flow_usd_m'))}({v['days']}일) · " for t, v in ef.items() if v.get("days", 0) >= 2))
    P.append('<details class="fold" style="margin-top:8px"><summary>숫자 자세히 — 달러 코스피 분해 · 외국인 순매수 · ETF 자금</summary>'
             f"<table><tr><th></th><th>달러 수익</th><th>주가 몫</th><th>환율 몫</th><th>원화 고유</th></tr>{rows}</table>"
             f"<p>외국인 순매수(달러 환산, {_e(fv['foreign']['date'])}까지, 매일 갱신)</p><table>{fr}</table><p>{etf}</p></details>")
    P.append("</div>")
    return P


def _core_macro(r: dict) -> str:
    mv = r.get("macro") or {}
    big = []
    for k, cut in MACRO_MOVE.items():
        x = mv.get(k)
        if x and x.get("chg") is not None and abs(x["chg"]) >= cut:
            unit = "bp" if x.get("chg_unit") == "bp" else "%"
            big.append(f"{x['name']} {x['value']:,.2f}{x.get('unit', '') if x.get('unit') == '%' else ''}({x['chg']:+.1f}{unit})")
    if big:
        return "크게 움직인 지표: " + " · ".join(big) + "."
    t10, fx = mv.get("US_10Y"), mv.get("USDKRW")
    tail = " · ".join(s for s in (f"미국 10년 {t10['value']:.2f}%" if t10 else "", f"원/달러 {fx['value']:,.0f}원" if fx else "") if s)
    return "금리 · 환율 · 유가는 큰 변화가 없었습니다" + (f"({tail})." if tail else ".")


def _core_news(r: dict) -> str:
    nw = next((x for x in r["ref"] if x["k"] == "뉴스"), None)
    if not nw or not nw.get("issues"):
        return ""
    top = nw["issues"][0]
    return f"가장 많이 다뤄진 뉴스는 \"{top['title'][:45]}\"({top['channels']}채널)입니다." if top.get("title") else ""


def _core_kr_theme(r: dict) -> str:
    rows, weak = _theme_pick(r)
    if not rows:
        return ""
    gs = (r.get("themes") or {}).get("groups") or []
    when = "어제 국내는" if r["slot"] == "am" else "오늘 국내는"
    return f"{when} {_names(gs[:2])} 테마가 강했고, {_names(gs[::-1][:2])} 테마는 약했습니다."


# ── 검증된 참고 신호(VM-SPC Core 9.277 · 9.282 · 9.283 · 9.286 · 9.294 · 9.296, 2026-10-10) ──────────────────────
# 보이는 곳 = 해당하는 날에만 짧은 한 줄(빈 "신호 없음" 줄은 쓰지 않음), 근거(계산값 · 정의 · 과거 성과 · 검증 번호) = 접힌 칸 "참고 신호 근거".
SIG_MAX = 3                                     # 미국 신호 줄 최대 개수(|σ| 큰 순)
HOT_SHARE = 1 / 3                               # 9.283: 종목 1/3 이상이 +5%인 테마도 1위 테마와 같은 주의


def _kr_rank(r: dict) -> tuple[dict, int]:
    gs = (r.get("themes") or {}).get("groups") or []
    return {g["theme"]: i + 1 for i, g in enumerate(gs)}, len(gs)


def _sig_size(s: dict) -> float:
    return abs(s["z"]) if s.get("z") is not None else abs(s["chg"]) / 2


def us_signals(r: dict) -> list[dict]:
    """미국 섹터 ±1.5σ(또는 ±2%) → 국내 연관 테마. 같은 국내 테마는 한 번(가장 크게 움직인 섹터), 방향이 엇갈리면 뺌,
    직전 국내 거래일에 이미 같은 방향 상위 5(급락이면 하위 5)였으면 '이미 반영'(9.286 D1)."""
    by: dict[str, list] = {}
    for s in (r.get("us_themes") or {}).get("sectors") or []:
        if s.get("signal") and s.get("kr"):
            by.setdefault(s["kr"], []).append(s)
    rank, n = _kr_rank(r)
    out = []
    for kr, xs in by.items():
        if len({x["chg"] > 0 for x in xs}) > 1:
            continue
        s = max(xs, key=_sig_size)
        up, rk = s["chg"] > 0, rank.get(kr)
        out.append({**s, "up": up, "kr_rank": rk, "kr_n": n,
                    "already": rk is not None and ((up and rk <= 5) or (not up and rk > n - 5))})
    return sorted(out, key=lambda x: -_sig_size(x))[:SIG_MAX]


def _soxx(r: dict) -> dict | None:
    sx = next((s for s in (r.get("us_themes") or {}).get("sectors") or [] if s.get("etf") == "SOXX"), None)
    return sx if sx and sx.get("signal") else None


def kr_day(r: dict) -> str:
    """미국 신호가 적용되는 국내 날 — 발송일이 토 · 일이면 "다음 거래일"(2026-10-12 VM-core: 9.286 날짜 규칙 = 미국 D → 다음 국내 거래일).
    평일 국내 휴장(연휴)은 2_kr kr_calendar.json(KIS 휴장일조회 캐시)으로 — 달력에 없는 날은 토 · 일 규칙만."""
    send = r.get("send") or _next_day(r["date"])
    if _date.fromisoformat(send).weekday() >= 5:
        return "다음 거래일"
    try:
        days = json.loads((EXCHANGE / "2_kr_market" / "kr_calendar.json").read_text(encoding="utf-8")).get("days", {})
    except (OSError, ValueError):
        days = {}
    return "다음 거래일" if days.get(send) is False else "오늘"


def us_signal_lines(r: dict) -> list[str]:
    L = [f"{s['theme']} · 미국 {s['chg']:+.1f}% → " + (f"국내 {s['kr']} 이미 반영" if s["already"]
         else f"{kr_day(r)} 국내 {s['kr']} 다른 테마보다 {'조금 강한' if s['up'] else '조금 약한'} 경향") for s in us_signals(r)]   # +0.18%p · 54%(평소 50%) — 9.286
    sx = _soxx(r)
    if sx:
        L.append(f"SOXX {sx['chg']:+.1f}% — 코스피 · 코스닥은 시가에 대부분 반영")
    return L


def _hot_share(g: dict) -> float:
    return g["hot"] / g["n"] if g.get("n") else 0.0


def chase_warning(r: dict) -> str:
    """9.283: 오늘 1위 테마와 +5% 종목이 1/3 이상인 테마 — 한 줄로."""
    gs = (r.get("themes") or {}).get("groups") or []
    if not gs:
        return ""
    top = gs[0]
    names = [f"{top['theme']}(1위" + (f" · +5% 종목 {_hot_share(top):.0%}" if _hot_share(top) >= HOT_SHARE else "") + ")"]
    names += [f"{g['theme']}(+5% 종목 {_hot_share(g):.0%})" for g in gs[1:] if _hot_share(g) >= HOT_SHARE]
    return "내일 시가 추격은 다른 테마보다 조금 불리한 경향 — " + " · ".join(names)   # −0.2%p — 9.283


def quarter_line(r: dict) -> str:
    """분기 국면(9.294 · 9.296) — 해당하는 것만 한 줄, 기준일 붙임. 둘 다 없으면 빈 문자열."""
    q = r.get("quarter") or {}
    parts = []
    if (q.get("wti_q_pct") or 0) > 0:
        parts.append("유가↑ → 다음 분기 에너지화학 · 운송 강한 경향")
    if (q.get("curve_q_pp") or 0) > 0:
        parts.append("금리차 가팔라짐 → 다음 분기 코스피 강한 경향")
    return f"분기 국면: {' · '.join(parts)} ({_md(q.get('asof', ''))} 기준)" if parts else ""


def _live_stats() -> list[dict]:
    try:
        import signal_log
        return signal_log.stats()
    except Exception as ex:  # noqa: BLE001 — 기록이 깨져도 리포트는 나가게
        print(f"[build_report] 실전 기록 읽기 실패: {ex}", file=sys.stderr)
        return []


def signal_evidence_html(r: dict) -> str:
    """접힌 칸 '참고 신호 근거' — 오늘 계산값 · 정의 · 과거 성과 · 검증 번호. 오늘 보이는 신호가 하나도 없으면 칸을 만들지 않음."""
    P = []
    if r["slot"] == "am":
        us = us_signals(r)
        if us:
            P.append("<p><b>미국 섹터 → 국내 테마</b></p><table><tr><th>미국 섹터</th><th>ETF</th><th>등락</th><th>σ배수</th>"
                     "<th>국내 테마</th><th>어제 국내 순위</th><th>표시</th></tr>")
            for s in us:
                z = "–" if s.get("z") is None else f"{s['z']:+.1f}"
                rk = f"{s['kr_rank']} / {s['kr_n']}" if s.get("kr_rank") else "–"
                P.append(f"<tr><td>{_e(s['theme'])}</td><td>{_e(s['etf'])}</td><td>{s['chg']:+.1f}%</td><td>{z}</td>"
                         f"<td>{_e(s['kr'])}</td><td>{rk}</td><td>{'이미 반영' if s['already'] else ('조금 강한 경향' if s['up'] else '조금 약한 경향')}</td></tr>")
            P.append("</table><p>신호 = 미국 섹터 ETF 등락 ÷ 60일 표준편차 ±1.5 이상(또는 ±2%). 다음 국내 거래일 그 테마가 다른 테마보다 평균 +0.18%p(같은 방향 54%, 평소 50%) — 매매 규칙 아님.</p>")
        sx = _soxx(r)
        if sx:
            z = "" if sx.get("z") is None else f", σ {sx['z']:+.1f}"
            P.append(f"<p><b>SOXX → 지수</b> — SOXX {sx['chg']:+.1f}%{z}. 갭 같은 방향 85 – 91%, 장중 · 3일 추가는 0 근처.</p>")
    else:
        gs = (r.get("themes") or {}).get("groups") or []
        if gs:
            hot = [g for g in gs if _hot_share(g) >= HOT_SHARE]
            rows = [gs[0]] + [g for g in hot if g is not gs[0]]
            P.append("<p><b>1위 · 무더기 급등 테마 추격 주의</b> — " + " · ".join(
                f"{_e(g['theme'])} 평균 {g['avg']:+.1f}% · +5% 종목 {g['hot']}/{g['n']}" for g in rows)
                + ". 다음 날 시가에 사면 다른 테마보다 평균 −0.2%p, 이긴 비율 42%(평소 47%).</p>")
    if quarter_line(r):
        q = r.get("quarter") or {}
        P.append(f"<p><b>분기 국면</b>({_e(_md(q.get('asof', '')))} 기준, 직전 63거래일 평균 − 그 앞 63거래일 평균) — "
                 + " · ".join(x for x in (f"WTI {q['wti_q_pct']:+.1f}%" if "wti_q_pct" in q else "",
                                          f"10Y-2Y {q['curve_q_pp']:+.2f}%p" if "curve_q_pp" in q else "") if x) + "</p>")
        if (q.get("wti_q_pct") or 0) > 0:
            P.append("<p>유가 상승 분기 → 다음 분기 에너지화학 +8.6%p · 운송 +10.4%p(다른 테마 대비), 10년 중 8번.</p>")
        if (q.get("curve_q_pp") or 0) > 0:
            P.append("<p>10Y-2Y 가팔라진 분기 → 다음 분기 코스피 +12.3% vs 나머지 −1.2%, 7번 중 5번.</p>")
    live = _live_stats()
    if live:
        P.append("<p><b>실전 기록</b>(리포트에 나간 신호의 실제 결과) — " + " · ".join(
            f"{_e(s['name'])} {s['n']}건 맞음 {s['hit']:.0%}" + ("" if s["avg"] is None else f" 평균 {s['avg']:+.2f}%p")
            + f"(백테스트 {_e(s['bt'])})" for s in live) + ". 표본이 적어 참고만.</p>")
    return ('<details class="fold"><summary>참고 신호 근거</summary>' + "".join(P) + "</details>") if P else ""


def core_summary(r: dict) -> list[str]:
    """맨 위 핵심 — 짧은 문장 몇 개. 검증 전 자료라 방향 판단 문장은 쓰지 않는다."""
    if r.get("weekend"):
        S = _core_us(r)[:1] + [_core_news(r).replace("가장 많이 다뤄진", "주말에 가장 많이 다뤄진"), _core_foreign(r), _core_checklist(r), _core_liquidity(r), _core_macro(r)]
    elif r["slot"] == "am":
        S = _core_us(r) + [_core_news(r), _core_kr_theme(r), _core_foreign(r), _core_checklist(r), _core_liquidity(r), _core_macro(r)]
    else:
        S = [_core_kr_theme(r), _core_news(r)]
    return [s for s in S if s]


def ref_signals(r: dict) -> list[str]:
    """검증된 참고 신호 줄(해당하는 날만) — 아침: 미국 섹터 · SOXX, 마감: 추격, 둘 다: 분기 국면. 없으면 빈 목록(블록을 만들지 않음)."""
    S = us_signal_lines(r) if r["slot"] == "am" else [chase_warning(r)]
    return [x for x in S + [quarter_line(r)] if x]


# ── 텔레그램 문안 — 가장 압축(2026-10-11 사용자: "숫자 빼고 중요사항 위주, 텔레그램 → 파일 맨 위 → 아래로 갈수록 자세히") ──
# 단계: ① 텔레그램 = 단어 위주 · 숫자 없음 ② 파일 윗부분 = 문장 + 숫자 한두 개(core_summary · 할 일) ③ 아래 = 표 · 목록 ④ 접힌 칸 = 근거 · 원문.
MACRO_WORD = {"US_10Y": "미국 금리", "USDKRW": "환율", "WTI": "유가", "VIX": "VIX"}


def _hold_word(body: str) -> str:
    return body.split(" · ", 1)[0].strip()          # "이익 실현 고려 · PBR 상단" → "이익 실현 고려"


def _tg_holdings(r: dict) -> list[str]:
    """판단이 있는 보유 종목만(판단 없음은 뺌)."""
    acts, _ = _holding_split(r)
    return [f"· {n} {_hold_word(b)}" for n, b, _ in acts]


def _tg_regime(r: dict) -> str:
    g = r.get("regime")
    if g is None:
        return "국내 정리본 없음 — 장세 판단 못 함"
    when = "첫날" if g.get("days") == 1 else ""
    return f"코스피 {g['state']}{' ' + when if when else ''} — {g['strategy']}" + (" · 🟢 대량 복귀일" if g["mass_today"] else "")


def _tg_warn(r: dict) -> list[str]:
    return ["⚠ 일부 수집 실패 · 전날 자료 섞였을 수 있음(파일 맨 위)"] if data_warning(r) else []


def _tg_kr_themes(r: dict) -> str:
    gs = (r.get("themes") or {}).get("groups") or []
    return f"· 강세 {_names(gs[:2])} / 약세 {_names(gs[::-1][:2])}" if gs else ""


def _tg_news(r: dict) -> str:
    nw = next((x for x in r["ref"] if x["k"] == "뉴스"), None)
    iss = [i["issue"] for i in (nw or {}).get("issues", [])[:2] if i.get("issue")]
    return "· 뉴스 " + " / ".join(iss) if iss else ""


def _tg_us(r: dict) -> list[str]:
    L = []
    uv = r.get("us_close") or {}
    spy, qqq, soxx = uv.get("S&P500(SPY)"), uv.get("나스닥100(QQQ)"), uv.get("반도체(SOXX)")
    if spy is not None and qqq is not None:
        m = (spy + qqq) / 2
        s = "미국 " + ("상승" if m >= MKT_FLAT else "하락" if m <= -MKT_FLAT else "보합")
        if soxx is not None and abs(soxx - m) >= SEMI_GAP:
            s += " · 반도체 " + ("강세" if soxx > m else "약세")
        L.append("· " + s)
    ss = (r.get("us_themes") or {}).get("sectors") or []
    if ss:
        L.append(f"· 강세 {_names(ss)} / 약세 {_names(ss[::-1][:2], n=2)}")
    mv = r.get("macro") or {}
    big = [MACRO_WORD[k] + ("↑" if mv[k]["chg"] > 0 else "↓") for k, cut in MACRO_MOVE.items()
           if mv.get(k) and mv[k].get("chg") is not None and abs(mv[k]["chg"]) >= cut]
    L.append("· " + (" · ".join(big) if big else "금리 · 환율 · 유가 잠잠"))
    return L


def _tg_signals(r: dict) -> list[str]:
    """참고 신호를 단어로 — 같은 방향 테마는 한 줄로 묶음."""
    L = []
    if r["slot"] == "am":
        us = us_signals(r)
        for up in (True, False):
            xs = [s["kr"] for s in us if s["up"] == up and not s["already"]]
            if xs:
                L.append(f"· 국내 {' · '.join(xs)} {'조금 강한' if up else '조금 약한'} 경향")   # 효과 크기에 맞춤(+0.18%p · 54%) — 9.286
        done = [s["kr"] for s in us if s["already"]]
        if done:
            L.append(f"· {' · '.join(done)}는 이미 반영")
        if _soxx(r):
            L.append("· 반도체 큰 움직임 — 지수는 시가에 반영")
    else:
        gs = (r.get("themes") or {}).get("groups") or []
        if gs:
            names = [gs[0]["theme"]] + [g["theme"] for g in gs[1:] if _hot_share(g) >= HOT_SHARE]
            L.append(f"· 내일 {' · '.join(names)} 시가 추격 불리")
    q = r.get("quarter") or {}
    qs = (["유가↑ → 에너지 · 운송"] if (q.get("wti_q_pct") or 0) > 0 else []) + (["금리차↑ → 코스피"] if (q.get("curve_q_pp") or 0) > 0 else [])
    if qs:
        L.append("· 분기: " + " · ".join(qs) + " 우호")
    return L


def _weekly_themes(r: dict, k: int = 3) -> tuple[list, list]:
    """지난주(5거래일 r5) 테마 상위 · 하위 k."""
    gs = [g for g in (r.get("themes") or {}).get("groups") or [] if g.get("r5") is not None]
    gs.sort(key=lambda g: -g["r5"])
    return gs[:k], gs[::-1][:k] if len(gs) > k else []


def telegram_weekend(r: dict) -> str:
    L = [f"🗞 주말 정리 — 미국 {_md(r['date'])} 마감 · 주말 뉴스"] + _tg_warn(r)
    L += ["", "■ 금요일 미국"] + _tg_us(r)
    iss = [i["issue"] for i in r.get("issues_all", [])[:5] if i.get("issue")]
    if iss:
        L += ["", "■ 주말 뉴스", "· " + " / ".join(iss)]
        hn = list(dict.fromkeys(x["names"] for x in r.get("holdings_news", [])))
        if hn:
            L.append("· 종목 기사 " + " · ".join(hn[:4]))
        rv = r.get("reports", {}).get("value") or {}
        up, dn = [x["name"] for x in rv.get("상향", [])[:2]], [x["name"] for x in rv.get("하향", [])[:2]]
        if up or dn:
            L.append("· 목표가 " + " / ".join(x for x in (f"상향 {' · '.join(up)}" if up else "", f"하향 {' · '.join(dn)}" if dn else "") if x))
    sig = _tg_signals(r)
    if sig:
        L += ["", "■ 오늘 신호" if kr_day(r) == "오늘" else "■ 다음 거래일 신호"] + sig
    L += ["", "■ 지난주 국내", "· " + _tg_regime(r)] + _tg_holdings(r)
    top, bot = _weekly_themes(r, 2)
    if top:
        L.append(f"· 주간 강세 {_names(top)}" + (f" / 약세 {_names(bot)}" if bot else ""))
    return "\n".join(L)


def telegram_text(r: dict) -> str:
    if r.get("weekend"):
        return telegram_weekend(r)
    if r["slot"] == "am":
        L = [f"🌐 {TITLE['am']} — 미국 {_md(r['date'])} 마감"] + _tg_warn(r)
        L += ["", "■ 밤사이"] + _tg_us(r) + [x for x in (_tg_news(r), _tg_checklist(r), _tg_foreign(r)) if x]
        sig = _tg_signals(r)
        if sig:
            L += ["", "■ 오늘 신호" if kr_day(r) == "오늘" else "■ 다음 거래일 신호"] + sig
        L += ["", "■ 어제 국내", "· " + _tg_regime(r)] + _tg_holdings(r)
        L += _tg_liquidity(r)
        return "\n".join(L)
    L = [f"📊 {TITLE['pm']} {_md(r['date'])}"] + _tg_warn(r) + [_tg_regime(r)]
    if r.get("regime") is None:
        return "\n".join(L)
    L += ["", "■ 할 일"]
    L.append("· 신규 " + (" · ".join(c.get("name", "") for c in r["candidates"]) if r["candidates"] else "없음"))
    L += _tg_holdings(r)
    fl = [f"{h['name']}({k})" for h in r.get("holdings", []) + r.get("watch", []) if (k := _flow_kind(h, r["date"]))]
    if fl:
        L.append("· 수급 주의 " + " · ".join(fl))
    L += ["", "■ 흐름"] + [x for x in (_tg_kr_themes(r), _tg_news(r)) if x]
    sig = _tg_signals(r)
    if sig:
        L += ["", "■ 신호"] + sig
    return "\n".join(L)


# ── HTML ────────────────────────────────────────────────────────────────

BASE_CSS = """
  * { box-sizing:border-box; }
  body { background:var(--bg); color:var(--tx); margin:0 auto; }
  a { color:inherit; border-bottom:1px dotted var(--dim); text-decoration:none; }
  .sub { color:var(--dim); font-size:0.75rem; }
  .market { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 10px; padding:12px 14px; margin:12px 0 8px;
            border:1px solid var(--line); background:var(--card); }
  .market.up b { color:var(--up); } .market.dn b { color:var(--dn); } .market.side b { color:var(--warn); }
  .market .mf { color:var(--tx); font-weight:700; } .market .mx { flex-basis:100%; color:var(--mut); font-size:0.78rem; }
  h2 { font-size:0.8rem; color:var(--mut); font-weight:600; margin:22px 0 6px; letter-spacing:.3px; }
  .card { background:var(--card); border:1px solid var(--line); padding:12px 14px; margin-bottom:8px; }
  .row { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 10px; padding:6px 0; border-bottom:1px solid var(--line); }
  .row:last-child { border-bottom:0; }
  .row .nm { min-width:96px; } .row .tx { flex:1; min-width:180px; }
  .badge { font-size:0.7rem; color:var(--dim); border:1px solid var(--line); padding:1px 8px; white-space:nowrap; }
  .muted { color:var(--mut); font-size:0.82rem; }
  .ref { border-left:3px solid var(--line); }
  .ref .row { font-size:0.85rem; } .ref .k { color:var(--dim); font-size:0.72rem; min-width:44px; }
  .late { color:var(--warn); font-size:0.72rem; }
  details.fold { margin-top:8px; border:1px solid var(--line); background:var(--card); padding:8px 12px; font-size:0.8rem; color:var(--mut); }
  details.fold > summary { cursor:pointer; font-weight:600; }
  details.fold table { width:100%; border-collapse:collapse; margin-top:6px; }
  details.fold th, details.fold td { padding:3px 4px; text-align:left; border-bottom:1px solid var(--line); vertical-align:top; }
  details.fold p { margin:6px 0; line-height:1.6; }
  .warnbox { border-color:var(--warn); color:var(--warn); font-size:0.85rem; }
  .fw { color:var(--warn); font-size:0.78rem; }
  h2 .no { display:inline-block; min-width:1.4em; color:var(--dim); font-family:'IBM Plex Mono',monospace; }
  .ok { color:var(--up); } .partial { color:var(--warn); } .failed { color:var(--dn); }
  .core .sig-h { margin:10px 0 2px; font-size:0.72rem; color:var(--dim); border-top:1px dashed var(--line); padding-top:8px; }
  .core ul.sig li { font-size:0.85rem; }
  .core ul { margin:0; padding-left:18px; } .core li { margin:4px 0; line-height:1.65; font-size:0.9rem; }
  .tl .it { padding:9px 0; border-bottom:1px solid var(--line); }
  .tl .it:last-of-type { border-bottom:0; }
  .tl .h { display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 8px; font-size:0.88rem; }
  .tl .h b { font-weight:700; }
  .tl .d { margin-top:3px; font-size:0.78rem; color:var(--mut); line-height:1.6; }
  .tl .up { color:var(--up); } .tl .dn { color:var(--dn); }
  .tl .tag { font-size:0.68rem; color:var(--warn); border:1px solid var(--line); padding:0 6px; }
  .tl .tag.new { color:var(--dim); }
  .tl .chip { font-size:0.7rem; color:var(--mut); border:1px solid var(--line); padding:0 6px; border-bottom:1px solid var(--line); }
  .tl .sep { margin-top:8px; padding-top:6px; font-size:0.7rem; color:var(--dim); border-top:1px dashed var(--line); }
  .tl p.sub { margin:6px 0 0; line-height:1.6; }
  .tm table { width:100%; border-collapse:collapse; font-size:0.8rem; }
  .tm th { color:var(--dim); font-weight:500; font-size:0.7rem; text-align:left; padding:3px 6px 3px 0; border-bottom:1px solid var(--line); }
  .tm td { padding:5px 6px 5px 0; border-bottom:1px solid var(--line); vertical-align:top; white-space:nowrap; }
  .tm td.top { white-space:normal; color:var(--mut); }
  .tm .up { color:var(--up); } .tm .dn { color:var(--dn); }
  .tm p.sub { margin:6px 0 0; }
  @media (max-width:520px) { .tm table { font-size:0.72rem; } .tm th:nth-child(4), .tm td:nth-child(4) { display:none; } }
  @media (max-width:520px) { .row .nm { min-width:0; } }
"""


# GOLDEN_THEME은 .badge를 IBM Plex Mono로 그려 한글 자간이 벌어진다("판 단 없 음") — 배지만 한글 글꼴로(테마 뒤에 둬야 이김)
BADGE_FIX = "<style>.badge { font-family:'Noto Sans KR',-apple-system,\"Malgun Gothic\",sans-serif; font-variant-numeric:normal; }</style>"


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _html_kr(r: dict) -> list[str]:
    """국내 마감 리포트 윗부분 — 장세 · 전략 한 줄과 오늘 할 일."""
    P: list[str] = []
    g = r.get("regime")
    if g is None:
        P.append('<div class="market side"><b>국내 시장 정리본 없음</b><span class="mx">장세 판단을 못 했습니다 — 2_kr_market 상태를 확인하세요.</span></div>')
    else:
        cls = {"상승장": "up", "하락장": "dn"}.get(g["state"], "side")
        P.append(f'<div class="market {cls}"><b>코스피 {_e(g["state"])} {_e(g["days"])}일째</b>'
                 f'<span class="mf">{_e(g["strategy"])}</span>'
                 f'<span class="mx">{_e(g["favor"])}</span>'
                 f'<span class="mx">{"🟢 오늘 대량 복귀일 · " if g["mass_today"] else "대량 복귀일 아님 · "}{_e(g["mass_text"].split("·", 1)[-1].strip())}</span></div>')

        # 2. 오늘 할 일
        P.append("<h2>오늘 할 일</h2>")
        P.append('<div class="card">')
        if r["candidates"]:
            for c in r["candidates"]:
                P.append(f'<div class="row"><span class="nm">{_e(c.get("name"))}</span><span class="tx">{_e(c.get("setup", ""))} · '
                         f'손절 <span class="px">{c.get("stop", 0):,}</span> · 목표 <span class="px">{c.get("target", 0):,}</span></span>'
                         f'<span class="badge on">신규 후보</span></div>')
        else:
            P.append('<div class="row"><span class="nm">신규 후보</span><span class="tx">없음 — 규칙 충족 0개</span></div>')
        for o in r["observe"]:
            P.append(f'<div class="row"><span class="nm">{_e(o["name"])}</span><span class="tx muted">{_e(_r(o.get("info", "")))}</span>'
                     f'<span class="badge">관찰 · 거래 규칙 아님</span></div>')
        P.append("</div>")
        P += _html_holdings(r)
        if r["watch"]:
            nw_ = sum(bool(flow_warn(h, r["date"])[0]) for h in r["watch"])
            P.append('<details class="fold"><summary>관심 종목 ' + str(len(r["watch"])) + "개 — 매수 신호 없음"
                     + (f" · 수급 경고 {nw_}" if nw_ else "") + "</summary><table>")
            for h in r["watch"]:
                W, R = flow_warn(h, r["date"])
                fw = (f'<br><span class="fw">⚠ {_e(" · ".join(W))} — {FLOW_WARN_TAIL}</span>' if W else "") + \
                     (f'<br><span class="sub">참고: {_e(" · ".join(R))}</span>' if R else "")
                P.append(f'<tr><td>{_e(h["name"])}</td><td>{_e(_r(h.get("head", "")))}{fw}</td><td>{_e(_r(h.get("verdict", "")))}</td></tr>')
            P.append("</table></details>")
    return P


# ── 보유 종목 세 층(2026-10-15 사용자 승인) ─────────────────────────────────────────────
# ① 경고 = 검증된 수급 경고만(flow_warn) · ② 추세 = 250일선 이격 × 120일선 방향 + Core 추세 강도(9.330 · 9.342: 이어지는 쪽, 끝은 모름)
# ③ 사실 · 위험 = 예측 아님(2_kr holding_facts.py 값). 맨 위에 같은 테마 묶음(60일 상관).
HOLD_CSS = """
 .hgrp { border-left:3px solid var(--warn); } .hgrp .gh { font-size:0.75rem; color:var(--warn); font-weight:700; margin-bottom:4px; }
 .hgrp .gl { font-size:0.85rem; line-height:1.65; }
 .hc .hh { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 10px; padding-bottom:6px; border-bottom:1px solid var(--line); margin-bottom:4px; }
 .hc .hn { font-weight:700; font-size:0.95rem; } .hc .hb { font-weight:700; } .hc .hh .badge { margin-left:auto; }
 .ly { display:flex; gap:10px; padding:4px 0; font-size:0.84rem; line-height:1.6; }
 .lk { min-width:56px; color:var(--dim); font-size:0.74rem; padding-top:2px; } .lk.w { color:var(--warn); }
 .lt { flex:1; } .hc .up, .hgrp .up { color:var(--up); } .hc .dn, .hgrp .dn { color:var(--dn); } .hc .wn { color:var(--warn); }
 @media (max-width:520px){ .ly { flex-direction:column; gap:0; } .hc .hh .badge { margin-left:0; } }
"""


def _pc(v: float, d: int = 1) -> str:
    return f'<span class="{"up" if v > 0 else "dn"}">{v:+.{d}f}%</span>'


def _trend_word(x: dict) -> tuple[str, str]:
    a, b = x["gap250"] > 0, x["slope120"] > 0
    return ("살아 있음", "up") if a and b else (("꺾임", "dn") if not a and not b else ("엇갈림", "wn"))


def _html_holdings(r: dict) -> list[str]:
    P: list[str] = []
    for g in r.get("hold_groups", []):
        out = f' 나머지와는 {g["corr_out"]:.2f}.' if g.get("corr_out") is not None else ""
        P.append(f'<div class="card hgrp"><div class="gh">묶음으로 보기</div>'
                 f'<div class="gl">{_e(g["theme"])} {len(g["codes"])}종목({_e(" · ".join(g["names"]))})은 최근 60일 서로 상관 평균 '
                 f'<b>{g["corr_in"]:.2f}</b> — 사실상 한 덩어리로 움직입니다.{out}</div>'
                 f'<div class="gl">오늘 평균 <b>{_pc(g["today"])}</b> — 보유의 {len(g["codes"])}/{g["n_hold"]}이 같은 재료에 걸려 있습니다.</div></div>')
    news = r.get("holdings_news", [])
    for h in r["holdings"]:
        body, v = _holding_line(h)
        badge = f'<span class="badge vf">{_e(v)}</span>' if v == "검증됨" else f'<span class="badge">{_e(body)}</span>'
        rank = _r(h.get("head", "")).split("→", 1)[0].replace("보유 ·", "").strip()
        x = h.get("facts") or {}
        W, Rf = flow_warn(h, r["date"])
        P.append('<div class="card hc">')
        top = (f'{_pc(x["today"])}<span class="sub">오늘 · 거래량 평소 {x["vol_ratio"]:.1f}배</span>' if x else "")
        P.append(f'<div class="hh"><span class="hn">{_e(h["name"])}</span>{top}{badge}</div>')
        if v == "검증됨" and body:
            P.append(f'<div class="ly"><span class="lk">판단</span><span class="lt">{_e(body)}</span></div>')
        P.append(f'<div class="ly"><span class="lk w">① 경고</span><span class="lt fw">⚠ {_e(" · ".join(W))} — {FLOW_WARN_TAIL}</span></div>' if W else
                 '<div class="ly"><span class="lk">① 경고</span><span class="lt muted">검증된 경고 없음</span></div>')
        if not x:
            P.append(f'<div class="ly"><span class="lk">② 추세</span><span class="lt">{_e(rank)} <span class="muted">(일봉 값 없음)</span></span></div></div>')
            continue
        tw, tc = _trend_word(x)
        P.append(f'<div class="ly"><span class="lk">② 추세</span><span class="lt">긴 추세 <b class="{tc}">{tw}</b> — '
                 f'250일선 {x["gap250"]:+.0f}% {"위" if x["gap250"] > 0 else "아래"} · 120일선 {"오르는 중" if x["slope120"] > 0 else "내리는 중"} · '
                 f'1년 {x["r250"]:+.0f}% · {_e(rank)}</span></div>')
        volw = "평소보다 큼" if x["vol_rank"] >= 0.8 else ("평소보다 작음" if x["vol_rank"] <= 0.2 else "평소 수준")
        facts = [f'20일 {_pc(x["r20"])}' + (f'(코스피200 {x["bm20"]:+.1f}%)' if "bm20" in x else ""),
                 f'1년 고점 대비 {_pc(x["dd250"])}', f'하루 보통 ±{x["vol20"]:.1f}% 움직임({volw})']
        f = h.get("flow") or {}
        fl = ([f'기관 20일 합 {f["inst_sum20"] / 100:+,.0f}억({f["inst_days20"]}일 순매수)'] if "inst_sum20" in f else []) + \
             ([f'공매도 비중 {f["short_pct20"]}%'] if "short_pct20" in f else [])
        sub = " · ".join(fl) + (f' · 참고: {" · ".join(Rf)}' if Rf else "")
        P.append(f'<div class="ly"><span class="lk">③ 사실</span><span class="lt">{" · ".join(facts)}'
                 + (f'<br><span class="muted">수급: {_e(sub)}</span>' if sub else "") + '</span></div>')
        ev = list(x.get("events", [])) + ([f'작년엔 {x["prelim_ly"]} 잠정실적 발표'] if x.get("prelim_ly") else []) + \
             [f'기사: {n["title"]}' for n in news if h["name"] in n.get("names", "")][:2]
        if ev:
            P.append('<div class="ly"><span class="lk">사건</span><span class="lt muted">' + " / ".join(_e(e) for e in ev) + "</span></div>")
        P.append("</div>")
    return P


def _html_charts(r: dict) -> list[str]:
    """종목 차트 — 보유 · 신규(Core 페이지의 종목 칸을 그대로, core_charts.py). 요약 아래(자세한 단계)."""
    if r.get("regime") is None:
        return []
    css, body = charts_html(r["date"], {h["code"] for h in r["holdings"]}, {c["code"] for c in r["candidates"] if c.get("code")})
    r["_chart_css"] = css
    return ["<h2>종목 차트 — 보유 · 신규</h2>", body]


def _html_ref(r: dict, heading: str) -> list[str]:
    P = [f"<h2>{heading}</h2>", '<div class="card ref">']
    for x in r["ref"]:
        late = ' <span class="late">기준일 뒤 자료</span>' if x["late"] else ""
        if x["k"] == "해외":
            extra = "".join(f'<br><span class="muted">{_e(s)}</span>' for s in (x.get("t2"), x.get("t3")) if s)
            P.append(f'<div class="row"><span class="k">해외</span><span class="tx">{_e(x["t"])}{late}{extra}</span></div>')
        elif x["k"] == "매크로":
            P.append(f'<div class="row"><span class="k">매크로</span><span class="tx">{_e(x["t"])} <span class="sub">{_e(_md(x["d"]))} 기준</span>{late}</span></div>')
        else:
            items = "<br>".join(f'<a href="{_e(i["link"])}">{_e(i["issue"])}</a> <span class="sub">채널 {i["channels"]}</span> — '
                                f'<span class="muted">{_e(i["title"][:70])}</span>' for i in x.get("issues", []))
            P.append(f'<div class="row"><span class="k">뉴스</span><span class="tx">{items}</span></div>')
            ub = x.get("us_brief")
            if ub:
                P.append(f'<div class="row"><span class="k">미국</span><span class="tx"><a href="{_e(ub.get("link", ""))}">{_e(ub["text"])}</a></span></div>')
    if r.get("night_futures"):
        P.append(f'<div class="row"><span class="k">야간선물</span><span class="tx">{_e(r["night_futures"])}</span></div>')
    P.append("</div>")
    return P


def _html_core(r: dict, heading: str) -> list[str]:
    S = core_summary(r)
    if not S:
        return []
    sig = ref_signals(r)
    extra = ('<div class="sig-h">참고 신호</div><ul class="sig">' + "".join(f"<li>{_e(x)}</li>" for x in sig) + "</ul>") if sig else ""
    return [f"<h2>{heading}</h2>", '<div class="card core"><ul>' + "".join(f"<li>{_e(s)}</li>" for s in S) + "</ul>" + extra + "</div>"]


def _streak_tag(n: int) -> str:
    return f'<span class="tag">{n}일째</span>' if n >= 2 else ('<span class="tag new">오늘</span>' if n == 1 else "")


def _pct(v, digits: int = 1, unit: str = "%") -> str:
    return "" if v is None else f'<span class="{"up" if v > 0 else "dn" if v < 0 else ""}">{v:+.{digits}f}{unit}</span>'


def _html_themes(r: dict, heading: str) -> list[str]:
    """테마 흐름 — 테마마다 두 줄(이름 · 평균 등락 · 지속 · 뉴스 / 상위 종목). 휴대폰에서 칸이 쪼개지지 않게 표 대신 목록(2026-10-10)."""
    t = r.get("themes") or {}
    rows, weak = _theme_pick(r)
    P = [f"<h2>{heading}</h2>"]
    if not rows:
        P.append(f'<div class="card ref"><span class="muted">테마 자료 없음 — {_e(t.get("note", "2 국내 themes.json 없음"))}</span></div>')
        return P
    P.append('<div class="card ref tl">')
    for g in rows:
        nw = r.get("theme_news", {}).get(g["theme"])
        news = ""
        if nw:
            news = (f'<a class="chip" href="{_e(nw["link"])}">뉴스 {nw["channels"]}채널</a>' if nw.get("link")
                    else f'<span class="chip">뉴스 {nw["channels"]}채널</span>')
        meta = f'+5%↑ {g["hot"]}/{g["n"]}' + (f' · 5일 {g["r5"]:+.1f}%' if g.get("r5") is not None else "")
        top = " · ".join(f'{_e(x["name"])} {_pct(x["pct"])}' for x in g["top"])
        P.append(f'<div class="it"><div class="h"><b>{_e(g["theme"])}</b> {_pct(g["avg"])} {_streak_tag(g["streak"])} '
                 f'<span class="sub">{meta}</span> {news}</div><div class="d">{top}</div></div>')
    if weak:
        P.append('<p class="sub">약한 테마: ' + " · ".join(f'{_e(g["theme"])} {_pct(g["avg"])}' for g in weak) + "</p>")
    titles = [x for x in sorted(r.get("theme_news", {}).values(), key=lambda x: (-x["channels"], -x["msgs"]))
              if x["channels"] >= THEME_NEWS_MIN and x.get("title")][:3]
    for x in titles:
        P.append(f'<p class="sub">{_e(x["theme"])} 뉴스 — <a href="{_e(x["link"])}">{_e(x["title"][:70])}</a></p>')
    P.append(f'<p class="sub">{_e(_md(t.get("date", "")))} 종가 · Core 테마 묶음 {len(t.get("groups", []))}개 중 평균 등락 상위와 뉴스 많은 테마 · '
             f'"N일째" = 평균 등락 상위 {t.get("top_n", 5)} 연속 · 뉴스 = 그 테마 종목 · 키워드를 다룬 채널 수.</p></div>')
    return P


# ── 테마 돈의 흐름(2026-10-15 사용자 승인 — 테마 사이클 자료의 관점: 어디로 돈이 갔나 · 어느 덩치가 움직였나 · 며칠 머물렀나) ──
# 값은 2_kr themes.json "flow"(theme_flow.py · theme_map.json). 방향 판단 없음(참고).
FLOW_CSS = """
 .tf .tiers { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:8px; }
 .tf .tier { flex:1; min-width:96px; border:1px solid var(--line); padding:6px 8px; font-size:0.78rem; }
 .tf .tier b { display:block; font-size:0.72rem; color:var(--dim); font-weight:600; }
 .tf .sum { font-size:0.86rem; line-height:1.65; margin:4px 0 8px; }
 .tf .g { padding:7px 0; border-bottom:1px solid var(--line); }
 .tf .g:last-of-type { border-bottom:0; }
 .tf .gh { display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 8px; font-size:0.88rem; }
 .tf .gd { margin-top:2px; font-size:0.76rem; color:var(--mut); line-height:1.6; }
 .tf .up { color:var(--up); } .tf .dn { color:var(--dn); }
 .tf .tag { font-size:0.68rem; color:var(--warn); border:1px solid var(--line); padding:0 6px; }
 .heat { overflow-x:auto; margin-top:6px; }
 .heat table { border-collapse:separate; border-spacing:2px; font-size:0.66rem; }
 .heat td { width:16px; height:16px; padding:0; text-align:center; }
 .heat td.n { width:auto; white-space:nowrap; padding-right:6px; color:var(--mut); text-align:left; }
 .heat td.on { outline:1px solid var(--tx); }
 .heat th { font-weight:400; color:var(--dim); font-size:0.6rem; }
"""


def _heat_bg(v) -> str:
    if v is None:
        return "transparent"
    a = min(abs(v) / 6, 1) * 0.85 + 0.08
    return f"color-mix(in srgb, var({'--up' if v > 0 else '--dn'}) {a * 100:.0f}%, transparent)"


def _html_theme_flow(r: dict, heading: str) -> list[str]:
    f = (r.get("themes") or {}).get("flow") or {}
    gs = f.get("groups") or []
    P = [f"<h2>{heading}</h2>"]
    if not gs:
        P.append(f'<div class="card ref"><span class="muted">테마 흐름 자료 없음 — {_e(f.get("note", "2 국내 themes.json flow 없음"))}</span></div>')
        return P
    P.append('<div class="card ref tf">')
    # 어느 덩치가 움직였나
    tz = f.get("tiers") or {}
    P.append('<div class="tiers">' + "".join(
        f'<div class="tier"><b>{tn} {t["n"]}종목</b>{_pct(t["ret"])} · 거래대금 {t["share"]:.0f}%'
        f'<span class="sub"> (평소 {t["share_usual"]:.0f}%)</span></div>' for tn, t in tz.items()) + "</div>")
    # 한 줄: 돈이 몰린 곳 · 빠진 곳(거래대금 몫이 평소 대비 크게 바뀐 그룹 — 몫 0.5% 이상만)
    big = [g for g in gs if g.get("share_x") and g["share"] >= 0.5]
    inn = sorted([g for g in big if g["share_x"] >= 1.2], key=lambda g: -g["share_x"])[:3]
    outg = sorted([g for g in big if g["share_x"] <= 0.8], key=lambda g: g["share_x"])[:3]
    lead = max(tz.items(), key=lambda kv: kv[1]["share"] - kv[1]["share_usual"])[0] if tz else ""
    s = []
    if inn:
        s.append("돈이 더 몰린 곳: " + " · ".join(f'<b>{_e(g["theme"])}</b>(평소의 {g["share_x"]:.1f}배)' for g in inn))
    if outg:
        s.append("빠진 곳: " + " · ".join(f'{_e(g["theme"])}({g["share_x"]:.1f}배)' for g in outg))
    if lead:
        s.append(f"거래대금이 평소보다 {lead}주 쪽으로 쏠림")
    if s:
        P.append('<div class="sum">' + "<br>".join(s) + "</div>")
    for g in gs:
        tiers = " · ".join(f'{tn} {_pct(t["ret"])}' for tn, t in g.get("tiers", {}).items())
        spread = (f' · 확산 {g["spread"]:.2f}' if g.get("spread") is not None else "")
        top = " · ".join(f'{_e(x["name"])} {_pct(x["pct"])}' for x in g["top"])
        P.append(f'<div class="g"><div class="gh"><b>{_e(g["theme"])}</b> {_pct(g["ret"])} {_streak_tag(g["streak"])}'
                 f'<span class="sub">5일 {g["r5"]:+.1f}% · 거래대금 몫 {g["share"]:.1f}%(평소 {g["share_x"]:.1f}배) · 오른 종목 {g["up"]}/{g["n"]}{spread}</span></div>'
                 f'<div class="gd">{tiers}<br>{top}</div></div>')
    # 히트맵 — 최근 20거래일 그룹별 거래대금 가중 등락, 최신 날짜가 왼쪽, 테두리 = 그날 상위 {top_n}
    days = [d for d, _, _ in gs[0]["heat"]][::-1]
    P.append('<details class="fold" open><summary>최근 20거래일 히트맵</summary><div class="heat"><table><tr><th></th>'
             + "".join(f'<th>{d[8:]}</th>' for d in days) + "</tr>")
    for g in gs:
        P.append(f'<tr><td class="n">{_e(g["theme"])}</td>' + "".join(
            f'<td class="{"on" if on else ""}" style="background:{_heat_bg(v)}" title="{d} {"" if v is None else f"{v:+.1f}%"}"></td>'
            for d, v, on in g["heat"][::-1]) + "</tr>")
    P.append("</table></div></details>")
    P.append(f'<p class="sub">{_e(_md(f.get("date", "")))} 종가 · {f.get("n_stocks")}종목 · 등락 = 20일 거래대금 가중 · '
             f'확산 = 5등 ÷ 1등 등락 · 층 = 대형 10조+ · 중형 1 – 10조 · 소형 1조 미만 · 테두리 = 그날 상위 {f.get("top_n", 5)}.</p></div>')
    return P


# 검증 번호(9.xxx) — 값(+9.8 · 9.11% · 0.9배)과 구분: 앞에 숫자 · 부호 · 점 없음, 뒤에 숫자 · % · σ · 배 없음
_REF = r"(?<![\d+\-−.,])9\.\d{1,3}(?:\s*[A-Z]\d|\s*[①-⑩])?(?![\d%.σ배])"
_TRIM = [re.compile(p) for p in (r"\s*\([^()<>]*" + _REF + r"[^()<>]*\)", r"\s*[—–]\s*" + _REF + r"(?:\s*·\s*" + _REF + r")*",
                                  r"(?:\s*·)?\s*대량 복귀일 근거 " + _REF + r"(?:\s*·\s*" + _REF + r")*",
                                  r"\s*\(전환 기간\)", r"\.?\s*기계 규칙 · 검증 전\(참고\)", r"\s*→ 동시 지표 · 기록")]


def _trim(t: str) -> str:
    """자료에서 온 설명문에서 검증 번호 · 이력 꼬리를 뺌 — 화면엔 지금 기준만."""
    for p in _TRIM:
        t = p.sub("", t or "")
    return t.strip(" ·,;")


def _trim_html(h: str) -> str:
    """태그 밖 글자에만 _trim 규칙 적용(텔레그램 문안 <pre>는 그대로)."""
    out = []
    for part in re.split(r"(<pre[\s\S]*?</pre>|<[^>]+>)", h):
        if part and not part.startswith("<"):
            for p in _TRIM:
                part = p.sub("", part)
        out.append(part)
    return "".join(out)


US_TOP, US_LOW = 5, 3   # 미국 섹터: 강한 5 + 약한 3


def _html_us_sectors(r: dict, heading: str) -> list[str]:
    """미국 섹터 흐름 — 섹터마다 두 줄(섹터 · ETF 등락 · 지속 · 국내 연관 / 많이 움직인 종목)."""
    t = r.get("us_themes") or {}
    ss = t.get("sectors") or []
    P = [f"<h2>{heading}</h2>"]
    if not ss:
        P.append(f'<div class="card ref"><span class="muted">미국 섹터 자료 없음 — {_e(t.get("note", "3 해외 us_themes.json 없음"))}</span></div>')
        return P
    kr = {g["theme"]: g for g in (r.get("themes") or {}).get("groups", [])}
    strong, weak = ss[:US_TOP], [s for s in ss[::-1][:US_LOW][::-1] if s not in ss[:US_TOP]]
    P.append('<div class="card ref tl">')
    for i, s in enumerate(strong + weak):
        if i == len(strong) and weak:
            P.append('<div class="sep">약한 섹터</div>')
        k = kr.get(s.get("kr", ""))
        link = ""
        if s.get("kr"):
            link = f'<span class="chip">국내 {_e(s["kr"])}' + (f' · {"어제 " if r["slot"] == "am" else ""}{k["avg"]:+.1f}%' if k else "") + "</span>"
        meta = f'{_e(s["etf"])}' + (f' · 평소의 {abs(s["z"]):.1f}배' if s.get("z") is not None else "") + (f' · 5일 {s["r5"]:+.1f}%' if s.get("r5") is not None else "")
        top = " · ".join(f'{_e(x["code"])} {_pct(x["pct"])}' for x in s["top"])
        P.append(f'<div class="it"><div class="h"><b>{_e(s["theme"])}</b> {_pct(s["chg"])} {_streak_tag(s["streak"])} '
                 f'<span class="sub">{meta}</span> {link}</div><div class="d">{top}</div></div>')
    mv = t.get("movers") or []
    if mv:
        P.append(f'<p class="sub">큰 움직임(±{t.get("big_pct", 5):.0f}% 이상): ' + " · ".join(
            f'{_e(m["code"])} {_pct(m["pct"])} <span class="sub">{_e(m["sector"])}</span>' for m in mv[:10]) + "</p>")
    P.append(f'<p class="sub">{_e(_md(t.get("date", "")))} 미국 종가 · VM-SPC Global 섹터 ETF {len(ss)}개와 구성 대형주 · "N일째" = ETF 등락 상위 {t.get("top_n", 5)} 연속 · '
             "국내 칩 = 같은 성격의 국내 테마.</p></div>")
    return P


def _html_kr_brief(r: dict) -> list[str]:
    l1, l2 = _kr_brief(r)
    g = r.get("regime") or {}
    cls = {"상승장": "up", "하락장": "dn"}.get(g.get("state"), "side")
    P = ["<h2>어제 국내</h2>", f'<div class="market {cls}"><span class="mf">{_e(l1)}</span>']
    if l2:
        P.append(f'<span class="mx">{_e(l2)}</span>')
    if g:
        n = len(r.get("candidates", []))
        P.append(f'<span class="mx">신규 후보 {n}개' + (f' · 관찰 {_e(", ".join(o["name"] for o in r.get("observe", [])))}' if r.get("observe") else "") + "</span>")
    P.append("</div>")
    return P


def _html_weekend_news(r: dict) -> list[str]:
    iss = r.get("issues_all", [])
    if not iss:
        return []
    P = ["<h2>주말 뉴스 — 다룬 채널 수 순</h2>", '<div class="card ref">']
    for i, x in enumerate(iss, 1):
        t = f'<a href="{_e(x["link"])}">{_e(x["title"][:70])}</a>' if x.get("link") else _e(x.get("title", "")[:70])
        P.append(f'<div class="row"><span class="k">{i}</span><span class="tx">{_e(x["issue"])} <span class="sub">채널 {x["channels"]}</span>'
                 f'<br><span class="muted">{t}</span></span></div>')
    for x in r.get("holdings_news", []):
        P.append(f'<div class="row"><span class="k">종목</span><span class="tx">{_e(x["names"])} — <span class="muted">{_e(x["title"])}</span></span></div>')
    if r.get("reports", {}).get("text"):
        P.append(f'<div class="row"><span class="k">리포트</span><span class="tx">{_e(r["reports"]["text"])}</span></div>')
    P.append("</div>")
    return P


def _html_weekly_kr(r: dict) -> list[str]:
    P = _html_kr_brief(r)
    P[0] = "<h2>지난주 국내</h2>"
    top, bot = _weekly_themes(r)
    if top:
        P.append('<div class="card"><div class="row"><span class="k">주간 강세</span><span class="tx">'
                 + " · ".join(f"{_e(g['theme'])} {_pct(g['r5'])}" for g in top) + "</span></div>"
                 + ('<div class="row"><span class="k">주간 약세</span><span class="tx">'
                    + " · ".join(f"{_e(g['theme'])} {_pct(g['r5'])}" for g in bot) + "</span></div>" if bot else "")
                 + f'<p class="sub">테마 묶음 5거래일 평균 등락 · {_e(_md((r.get("themes") or {}).get("date", "")))} 기준</p></div>')
    return P


def render_html(r: dict, tg: str) -> str:
    am = r["slot"] == "am"
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    g = r.get("regime")
    P: list[str] = []
    dw = f'<div class="card warnbox">{_e(data_warning(r))}</div>' if data_warning(r) else ""
    if r.get("weekend"):
        P.append(f'<h1>주말 정리 · 미국 {_e(r["date"])} 마감 · 주말 뉴스</h1>')
        P.append(f'<div class="intro">{_e(TOP_LINE)}</div>')
        if dw:
            P.append(dw)
        P += _html_core(r, "핵심")
        P += _html_weekend_news(r)
        P += _html_weekly_kr(r)
        P += _html_us_sectors(r, "미국 섹터 흐름(금요일)")
        P += _html_foreign(r)
        P += _html_checklist(r)
        P += _html_liquidity(r)
        P += _html_ref(r, "자세히 — 금요일 미국 · 매크로")
    elif am:
        P.append(f'<h1>{TITLE["am"]} · 미국 {_e(r["date"])} 마감</h1>')
        P.append(f'<div class="intro">{_e(TOP_LINE)}</div>')
        if dw:
            P.append(dw)
        # 칸 순서(2026-10-15 사용자: "중요한 순서대로") — 판단 · 오늘 할 일에 가까운 것 먼저, 느린 배경 · 원자료는 뒤로
        P += _html_core(r, "핵심")
        P += _html_kr_brief(r)
        P += _html_us_sectors(r, "미국 섹터 흐름")
        P += _html_themes(r, "어제 국내 테마 · 밤사이 뉴스 언급")
        P += _html_theme_flow(r, "어제 국내 테마 돈의 흐름")
        P += _html_foreign(r)
        P += _html_checklist(r)
        P += _html_liquidity(r)
        P += _html_ref(r, "자세히 — 밤사이 숫자")
    else:
        P.append(f'<h1>{TITLE["pm"]} · {_e(r["date"])}</h1>')
        P.append(f'<div class="intro">{_e(TOP_LINE)}</div>')
        if dw:
            P.append(dw)
        P += _html_kr(r)
        P += _html_core(r, "요약")
        P += _html_charts(r)
        P += _html_themes(r, "테마 흐름")
        P += _html_theme_flow(r, "테마 돈의 흐름")
        P += _html_ref(r, "자세히 — 해외 · 매크로 · 뉴스")

    # 칸 번호(2026-10-11 사용자: "순번이 있어야") — 위에서부터 1, 2, 3 …, 접힌 칸은 맨 아래 근거
    k = 0
    for i, x in enumerate(P):
        if x.startswith("<h2>"):
            k += 1
            P[i] = x.replace("<h2>", f'<h2><span class="no">{k}</span> ', 1)

    # 4. 접힌 칸
    ev = signal_evidence_html(r)
    if ev:
        P.append(ev)
    if not am:
        fe = flow_evidence_html(r)
        if fe:
            P.append(fe)
    if g is not None:
        P.append('<details class="fold"><summary>판단 근거</summary>')
        P.append(f"<p>{_e(g['why'])}</p><p>{_e(g['nums'])}</p><p>{_e(g['text'])} · 대량 복귀일 근거 {_e(g['mass_ref'])}</p>")
        if r.get("flows"):
            P.append(f"<p>코스피 수급: {_e(r['flows'])}</p>")
        P.append("</details>")
    nw = r["srcs"].get("5_news")
    if nw:
        it = nw["_items"]
        P.append('<details class="fold"><summary>뉴스 더 보기</summary>')
        for k in ("kr_close", "reports", "holdings_news"):
            if k in it:
                P.append(f"<p><b>{_e(it[k]['title'])}</b> — {_e(it[k]['text'])}</p>")
        P.append("</details>")
    us = r["srcs"].get("3_us_market")
    mc = r["srcs"].get("4_macro")
    if us or mc:
        P.append('<details class="fold"><summary>해외 · 매크로 전체</summary>')
        if us:
            P.append(f"<p>{_e(us['_items'].get('us_close', {}).get('text', ''))}</p>")
            if r.get("etf_note"):
                P.append(f"<p>{_e(r['etf_note'])}</p>")
        if mc:
            for it in mc.get("items", []):
                P.append(f"<p><b>{_e(it['title'])}</b> — {_e(it['text'])}</p>")
        P.append("</details>")

    P.append('<details class="fold"><summary>정리본 원문 · 생성 시각 · status</summary><table>'
             "<tr><th>역할</th><th>기준일</th><th>생성</th><th>status</th><th>원문</th></tr>")
    for role in ROLES:
        s = r["srcs"].get(role)
        if s is None:
            P.append(f'<tr><td>{ROLE_NAME[role]}</td><td colspan="4" class="failed">정리본 없음</td></tr>')
            continue
        md = s["_file"].with_suffix(".md")
        rel = os.path.relpath(md if md.exists() else s["_file"], RESULTS).replace("\\", "/")
        st = s.get("status", "?")
        late = ' <span class="late">기준일 뒤</span>' if s["_late"] else ""
        P.append(f'<tr><td>{ROLE_NAME[role]}</td><td>{_e(s["date"])} {_e(s.get("slot", ""))}{late}</td>'
                 f'<td>{_e(s.get("generated_at", "")[:16].replace("T", " "))}</td><td class="{_e(st)}">{_e(st)}</td>'
                 f'<td><a href="{_e(rel)}">{_e(s["_file"].name)}</a></td></tr>')
    P.append("</table>")
    notes = [f"{ROLE_NAME[k]}: {s['notes']}" for k, s in r["srcs"].items() if s and s.get("notes")]
    for n in notes:
        P.append(f"<p>{_e(_trim(n))}</p>")
    P.append(f'<p>텔레그램 문안</p><pre style="white-space:pre-wrap;font-family:\'IBM Plex Mono\',monospace;font-size:0.75rem">{_e(tg)}</pre>')
    P.append("</details>")
    P.append(f'<p class="sub" style="margin-top:16px">만든 시각 {now} KST · hub-core build_report.py</p>')

    return ('<!DOCTYPE html>\n<html lang="ko"><head><meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
            f"<title>{TITLE[r['slot']]} {_e(r['date'])}</title>\n<style>{BASE_CSS}{HOLD_CSS}{FLOW_CSS}</style>"
            + GOLDEN_THEME + BADGE_FIX + (f"<style>{r['_chart_css']}</style>" if r.get('_chart_css') else "") + '</head>\n<body>\n  <div class="rb"></div>\n' + _trim_html("\n".join(P)) + "\n</body></html>\n")


# ── 실행 ────────────────────────────────────────────────────────────────

def write_exchange(r: dict, html_path: Path, sent: str) -> None:
    d = EXCHANGE / "1_core" / r["date"]
    d.mkdir(parents=True, exist_ok=True)
    srcs = r["srcs"]
    status = "ok" if all(srcs.get(k) and srcs[k].get("status") == "ok" for k in ROLES) else "partial"
    g = r.get("regime") or {}
    head = f"코스피 {g.get('state', '?')} {g.get('days', '')}일째 — {g.get('strategy', '')}" if g else "국내 정리본 없음"
    if r["slot"] == "am":
        us = srcs.get("3_us_market")
        head = (us.get("headline", "") if us else "해외 정리본 없음") + " | 어제 국내: " + head
    s = {
        "role": "1_core", "date": r["date"], "slot": r["slot"],
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"), "status": status,
        "sources": [f"{k}/{v['date']}/{v['_file'].name}" for k, v in srcs.items() if v],
        "headline": head,
        "items": [{"key": "report", "title": "최종 리포트", "text": head,
                   "value": {"html": str(html_path), "telegram": sent}, "grade": "서술", "ref": "", "link": ""}],
        "notes": "; ".join(f"{k} 기준일 뒤 자료({v['date']})" for k, v in srcs.items() if v and v["_late"]),
    }
    name = r["slot"] + ("_weekend" if r.get("weekend") else "")     # 주말판이 토요일 아침판(같은 미국 기준일)을 덮지 않게
    # 이미 보낸 날을 --send 없이 다시 만들면(확인용) 전송 기록은 그대로 둔다 — "보내지 않음(시범본)"으로 덮이지 않게
    old = d / f"summary_{name}.json"
    if not sent.endswith("보냄") and old.exists():
        try:
            prev = json.loads(old.read_text(encoding="utf-8"))["items"][0]["value"]["telegram"]
            if str(prev).endswith("보냄"):
                sent = prev
                s["items"][0]["value"]["telegram"] = prev
        except (ValueError, KeyError, IndexError, TypeError):
            pass
    (d / f"summary_{name}.json").write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / f"summary_{name}.md").write_text(
        f"# 코어 리포트 {r['date']} {r['slot']}\n\n- {head}\n- HTML: {html_path}\n- 텔레그램: {sent}\n- status: {status}\n"
        + (f"- 비고: {s['notes']}\n" if s["notes"] else ""), encoding="utf-8")
    (EXCHANGE / "1_core" / "latest.json").write_text(json.dumps({"date": r["date"], "slot": r["slot"]}), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="기준일 YYYY-MM-DD — pm은 한국 거래일(없으면 2_kr latest), am은 미국 현지 거래일(없으면 3_us latest)")
    ap.add_argument("--slot", choices=["am", "pm"], default="pm")
    ap.add_argument("--send", action="store_true", help="텔레그램 전송(문안 + HTML 파일)")
    ap.add_argument("--warn", default="", help="예약 스크립트가 넘기는 실패 단계(맨 위 ⚠ 줄)")
    ap.add_argument("--weekend", action="store_true", help="월요일 주말 정리판(--slot am과 함께) — 뉴스 · 매크로는 오늘(월)까지")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    target = args.date
    if not target:
        lj = EXCHANGE / ("3_us_market" if args.slot == "am" else "2_kr_market") / "latest.json"
        target = json.loads(lj.read_text(encoding="utf-8"))["date"] if lj.exists() else _date.today().isoformat()

    if args.send:
        try:   # 앞서 나간 참고 신호의 결과 채우기(이미 있는 일봉만 읽음) — 접힌 칸 실전 기록에 쓰임
            import signal_log
            print(f"[build_report] 실전 기록 결과 채움 {signal_log.evaluate()}건")
        except Exception as ex:  # noqa: BLE001
            print(f"[build_report] 실전 기록 채우기 실패: {ex}", file=sys.stderr)
    r = build(target, args.slot, weekend=args.weekend)
    r["warn"] = args.warn.strip()
    tg = _trim_html(telegram_text(r))      # 텔레그램도 지금 기준만 — 검증 번호 · 이력 꼬리 뺌
    RESULTS.mkdir(exist_ok=True)
    stem = f"report_{target}_{args.slot}" + ("_weekend" if args.weekend else "")
    html_path = RESULTS / f"{stem}.html"
    html_path.write_text(render_html(r, tg), encoding="utf-8")
    (RESULTS / f"{stem}.txt").write_text(tg, encoding="utf-8")

    sent = "보내지 않음(시범본)"
    if args.send:
        # 전송이 실패해도 예약 스크립트가 멈추지 않게 — 로그만 남기고 0으로 끝낸다(HTML · 문안은 이미 저장됨)
        try:
            from vm_spc.notify_telegram import send_document, send_message
            send_message(tg)
            send_document(html_path, caption=("주말 정리" if args.weekend else TITLE[args.slot]) + f" {target}")
            sent = datetime.now(KST).strftime("%Y-%m-%d %H:%M 보냄")
            try:
                import signal_log
                print(f"[build_report] 참고 신호 기록 {signal_log.record(r)}건")
            except Exception as ex2:  # noqa: BLE001
                print(f"[build_report] 참고 신호 기록 실패: {ex2}", file=sys.stderr)
        except Exception as ex:  # noqa: BLE001
            msg = re.sub(r"/bot[^/\s]+/", "/bot***/", str(ex))   # 오류 URL에 봇 토큰이 들어 있음 — 로그 · 정리본에 남기지 않음
            sent = f"전송 실패: {type(ex).__name__}: {msg}"
            print(f"[build_report] 텔레그램 {sent}", file=sys.stderr)
    write_exchange(r, html_path, sent)
    print(tg)
    print(f"\nHTML: {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
