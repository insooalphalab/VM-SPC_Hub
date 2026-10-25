"""results/ 아래 폴더별(ETF·바스켓별)로 흩어진 대시보드를 한 화면에서 보는 통합 인덱스.

각 바스켓 폴더(results/{basket}/)를 스캔해 완전히 다른 두 예측을 나란히, 절대 섞이지 않게 보여준다
(2026-09-27, 실제 사용자 혼동 사례로 분리 확정됨 — "한국콜마 69% 상승우세"가 ETF 얘기인지 콜마
얘기인지 구분이 안 된다는 지적):

  ① ETF 자체 예측 — 예측모델(Legacy/Breadth)이 그 타겟 ETF 자신의 익일 방향을 추정한 값
     (v2_summary_metrics.json 의 breadth_series 최신값 vs breadth_threshold, 대시보드 헤더의
     "오늘 기준 실시간 예측 카드"와 정확히 같은 로직).
  ② 센서 종목 중 최고 신호 — 챔피언-챌린저 모델이 그 바스켓 안의 개별 구성종목(센서)들을 서로
     비교해서 가장 확신이 강한 종목 하나를 뽑은 것. ETF 자체의 등락과는 무관하다 — "이 종목이
     바스켓 내 다른 종목들 대비 상대적으로 강할 확률"일 뿐, "이 종목 때문에 ETF가 오른다"는 뜻이
     아니다(대시보드 챔피언-챌린저 탭의 캡션과 동일한 제약).

상세는 각 바스켓 자기 dashboard_v2.html로 링크한다.

국내판(VM-SPC_Core, v2_config.core_root())의 결과 파일이 있으면 같은 두 예측을 아래에 "국내 ETF" 영역으로
붙인다 — 국내판이 만든 v2_summary_metrics.json·vm_spc_dashboard_data.json·etf_extras.json 을 **읽기만**
하고, 국내판 화면과 같은 값(괴리율 보정 적중률 포함)을 그대로 보여준다. 07:00에 열면 국내 영역은 전날
16:30 국내판 실행분 = 그날 국내장 예측이다.

  python vm_spc/build_index.py                 # results/index.html 생성
  python vm_spc/pipeline.py                    # 전체 바스켓(기본, --basket 없이) 처리 후 자동 재생성
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parent.parent
for _p in (_ROOT, _ROOT / "core", _ROOT / "vm_predict", _ROOT / "pair_spc"):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import ast
import html
import json
import logging
import os
import sys
from pathlib import Path

from v2_config import KST, core_root, load_baskets, results_dir

log = logging.getLogger("vm_spc.build_index")


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _etf_prediction(summary: dict, extras: dict | None = None) -> dict | None:
    """Panel 1(예측모델/Legacy)의 '내일(T+1) 예측'을 그대로 재현 — ETF 자기 자신의 방향 예측.
    대시보드 헤더 JS(오늘 기준 실시간 예측 카드, v2_render_dashboard.py TEMPLATE)와 로직을 맞췄다.
    괴리율 조건이 검증을 통과해 있으면(extras["premium"]) 과거 같은 조건에서의 적중률을 쓴다."""
    br, cm, p = summary["breadth_series"], summary["confusion_matrix"], summary["params"]
    vals = br["breadth"]
    i = len(vals) - 1
    while i >= 0 and vals[i] is None:
        i -= 1
    if i < 0:
        return None
    val = vals[i]
    pred_up = val >= p["breadth_threshold"]
    npv = (cm["tn"] / (cm["tn"] + cm["fn"])) if (cm["tn"] + cm["fn"]) else None
    hit_rate = cm["precision"] if pred_up else npv
    base = cm.get("base_rate")
    usual = None if base is None else (base if pred_up else 1 - base)
    premium = None
    if extras and extras.get("date") == br["dates"][i] and extras.get("pred_up") == pred_up:
        premium = extras.get("premium")
        if premium and premium.get("conditional", True) and premium.get("hit_rate") is not None:
            hit_rate = premium["hit_rate"]
    return {"date": br["dates"][i], "pred_up": pred_up, "hit_rate": hit_rate, "usual": usual, "premium": premium}


def _validated_extras(root: Path, basket_name: str) -> dict | None:
    """v2_render_dashboard.validated_etf_extras 와 같은 규칙(전 바스켓 풀링 검증을 통과한 항목만)을
    임의의 results 폴더에 적용한다 — 국내판 결과 폴더도 같은 규칙으로 읽기 위함."""
    extras, validation = _load_json(root / basket_name / "etf_extras.json"), _load_json(root / "etf_extras_validation.json")
    if not extras or validation is None:
        return None
    for key in ("premium", "reliability"):
        if not validation.get(key, {}).get("validated"):
            extras[key] = None
    return extras


def _top_sensor_signal(vm: dict) -> tuple[dict, float, bool] | None:
    """그 바스켓의 오늘 시나리오(구성 센서종목들) 중 |P-0.5| 가 가장 큰(가장 확신이 강한) 종목
    하나 — 어디까지나 '바스켓 내 다른 종목 대비 상대적 우열'이지 ETF 자체 예측이 아니다.

    챔피언이 있으면(p_champion) 검증된 확률을, 게이트 미달(REJECTED)이라 챔피언이 없으면 Baseline
    의 원값을 대신 쓴다 — 계산 자체가 안 된 것(vm_spc 데이터 없음)과, 계산은 됐는데 기준을 못
    넘은 것을 구분해서 빈칸 대신 "미검증"이라고 명시하고 보여주는 쪽이 아예 안 보여주는 것보다
    낫다는 판단(2026-09-27 사용자 피드백).

    반환: (종목, 확률, validated) — validated=False 면 게이트 미달 참고치."""
    best, best_gap, validated = None, -1.0, False
    for s in vm.get("scenario", []):
        p = s.get("p_champion")
        if p is not None:
            gap = abs(p - 0.5)
            if gap > best_gap:
                best, best_gap, validated = s, gap, True
    if best is not None:
        return best, best["p_champion"], True
    # 챔피언 없음(REJECTED) — Baseline 원값으로 대체(참고용, 미검증 표시)
    for s in vm.get("scenario", []):
        p = s.get("p_baseline")
        if p is None:
            continue
        gap = abs(p - 0.5)
        if gap > best_gap:
            best, best_gap = s, gap
    return (best, best["p_baseline"], False) if best is not None else None


def collect_rows(root: Path | None = None, baskets: list[dict] | None = None) -> list[dict]:
    """root/baskets 생략 시 이 프로젝트(Global). 국내판을 읽을 때는 국내판 results·바스켓 목록을 넘긴다."""
    root = root or results_dir()
    rows = []
    for basket in (baskets if baskets is not None else load_baskets()):
        name = basket["name"]
        bdir = root / name
        summary = _load_json(bdir / "v2_summary_metrics.json")
        if summary is None:
            continue  # Stage1/2 도 아직 안 돈 바스켓 — 표시할 게 없음
        target = summary["basket"]["target"]
        dash_path = bdir / "dashboard_v2.html"
        row = {
            "basket": name, "etf_name": target["name"], "etf_code": target["code"],
            "n_sensors": len(summary["basket"]["sensors"]),
            "coverage": summary["basket"].get("sensor_coverage"),
            "has_dashboard": dash_path.exists(),
            "etf_pred": _etf_prediction(summary, _validated_extras(root, name)),
            "champion": None, "top": None, "top_p": None, "top_validated": False, "gap": -1.0,
        }
        vm = _load_json(bdir / "vm_spc" / "vm_spc_dashboard_data.json")
        if vm is not None:
            row["champion"] = vm["decision"]["champion"]
            res = _top_sensor_signal(vm)
            if res is not None:
                row["top"], row["top_p"], row["top_validated"] = res
                row["gap"] = abs(row["top_p"] - 0.5)
        rows.append(row)
    # 정렬: 1차 목표는 'ETF 자체 예측'이므로 그 과거 적중률이 높은 순으로 먼저 정렬하고
    # (적중률 없는 바스켓은 맨 뒤로), 같은 적중률이면 센서 종목 신호 확신이 강한 순으로 보조 정렬한다.
    def _sort_key(r):
        ep = r["etf_pred"]
        hit = ep["hit_rate"] if ep and ep["hit_rate"] is not None else -1.0
        return (-hit, -r["gap"], r["basket"])
    rows.sort(key=_sort_key)
    return rows


def collect_core_rows() -> list[dict] | None:
    """국내판 결과(읽기 전용). 국내판 폴더·바스켓 파일이 없거나 읽다 실패하면 None — 국내 영역만
    빠지고 Global 화면은 그대로 만든다."""
    croot = core_root()
    try:
        baskets = load_baskets(croot / "basket_watchlist.json")
        return collect_rows(croot / "results", baskets)
    except Exception as e:  # 국내판 스키마가 바뀌어도 Global 인덱스 생성은 멈추지 않는다
        log.warning("국내판 결과를 못 읽어 국내 영역을 건너뜀: %s (%s)", croot, e)
        return None


def _etf_pred_cell(r: dict) -> str:
    ep = r["etf_pred"]
    if ep is None:
        return '<span class="c-empty">—</span>'
    up, hr, pr = ep["pred_up"], ep["hit_rate"], ep.get("premium")
    arrow, label, cls = ("&#9650;", "상승", "c-up") if up else ("&#9660;", "하락", "c-flat")
    # 평소 비율(예측과 상관없이 그 방향으로 움직인 날의 비율)을 항상 같이 — 강세장의 높은 "상승 적중"을
    # 실력으로 착각하지 않도록(설계 부록 A.10 표시 원칙, 국내판과 동일).
    usual = ep.get("usual")
    hr_str = (f"(적중 {hr:.0%}" + (f" · 평소 {usual:.0%})" if usual is not None else ")")) if hr is not None else ""
    note = ""
    if pr and pr.get("state") not in (None, "중립"):
        note_cls = "c-up" if pr["state"] == "동의" else "c-warn"
        note = (f'<span class="note-block">괴리율 {pr["dprt"]:+.2f}% · '
                f'<span class="{note_cls}">예측과 {"같은" if pr["state"] == "동의" else "반대"} 방향</span></span>')
    return f'<span class="val {cls}">{arrow} {label}</span> <span class="sub">{hr_str}</span>{note}'


def _sensor_signal_cell(r: dict) -> str:
    top = r["top"]
    if top is None:
        if r["champion"] is None:
            return '<span class="c-empty">검증 대기<span class="note-block">(데이터 부족)</span></span>'
        return '<span class="c-muted">신호 없음</span>'
    p = r["top_p"]
    up = p >= 0.5
    conf = p if up else (1 - p)
    if r["top_validated"]:
        arrow, label, cls = ("&#9650;", "상승 우세", "c-up") if up else ("&#9660;", "하락 우세", "c-down")
        suffix = ""
    else:
        # 게이트 미달(REJECTED) — Baseline 원값을 흐리게 보여준다. 빈칸보다 낫다는 판단이지만
        # 검증된 신호와는 확실히 구분되게(연한 색 + 라벨) 표시한다.
        arrow, label, cls = ("&#9650;", "상승", "c-muted") if up else ("&#9660;", "하락", "c-muted")
        suffix = ' <span class="note-inline">(게이트 미달·참고)</span>'
    return (f'<span class="val {cls}">{arrow} {html.escape(top["name"])}</span> '
            f'<span class="sub">({html.escape(top["code"])})</span> '
            f'<span class="val {cls} strong">{conf:.0%}</span>{suffix}')


def _row_html(r: dict, link_prefix: str = "", extra: str = "") -> str:
    """표(가로 스크롤)는 모바일에서 셀마다 세로로 뭉개지는 문제가 있어서, 폭에 상관없이
    항상 읽히는 카드 하나로 바꿨다(2026-09-27, 모바일 실사용 피드백) — 좁은 화면에선 1열로
    쌓이고 넓은 화면에선 그리드로 나열된다(TEMPLATE 의 .grid 미디어쿼리).

    스타일은 Tailwind CDN 스크립트(cdn.tailwindcss.com)가 아니라 TEMPLATE 안에 고정 CSS로
    직접 넣는다 — 이 파일은 텔레그램으로 받아 로컬로 여는 경우가 많은데, 그때 외부 CDN 스크립트가
    막히거나 늦게 불러와지면 스타일이 하나도 안 먹혀서 브라우저 기본 파란 링크 목록처럼 보이는
    문제가 실제로 있었다(2026-09-27, 모바일 실사용 스크린샷으로 확인)."""
    link = f"{link_prefix}{r['basket']}/dashboard_v2.html" if r["has_dashboard"] else None
    ep = r["etf_pred"]
    strong = " strong" if (ep and ep["hit_rate"] is not None and ep["hit_rate"] >= 0.6) else ""
    tag = "a" if link else "div"
    cov_note = (f' &middot; <span class="c-warn">센서 커버율 낮음({r["coverage"]:.0f}%)</span>'
                if r.get("coverage") is not None else "")
    href_attr = f' href="{link}"' if link else ""
    return f"""<{tag}{href_attr} class="card{strong}">
      <div class="card-top">
        <div class="etf-name">{html.escape(r['etf_name'])}</div>
        <div class="etf-code">{html.escape(r['etf_code'])}</div>
      </div>
      <div class="basket-sub">{html.escape(r['basket'])} &middot; 센서 {r['n_sensors']}종목{cov_note}</div>
      <div class="label" title="이 ETF 자신의 내일 방향 예측(예측모델/Legacy 기준) — 구성종목 신호와는 다른 예측입니다.">ETF 자체 예측</div>
      <div class="row-val">{_etf_pred_cell(r)}</div>
      <div class="label" title="이 ETF를 구성하는 센서 종목들 중 서로 비교했을 때 가장 확신이 강한 종목 — 상대적 우열이지, 이 신호 때문에 ETF가 오른다는 뜻이 아닙니다.">구성종목 중 최고 신호</div>
      <div class="row-val last">{_sensor_signal_cell(r)}</div>{extra}
    </{tag}>"""


TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>VM-SPC Global — 전체 ETF 현황</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  * { box-sizing:border-box; }
  body { background:#0f172a; color:#e2e8f0; margin:0; padding:16px;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Malgun Gothic",sans-serif; }
  a { text-decoration:none; color:inherit; }
  header.card { padding:16px; margin-bottom:16px; }
  header h1 { font-size:1.15rem; font-weight:700; color:#fff; margin:0 0 6px; }
  header p { font-size:0.8rem; color:#94a3b8; margin:4px 0; line-height:1.55; }
  header p b { color:#e2e8f0; }
  header .meta { font-size:0.7rem; color:#64748b; }
  .grid { display:grid; grid-template-columns:1fr; gap:12px; }
  @media (min-width:640px) { .grid { grid-template-columns:1fr 1fr; } }
  @media (min-width:1024px) { .grid { grid-template-columns:1fr 1fr 1fr; } }
  .card { display:block; background:#1e293b; border:1px solid #334155; border-radius:12px; padding:14px; }
  a.card:active, a.card:hover { border-color:#0891b2; }
  .card.strong { border-color:#0e7490; }
  .card-top { display:flex; align-items:flex-start; justify-content:space-between; gap:8px; }
  .etf-name { font-weight:700; color:#67e8f9; font-size:0.98rem; }
  .etf-code { font-size:0.72rem; color:#64748b; white-space:nowrap; padding-top:2px; }
  .basket-sub { font-size:0.72rem; color:#64748b; margin:4px 0 10px; }
  .label { font-size:0.68rem; color:#64748b; border-bottom:1px dotted #475569; display:inline-block;
           margin-bottom:3px; cursor:help; }
  .row-val { margin-bottom:10px; font-size:0.9rem; }
  .row-val.last { margin-bottom:0; }
  .val { font-weight:600; }
  .val.strong { font-weight:700; margin-left:4px; }
  .c-up { color:#34d399; }
  .c-down { color:#f87171; }
  .c-flat { color:#cbd5e1; }
  .c-muted { color:#94a3b8; }
  .c-empty { color:#475569; }
  .c-warn { color:#fbbf24; }
  .sub { color:#64748b; font-size:0.75rem; }
  .note-inline { color:#475569; font-size:0.68rem; }
  .note-block { display:block; color:#475569; font-size:0.68rem; }
  footer.note { font-size:0.75rem; color:#475569; margin-top:16px; }
  h2.sec { font-size:1rem; color:#fff; margin:20px 0 10px; }
  h2.sec .sec-link { color:#67e8f9; text-decoration:underline; }
  h2.sec .sec-sub { display:block; font-size:0.72rem; font-weight:400; color:#64748b; margin-top:3px; }
</style>
</head>
<body>
  <header class="card">
    <h1>VM-SPC Global — 전체 ETF 현황</h1>
    <p>이 파이프라인의 1차 목표인 <b>ETF 자체 예측</b>의 적중률이 높은 순으로 정렬했습니다(미국 __N_TOTAL__개 중
      60% 이상 __N_SIGNAL__개). 적중률은 과거에 오늘과 같은 방향으로 예측한 날의 실제 적중 비율, 평소는 예측과 상관없이 그 방향으로 움직인 날의 비율입니다. __CORE_HEADER__구성종목 신호는 참고용으로 옆에 같이 둡니다. 자세한 근거는 각 ETF를 눌러 확인하세요.</p>
    <p class="meta">생성 시각: __GENERATED_AT__</p>
  </header>

  <h2 class="sec">미국 ETF <span class="sec-sub">미국 현지 __US_DATE__ 마감 기준 · 다음 미국장 예측</span></h2>
  <div class="grid">__ROWS__</div>
__CORE_SECTION__
  <footer class="note">자동 주문은 하지 않습니다 — 장 마감 후 계산한 참고용 방향 신호이며, 진입 여부는 사람이 판단합니다.</footer>
</body>
</html>
"""


