"""종목 차트 — VM-SPC_Core가 만든 페이지에서 종목 칸(차트 포함)을 잘라 리포트 한 장 안에 넣는다(2026-10-10 사용자 결정).

- 차트는 허브에서 다시 그리지 않는다. hub_pm.ps1이 15:41에 실행하는 Core `scenario/render_risk.py`(보유 · 관심 → risk_scenarios.html)와
  `scenario/screen.py`(오늘의 후보 → screen.html)의 결과를 읽기만 한다.
- 넣는 종목: 보유 + 신규 후보. 칸 안의 "{코드} · {날짜} 종가 기준"이 리포트 기준일과 다르면 넣지 않는다(어제 차트가 섞이지 않게).
- Core 페이지 CSS는 `.stx` 아래로 범위를 좁혀 가져온다 — 리포트의 .row · .nm · .market 등과 겹치지 않게. 색은 리포트 GOLDEN_THEME 것을 그대로 씀.
- 탭은 Core와 같은 방식(숨긴 라디오 + CSS, 스크립트 없음 — 텔레그램 · 휴대폰 HTML 뷰어).
"""
from __future__ import annotations

import html
import re
from pathlib import Path

SCEN = Path(__file__).resolve().parents[2] / "VM-SPC_Core" / "results" / "scenario"
PAGES = (("risk_scenarios.html", "hold"), ("screen.html", "new"))

_SEC = re.compile(r'<section id="s-(\d{6})" class="stock[^"]*">(.*?)</section>', re.S)
_DATE = re.compile(r'\d{6} · (\d{4}-\d{2}-\d{2}) 종가 기준')
_NAME = re.compile(r'<div class="nm">(.*?)</div>')
_SKIP = re.compile(r'^\s*(:root|\*|body|h1|\.intro|\.budget|\.holdsum|\.market)\b')


def _scoped_css(page: str) -> str:
    """Core 페이지 첫 <style>(기본 CSS)을 .stx 아래로. 페이지 머리(:root · body · 장세 칸 등) 규칙은 뺀다."""
    m = re.search(r"<style>(.*?)</style>", page, re.S)
    if not m:
        return ""
    out = []

    def rules(css: str, pre: str = "") -> None:
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            sel = sel.strip()
            if not sel or _SKIP.match(sel):
                continue
            out.append(pre + ", ".join(f".stx {s.strip()}" for s in sel.split(",")) + " {" + body + "}")

    css = m.group(1)
    for mq, inner in re.findall(r"(@media[^{]+)\{((?:[^{}]*\{[^{}]*\})*)\s*\}", css):
        start = len(out)
        rules(inner)
        out[start:] = [mq.strip() + " { " + " ".join(out[start:]) + " }"]
    rules(re.sub(r"@media[^{]+\{(?:[^{}]*\{[^{}]*\})*\s*\}", "", css))
    return "\n".join(out)


def charts_html(target: str, hold_codes: set[str], new_codes: set[str]) -> tuple[str, str]:
    """(CSS, 본문 HTML). 넣을 게 없으면 본문은 이유 한 줄."""
    css, items, notes = "", [], []
    seen: set[str] = set()
    for fn, kind in PAGES:
        p = SCEN / fn
        want = hold_codes if kind == "hold" else new_codes
        if not want:
            continue
        if not p.exists():
            notes.append(f"{fn} 없음")
            continue
        page = p.read_text(encoding="utf-8")
        css = css or _scoped_css(page)
        for code, body in _SEC.findall(page):
            if code not in want or code in seen:
                continue
            d = _DATE.search(body)
            if not d or d.group(1) != target:
                notes.append(f"{code} 차트가 {d.group(1) if d else '?'} 기준이라 넣지 않음")
                continue
            seen.add(code)
            nm = _NAME.search(body)
            body = body.replace(f'clip{code}', f'hclip{code}').replace(" — 판단에 쓰지 않음", "")   # 판단 안내는 리포트 맨 위 한 줄만(2026-10-10)
            items.append((code, html.unescape(nm.group(1)) if nm else code, kind, body))
    if not items:
        why = " · ".join(notes) or "보유 · 신규 후보 없음"
        return "", f'<div class="card"><span class="sub">종목 차트 없음 — {html.escape(why)}</span></div>'
    radios, tabs, secs, tcss = [], [], [], []
    for i, (code, nm, kind, body) in enumerate(items):
        radios.append(f'<input type="radio" name="htab" class="tabr" id="ht-{code}"{" checked" if i == 0 else ""}>')
        tabs.append(f'<label for="ht-{code}">{html.escape(nm)} · {"보유" if kind == "hold" else "신규"}</label>')
        secs.append(f'<section id="hs-{code}" class="stock">{body}</section>')
        tcss.append(f'#ht-{code}:checked ~ #hs-{code} {{ display:block; }} '
                    f'#ht-{code}:checked ~ .tabs label[for="ht-{code}"] {{ color:var(--bg); background:var(--acc); border-color:var(--acc); font-weight:700; }}')
    note = f'<p class="sub">{html.escape(" · ".join(notes))}</p>' if notes else ""
    body = (f'<div class="stx">{"".join(radios)}<style>{"".join(tcss)}</style>'
            f'<div class="tabs">{"".join(tabs)}</div>{"".join(secs)}</div>{note}')
    return css, body
