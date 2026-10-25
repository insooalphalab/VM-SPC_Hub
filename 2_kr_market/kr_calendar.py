"""국내 개장일 달력 — KIS 국내휴장일조회(CTCA0903R)를 하루 한 번 불러 캐시한다(2026-10-12 사용자 결정 · VM-core 제안).

  python kr_calendar.py            # 앞으로 14일이 이미 있으면 부르지 않음
  python kr_calendar.py --force    # 무조건 다시 받기
→ ../exchange/2_kr_market/kr_calendar.json  {"updated": ..., "days": {"2026-10-12": true, ...}}  (true = 개장일)

- 1_core가 읽어 "다음 거래일" 문구를 고른다(토요일 · 연휴 다음 날 아침판). 판단 규칙에는 쓰지 않음.
- KIS 코드는 VM-SPC_Core `core\\` 4개 파일을 복사해 쓴다(kis_auth · kis_client · secrets_loader · v2_config, 수정 없음).
  키는 이 폴더 `.streamlit\\secrets.toml`의 KIS_APP_KEY · KIS_APP_SECRET 두 줄(커밋 금지), 토큰 캐시는 `state\\`.
- 접근토큰 발급은 5분 1회 — hub_am.ps1이 Global(07:00, KIS 사용) 끝나고 10분 넘게 지난 뒤 부른다. 실패해도 0으로 끝냄(리포트는 토 · 일 규칙만으로 돈다).
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "core"))
OUT = ROOT.parent / "exchange" / "2_kr_market" / "kr_calendar.json"
KST = timezone(timedelta(hours=9))
PATH, TR = "/uapi/domestic-stock/v1/quotations/chk-holiday", "CTCA0903R"
AHEAD, MAX_CALLS = 14, 3          # 앞으로 14일이 채워져 있으면 그만, 한 번 실행에 최대 3콜


def load() -> dict:
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"days": {}}


def _covered(cal: dict, today: date) -> bool:
    return all((today + timedelta(days=k)).isoformat() in cal.get("days", {}) for k in range(AHEAD + 1))


def fetch(cal: dict, today: date) -> int:
    from kis_client import RateLimitedCaller
    caller = RateLimitedCaller(min_interval=1.0)
    days, start, n = cal.setdefault("days", {}), today, 0
    for _ in range(MAX_CALLS):
        body = caller.get(PATH, TR, {"BASS_DT": start.strftime("%Y%m%d"), "CTX_AREA_NK": "", "CTX_AREA_FK": ""})
        rows = body.get("output") or []
        for x in rows:
            d = x.get("bass_dt", "")
            if len(d) == 8:
                days[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = x.get("opnd_yn") == "Y"     # 개장일 여부
                n += 1
        if not rows or _covered(cal, today):
            break
        start = datetime.strptime(max(days), "%Y-%m-%d").date() + timedelta(days=1)
    return n


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    today = datetime.now(KST).date()
    cal = load()
    if "--force" not in sys.argv and _covered(cal, today):
        print(f"[kr_calendar] 앞으로 {AHEAD}일 이미 있음 — 부르지 않음")
        return 0
    try:
        n = fetch(cal, today)
    except Exception as ex:  # noqa: BLE001 — 달력이 없어도 리포트는 토 · 일 규칙으로 돈다
        print(f"[kr_calendar] 조회 실패: {type(ex).__name__}: {ex}", file=sys.stderr)
        return 0
    keep = (today - timedelta(days=30)).isoformat()
    cal["days"] = {d: v for d, v in sorted(cal["days"].items()) if d >= keep}
    cal["updated"] = datetime.now(KST).isoformat(timespec="seconds")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cal, ensure_ascii=False, indent=1), encoding="utf-8")
    closed = [d for d, v in cal["days"].items() if not v and d >= today.isoformat() and date.fromisoformat(d).weekday() < 5]
    print(f"[kr_calendar] {n}일 받음 · 앞으로 평일 휴장: {', '.join(closed) or '없음'} → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
