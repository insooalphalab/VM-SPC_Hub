"""테마 흐름(하루치) — VM-SPC_Core 테마 묶음(바스켓) 일봉을 읽어 테마별 그날 강도 · 지속을 낸다(2026-10-10 사용자 결정).

  python themes.py [YYYY-MM-DD]      # 확인용 출력. 평소에는 export_exchange.py 가 불러 themes.json 으로 저장

- 테마 = Core basket_watchlist.json 의 테마 39개를 비슷한 것끼리 합친 GROUPS(종목은 각 바스켓 폴더의 일봉 파일).
- 강도 = 그날 종목 평균 등락 · +5% 이상 종목 수 · 상위 종목. 지속 = 평균 등락 상위 TOP_N 안에 든 날이 며칠째 이어지는지.
- 방향 판단은 하지 않는다(검증 전 · 참고). 예시: 5_news 의 "데구르르 테마 사이클" — 그 하루치 축약판.
- 키워드는 5_news 가 테마별 뉴스 언급을 셀 때 쓴다(themes.json 에 같이 실음).
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent.parent / "VM-SPC_Core"
DATA = CORE / "data"
TOP_N, HOT, LOOKBACK = 5, 5.0, 25          # 지속은 상위 5 기준, +5% 이상 = 강한 종목, 지속 계산에 볼 거래일

# (테마, Core 바스켓 이름들, 뉴스 키워드) — 바스켓 39개 중 '코스피 대형'(테마 아님)만 뺌
GROUPS = [
    ("반도체", ["semiconductor_to_etf", "semiconductor_krx_scan", "semiconductor_top10_fnguide_scan", "semiconductor_k_price_scan",
             "semiconductor_ai_top3_scan", "semiconductor_ai_top2plus_scan", "semiconductor_ai_top2plus_pr_scan", "semiconductor_hbm_scan"],
     ["반도체", "HBM", "D램", "디램", "낸드", "메모리", "파운드리"]),
    ("반도체 소부장", ["semiconductor_ai_equip_scan", "semiconductor_frontend_scan", "semiconductor_ai_core_equip_scan"],
     ["소부장", "반도체 장비", "전공정", "후공정", "패키징", "유리기판"]),
    ("전력기기", ["power_equipment_to_etf", "power_equipment_kedi_scan", "power_ai_core_scan"],
     ["전력기기", "변압기", "전력망", "송전", "배전", "전선", "전력설비"]),
    ("원전", ["nuclear_smr_scan", "nuclear_korea_scan"], ["원전", "원자력", "SMR", "웨스팅하우스"]),
    ("2차전지", ["secondary_battery_fnguide_scan", "secondary_battery_krx_scan"],
     ["2차전지", "이차전지", "배터리", "전고체", "양극재", "ESS", "리튬"]),
    ("화장품", ["cosmetics_to_etf", "cosmetics_fnguide_scan", "cosmetics_wise_scan"], ["화장품", "K뷰티", "뷰티"]),
    ("조선", ["shipbuilding_to_etf"], ["조선", "LNG선", "선박", "해양플랜트", "MASGA"]),
    ("로봇", ["robotics_to_etf"], ["로봇", "휴머노이드"]),
    ("방산", ["defense_to_etf"], ["방산", "미사일", "전투기", "무기", "국방"]),
    ("자동차", ["auto_to_etf"], ["자동차", "완성차", "전기차", "자율주행"]),
    ("바이오", ["bio_to_etf"], ["바이오", "신약", "임상", "FDA", "기술이전", "비만"]),
    ("IT", ["it_general_scan"], ["스마트폰", "전자부품", "MLCC", "기판", "카메라모듈"]),
    ("금융(은행 · 보험)", ["bank_to_etf", "insurance_to_etf"], ["은행주", "시중은행", "보험주", "금융지주"]),   # "은행"은 한국은행에 걸림
    ("증권", ["securities_to_etf"], ["증권주", "거래대금"]),                                            # "증권사"는 리포트 출처에 늘 나옴
    ("에너지화학", ["energy_chem_to_etf"], ["정유", "석유화학", "화학", "유가", "원유"]),
    ("철강", ["steel_to_etf"], ["철강", "철광석"]),
    ("건설", ["construction_to_etf"], ["건설", "재건", "주택", "부동산"]),
    ("운송", ["transport_to_etf"], ["항공", "해운", "운임", "물류"]),
    ("게임", ["game_to_etf"], ["게임", "신작"]),
    ("인터넷", ["internet_to_etf"], ["인터넷", "플랫폼"]),
    ("필수소비재", ["staples_to_etf"], ["음식료", "식품", "라면", "담배"]),
    ("엔터", ["entertainment_to_etf"], ["엔터", "K팝", "콘텐츠", "아이돌", "드라마"]),
]


def _watchlist() -> dict:
    return json.loads((CORE / "basket_watchlist.json").read_text(encoding="utf-8"))


def _names(wl: dict) -> dict[str, str]:
    nm = {}
    p = DATA / "_scenario" / "names.json"
    if p.exists():
        nm.update(json.loads(p.read_text(encoding="utf-8")))
    nm.update({s["code"]: s["name"] for s in wl.get("stocks", [])})
    return nm


def _closes(path: Path, n: int) -> dict[str, float]:
    """일봉 CSV 마지막 n줄 → {YYYY-MM-DD: 종가}."""
    with path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))[-n:]
    return {f"{r['date'][:4]}-{r['date'][4:6]}-{r['date'][6:8]}": float(r["close"]) for r in rows if r.get("close")}


def compute(day: str) -> dict:
    wl = _watchlist()
    names = _names(wl)
    targets = {t["target"]["code"] for t in wl["themes"].values()}
    groups, closes = [], {}
    for g, baskets, kw in GROUPS:
        codes = sorted({p.stem for b in baskets if (DATA / b).exists() for p in (DATA / b).glob("*.csv")
                        if p.stem.isdigit() and p.stem not in targets})
        for c in codes:
            if c not in closes:
                f = next((DATA / b / f"{c}.csv" for b in baskets if (DATA / b / f"{c}.csv").exists()), None)
                closes[c] = _closes(f, LOOKBACK + 10) if f else {}
        groups.append({"theme": g, "gi": len(groups), "codes": codes, "keywords": kw})

    days = sorted({d for cl in closes.values() for d in cl if d <= day})[-(LOOKBACK + 6):]
    if not days or days[-1] != day:
        return {"date": day, "groups": [], "note": f"테마 묶음 일봉에 {day} 봉 없음(마지막 {days[-1] if days else '없음'})"}

    def ret(c: str, i: int, k: int = 1) -> float | None:
        cl = closes.get(c, {})
        a, b = cl.get(days[i - k]), cl.get(days[i])
        return (b / a - 1) * 100 if a and b else None

    # 날마다 테마 평균 등락 → 상위 TOP_N 안에 든 날의 연속 횟수(지속)
    hist = {g["theme"]: [] for g in groups}
    for i in range(1, len(days)):
        avgs = {}
        for g in groups:
            rs = [r for r in (ret(c, i) for c in g["codes"]) if r is not None]
            avgs[g["theme"]] = sum(rs) / len(rs) if rs else None
        ranked = sorted((v, t) for t, v in avgs.items() if v is not None)[::-1]
        top = {t for _, t in ranked[:TOP_N]}
        for t in hist:
            hist[t].append(t in top)

    last = len(days) - 1
    out = []
    for g in groups:
        rows = [(c, ret(c, last)) for c in g["codes"]]
        rows = [(c, r) for c, r in rows if r is not None]
        if not rows:
            continue
        rs = [r for _, r in rows]
        r5 = [r for r in (ret(c, last, 5) for c in g["codes"]) if r is not None] if last >= 5 else []
        streak = 0
        for on in reversed(hist[g["theme"]]):
            if not on:
                break
            streak += 1
        top = sorted(rows, key=lambda x: -x[1])[:3]
        out.append({
            "theme": g["theme"], "gi": g["gi"], "n": len(rows), "avg": round(sum(rs) / len(rs), 2), "med": round(statistics.median(rs), 2),
            "hot": sum(r >= HOT for r in rs), "cold": sum(r <= -HOT for r in rs), "up": sum(r > 0 for r in rs),
            "r5": round(sum(r5) / len(r5), 2) if r5 else None, "streak": streak,
            "top": [{"code": c, "name": names.get(c, c), "pct": round(r, 2)} for c, r in top],
            "names": [names[c] for c in g["codes"] if c in names], "keywords": g["keywords"],
        })
    out.sort(key=lambda x: -x["avg"])
    return {"date": day, "top_n": TOP_N, "hot_pct": HOT, "groups": out,
            "note": f"테마 {len(out)}개 · Core 테마 묶음 일봉 · 지속 = 평균 등락 상위 {TOP_N} 연속 일수"}


def line(t: dict, k: int = 3) -> str:
    """요약 한 줄 — 강한 테마 k개."""
    gs = t.get("groups") or []
    if not gs:
        return t.get("note", "테마 자료 없음")
    return " · ".join(f"{g['theme']} {g['avg']:+.1f}%" + (f"({g['streak']}일째)" if g["streak"] >= 2 else "") for g in gs[:k])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    d = sys.argv[1] if len(sys.argv) > 1 else json.loads((CORE / "results" / "scenario" / "screen.json").read_text(encoding="utf-8"))["date"]
    t = compute(d)
    print(t["note"])
    for g in t["groups"]:
        print(f"{g['theme']:12s} 평균 {g['avg']:+6.2f}% 중앙 {g['med']:+6.2f}% · +5%↑ {g['hot']}/{g['n']} · 5일 {g['r5'] if g['r5'] is not None else '–':>6} · "
              f"지속 {g['streak']}일 · " + " ".join(f"{x['name']} {x['pct']:+.1f}%" for x in g["top"]))
