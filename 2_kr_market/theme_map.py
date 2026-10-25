"""테마 흐름용 상위군 소속표(2026-10-15 사용자 승인 — "테마 흐름을 보는 관점을 가져오고 싶다", 분기마다 다시 만듦).

  python theme_map.py          → theme_map.json 다시 만들기 + 바뀐 점 출력
  python theme_map.py --dry    → 저장하지 않고 출력만

themes.GROUPS(23군 · Core 바스켓)는 그대로 둔다 — signal_log 검증 신호 · 5_news 키워드 · 3_us 연관 테마가 그 이름을 쓴다.
이 파일은 그 위에 "돈의 흐름" 보기용 소속표를 따로 만든다. 규칙(미리 정함, 결과 보고 바꾸지 않음):
1. 시장 뺀 일별 수익(동일가중 시장 × 종목 베타를 뺀 나머지)으로 그룹 지수(종목 동일가중) 상관을 120 · 250거래일 두 기간에 잰다.
2. 합치기: 그룹 지수끼리 상관이 두 기간 모두 MERGE_AT(0.75) 이상이면 한 상위군(이름은 " · "로 잇고 원래 이름은 꼬리표).
3. 빼기: 그룹 안 상관(종목 ↔ 자기 그룹 나머지) 중앙값이 두 기간 모두 DROP_AT(0.2) 미만인 그룹은 상위군에서 뺌 — 종목은 4로 다시 배정.
4. 종목은 상위군 하나에만: 두 기간 평균 상관이 가장 높은 상위군. 그 값이 KEEP_AT(0.2) 미만이면 "기타"(흐름 집계에서 뺌).
5. 넓히기(골라서): 바스켓 밖 Core _long_history 종목 중 60일 하루 거래대금 ≥ EXTRA_TV(200억) ∧ 가장 잘 맞는 상위군 상관 ≥ EXTRA_CORR(0.4) ∧ ETF 아님.
   이 종목 일봉은 theme_extra.py가 매일 받는다(바스켓 · _scenario에 있으면 그걸 읽음).
6. 상위군은 종목 MIN_N(5)개 이상만.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from themes import DATA, GROUPS, _names, _watchlist

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "theme_map.json"
MERGE_AT, DROP_AT, KEEP_AT, EXTRA_TV, EXTRA_CORR, MIN_N = 0.75, 0.2, 0.2, 200e8, 0.4, 5
WINS = (120, 250)
# 보이는 이름만 바꿈(소속 규칙은 그대로) — 2026-10-15 점검: Core "IT" 바스켓은 삼성전자 · SK하이닉스 · 삼성전기 · SK스퀘어 등 대형이라
# 시장 뺀 상관으로 그 종목들이 여기 남고, 중소형 반도체 · 소부장은 "반도체"에 모임(대형 반도체 날 / 소부장 날이 갈림).
RENAME = {"IT": "대형 반도체 · IT", "반도체": "반도체 중소형 · 소부장"}
LIQ_TV = 30e8           # 바스켓 밖 후보를 볼 때 최소 거래대금(30억)


def _read(f: Path, n: int = 400) -> pd.DataFrame:
    d = pd.read_csv(f, encoding="utf-8-sig", usecols=["date", "close", "volume"]).tail(n)
    d.index = pd.to_datetime(d["date"].astype(str))
    return d


def _resid(P: pd.DataFrame, w: int) -> pd.DataFrame:
    R = np.log(P).diff().tail(w)
    R = R.loc[:, R.notna().mean() > 0.9]
    m = R.mean(axis=1)
    b = R.apply(lambda s: s.cov(m)) / m.var()
    return R - np.outer(m.values, b.values)


def build() -> tuple[dict, list[str]]:
    wl = _watchlist()
    names = _names(wl)
    targets = {t["target"]["code"] for t in wl["themes"].values()}
    mem: dict[str, set] = {}
    files: dict[str, Path] = {}
    for g, bs, _ in GROUPS:
        for b in bs:
            for p in (DATA / b).glob("*.csv"):
                if p.stem.isdigit() and p.stem not in targets:
                    mem.setdefault(p.stem, set()).add(g)
                    files.setdefault(p.stem, p)
    px = {c: _read(f)["close"] for c, f in files.items()}
    P = pd.DataFrame(px).sort_index()
    E = {w: _resid(P, w) for w in WINS}
    gn = [g for g, _, _ in GROUPS]

    def gidx(e, cs, skip=None):
        cs = [c for c in cs if c in e.columns and c != skip]
        return e[cs].mean(axis=1) if len(cs) >= 3 else None

    # 2 합치기
    gi = {w: pd.DataFrame({g: gidx(E[w], [c for c in mem if g in mem[c]]) for g in gn}).dropna(axis=1, how="all") for w in WINS}
    parent = {g: g for g in gn}

    def root(g):
        while parent[g] != g:
            g = parent[g]
        return g
    pairs = []
    for i, a in enumerate(gn):
        for b in gn[i + 1:]:
            cs = [gi[w][a].corr(gi[w][b]) if a in gi[w] and b in gi[w] else np.nan for w in WINS]
            if all(c >= MERGE_AT for c in cs):
                parent[root(b)] = root(a)
                pairs.append(f"{a} + {b}({min(cs):.2f} – {max(cs):.2f})")
    sup: dict[str, list[str]] = {}
    for g in gn:
        sup.setdefault(root(g), []).append(g)
    sname = {r: (gs[0] if all(g.startswith(gs[0]) for g in gs) else " · ".join(gs)) for r, gs in sup.items()}   # 반도체 + 반도체 소부장 → 반도체
    sname = {r: RENAME.get(v, v) for r, v in sname.items()}
    s_of = {g: sname[root(g)] for g in gn}
    s_root = {v: k for k, v in sname.items()}

    # 3 빼기 — 원래 그룹 단위 안쪽 상관 중앙값
    drop = []
    for g in gn:
        meds = []
        for w in WINS:
            cs = [c for c in mem if g in mem[c] and c in E[w].columns]
            v = [E[w][c].corr(gidx(E[w], cs, c)) for c in cs if gidx(E[w], cs, c) is not None]
            meds.append(np.nanmedian(v) if v else np.nan)
        if len(sup[root(g)]) == 1 and all(m < DROP_AT for m in meds if not np.isnan(m)):
            drop.append(f"{g}(안쪽 상관 중앙값 {meds[0]:.2f} · {meds[1]:.2f})")
    dropped = {d.split("(")[0] for d in drop}
    supers = sorted({s_of[g] for g in gn if g not in dropped}, key=lambda s: gn.index(s_root[s]))
    smem = {s: [c for c in mem if any(s_of[g] == s for g in mem[c])] for s in supers}

    # 4 종목 배정
    def score(e_by_w, c, ref):
        v = []
        for w in WINS:
            e = e_by_w[w]
            if c not in e.columns:
                continue
            idx = gidx(e, ref, c)
            if idx is not None:
                v.append(e[c].corr(idx))
        return float(np.mean(v)) if v else np.nan

    stocks = {}
    for c in mem:
        sc = {s: score(E, c, smem[s]) for s in supers}
        sc = {s: v for s, v in sc.items() if not np.isnan(v)}
        if not sc:
            continue
        best = max(sc, key=sc.get)
        stocks[c] = {"name": names.get(c, c), "group": best if sc[best] >= KEEP_AT else "기타", "corr": round(sc[best], 3),
                     "tags": sorted(mem[c]), "src": "basket"}

    # 5 넓히기
    LH = DATA / "_long_history"
    xp, xtv = {}, {}
    for f in LH.glob("*.csv"):
        if f.stem in mem or not f.stem.isdigit():
            continue
        d = _read(f)
        if len(d) < 260 or (d.close * d.volume).tail(60).mean() < LIQ_TV:
            continue
        xp[f.stem], xtv[f.stem] = d["close"], float((d.close * d.volume).tail(60).mean())
    etf_words = ("KODEX", "TIGER", "KBSTAR", "ARIRANG", "HANARO", "KOSEF", "ACE", "SOL", "RISE", "PLUS")
    PX = pd.concat([P, pd.DataFrame(xp)], axis=1).sort_index()
    EX = {w: _resid(PX, w) for w in WINS}
    for c in xp:
        nm = names.get(c, c)
        if xtv[c] < EXTRA_TV or nm.split()[0] in etf_words or nm.isdigit():
            continue
        sc = {s: score(EX, c, smem[s]) for s in supers}
        sc = {s: v for s, v in sc.items() if not np.isnan(v)}
        if sc and max(sc.values()) >= EXTRA_CORR:
            best = max(sc, key=sc.get)
            stocks[c] = {"name": nm, "group": best, "corr": round(sc[best], 3), "tags": [], "src": "extra"}

    groups = {}
    for s in supers:
        cs = [c for c, v in stocks.items() if v["group"] == s]
        if len(cs) >= MIN_N:
            groups[s] = {"tags": sup[s_root[s]], "codes": cs}
    for c, v in stocks.items():
        if v["group"] not in groups:
            v["group"] = "기타"
    keywords = {s: sorted({k for g in groups[s]["tags"] for gg, _, kw in GROUPS if gg == g for k in kw}) for s in groups}
    for s in groups:
        groups[s]["keywords"] = keywords[s]
    asof = f"{P.index.max():%Y-%m-%d}"
    m = {"asof": asof, "rules": {"merge_at": MERGE_AT, "drop_at": DROP_AT, "keep_at": KEEP_AT, "extra_tv_eok": EXTRA_TV / 1e8,
                                 "extra_corr": EXTRA_CORR, "min_n": MIN_N, "windows": list(WINS)},
         "merged": pairs, "dropped": drop, "groups": groups, "stocks": stocks}
    log = [f"기준 {asof} · 상위군 {len(groups)} · 종목 {sum(v['group'] != '기타' for v in stocks.values())} (기타 {sum(v['group'] == '기타' for v in stocks.values())})",
           "합침: " + (" / ".join(pairs) or "없음"), "뺌: " + (" / ".join(drop) or "없음"),
           "넓힘: " + " · ".join(f"{v['name']}→{v['group']}({v['corr']:.2f})" for v in stocks.values() if v["src"] == "extra")]
    moved = [f"{v['name']}: {'/'.join(v['tags'])} → {v['group']}({v['corr']:.2f})" for v in stocks.values()
             if v["src"] == "basket" and not any(s_of[t] == v["group"] for t in v["tags"])]
    log.append("옮김 · 기타: " + (" / ".join(moved) or "없음"))
    return m, log


def load() -> dict:
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    m, log = build()
    print("\n".join(log))
    for s, g in m["groups"].items():
        print(f"  {s}: {len(g['codes'])}종목")
    if "--dry" not in sys.argv:
        OUT.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        print("저장:", OUT)
