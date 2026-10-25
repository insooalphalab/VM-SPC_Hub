"""오늘의 주요 뉴스 — 텔레그램 리서치 채널 원문에서 규칙으로 뽑은 하루 요약(2026-10-09 사용자 요청, 요약 생성 없이 원문 문장 그대로).

방향 판단에는 쓰지 않는 참고 자료(뉴스 · 리포트는 이후 방향을 알려 주지 않았다 — 9.17 · 9.106 · 9.275).
  python reports/news_digest.py [--date 2026-10-08] [--slot am|pm]
  python reports/news_digest.py --date 2026-10-12 --slot am --since 2026-10-10   # 주말판(2026-10-12): 토 00:00 – 월 아침을 한 묶음, 이슈 상위 10
    → results/reports/news_digest.json · news_digest.md(긴 원문판)
    → ../exchange/5_news/{날짜}/summary_{slot}.json · .md(10줄) + latest.json
  데이터 위치는 환경변수 V2_DATA_DIR = ../../VM-SPC_Core/data(전환 기간 — 읽기만).
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parent.parent
for _p in (_ROOT, _ROOT / "core", _ROOT / "reports", _ROOT / "scenario", _ROOT / "research"):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

from parse import load_raw
from v2_config import data_dir, results_dir

KST = timezone(timedelta(hours=9))
US_CH, KR_CH = "aicorporateanalysisdeepdive", "shmstory"
SECTIONS = {"핵심 요약": "미국 시황", "국장 영향": "국내 영향", "주요 지수 종합": "지수 · 금리 · 환율"}


def _day(m) -> str:
    return datetime.fromisoformat(m["date"]).astimezone(KST).strftime("%Y-%m-%d")


def us_brief(day: str) -> dict | None:
    """AI 리서치 딥다이브 모닝 시황: 제목 줄 + ► 섹션(핵심 요약 · 국장 영향 · 주요 지수)."""
    for m in sorted(load_raw(US_CH), key=lambda x: x["id"]):
        if _day(m) != day or "모닝 시황" not in m["text"][:40]:
            continue
        lines = [x.strip().strip("*").strip() for x in m["text"].splitlines()]
        head = next((x for x in lines[1:] if x and not x.startswith("─")), "")
        out, cur = {"headline": head, "link": f"https://t.me/{US_CH}/{m['id']}"}, None
        for x in lines:
            k = re.sub(r"^[►▶]\s*|^<|>$", "", x).strip()
            if x.startswith(("►", "▶", "<")) and k:
                cur = SECTIONS.get(k) or next((v for s, v in SECTIONS.items() if s.replace(" ", "") in k.replace(" ", "")), None)
                continue
            if x.startswith("─"):
                cur = None
                continue
            if cur and x:
                out.setdefault(cur, []).append(x)
        return out
    return None


def kr_brief(day: str) -> list[dict]:
    """shmstory: 그날 아침 시황 · 장중 · 마감 시황 — 제목 + 첫 몇 줄."""
    out = []
    for m in sorted(load_raw(KR_CH), key=lambda x: x["id"]):
        if _day(m) != day:
            continue
        lines = [x.strip() for x in m["text"].splitlines() if x.strip()]
        if not lines or not re.match(r"^(\d{1,2}월 \d{1,2}일 시황|마감 시황|지수 (하락|상승) 이유)", lines[0]):
            continue
        t = datetime.fromisoformat(m["date"]).astimezone(KST)
        body = [x for x in lines[1:] if not x.startswith(("◎", "http"))][:4]
        out.append({"time": t.strftime("%H:%M"), "title": lines[0], "lines": body, "link": f"https://t.me/{KR_CH}/{m['id']}"})
    return out


def names() -> dict:
    out = {}
    for f in ("kospi_code_master.txt", "kosdaq_code_master.txt"):
        p = _ROOT / "state" / f
        if p.exists():
            for ln in p.read_bytes().split(b"\n"):
                s = ln.decode("utf-8", "ignore")
                out[s[:9].strip()] = re.split(r"\s{2,}", s[21:61].strip())[0]
    r = pd.read_csv(data_dir() / "_reports" / "reports.csv", dtype={"code": str}, usecols=["code", "name"]).dropna()
    out.update(dict(zip(r.code, r.name)))
    return out


def stock_news(day: str, nm: dict, top: int = 5) -> list[dict]:
    """그날 기사가 가장 많이 붙은 종목(서로 다른 제목 수) + 대표 제목."""
    d = pd.read_csv(data_dir() / "_reports" / "news.csv", dtype=str)
    d = d[(d.date == day) & (d.kind == "뉴스")].drop_duplicates(["code", "title"])
    if d.empty:
        return []
    g = d.groupby("code").title.agg(["count", "first"]).sort_values("count", ascending=False).head(top)
    return [{"code": c, "name": nm.get(c, c), "n": int(r["count"]), "title": r["first"]} for c, r in g.iterrows()]


def _span(day: str) -> list[str]:
    """기간 묶음(주말판)이면 SINCE – day 날짜들, 아니면 그날 하나."""
    if not SINCE:
        return [day]
    d0, d1 = datetime.strptime(SINCE, "%Y-%m-%d"), datetime.strptime(day, "%Y-%m-%d")
    return [(d0 + timedelta(days=k)).strftime("%Y-%m-%d") for k in range((d1 - d0).days + 1)]


def report_moves(day: str) -> dict:
    """그날(주말판은 기간) 증권사 리포트 목표가 상향 · 하향 종목(건수 순)."""
    r = pd.read_csv(data_dir() / "_reports" / "reports.csv", dtype={"code": str})
    r = r[r.date.isin(_span(day))]
    out = {}
    for k, lab in (("up", "상향"), ("down", "하향")):
        g = r[r.dir == k].groupby(["code", "name"]).broker.nunique().sort_values(ascending=False)
        out[lab] = [{"code": c, "name": n, "n": int(v)} for (c, n), v in g.items()]
    out["신규 커버"] = [{"code": c, "name": n} for c, n in r[r.dir == "new"][["code", "name"]].drop_duplicates().itertuples(index=False)]
    return out


TARGETS = _ROOT.parent.parent / "VM-SPC_Core" / "scenario_targets.json"     # 전환 기간 — 읽기만(비밀, 커밋 금지)


def target_codes() -> list[str]:
    """scenario_targets.json 의 stocks — 문자열("005930") 또는 {"code": ...} 둘 다 받는다."""
    if not TARGETS.exists():
        return []
    items = json.loads(TARGETS.read_text(encoding="utf-8")).get("stocks", [])
    return [str(x["code"] if isinstance(x, dict) else x).strip().zfill(6) for x in items]


def my_news(day: str, nm: dict) -> list[dict]:
    """보유 · 관심 종목에 붙은 그날 기사."""
    mine = set(target_codes())
    if not mine:
        return []
    d = pd.read_csv(data_dir() / "_reports" / "news.csv", dtype=str)
    d = d[d.date.isin(_span(day)) & d.code.isin(mine)].drop_duplicates(["code", "title"])
    g = d.groupby("title", sort=False).code.apply(lambda s: " · ".join(nm.get(c, c) for c in s))
    return [{"names": n, "title": t} for t, n in g.items()]


# ── 오늘의 이슈(hub-news 2단계) ──────────────────────────────────────────────
# 순위 = 다룬 채널 수 → 글 무게. 리포트 채널은 빼고("리포트" 줄로 따로), 여러 이슈를 담은 긴 글(시황 · 브리핑 · 목록)은
# 본문 낱말마다 1 ÷ 이슈 수, 기사 한 편은 제목 낱말마다 1, 공시는 회사 이름 하나만. 이슈 후보는 그날 기사 · 공시 제목에 나온 낱말만
# (대표 제목을 제목에서 고를 수 있게). 넓은 단어 · 증권사 이름 · 평소 제목에 늘 나오는 단어는 세지 않는다.
ISSUE_CH = ["aicorporateanalysisdeepdive", "shmstory", "ked_epic_ai", "darthacking", "easobi",    # butler_works = 리포트 전용
            "habit4117", "krwatch"]                    # hub-news가 웹 미리보기로 받는 채널(2026-10-09 사용자) — 원문은 이 폴더 data/
CHAT_CH = {"krwatch"}       # 대화형 채널 — 기사 · 시황 글은 "chat"으로 보고 이슈를 만들지 않고 채널 수만 보탬(2026-10-10). 가격 알림(공시 꼴)은 그대로
LINK_CH = {"habit4117"}     # 뉴스 제목 옮기는 채널 — 링크 있는 글만 기사, 링크 없는 짧은 말 · 격언은 "chat"(2026-10-10, 30일 기준 기사의 76%가 링크)
HUB_RAW = _ROOT / "data" / "_reports" / "raw"
SLOT_END = {"am": (7, 40), "pm": (15, 50)}
WRAP_LEN, BASE_DAYS, GENERIC_RATE, SPIKE = 1800, 20, 0.4, 1.5
BROAD = set("""
실적 AI 반도체 메모리 바이오 시황 증시 주가 주식 목표주가 목표가 목표 상향 하향 상승 하락 급등 급락 강세 약세 반등 조정 전망 발표 예상 미국 한국 국내
해외 중국 일본 글로벌 시장 투자 투자자 기업 종목 업종 지수 마감 장중 장전 모닝 브리핑 분기 영업이익 매출 매출액 이익 순이익 컨센서스 컨센 추정치 기대
우려 확대 증가 감소 개선 성장 회복 오늘 지난 이번 다음 다시 관련 대비 기준 외국인 기관 개인 순매수 순매도 매수 매도 코스피 코스닥 KOSPI KOSDAQ 나스닥
NASDAQ S&P500 S&P 다우 핵심 요약 주요 내용 리포트 보고서 시가총액 달러 ETF 리서치 증권 분석 텔레그램 REPORT 센티먼트 영향 이유 가능성 수혜 테마 뉴스
공시 체크 기록 최고 최대 최저 사상 최고치 협력 위해 대한 통해 따른 이후 현재 사업 회사 산업 섹터 경제 정부 정책 YOY QOQ EPS PER 올해 내년 3분기 4분기
수주 계약 공급 수요 가격 판가 비중 규모 계획 확인 지속 유지 추가 신규 시총 대형주 주도주 연휴 이슈 소식 언급 평가 주목 의견 영업 손실 시대 공개 체결
자회사 필요 장비 인프라 낙폭 상승폭 하락폭 주도 예정 수준 최근 상승세 하락세 변동성 고점 저점 기술주 단기 장기 심리 랠리 저평가 고평가 주주환원 증권가 월가 대폭 소폭 다만 단독 속보 종합 부품 소재 신작 제품 서비스 플랫폼 효과 변수 리스크 경쟁 점유율 본격 돌파 진출 전환
""".split())
# 기능어 — 어느 기사에나 붙어 이슈를 가리키지 못하는 낱말(2026-10-10, 최근 60거래일 제목에서 추림). 확보 · 입찰 · 인수처럼 사건을 뜻하는 낱말은 넣지 않는다.
# 조사를 떼면 한 글자만 남는 꼴(것이 · 돈을)은 조사가 붙은 채 남으므로 그대로 적는다.
BROAD |= set("""
것이 것으 것을 것은 것도 것이라고 것이다 있는 있어 있지만 있을 있다고 있는데 있었는데 있어야 없는 없어 없이 없을 되는 되고 되나 될까 하지 하고 해도 아닌 아니라 아냐
으로 까지 에서 에도 때문 경우 정도 가지 동안 때는 때까지 수밖 만에
이런 이것 나는 저는 내가 우리 당신 그는 누가 누구 무슨 어디 어느 어떻게 아무 아무것 분들 사람 사람들 자신 자체 혼자 기업들
특히 가장 이미 이제 이젠 이번엔 아직 계속 모두 모든 너무 크게 매우 많이 먼저 결국 바로 함께 오히려 여전히 그냥 무조건 진짜 전혀 완전히 일제히 잇따라 잇달아 처음
벌써 거의 자주 꾸준히 빠르게 사실상 대부분 일부 전체 전반 그리고 하지만 그러나 또는 만약 따라서 한번 아주 오래 실제 줄줄 비싸게
지금 하루 내일 전날 작년 전년 이달 요즘 매일 연간 연환산 직전 향후 이전 시간 시점 시기 기간 과거 첫날 한달 반년 기존 이르면
넘어 넘게 넘는 올라 오를 오르면 오면 커져 커진 팔고 팔아 사는 버는 쓰는 먹고 타고 두고 알고 알지 보니 봐야 마라 마세요 말라 말고 사라 나서 나선 나온 만든 만난
남는 막고 늘어 늘려 늘어난 줄이고 바꿔야 빠진 흔들리 했더니 텐데 돈을 돈이 일이 앞두고 앞으 따라 걸쳐 스스 하락할 않을 않는 않아 않으면 이어 이어질 미친 주는
같은 같이 위한 대해 통한 의한 인한 맞먹어 열흘
상황 문제 결과 방식 방법 방향 의미 이름 질문 생각 과정 차이 변화 흐름 요인 포인트 전략 속도 상위 이상 이하 미만 평균 절반 하나 차례 구간 단계 사용 국가 대형 그룹
현황 정리 안내 일반 약식 기타 실시간 개인적 부정적 긍정적 세상 인생 인간 이야기 얘기 정보 내용들 부분 측면 모습 상태 사실 점검 동향 시사점 코멘트 리스트
특징주 관련주 투자의견 보도자료 보도참고자료 VS HTTPS HTTP WWW COM
""".split())
BROKERS = set("""
DA데이비슨 번스타인 골드만삭스 골드만 모건스탠리 JP모건 씨티 웨드부시 에버코어 UBS BOFA 제프리스 노무라 맥쿼리 CLSA HSBC 바클레이즈 키움 미래에셋 한투 메리츠
대신 유안타 신영 다올 상상인 IM DS LS 교보 NH KB 하이투자 이베스트 리서치센터 와이즈리포트
""".split())
ALIAS = {"하이닉스": "SK하이닉스", "삼전": "삼성전자", "엔솔": "LG에너지솔루션", "LG엔솔": "LG에너지솔루션",
         "국제유": "유가", "국제유가": "유가", "연방준비제": "연준"}    # 국제유가 → 조사 "가"로 잘려 "국제유"가 됨
JOSA = sorted("은 는 이 가 을 를 의 에 와 과 도 로 으로 에서 에게 까지 부터 보다 만에 처럼 이라 이며 라는 에도 株".split(), key=len, reverse=True)
VERBISH = re.compile(r"(다|며|면서|했|해|된|돼|될|하는|하며|한다|된다|겠|던|한|운|은|린|른)$")    # 동사 · 형용사 꼴(종목명은 예외)
SPLIT = re.compile(r"[^0-9A-Za-z가-힣&]+")
_RAW: dict[str, list] = {}


def _raw(ch: str) -> list[dict]:
    if ch not in _RAW:
        seen, out = set(), []
        p = HUB_RAW / f"{ch}.jsonl"
        rows = [json.loads(x) for x in p.open(encoding="utf-8")] if p.exists() else load_raw(ch)
        for m in rows:
            if m["id"] not in seen and (m.get("text") or "").strip():
                seen.add(m["id"])
                out.append(dict(m, ch=ch, t=datetime.fromisoformat(m["date"]).astimezone(KST)))
        _RAW[ch] = out
    return _RAW[ch]


def _kind(m: dict) -> tuple[str, str]:
    """(kind, 제목) — kind: wrap(여러 이슈) · article(기사 한 편) · disclosure(공시) · report · skip."""
    L = [x.strip().strip("*").strip() for x in m["text"].splitlines() if x.strip() and not x.strip().startswith("─")]
    first = L[0] if L else ""
    if first.startswith("[✨ 리서치"):
        return "report", first                                           # ked 리포트 요약 · 목표가 목록
    nm = re.search(r"기업명:\s*([^(\n]+)", m["text"])
    if nm and (m["ch"] == "darthacking" or re.match(r"^\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}$", first)):
        rp = re.search(r"보고서명:\s*([^\n]+)", m["text"])
        return "disclosure", f"{nm.group(1).strip()} {re.sub(r'\s+', ' ', rp.group(1)).strip() if rp else ''}".strip()
    alert = re.match(r"^(.+?)\s*\([+-]?[\d.]+%\)$", first)
    if m["ch"] == "krwatch" and alert and "💥" in m["text"]:                  # 종목 가격 알림 = 종목 이름 하나
        return "disclosure", f"{alert.group(1).strip()} {L[1].lstrip('💥 ') if len(L) > 1 else ''}".strip()
    if m["ch"] == "krwatch" and first.startswith(("📊", "🇰🇷", "🇺🇸")):
        return "skip", first                                              # 등락 랭킹 표(종목 수십 개)
    if len(m["text"]) < (60 if m["ch"] == "easobi" else 15) or first.startswith(("[입법]", "💬")):
        return "skip", first
    if re.match(r"^\[.*모닝 시황\]$", first):
        return "wrap", L[1] if len(L) > 1 else first
    if m["ch"] == "shmstory" or len(m["text"]) > WRAP_LEN or first.startswith(("[시황]", "[종목 토론실", "[퀀트", "<", "✅", "📝")):
        return "wrap", re.sub(r"^\[시황\]\s*", "", first)
    return "article", first


SINCE: str | None = None     # 주말판 시작일(--since) — 있으면 창 시작 = 그날 00:00


def window(day: str, slot: str) -> tuple[datetime, datetime]:
    """am = 전날 15:30 – 07:40(밤사이 · 아침), pm = 그날 00:00 – 15:50(장중 · 마감). 오늘 늦게 돌리면 지금까지.
    주말판(SINCE)이면 SINCE 00:00 – day 끝 시각."""
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=KST)
    if SINCE:
        end = d.replace(hour=SLOT_END[slot][0], minute=SLOT_END[slot][1])
        now = datetime.now(KST)
        if now.date() == end.date() and now > end:
            end = now
        return datetime.strptime(SINCE, "%Y-%m-%d").replace(tzinfo=KST), end
    end = d.replace(hour=SLOT_END[slot][0], minute=SLOT_END[slot][1])
    now = datetime.now(KST)
    if now.date() == end.date() and now > end:
        end = now
    return (d - timedelta(hours=8, minutes=30) if slot == "am" else d), end


def _msgs(start: datetime, end: datetime) -> list[dict]:
    out = []
    for ch in ISSUE_CH:
        for m in _raw(ch):
            if start <= m["t"] < end:
                k, title = _kind(m)
                if (ch in CHAT_CH and k in ("article", "wrap")) or (ch in LINK_CH and k == "article" and "http" not in m["text"]):
                    k = "chat"
                if k not in ("report", "skip"):
                    out.append(dict(m, kind=k, title=title))
    return out


def _norm(w: str, stock: frozenset) -> str:
    t = w.strip("&")
    if not t or t[0].isdigit():
        return ""
    if re.fullmatch(r"[A-Za-z&0-9]+", t):
        t = t.upper()
        return t if len(t) >= 2 and t not in BROAD and t not in BROKERS else ""
    if t not in stock and t not in BROAD:
        t = next((t[: -len(j)] for j in JOSA if t.endswith(j) and len(t) - len(j) >= 2), t)
    t = ALIAS.get(t, t)
    if len(t) < 2 or t in BROAD or t in BROKERS or t.endswith(("증권", "자산운용")) or (VERBISH.search(t) and t not in stock):
        return ""
    return t


def _tokens(s: str, stock: frozenset) -> list[str]:
    return list(dict.fromkeys(x for x in (_norm(w, stock) for w in SPLIT.split(s)) if x))


def _issue_tokens(m: dict, stock: frozenset) -> list[str]:
    if m["kind"] == "disclosure":
        return _tokens(m["title"].split(" ", 1)[0], stock)[:1]                  # 회사 이름만
    return _tokens(m["title"] if m["kind"] == "article" else m["text"], stock)


def _tally(ms: list[dict], stock: frozenset) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for m in ms:
        if m["kind"] == "chat":
            continue
        toks = _issue_tokens(m, stock)
        w = 1.0 if m["kind"] != "wrap" else 1.0 / max(len(toks), 1)
        for t in toks:
            o = out.setdefault(t, {"ch": set(), "w": 0.0, "msgs": []})
            o["ch"].add(m["ch"])
            o["w"] += w
            o["msgs"].append(m)
    for m in ms:                                       # 대화 채널은 형식 채널이 낸 이슈에 채널 수만 보탠다(낱말 · 대표 제목 · 무게는 안 만듦)
        if m["kind"] == "chat":
            for t in _tokens(m["text"], stock):
                if t in out:
                    out[t]["ch"].add(m["ch"])
    return out


def _baseline(day: str, stock: frozenset) -> dict[str, tuple[float, float]]:
    """지난 BASE_DAYS 거래일: 낱말 → (제목에 나온 날 비율, 하루 무게 중앙값)."""
    d0, n, title_days, ws = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=KST), 0, {}, {}
    for k in range(1, BASE_DAYS * 2):
        s = d0 - timedelta(days=k)
        ms = _msgs(s, s + timedelta(days=1))
        if len(ms) < 30:                                                   # 주말 · 휴일
            continue
        n += 1
        for t in {t for m in ms for t in _tokens(m["title"], stock)}:
            title_days[t] = title_days.get(t, 0) + 1
        for t, o in _tally(ms, stock).items():
            ws.setdefault(t, []).append(o["w"])
        if n >= BASE_DAYS:
            break
    out = {}
    for t in set(title_days) | set(ws):
        w = sorted(ws.get(t, []) + [0.0] * (n - len(ws.get(t, []))))
        out[t] = (title_days.get(t, 0) / max(n, 1), w[len(w) // 2] if w else 0.0)
    return out


def issues(day: str, slot: str, nm: dict, top: int = 5) -> list[dict]:
    stock = frozenset(nm.values())
    ms = _msgs(*window(day, slot))
    vocab = {t for m in ms if m["kind"] in ("article", "disclosure") for t in _tokens(m["title"], stock)}   # 형식 채널 기사 · 공시 제목에 나온 낱말만 후보
    base = _baseline(day, stock)
    cand = []
    for t, o in _tally(ms, stock).items():
        rate, med = base.get(t, (0.0, 0.0))
        if t not in vocab or (rate >= GENERIC_RATE and o["w"] < SPIKE * max(med, 1.0)):
            continue                                                      # 평소 제목에 늘 나오는 단어
        cand.append((len(o["ch"]), o["w"], t, o))
    cand.sort(key=lambda x: (-x[0], -x[1], x[2]))
    picked: list[dict] = []
    for nch, w, t, o in cand:
        ids = {(m["ch"], m["id"]) for m in o["msgs"] if m["kind"] != "wrap"}     # 시황 글은 여러 이슈가 섞여 빼고 본다
        dup = next((p for p in picked if ids and p["ids"] and len(ids & p["ids"]) >= 0.7 * min(len(ids), len(p["ids"]))), None)
        if dup:                                                           # 기사 대부분이 앞 이슈 기사에 들어 있는 낱말 = 같은 이슈(2026-10-10: 스페이스X · 인수 · 통신이 따로 나옴)
            if len(dup["names"]) < 2:
                dup["names"].append(t)
            continue
        picked.append({"names": [t], "channels": nch, "weight": round(w, 2), "ids": ids, "msgs": o["msgs"]})
        if len(picked) >= top:
            break
    rank = {"article": 0, "disclosure": 1, "wrap": 2}
    out = []
    for p in picked:
        ok = [m for m in p["msgs"] if any(n in _tokens(m["title"], stock) for n in p["names"])]
        rep = min(ok, key=lambda m: (-sum(n in _tokens(m["title"], stock) for n in p["names"]),            # 묶인 이름이 다 나온 제목 먼저
                                     len(_tokens(m["title"], stock)) < 2, rank[m["kind"]], m["ch"] == "krwatch",   # 이름만 있는 제목 · 가격 알림은 뒤로
                                     len(_tokens(m["title"], stock)), m["t"])) if ok else None
        out.append({"issue": " · ".join(p["names"]), "channels": p["channels"], "weight": p["weight"],
                    "title": rep["title"] if rep else "", "link": f"https://t.me/{rep['ch']}/{rep['id']}" if rep else ""})
    return out


# ── 테마별 뉴스 언급(2026-10-10) ─────────────────────────────────────────────
# 테마 · 종목 · 키워드는 2 국내가 낸 themes.json(Core 테마 묶음)을 읽기만 한다. 기사 · 공시 · 시황은 제목, 대화 채널은 본문에서 찾는다.
KR_EXCHANGE = _ROOT.parent / "exchange" / "2_kr_market"


def _theme_groups(day: str) -> tuple[str, list[dict]]:
    ds = sorted(p.name for p in KR_EXCHANGE.glob("20??-??-??") if p.name <= day and (p / "themes.json").exists()) if KR_EXCHANGE.exists() else []
    if not ds:
        return "", []
    t = json.loads((KR_EXCHANGE / ds[-1] / "themes.json").read_text(encoding="utf-8"))
    return ds[-1], t.get("groups", [])


def theme_news(day: str, slot: str) -> dict:
    src, groups = _theme_groups(day)
    ms = [m for m in _msgs(*window(day, slot)) if m["kind"] != "disclosure"]   # 공시(대량보유 · IR 등) · 가격 알림은 뉴스가 아님 — 가격은 2 국내 테마 표가 맡음
    own: dict[str, str] = {}                                                # 여러 테마 묶음에 든 종목(삼성전자 등)은 2 국내 GROUPS 순서로 처음 나온 테마 하나에만
    for g in sorted(groups, key=lambda x: x.get("gi", 99)):
        for n in g.get("names", []):
            own.setdefault(n, g["theme"])
    out = []
    for g in groups:
        words = [w for w in g.get("keywords", [])] + [n for n in g.get("names", []) if len(n) >= 3 and own.get(n) == g["theme"]
                                                         and not n.endswith("증권")]   # 증권사 이름은 리포트 출처로 늘 나옴
        hit = []
        for m in ms:
            hay = m["text"] if m["kind"] == "chat" else m["title"]
            found = [w for w in words if w in hay]
            if found:
                hit.append((m, found))
        if not hit:
            continue
        reps = [(m, f) for m, f in hit if m["kind"] in ("article", "disclosure")]
        rep = max(reps, key=lambda x: (len(x[1]), x[0]["t"]))[0] if reps else None
        words_c = {}
        for _, f in hit:
            for w in f:
                words_c[w] = words_c.get(w, 0) + 1
        out.append({"theme": g["theme"], "channels": len({m["ch"] for m, _ in hit}), "msgs": len(hit),
                    "words": [w for w, _ in sorted(words_c.items(), key=lambda x: -x[1])[:3]],
                    "title": rep["title"] if rep else "", "link": f"https://t.me/{rep['ch']}/{rep['id']}" if rep else ""})
    out.sort(key=lambda x: (-x["channels"], -x["msgs"]))
    return {"source": src, "items": out}


def build(day: str | None = None, slot: str | None = None, since: str | None = None) -> dict:
    global SINCE
    SINCE = since
    now = datetime.now(KST)
    day = day or now.strftime("%Y-%m-%d")
    slot = slot or ("am" if now.hour < 12 else "pm")
    nm = names()
    dg = {"date": day, "slot": slot, "us": us_brief(day), "kr": kr_brief(day), "stocks": stock_news(day, nm), "reports": report_moves(day),
          "mine": my_news(day, nm), "issues": issues(day, slot, nm, top=10 if since else 5), "themes": theme_news(day, slot)}
    if since:
        dg["weekend"] = since
    if slot == "am":                                                      # 아침엔 전 거래일 마감
        prev = datetime.strptime(day, "%Y-%m-%d")
        dg["kr"] = []
        for k in range(1, 6):
            dg["kr"] = kr_brief((prev - timedelta(days=k)).strftime("%Y-%m-%d"))
            if any(x["title"].startswith("마감 시황") for x in dg["kr"]):
                break
    p = results_dir() / "reports"
    p.mkdir(parents=True, exist_ok=True)
    (p / "news_digest.json").write_text(json.dumps(dg, ensure_ascii=False, indent=1), encoding="utf-8")
    (p / "news_digest.md").write_text(to_md(dg), encoding="utf-8")
    write_exchange(dg)
    return dg


# ── exchange 출력(..\exchange\README.md 형식) ────────────────────────────────
EXCHANGE = _ROOT.parent / "exchange" / "5_news"


def _kr_close(dg: dict) -> dict | None:
    return next((x for x in reversed(dg["kr"]) if x["title"].startswith("마감 시황")), dg["kr"][-1] if dg["kr"] else None)


def report_line(rp: dict, k: int = 3) -> str:
    part = lambda lst: " · ".join(x["name"] + (f" {x['n']}곳" if x["n"] > 1 else "") for x in lst[:k])
    if not (rp["상향"] or rp["하향"]):
        return "목표가 변경 없음"
    return f"목표가 상향 {len(rp['상향'])}종목({part(rp['상향'])}) · 하향 {len(rp['하향'])}종목({part(rp['하향'])})"


def summary(dg: dict) -> dict:
    us, kr = dg["us"], _kr_close(dg)
    mine = dg["mine"][:3]
    it = lambda key, title, text, value=None, grade="서술", link="": {"key": key, "title": title, "text": text, "value": value,
                                                                     "grade": grade, "ref": "", "link": link}
    items = [
        it("us_brief", "미국 시황", us["headline"] if us else "", link=us["link"] if us else ""),
        it("kr_close", "국내 마감 시황" + ("(전 거래일)" if dg["slot"] == "am" else ""), kr["title"] if kr else "", link=kr["link"] if kr else ""),
        it("issues", "오늘의 이슈", " · ".join(f"{x['issue']}({x['channels']})" for x in dg["issues"]), dg["issues"]),
        it("reports", "리포트", report_line(dg["reports"]), dg["reports"], "참고"),
        it("holdings_news", "보유 · 관심 종목 기사", " · ".join(f"{x['names']}: {x['title']}" for x in mine), mine, "참고"),
        it("theme_news", "테마별 뉴스 언급" + (f"(테마 기준 {dg['themes']['source']})" if dg.get("themes", {}).get("source") else ""),
           " · ".join(f"{x['theme']}({x['channels']})" for x in dg.get("themes", {}).get("items", [])[:5]),
           dg.get("themes", {}).get("items", []), "참고"),
    ]
    miss = [x["key"] for x in items if not x["text"] and x["key"] not in ("holdings_news", "theme_news")]
    have = sorted({m["ch"] for m in _msgs(*window(dg["date"], dg["slot"]))})
    return {"role": "5_news", "date": dg["date"], "slot": dg["slot"], "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
            "status": "failed" if len(miss) >= 3 else ("partial" if miss else "ok"), "sources": have,
            "headline": (us["headline"] if dg["slot"] == "am" and us else kr["title"] if kr else ""), "items": items,
            "weekend": dg.get("weekend"),
            "notes": ("주말판 " + dg["weekend"] + " 00:00 – · " if dg.get("weekend") else "") + ("비어 있음: " + ", ".join(miss) + " · " if miss else "") + "원문 수집은 5_news reports/run.py(07:15 · 16:00)"}


def to_brief(s: dict) -> str:
    """10줄: 미국 1 · 국내 마감 1 · 이슈 5 · 리포트 1 · 보유 종목 기사 최대 3(없으면 줄 없음)."""
    it = {x["key"]: x for x in s["items"]}
    a = lambda x: f"[{x['text']}]({x['link']})" if x["link"] and x["text"] else (x["text"] or "–")
    L = [f"# 주요 뉴스 · {s['date']} {'아침' if s['slot'] == 'am' else '마감'}", "",
         f"- **미국** {a(it['us_brief'])}", f"- **{it['kr_close']['title'].replace(' 시황', '')}** {a(it['kr_close'])}"]
    for i, x in enumerate(it["issues"]["value"], 1):
        L.append(f"- **이슈 {i}** {x['issue']} · {x['channels']}채널 — " + (f"[{x['title']}]({x['link']})" if x["title"] else "_제목에 나온 글 없음_"))
    L.append(f"- **리포트** {it['reports']['text']}")
    L += [f"- **{x['names']}** {x['title']}" for x in it["holdings_news"]["value"]]
    return "\n".join(L + ["", "_원문 제목 그대로 · 방향 판단 아님_"]) + "\n"


def write_exchange(dg: dict) -> _Path:
    s = summary(dg)
    d = EXCHANGE / dg["date"]
    d.mkdir(parents=True, exist_ok=True)
    (d / f"summary_{dg['slot']}.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / f"summary_{dg['slot']}.md").write_text(to_brief(s), encoding="utf-8")
    (EXCHANGE / "latest.json").write_text(json.dumps({"date": dg["date"], "slot": dg["slot"]}), encoding="utf-8")
    dg["summary"] = s
    return d


def to_md(dg: dict) -> str:
    L = [f"# 오늘의 주요 뉴스 · {dg['date']}", "", "_원문 문장 그대로 · 방향 판단 아님_", ""]
    us = dg["us"]
    if us:
        L += [f"## 미국 시황 — {us['headline']}", ""]
        for sec in ("미국 시황", "국내 영향", "지수 · 금리 · 환율"):
            if us.get(sec):
                L += [f"**{sec}**", ""] + [f"- {x}" for x in us[sec]] + [""]
    for k in dg["kr"]:
        L += [f"## {k['time']} {k['title']}", ""] + [f"- {x}" for x in k["lines"]] + [""]
    if dg["stocks"]:
        L += ["## 기사가 많이 붙은 종목", ""] + [f"- {s['name']}({s['code']}) {s['n']}건 — {s['title']}" for s in dg["stocks"]] + [""]
    rp = dg["reports"]
    if any(rp.values()):
        L += ["## 증권사 리포트", ""]
        for lab in ("상향", "하향"):
            if rp[lab]:
                L.append(f"- 목표가 {lab} {len(rp[lab])}종목: " + " · ".join(f"{x['name']}" + (f" {x['n']}곳" if x["n"] > 1 else "") for x in rp[lab][:12]))
        if rp["신규 커버"]:
            L.append("- 신규 커버: " + " · ".join(x["name"] for x in rp["신규 커버"]))
        L.append("")
    if dg["mine"]:
        L += ["## 보유 · 관심 종목 기사", ""] + [f"- {x['names']}: {x['title']}" for x in dg["mine"]] + [""]
    return "\n".join(L)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--slot", choices=["am", "pm"], help="기본: 12시 전이면 am")
    ap.add_argument("--since", help="주말판 — 이 날 00:00부터 묶음(예: 토요일 날짜)")
    a = ap.parse_args()
    dg = build(a.date, a.slot, a.since)
    print(to_brief(dg["summary"]))
    print(f"→ {EXCHANGE / dg['date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
