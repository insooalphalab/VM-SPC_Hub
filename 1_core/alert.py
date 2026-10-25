"""예약 작업 실패 알림 — 텔레그램 한 줄(2026-10-11 사용자 결정). hub_am.ps1 · hub_pm.ps1이 리포트를 못 보낸 날 부른다.

  python alert.py "⚠ 마감 리포트 못 보냄 — 실패: core: screen candidates"

build_report.py를 import하지 않는다(리포트 쪽이 깨진 날에도 알림은 가게). 전송 실패는 stderr에만 남기고 0으로 끝낸다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    text = " ".join(sys.argv[1:]).strip() or "⚠ VM-Hub 예약 작업 실패"
    try:
        from vm_spc.notify_telegram import send_message
        send_message(text)
        print(f"[alert] 보냄: {text}")
    except Exception as ex:  # noqa: BLE001
        print(f"[alert] 전송 실패: {type(ex).__name__}: {re.sub(r'/bot[^/\s]+/', '/bot***/', str(ex))}", file=sys.stderr)
    sys.exit(0)
