"""리서치 채널 원문 → 사람이 읽는 날짜별 Markdown(Golden 텔레그램 백업을 대신, 2026-10-09 사용자 결정).

  python reports/export_md.py [--days 60]
data/_reports/raw/{채널}.jsonl → results/research_md/{YYYY-MM-DD}/{채널}.md (KST 날짜). 매번 최근 N일을 다시 쓰고
N일보다 오래된 날짜 폴더는 지운다(구글 드라이브 미러링 용량 — 원문은 raw 에 그대로 남음).
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parent.parent
for _p in (_ROOT, _ROOT / "core"):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone

from v2_config import data_dir, results_dir

KST = timezone(timedelta(hours=9))
CHANNELS = {"butler_works": "버틀러 · 증권사 리포트 요약", "ked_epic_ai": "Epic AI · 한투 리서치 요약",
            "aicorporateanalysisdeepdive": "AI 리서치 딥다이브 · 해외 시황"}
SKIP = ("Channel created", "Channel name was changed", "Channel photo updated")


def load(ch: str, since: datetime) -> dict[str, list[tuple[datetime, int, str]]]:
    """KST 날짜 문자열 → [(시각, id, 본문)]."""
    p = data_dir() / "_reports" / "raw" / f"{ch}.jsonl"
    out: dict[str, list] = {}
    if not p.exists():
        return out
    seen = set()
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            m = json.loads(ln)
        except ValueError:
            continue
        txt = (m.get("text") or "").strip()
        if not txt or txt.startswith(SKIP) or m.get("id") in seen:
            continue
        t = datetime.fromisoformat(m["date"]).astimezone(KST)
        if t < since:
            continue
        seen.add(m.get("id"))
        out.setdefault(t.strftime("%Y-%m-%d"), []).append((t, m.get("id"), txt))
    return out


def build(days: int = 60) -> int:
    root = results_dir() / "research_md"
    since = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    n = 0
    keep = set()
    for ch, title in CHANNELS.items():
        for day, msgs in load(ch, since).items():
            msgs.sort()
            keep.add(day)
            d = root / day
            d.mkdir(parents=True, exist_ok=True)
            body = [f"# {title} ({ch}) · {day}", "", f"{len(msgs)}건 · 시각 KST", ""]
            for t, mid, txt in msgs:
                body += [f"### [{t:%H:%M}] (ID {mid})", "", txt, "", "---", ""]
            (d / f"{ch}.md").write_text("\n".join(body), encoding="utf-8")
            n += 1
    if root.exists():
        for d in root.iterdir():
            if d.is_dir() and d.name not in keep and d.name < since.strftime("%Y-%m-%d"):
                shutil.rmtree(d)
    return n


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    print(f"Markdown {build(ap.parse_args().days)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
