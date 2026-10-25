"""리포트 디자인 — VM-SPC_Core scenario/render_risk.py 의 GOLDEN_THEME 을 그대로 복사(2026-10-10). 고치지 말고 원본과 맞춘다."""

GOLDEN_THEME = r"""<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@700;900&family=IBM+Plex+Mono:wght@400;600&family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
  :root { --bg:#0a0e16; --card:#141a26; --line:#252d3d; --tx:#e6edf6; --mut:#9aa7bd; --dim:#7d8aa3; --faint:#5b677d;
          --up:#2ecc71; --dn:#f4556b; --warn:#f0b429; --acc:#22d3c5; --blue:#4a8cff; --pur:#a06bff; }
  body { font-family:'Noto Sans KR',-apple-system,"Malgun Gothic",sans-serif; font-size:14px; line-height:1.55; padding:0 16px 40px; max-width:820px; }
  .rb { height:4px; background:linear-gradient(90deg,#f4556b,#f0b429,#2ecc71,#22d3c5,#4a8cff,#a06bff); margin:0 -16px 18px; }
  h1 { font-family:'Archivo','Noto Sans KR',sans-serif; font-weight:900; font-size:1.6rem; letter-spacing:.3px; margin:6px 0 4px; }
  .intro { font-size:0.78rem; color:var(--mut); border-left:3px solid var(--warn); background:#10151f; padding:6px 10px; border-radius:0 6px 6px 0; }
  .card, .plan, .guide, .market, .holdsum, details.fold, .budget { border-radius:10px; border-color:var(--line); }
  .guide { border-left-width:4px; } .guide.on { border-left-color:var(--warn); }
  .g-head { font-family:'Archivo','Noto Sans KR',sans-serif; font-weight:900; font-size:1.05rem; }
  .market b { font-family:'Archivo','Noto Sans KR',sans-serif; font-weight:900; font-size:1.05rem; }
  .tabs label { background:#0f1420; border-color:var(--line); font-size:0.82rem; padding:5px 11px; }
  .nm { font-family:'Archivo','Noto Sans KR',sans-serif; font-weight:900; color:var(--acc); }
  .px, .v, table.lv td, details.fold td, .size b, .evt, .badge { font-family:'IBM Plex Mono',ui-monospace,monospace; font-variant-numeric:tabular-nums; }
  .px { font-weight:600; }
  .badge { border-radius:999px; background:#0f1420; }
  .badge.on { color:var(--warn); border-color:rgba(240,180,41,.5); background:rgba(240,180,41,.1); }
  .badge.vf { color:var(--up); border-color:rgba(46,204,113,.5); background:rgba(46,204,113,.08); }
  .plan.active { border-color:var(--warn); } .plan.verified { border-color:rgba(46,204,113,.6); }
  .market.up { border-color:rgba(46,204,113,.5); background:linear-gradient(90deg,rgba(46,204,113,.08),var(--card) 40%); }
  .market.dn { border-color:rgba(244,85,107,.5); background:linear-gradient(90deg,rgba(244,85,107,.08),var(--card) 40%); }
  .market.side { border-color:rgba(240,180,41,.5); background:linear-gradient(90deg,rgba(240,180,41,.08),var(--card) 40%); }
  .k { letter-spacing:.2px; text-transform:none; }
</style>"""
