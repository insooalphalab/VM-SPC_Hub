"""VM-SPC_Core 16:30 파이프라인 결과(읽기만)를 exchange/2_kr_market/{거래일}/ 로 내보낸다.

  python export_exchange.py
→ summary_pm.json · summary_pm.md · candidates.json · holdings.json + latest.json
판정은 다시 하지 않는다 — Core가 낸 JSON을 형식만 바꿔 옮긴다.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORE = ROOT.parent.parent / "VM-SPC_Core"
SCN = CORE / "results" / "scenario"
INVESTOR = CORE / "data" / "_market" / "investor_kospi.csv"
OUT = ROOT.parent / "exchange" / "2_kr_market"
KST = timezone(timedelta(hours=9))
# flows 에 싣는 투자자(investor_kospi.csv 열 → 이름). 금액 단위는 백만 원 → 억 원으로 바꿔 싣는다
WHO = {"foreign_amt": "외국인", "indiv_amt": "개인", "inst_amt": "기관", "pension_amt": "연기금", "fin_inv_amt": "금융투자"}


def load(name: str):
    return json.loads((SCN / name).read_text(encoding="utf-8"))


def won(info: str, word: str):
    """Core 카드 문구('… 손절 41,600 · 목표 65,900')에서 손절 · 목표 가격을 읽는다. 없으면 None."""
    m = re.search(word + r" ([\d,]+)", info or "")
    return int(m.group(1).replace(",", "")) if m else None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    market, screen, holds, mass_days = load("market.json"), load("screen.json"), load("summary.json"), load("mass_days.json")
    day, problems = screen["date"], []
    for k, d in (("market.json", market["date"]), *((f"summary.json {h['name']}", h["date"]) for h in holds)):
        if d != day:
            problems.append(f"{k} 기준일 {d}(screen {day})")

    # regime
    regime_txt = (f"{market['state']} {market['days']}일째 · 60일선 대비 {market['vs_ma60']:+.1%} · "
                  f"60일선 기울기 {market['ma60_slope']:+.1%}")
    # mass_recovery — 오늘 여부는 screen.json, 마지막 날짜는 mass_days.json(Core 기록)
    ms = screen["mass"]
    last_mass = mass_days[-1] if mass_days else None
    mass_txt = (f"{'오늘 대량 복귀일' if ms['today'] else '오늘 아님'} · 복귀 섹터 {ms['sectors']}/{ms['cut']} · "
                f"마지막 대량 복귀일 {last_mass}")
    # candidates — 시점별 규칙 충족 목록 + 관찰 카드(응축 등, 매수 규칙 밖)
    cands = []
    for ls in screen["lists"]:
        for x in ls["items"]:
            cands.append({"code": x["code"], "name": x["name"], "setup": ls["label"], "stop": won(x.get("info"), "손절"),
                          "target": won(x.get("info"), "목표"), "info": x.get("info", ""), "why": x.get("why", "")})
    observe = [{"code": x["code"], "name": x["name"], "setup": "관찰 · " + x.get("obs_why", ""), "stop": won(x.get("info"), "손절"),
                "target": won(x.get("info"), "목표"), "info": x.get("info", "")} for x in screen["observe"]["items"]]
    cand_txt = (f"규칙 충족 {len(cands)}개" + (" — " + " · ".join(c["name"] for c in cands) if cands else "")
                + f" | 관찰 {len(observe)}개" + (" — " + " · ".join(c["name"] for c in observe) if observe else ""))
    # holdings — Core 요약 그대로(head 문구는 Core 검증 규칙의 결과)
    holdings = [{k: h[k] for k in ("code", "name", "head", "verdict", "verified", "active", "hold")} for h in holds]
    n_hold = sum(h["hold"] for h in holdings)
    # 보유 · 관심 수급 표시 — 연기금 연속 · 기관 꾸준 · 공매도 비중 값만(문구는 1_core, 2026-10-14 · 9.322 · 9.325 · 9.326)
    import flow_flags as ff
    try:
        fflags = ff.compute([h["code"] for h in holdings], day)
    except Exception as ex:   # 표시가 빠질 뿐 정리본은 낸다
        fflags = {"short_date": None, "short_n": 0, "codes": {}}
        problems.append(f"flow_flags 실패: {ex}")
    for h in holdings:
        h["flow"] = fflags["codes"].get(h["code"], {})
        if h["flow"].get("flow_date") not in (None, day):
            problems.append(f"{h['name']} 투자자별 기준일 {h['flow']['flow_date']}")
    # 보유 코멘트 ② 추세 · ③ 사실 · 위험 값(2026-10-15) — 문구는 1_core
    import holding_facts as hfx
    try:
        hfacts = hfx.compute([h["code"] for h in holdings], day, {h["code"] for h in holdings if h["hold"]},
                             {h["code"]: h["name"] for h in holdings})
    except Exception as ex:
        hfacts = {"codes": {}, "groups": []}
        problems.append(f"holding_facts 실패: {ex}")
    for h in holdings:
        h["facts"] = hfacts["codes"].get(h["code"], {})
        if h["facts"] and h["facts"].get("px_date") != day:
            problems.append(f"{h['name']} 일봉 기준일 {h['facts']['px_date']}")
    flagged = [h["name"] for h in holdings if h["flow"].get("pension_flag") or h["flow"].get("inst_flag")]
    flag_txt = (f"연기금 연속 5일+ · 기관 꾸준 매수 해당 {len(flagged)}종목" + (" — " + " · ".join(flagged) if flagged else "")
                + f" | 공매도 비중 기준일 {fflags['short_date']}")
    # flows — 코스피 투자자별 순매수 마지막 날
    with INVESTOR.open(encoding="utf-8") as f:
        last = list(csv.DictReader(f))[-1]
    flow_day = f"{last['date'][:4]}-{last['date'][4:6]}-{last['date'][6:]}"
    flows = {name: round(float(last[col]) / 100) for col, name in WHO.items()}
    if flow_day != day:
        problems.append(f"investor_kospi.csv 기준일 {flow_day}")
    flow_txt = f"코스피 {float(last['kospi_close']):,.2f} · " + " · ".join(f"{k} {v:+,}억" for k, v in flows.items())
    # themes — Core 테마 묶음 일봉으로 테마별 그날 강도 · 지속(themes.py, 2026-10-10)
    import themes as th
    tm = th.compute(day)
    if not tm["groups"]:
        problems.append(tm["note"])
    theme_txt = th.line(tm)
    # 테마 돈의 흐름 — theme_map.json 상위군 · 거래대금 가중 · 몫 · 확산 · 시총 층(theme_flow.py, 2026-10-15)
    import theme_flow as tf
    try:
        tm["flow"] = tf.compute(day)
        if not tm["flow"].get("groups"):
            problems.append(f"theme_flow: {tm['flow'].get('note')}")
    except Exception as ex:
        problems.append(f"theme_flow 실패: {ex}")

    notes = ["판정 = VM-SPC_Core 16:30 파이프라인 결과", "flows 단위 억 원(순매수)"]
    summary = {
        "role": "2_kr_market", "date": day, "slot": "pm",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "status": "partial" if problems else "ok",
        "sources": ["VM-SPC_Core results/scenario", "VM-SPC_Core data/_market/investor_kospi.csv"],
        "headline": f"코스피 {market['state']} {market['days']}일째 · 대량 복귀일 {'예' if ms['today'] else '아님'} · "
                    f"규칙 충족 {len(cands)}개 · 보유 {n_hold}종목",
        "items": [
            {"key": "regime", "title": "코스피 장세", "text": regime_txt,
             "value": {k: market[k] for k in ("state", "days", "vs_ma60", "ma60_slope", "favor", "nums")},
             "grade": "서술", "ref": "", "link": ""},
            {"key": "mass_recovery", "title": "대량 복귀일", "text": mass_txt,
             "value": {"today": ms["today"], "sectors": ms["sectors"], "cut": ms["cut"], "recent": ms["recent"], "last": last_mass},
             "grade": "서술", "ref": "9.152 · 9.153", "link": ""},
            {"key": "candidates", "title": "오늘 규칙 충족 종목", "text": cand_txt, "value": "candidates.json",
             "grade": "서술", "ref": "", "link": ""},
            {"key": "holdings", "title": "보유 · 관심 종목 상태", "text": f"보유 {n_hold} · 관심 {len(holdings) - n_hold}",
             "value": "holdings.json", "grade": "서술", "ref": "", "link": ""},
            {"key": "flow_flags", "title": "보유 · 관심 수급 표시(값은 holdings.json 종목별 flow)", "text": flag_txt,
             "value": {"short_date": fflags["short_date"], "short_n": fflags["short_n"], "flagged": flagged},
             "grade": "서술", "ref": "9.322 · 9.325 · 9.326", "link": ""},
            {"key": "flows", "title": f"코스피 투자자별 순매수({flow_day}, 억 원)", "text": flow_txt, "value": flows,
             "grade": "참고", "ref": "9.15", "link": ""},
            {"key": "themes", "title": "테마 흐름(평균 등락 · 지속)", "text": theme_txt, "value": "themes.json",
             "grade": "참고", "ref": "", "link": ""},
        ],
        "notes": "; ".join(notes + problems),
    }

    out = OUT / day
    out.mkdir(parents=True, exist_ok=True)
    dump = lambda name, obj: (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dump("summary_pm.json", summary)
    dump("candidates.json", {"date": day, "state": screen["state"], "strategy": screen["strategy"], "why": screen["why"],
                             "candidates": cands, "observe": observe})
    dump("holdings.json", {"date": day, "holdings": holdings, "groups": hfacts["groups"]})
    dump("themes.json", tm)
    md = [f"# 국내 시장 — {day} 마감 (생성 {summary['generated_at'][:16].replace('T', ' ')} KST, {summary['status']})", "",
          f"**장세** {regime_txt}", f"- {market['favor']}", "",
          f"**대량 복귀일** {mass_txt}", "",
          f"**오늘 전략** {screen['strategy']} — {cand_txt}"]
    md += [f"- {c['name']}({c['code']}) {c['setup']} · {c['info']}" for c in cands + observe]
    md += ["", "**보유 · 관심**", "| 종목 | 상태 | 판정 |", "|---|---|---|"]
    md += [f"| {'보유' if h['hold'] else '관심'} {h['name']} | {h['head']} | {h['verdict'] or '–'} |" for h in holdings]
    md += ["", f"**보유 · 관심 수급 표시** {flag_txt}"]
    md += [f"- {h['name']}: 연기금 연속 {h['flow'].get('pension_streak', '–')}일 · 기관 20일 중 {h['flow'].get('inst_days20', '–')}일 순매수"
           + (f" · 공매도 비중 {h['flow']['short_pct20']}%(상위 {1 - h['flow']['short_rank']:.0%})" if "short_pct20" in h["flow"] else "")
           for h in holdings]
    md += ["", f"**수급(참고)** {flow_txt}", "", f"**테마 흐름(참고)** {theme_txt}"]
    md += [f"- {g['theme']} {g['avg']:+.1f}% · +5%↑ {g['hot']}/{g['n']} · 지속 {g['streak']}일 · "
           + " ".join(f"{x['name']} {x['pct']:+.1f}%" for x in g["top"]) for g in tm["groups"][:5]]
    md += ["", "참고: " + " / ".join(notes + problems)]
    (out / "summary_pm.md").write_text("\n".join(md).replace("~", "–") + "\n", encoding="utf-8")  # 물결표는 깃허브에서 취소선
    (OUT / "latest.json").write_text(json.dumps({"date": day, "slot": "pm"}), encoding="utf-8")
    print(f"완료: {out} ({summary['status']}, 후보 {len(cands)} · 관찰 {len(observe)} · 보유 {n_hold})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