def _latest_date(rows: list[dict]) -> str:
    dates = [r["etf_pred"]["date"] for r in rows if r["etf_pred"]]
    return max(dates) if dates else "-"


def _core_theme_family() -> dict[str, str]:
    """국내판 build_index.py 의 THEME_FAMILY(같은 테마 바스켓을 카드 하나로 묶는 표)를 **파싱만** 해서
    가져온다 — 복사해 두면 국내판이 테마를 추가할 때 어긋나므로. 못 읽으면 묶지 않는다."""
    try:
        tree = ast.parse((core_root() / "vm_spc" / "build_index.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "THEME_FAMILY" for t in node.targets):
                return ast.literal_eval(node.value)
    except Exception as e:
        log.warning("국내판 THEME_FAMILY 를 못 읽어 테마 묶음 없이 표시: %s", e)
    return {}


def _group_core(rows: list[dict]) -> list[list[dict]]:
    """국내판 index 와 같은 묶음 — 대표 = 테마 바스켓(*_to_etf) 우선, 없으면 센서가 많은 쪽.
    묶음 순서는 대표 카드의 정렬 순서. 이 화면엔 대표 카드만 싣고 나머지는 개수만 적는다."""
    family = _core_theme_family()

    def fam_of(b: str) -> str:
        return next((name for prefix, name in family.items() if b.startswith(prefix + "_")), b)

    fam: dict[str, list[dict]] = {}
    for r in rows:
        fam.setdefault(fam_of(r["basket"]), []).append(r)
    groups = [[lead, *(m for m in members if m is not lead)]
              for members in fam.values()
              for lead in [max(members, key=lambda m: (m["basket"].endswith("_to_etf"), m["n_sensors"]))]]
    order = {id(r): i for i, r in enumerate(rows)}
    return sorted(groups, key=lambda g: order[id(g[0])])


def _core_section(core_rows: list[dict] | None) -> tuple[str, str]:
    """(머리말 문구, 국내 영역 HTML). 국내판 결과가 없으면 둘 다 빈 문자열."""
    if not core_rows:
        return "", ""
    # 국내판 대시보드로 가는 상대 링크 — 로컬(New toy/)과 구글 드라이브(내 드라이브/) 모두 두 폴더가
    # 나란히 있어 같은 상대 경로가 맞는다.
    prefix = os.path.relpath(core_root() / "results", results_dir()).replace(os.sep, "/") + "/"
    n_sig = sum(1 for r in core_rows if r["etf_pred"] and r["etf_pred"]["hit_rate"] is not None
                and r["etf_pred"]["hit_rate"] >= 0.6)
    date = _latest_date(core_rows)
    header = f"아래쪽 <b>국내 ETF</b>는 국내판(VM-SPC Core)이 계산한 결과를 그대로 옮긴 것입니다(국내 {len(core_rows)}개 중 60% 이상 {n_sig}개). "
    cards = []
    for lead, *rest in _group_core(core_rows):
        extra = (f'\n      <div class="note-block" style="margin-top:8px">같은 테마 다른 구성 {len(rest)}개 — '
                 f'국내판 전체 화면에서 확인</div>' if rest else "")
        cards.append(_row_html(lead, prefix, extra))
    body = (f'\n  <h2 class="sec">국내 ETF <span class="sec-sub">국내 {date} 마감 기준 · 다음 국내장 예측 '
            f'(국내판 결과를 읽어옴) · <a class="sec-link" href="{prefix}index.html">국내판 전체 화면</a></span></h2>\n'
            f'  <div class="grid">{"".join(cards)}</div>\n')
    return header, body


def build_index() -> int:
    rows = collect_rows()
    if not rows:
        log.error("basket_watchlist.json 에 바스켓이 없거나 Stage1/2 가 하나도 안 돌았습니다 — "
                  "vm_predict/v2_run.py 먼저 실행하세요.")
        return 1
    n_signal = sum(1 for r in rows if r["etf_pred"] and r["etf_pred"]["hit_rate"] is not None
                  and r["etf_pred"]["hit_rate"] >= 0.6)
    core_header, core_body = _core_section(collect_core_rows())
    from datetime import datetime
    html_out = (TEMPLATE
                .replace("__CORE_HEADER__", core_header)
                .replace("__CORE_SECTION__", core_body)
                .replace("__US_DATE__", _latest_date(rows))
                .replace("__N_TOTAL__", str(len(rows)))
                .replace("__N_SIGNAL__", str(n_signal))
                .replace("__GENERATED_AT__", datetime.now(KST).strftime("%Y-%m-%d %H:%M"))
                .replace("__ROWS__", "".join(_row_html(r) for r in rows)))
    out_path = results_dir() / "index.html"
    out_path.write_text(html_out, encoding="utf-8")
    log.info("생성 완료: %s (%d개 ETF, 신호 %d개)", out_path, len(rows), n_signal)
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return build_index()


if __name__ == "__main__":
    sys.exit(main())
