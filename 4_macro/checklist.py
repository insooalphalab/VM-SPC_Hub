"""매크로 체크리스트 — data/macro_ext.csv(collect_ext.py)로 카드별 체크의 값 · 흐름 · 부담 신호를 기계 규칙으로 낸다.
2026-10-15 사용자 결정("내 체크리스트를 만들 수 있게") → 같은 날 흐름 방식으로 다시 짬(VM-SPC Core 9.334 · 9.335, 약함 개선안).
남의 체크리스트 문구 · 판정은 가져오지 않고, 우리 자료로 처음부터.

  python checklist.py            → data/checklist.json (export_exchange.py가 정리본 item `checklist`로 싣는다)

체크마다 형태(FORM)와 부담 방향(d, 원래 값 기준 +1 = 클수록 부담 · −1 = 작을수록 부담)은 9.334 · 9.335 권고 그대로:
- L{n}: 최근 n년 안 원래 값 순위 p(0 – 1) → 신호 = d × (2p − 1)
- F{k}: k개월 변화(가격 · 비율 체크는 원래 가격의 % 변화, 나머지는 값 변화) ÷ 과거 k개월 변화의 표준편차 = z → 신호 = d × clip(z / 2, −1, 1)
- Q: (5년 순위 ≥ 0.5) + (6개월 변화 > 0) ∈ {0, 1, 2} → 신호 = d × (Q − 1)
- 역할: score = 흐름 부담에 넣음 · sync = 동시 지표(지금 시장 상태, 예측 아님 — 9.335) · off = 기록만(빼기 · 역인과 · 표본 부족)
원점수 = score 체크 신호 평균 × 50 + 50(50 = 중립). 보이는 점수 = 2016 – 월말 원점수의 하위 5% · 상위 5% 값을 0 · 100으로 늘린 것(밖은 0 · 100에 붙임, 2026-10-15 사용자). 그 점수의 1/3 · 2/3 값으로 "높음 · 중간 · 낮음"을 붙인다
(9.334: 하위 1/3 달이 상위 1/3 달보다 이후 3 · 6 · 12개월 KODEX 200이 강했음 — 앞 · 최근 · 2006 – 2015 같은 방향, 통계 판정은 아님).
체크 · 카드 표시 등급(검증 아님, 보기용): 신호 ≥ 0.5 높음 · ≥ 0.15 높은 편 · 그 아래 낮음, 카드는 신호 평균 ≥ 0.35 · ≥ 0.10.
월 · 분기 지표는 지금 값은 그대로 쓰고, 과거 월말 부담(문턱 계산)에는 발표 지연 1개월을 둔다(9.334와 같게).
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
KST = timezone(timedelta(hours=9))
OBS = {"d": 252, "w": 52, "m": 12, "q": 4}          # 1년 관측 수
STALE = {"d": 10, "w": 21, "m": 100, "q": 140}      # 마지막 값이 이보다 오래되면 자료 부족
LABEL_STALE = {"글로벌 경제정책 불확실성": 160, "중국 수입 3개월 전년비": 160, "중국 수출 3개월 전년비": 160,   # 발표가 늦는 체크(일)
               "한국 실업률": 130, "미 신용카드 연체율": 200}
HIST0 = "2016-01-01"                                # 흐름 부담 문턱(1/3 · 2/3)을 잡는 월말 표본 시작


# ── 값 만들기 ─────────────────────────────────────────────────────────────
def S(df, c):
    return df[c].dropna() if c in df else pd.Series(dtype=float)


def lvl(c):
    return lambda df: S(df, c)


def diff(a, b):                                   # a − b (같은 날짜만)
    return lambda df: (S(df, a) - S(df, b)).dropna()


def chg_pct(c, n):                                # n관측 % 변화
    return lambda df: (S(df, c).pct_change(n) * 100).dropna()


def rel_pct(a, b, n):                             # a ÷ b 의 n관측 % 변화(상대 성과)
    return lambda df: ((S(df, a) / S(df, b)).dropna().pct_change(n) * 100).dropna()


def ratio(a, b):
    return lambda df: (S(df, a) / S(df, b)).dropna()


def yoy(c):
    return lambda df: (S(df, c).pct_change(12) * 100).dropna()


def ann3m(c):                                     # 월 지수의 3개월 연율
    return lambda df: (((S(df, c) / S(df, c).shift(3)) ** 4 - 1) * 100).dropna()


def ma(c, n):
    return lambda df: S(df, c).rolling(n).mean().dropna()


def chg_n(c, n):                                  # n관측 차이(수준)
    return lambda df: S(df, c).diff(n).dropna()


def above_min12(c):                               # 지금 − 직전 12관측 최저(샴 규칙식)
    return lambda df: (S(df, c) - S(df, c).rolling(12).min()).dropna()


def copper_gold(df):
    return ratio("y_copper", "y_gold")(df) * 1000


# 체크: (라벨, 값 함수, 주기, 부담 방향 d, 단위) — 9.333 검증 스크립트가 이 5칸 형식을 import해서 쓴다(바꾸지 말 것)
# 형태 · 역할 · 흐름 원천은 아래 SPEC(라벨 → (형태, 역할, 흐름 원천)). 흐름 원천: None = 값 자체, ("p", 열) · ("r", 열, 열) = 원래 가격 · 비율의 % 변화
CARDS = [
    ("1", "물가 · 기대인플레", "물가 기대가 높게 머물면 금리가 내려오기 어렵다.", [
        ("10년 기대인플레(BEI)", lvl("f_bei10"), "d", 1, "%"),
        ("5y5y 선도 기대인플레", lvl("f_5y5y"), "d", 1, "%"),
        ("미시간 1년 기대인플레", lvl("f_mich"), "m", 1, "%"),
        ("근원 CPI 3개월 연율", ann3m("f_core_cpi"), "m", 1, "%"),
        ("근원 PCE 전년비", yoy("f_core_pce"), "m", 1, "%")]),
    ("2", "정책 · 장기금리", "정책금리 기대와 장기금리가 오르는 흐름이면 부담.", [
        ("2년 − 연준 상단", diff("f_dgs2", "f_fedup"), "d", 1, "%p"),
        ("3개월 − 연준 상단", diff("f_dgs3mo", "f_fedup"), "d", 1, "%p"),
        ("2년 한 달 변화", chg_n("f_dgs2", 21), "d", 1, "%p"),
        ("연준 목표 상단", lvl("f_fedup"), "d", 1, "%"),
        ("미 10년", lvl("y_tnx"), "d", 1, "%"),
        ("기대 경로 몫(10년 − 기간 프리미엄)", diff("f_dgs10", "f_tp10"), "d", 1, "%"),
        ("10년 − 2년", lvl("f_t10y2y"), "d", -1, "%p"),
        ("미 30년", lvl("y_tyx"), "d", 0, "%"),
        ("10년 실질금리(TIPS)", lvl("f_real10"), "d", 0, "%"),
        ("10년 기간 프리미엄", lvl("f_tp10"), "d", 0, "%")]),
    ("3", "약한 기업 신용", "신용이 낮은 쪽부터 자금 사정이 나빠지는지.", [
        ("하이일드 ÷ 국채 ETF 한 달", rel_pct("y_hyg", "y_ief", 21), "d", 1, "%"),
        ("BDC ETF 한 달", chg_pct("y_bizd", 21), "d", 1, "%"),
        ("레버리지론 ETF 한 달", chg_pct("y_bkln", 21), "d", 0, "%"),
        ("HY 추가이자(OAS)", lvl("f_hy"), "d", 0, "%p"),
        ("CCC 이하", lvl("f_ccc"), "d", 0, "%p")]),
    ("4", "금융여건 · 대출", "은행 · 지역은행 쪽 흐름.", [
        ("세인트루이스 금융스트레스", lvl("f_stlfsi"), "w", -1, ""),
        ("은행 대기업 대출 긴축 응답", lvl("f_sloos_l"), "q", -1, "%"),
        ("지역은행 ÷ S&P500 한 달", rel_pct("y_kre", "y_spy", 21), "d", 1, "%"),
        ("시카고 연준 금융여건(NFCI)", lvl("f_nfci"), "w", 0, ""),
        ("은행 중소기업 대출 긴축 응답", lvl("f_sloos_s"), "q", 0, "%")]),
    ("5", "유동성", "재무부 계좌 · 통화량 · 역레포 흐름.", [
        ("재무부 TGA 4주 변화", chg_pct("f_tga", 4), "w", -1, "%"),
        ("M2 전년비", yoy("f_m2"), "m", -1, "%"),
        ("역레포 잔고", lvl("f_rrp"), "d", 1, "$bn"),
        ("연준 총자산 13주 변화", chg_pct("f_walcl", 13), "w", 0, "%")]),
    ("6", "해외 국채", "유럽 · 일본 금리 흐름.", [
        ("프랑스 − 독일 10년(월)", diff("f_fr10", "f_de10"), "m", -1, "%p"),
        ("일본 10년(월)", lvl("f_jp10"), "m", -1, "%"),
        ("신흥국 달러채 ETF 한 달", chg_pct("y_emb", 21), "d", -1, "%"),
        ("이탈리아 − 독일 10년(월)", diff("f_it10", "f_de10"), "m", 0, "%p"),
        ("영국 10년(월)", lvl("f_gb10"), "m", 0, "%")]),
    ("7", "에너지", "유가가 높게 머물거나 1년 흐름이 오르면 부담(앞서기 10 – 11개월).", [
        ("브렌트", lvl("y_brent"), "d", 1, "$"),
        ("WTI", lvl("y_wti"), "d", 1, "$"),
        ("디젤(난방유) 선물", lvl("y_ho"), "d", 1, "$"),
        ("천연가스", lvl("y_ng"), "d", 1, "$"),
        ("브렌트 흐름", chg_pct("y_brent", 21), "d", 1, "%")]),
    ("8", "환율 · 국가 흐름", "엔화 약세 · 한국 상대 강세 위치.", [
        ("엔/달러", lvl("y_jpy"), "d", 1, "엔"),
        ("한국 ÷ S&P500 3개월", rel_pct("y_ewy", "y_spy", 63), "d", -1, "%"),
        ("원/달러", lvl("y_krw"), "d", 0, "원"),
        ("달러인덱스", lvl("y_dxy"), "d", 0, ""),
        ("신흥국 ETF 한 달", chg_pct("y_eem", 21), "d", 0, "%"),
        ("한국 ÷ 대만 ETF 3개월", rel_pct("y_ewy", "y_ewt", 63), "d", 0, "%")]),
    ("9", "위험자산 온도", "변동성 · 경기 민감 자산 흐름.", [
        ("VIX", lvl("y_vix"), "d", -1, ""),
        ("MOVE(채권 변동성)", lvl("y_move"), "d", 1, ""),
        ("VVIX", lvl("y_vvix"), "d", -1, ""),
        ("구리 ÷ 금 ×1000", copper_gold, "d", 1, ""),
        ("비트코인 흐름", chg_pct("y_btc", 21), "d", -1, "%"),
        ("동일가중 ÷ 시총가중(상승 폭)", rel_pct("y_rsp", "y_spy", 63), "d", 1, "%")]),
    ("10", "반도체 · AI 가격", "AI 축의 가격 흐름.", [
        ("기술 ÷ 필수소비 흐름", rel_pct("y_xlk", "y_xlp", 21), "d", -1, "%"),
        ("마이크론 흐름", chg_pct("y_mu", 21), "d", 1, "%"),
        ("반도체 ÷ S&P500 국면", rel_pct("y_smh", "y_spy", 63), "d", -1, "%"),
        ("반도체 ETF 한 달", chg_pct("y_soxx", 21), "d", 0, "%"),
        ("엔비디아 한 달", chg_pct("y_nvda", 21), "d", 0, "%")]),
]
AUX = [
    ("14", "고용 · 경기(보조)", "흐름 부담에 넣지 않음.", [
        ("신규 실업수당 4주 평균", ma("f_icsa", 4), "w", -1, "건"),
        ("실업률 − 직전 12개월 최저", above_min12("f_unrate"), "m", -1, "%p"),
        ("비농업 고용 3개월 평균 증가", lambda df: S(df, "f_payems").diff().rolling(3).mean().dropna(), "m", 1, "천 명"),
        ("산업생산 전년비", yoy("f_indpro"), "m", 1, "%"),
        ("미시간 소비심리", lvl("f_umcsent"), "m", 1, "")]),
]
def yoy3(c):                                      # 월 값 3개월 합의 전년비(수출 · 수입처럼 들쭉날쭉한 월 값)
    return lambda df: ((S(df, c).rolling(3).sum() / S(df, c).rolling(3).sum().shift(12) - 1) * 100).dropna()


def ma_d(c, n):                                   # 일별 n일 평균
    return lambda df: S(df, c).rolling(n).mean().dropna()


# 2026-10-15 추가 카드(VM-SPC Core 9.337, 사용자 A안): 앞서거나 같이 가지 않는 확인 체크만 점수(score), 코스피와 같이 가거나 뒤따르는 확인 체크는
# 동시 지표(sync), 참고 · 빼기는 기록만(off). d = 9.337이 고른 원래 값 기준 방향(한국 경기 지표는 "고점일수록 부담", 스프레드 · 불확실성은 "벌어지는 중이면 이후 좋음").
CARDS += [
    ("11", "한국 금리 · 신용", "국내 장단기 차 · 회사채 스프레드 · 기준금리(9.337).", [
        ("국고 10년 − 3년", diff("k_ktb10", "k_ktb3"), "d", -1, "%p"),
        ("회사채 AA− − 국고 3년", diff("k_aa", "k_ktb3"), "d", -1, "%p"),
        ("회사채 BBB− − AA−", diff("k_bbb", "k_aa"), "d", -1, "%p"),
        ("한국 기준금리", lvl("k_base"), "d", 1, "%"),
        ("국고 3년 − 기준금리", diff("k_ktb3", "k_base"), "d", 0, "%p"),
        ("CD 91일 − 기준금리", diff("k_cd91", "k_base"), "d", 0, "%p"),
        ("한국 10년 − 미 10년", diff("k_ktb10", "f_dgs10"), "d", 0, "%p"),
        ("한국 CPI 전년비", yoy("k_cpi"), "m", 0, "%")]),
    ("12", "경기 · 불확실성", "침체 확률 · 글로벌 정책 불확실성(9.337).", [
        ("미 침체 확률", lvl("f_recprob"), "m", 1, "%"),
        ("글로벌 경제정책 불확실성", lvl("f_gepu"), "m", -1, ""),
        ("미 경제정책 불확실성 30일 평균", ma_d("f_epu", 30), "d", 0, ""),
        ("샴 규칙 실시간", lvl("f_sahm"), "m", 0, "%p"),
        ("미 건축허가 전년비", yoy("f_permit"), "m", 0, "%"),
        ("미 신용카드 연체율", lvl("f_cc_delinq"), "q", 0, "%")]),
    ("13", "한국 경기 · 수출", "수출 · 경기지수 — 코스피와 같이 가거나 코스피가 앞섬(9.337) → 동시 지표 · 기록.", [
        ("한국 수출 3개월 전년비", yoy3("k_exp"), "m", 0, "%"),
        ("한국 기업심리(OECD)", lvl("f_kr_bci"), "m", 0, ""),
        ("중국 수입 3개월 전년비", yoy3("f_cn_imp"), "m", 0, "%"),
        ("반도체 수출 3개월 전년비", yoy3("c_semi_exp"), "m", 0, "%"),
        ("한국 수입 3개월 전년비", yoy3("k_imp"), "m", 0, "%"),
        ("선행지수 순환변동치", lvl("k_lead"), "m", 0, ""),
        ("동행지수 순환변동치", lvl("k_coin"), "m", 0, ""),
        ("한국 실업률", lvl("f_kr_unemp"), "m", 0, "%"),
        ("중국 수출 3개월 전년비", yoy3("f_cn_exp"), "m", 0, "%")]),
]
PENDING: list = []       # 9.337로 모두 옮김(9.337 스크립트가 쓰던 원래 PENDING 정의는 Core results/macro_new23.json에 기록)
PENDING_FORM = "F12"
SPEC_ADD = {
    "국고 10년 − 3년": ("Q", "score", None, "9.337 최근경향"), "회사채 AA− − 국고 3년": ("F12", "score", None, "9.337 약함"),
    "회사채 BBB− − AA−": ("F6", "score", None, "9.337 최근경향"), "한국 기준금리": ("L5", "score", None, "9.337 참고 · 8개월 앞섬"),
    "국고 3년 − 기준금리": ("F6", "off", None, "참고(9.337) — 점수 제외"), "CD 91일 − 기준금리": ("F12", "off", None, "빼기(9.337)"),
    "한국 10년 − 미 10년": ("F12", "off", None, "빼기(9.337)"), "한국 CPI 전년비": ("F12", "off", None, "빼기(9.337)"),
    "미 침체 확률": ("L1", "score", None, "9.337 약함"), "글로벌 경제정책 불확실성": ("L3", "score", None, "9.337 최근경향"),
    "미 경제정책 불확실성 30일 평균": ("F12", "sync", None, "동시 · 역인과(9.337)"),
    "샴 규칙 실시간": ("L3", "off", None, "참고(9.337) — 점수 제외"), "미 건축허가 전년비": ("F12", "off", None, "빼기(9.337)"),
    "미 신용카드 연체율": ("F6", "off", None, "참고(9.337) — 점수 제외"),
    "한국 수출 3개월 전년비": ("L10", "sync", None, "동시 — 코스피가 4개월 앞섬(9.337)"),
    "한국 기업심리(OECD)": ("L10", "sync", None, "동시(9.337)"), "중국 수입 3개월 전년비": ("L10", "sync", None, "역인과(9.337)"),
    "반도체 수출 3개월 전년비": ("F12", "off", None, "빼기(9.337)"), "한국 수입 3개월 전년비": ("L10", "off", None, "참고(9.337) — 점수 제외"),
    "선행지수 순환변동치": ("L10", "off", None, "참고(9.337) — 점수 제외"), "동행지수 순환변동치": ("L10", "off", None, "참고(9.337) — 점수 제외"),
    "한국 실업률": ("F6", "off", None, "참고(9.337) — 점수 제외"), "중국 수출 3개월 전년비": ("L10", "off", None, "참고(9.337) — 점수 제외"),
}

SPEC = {   # 라벨 → (형태, 역할, 흐름 원천, 사유)
    "10년 기대인플레(BEI)": ("L10", "score", None, ""), "5y5y 선도 기대인플레": ("Q", "score", None, "9.335 국면"),
    "미시간 1년 기대인플레": ("L3", "score", None, ""), "근원 CPI 3개월 연율": ("F12", "score", None, ""),
    "근원 PCE 전년비": ("L10", "score", None, ""),
    "2년 − 연준 상단": ("L10", "score", None, ""), "3개월 − 연준 상단": ("L5", "score", None, ""),
    "2년 한 달 변화": ("L10", "score", None, ""), "연준 목표 상단": ("Q", "score", None, ""),
    "미 10년": ("F12", "score", None, "9.335 수준 → 12개월 흐름"),
    "기대 경로 몫(10년 − 기간 프리미엄)": ("F12", "score", None, "9.335 새 체크"),
    "10년 − 2년": ("L10", "score", None, ""),
    "미 30년": ("F12", "off", None, "무관(9.335)"), "10년 실질금리(TIPS)": ("F12", "off", None, "무관(9.335)"),
    "10년 기간 프리미엄": ("F12", "off", None, "역인과 — KOSPI가 8개월 앞섬(9.335)"),
    "하이일드 ÷ 국채 ETF 한 달": ("F12", "score", ("r", "y_hyg", "y_ief"), ""), "BDC ETF 한 달": ("L10", "score", None, ""),
    "레버리지론 ETF 한 달": ("F12", "off", ("p", "y_bkln"), "무관(9.335)"),
    "HY 추가이자(OAS)": ("L5", "off", None, "표본 부족(2023-10 – )"), "CCC 이하": ("L5", "off", None, "표본 부족(2023-10 – )"),
    "세인트루이스 금융스트레스": ("L10", "score", None, ""), "은행 대기업 대출 긴축 응답": ("L3", "score", None, ""),
    "지역은행 ÷ S&P500 한 달": ("F12", "score", ("r", "y_kre", "y_spy"), ""),
    "시카고 연준 금융여건(NFCI)": ("L10", "off", None, "무관(9.335)"),
    "은행 중소기업 대출 긴축 응답": ("L3", "off", None, "역인과 — KOSPI가 4개월 앞섬(9.335)"),
    "재무부 TGA 4주 변화": ("F12", "score", ("p", "f_tga"), ""), "M2 전년비": ("F12", "score", None, ""),
    "역레포 잔고": ("L10", "score", None, "9.335"), "연준 총자산 13주 변화": ("F12", "off", ("p", "f_walcl"), "무관(9.335)"),
    "프랑스 − 독일 10년(월)": ("F12", "score", None, ""), "일본 10년(월)": ("F6", "score", None, ""),
    "신흥국 달러채 ETF 한 달": ("L10", "score", None, ""),
    "이탈리아 − 독일 10년(월)": ("F12", "off", None, "역인과 — KOSPI가 1개월 앞섬(9.335)"),
    "영국 10년(월)": ("F12", "off", None, "무관(9.335)"),
    "브렌트": ("L10", "score", None, ""), "WTI": ("L10", "score", None, ""), "디젤(난방유) 선물": ("L10", "score", None, ""),
    "천연가스": ("L10", "score", None, ""), "브렌트 흐름": ("F12", "score", ("p", "y_brent"), "9.334 최근경향"),
    "엔/달러": ("L3", "score", None, ""), "한국 ÷ S&P500 3개월": ("L1", "score", None, ""),
    "원/달러": ("F6", "sync", ("p", "y_krw"), "동시 지표(9.335)"), "달러인덱스": ("F6", "sync", ("p", "y_dxy"), "동시 지표(9.335)"),
    "신흥국 ETF 한 달": ("F6", "sync", ("p", "y_eem"), "동시 지표(9.335)"),
    "한국 ÷ 대만 ETF 3개월": ("F6", "off", ("r", "y_ewy", "y_ewt"), "무관(9.335)"),
    "VIX": ("F12", "score", None, ""), "MOVE(채권 변동성)": ("L1", "score", None, "9.334 최근경향"), "VVIX": ("L3", "score", None, ""),
    "구리 ÷ 금 ×1000": ("L10", "score", None, ""), "비트코인 흐름": ("F3", "score", ("p", "y_btc"), ""),
    "동일가중 ÷ 시총가중(상승 폭)": ("F12", "score", ("r", "y_rsp", "y_spy"), ""),
    "기술 ÷ 필수소비 흐름": ("F6", "score", ("r", "y_xlk", "y_xlp"), ""), "마이크론 흐름": ("F12", "score", ("p", "y_mu"), ""),
    "반도체 ÷ S&P500 국면": ("Q", "score", ("r", "y_smh", "y_spy"), "9.335 국면"),
    "반도체 ETF 한 달": ("F6", "sync", ("p", "y_soxx"), "동시 지표(9.335)"),
    "엔비디아 한 달": ("F6", "off", ("p", "y_nvda"), "역인과 — KOSPI가 2개월 앞섬(9.335)"),
    "신규 실업수당 4주 평균": ("F12", "aux", None, ""), "실업률 − 직전 12개월 최저": ("L5", "aux", None, ""),
    "비농업 고용 3개월 평균 증가": ("F12", "aux", None, ""), "산업생산 전년비": ("L5", "aux", None, ""),
    "미시간 소비심리": ("F12", "aux", None, ""),
}
SPEC.update(SPEC_ADD)
BOARD = [   # 가격 반응 보드 — 1주(5거래일) 변화, 부담 방향 화살표만(2026-10-20 매크로 · AI로 나누고 넓힘)
    ("매크로", [("미 10년", "y_tnx", "d", 1, "bp"), ("미 2년", "f_dgs2", "d", 1, "bp"), ("10년 − 2년", "f_t10y2y", "d", -1, "bp"),
              ("2년 − 연준 상단", ("f_dgs2", "f_fedup"), "d", 1, "bp"), ("하이일드 ÷ 국채", ("y_hyg", "y_ief", "r"), "d", -1, "%"),
              ("브렌트", "y_brent", "d", 1, "%"), ("달러인덱스", "y_dxy", "d", 0, "%"), ("VIX", "y_vix", "d", 1, "%")]),
    ("AI", [("기술 ÷ 필수소비", ("y_xlk", "y_xlp", "r"), "d", -1, "%"), ("반도체 ETF", "y_soxx", "d", -1, "%"),
            ("마이크론", "y_mu", "d", -1, "%"), ("메모리 ETF", "y_dram", "d", -1, "%"), ("코어위브", "y_crwv", "d", -1, "%"),
            ("하이퍼스케일러 4", "x_hyper", "d", -1, "%"), ("전력 · 설비 3", "x_power", "d", -1, "%"),
            ("동일가중 ÷ 시총가중", ("y_rsp", "y_spy", "r"), "d", -1, "%"), ("한국 ÷ 대만", ("y_ewy", "y_ewt", "r"), "d", -1, "%")]),
]

# ── AI 투자 · 인프라 참고 카드(2026-10-20 사용자 — "시장이 급변해 더 많은 걸 고려") ─────────────────────
# 점수(매크로 부담) 밖. 역할 ref = 신호 · 등급은 보이지만 부담 점수 · 문턱에는 안 들어감(검증 전). 쌓인 뒤 VM-core 검증으로만 점수에 넣는다.
# CARDS는 VM-core 검증 스크립트가 import하므로 건드리지 않고 따로 둔다. 남의 체크리스트 문구 · 판정은 가져오지 않음(구성은 우리 자료).
GLOBAL_DATA = os.path.join(HERE, "..", "..", "VM-SPC_Global", "data")
HYPER = ["y_msft", "y_meta", "y_googl", "y_amzn"]
POWER = ["y_vrt", "y_ceg", "y_vst"]


def basket_idx(cols):                              # 같은 비중 묶음 지수(있는 종목의 일 수익 평균을 누적)
    def f(df):
        r = pd.concat([S(df, c).pct_change() for c in cols], axis=1).mean(axis=1, skipna=True).dropna()
        return (1 + r).cumprod() * 100
    return f


def corr_rate(a, n=60):                            # a 일 수익과 미 10년 변화의 n일 상관(− 클수록 금리 오를 때 약함)
    def f(df):
        x = pd.concat([S(df, a).pct_change(), S(df, "y_tnx").diff()], axis=1).dropna()
        return x.iloc[:, 0].rolling(n).corr(x.iloc[:, 1]).dropna()
    return f


def fed_path(df):                                  # 연방기금 선물(가까운 달) 금리 − EFFR = 시장이 보는 가까운 인하(−) · 인상(+)
    return ((100 - S(df, "y_zq")) - S(df, "f_effr")).dropna()


def us_breadth() -> pd.Series:
    """VM-SPC_Global 미국 대형주 · ETF 일봉(약 270종목)으로 200일선 위 비율(%). 종목 100개 이상인 날만."""
    rows = {}
    for root, _, files in os.walk(GLOBAL_DATA):
        if os.path.basename(root) == "for_core":
            continue
        for fn in files:
            if fn.endswith(".csv") and fn[:-4] not in rows:
                try:
                    s = pd.read_csv(os.path.join(root, fn), usecols=["date", "close"], dtype={"date": str}, encoding="utf-8-sig")
                except Exception:  # noqa: BLE001
                    continue
                s = s.set_index(pd.to_datetime(s["date"], format="%Y%m%d"))["close"].astype(float)
                rows[fn[:-4]] = (s > s.rolling(200).mean()).where(s.rolling(200).count() >= 200)
    if not rows:
        return pd.Series(dtype=float)
    a = pd.DataFrame(rows)
    n = a.notna().sum(axis=1)
    return (a.mean(axis=1) * 100)[n >= 100].dropna()


REF_CARDS = [
    ("15", "AI 투자 · 인프라(참고)", "AI 쪽 돈 · 신용 · 전력 · 메모리의 가격 흐름 — 점수 밖, 검증 전(2026-10-20).", [
        ("메모리 ETF 한 달", chg_pct("y_dram", 21), "d", -1, "%"),
        ("하이퍼스케일러 4 ÷ S&P500 한 달", lambda df: (basket_idx(HYPER)(df) / S(df, "y_spy")).dropna().pct_change(21).mul(100).dropna(), "d", -1, "%"),
        ("전력 · 설비 3 ÷ S&P500 한 달", lambda df: (basket_idx(POWER)(df) / S(df, "y_spy")).dropna().pct_change(21).mul(100).dropna(), "d", -1, "%"),
        ("TSMC ADR 한 달", chg_pct("y_tsm", 21), "d", -1, "%"),
        ("반도체 · 미 10년 60일 상관", corr_rate("y_smh"), "d", -1, ""),
        ("미국 대형주 200일선 위 비율", lvl("x_breadth"), "d", -1, "%"),
        ("연준 선물 − EFFR(가까운 인하 −)", fed_path, "d", 1, "%p")]),
    # 2026-10-20 사용자("재무 · 신용 쪽에 문제가 제일 많은 것 같다") — 기업별 CDS는 유료라 받을 수 있는 대리 지표로. 넓은 신용(IG)은 평소인데
    # 빚으로 AI 설비투자를 하는 기업 · 저신용 쪽에만 압박이 몰리는지 본다. 점수 밖 · 가중 없음(지금 움직이는 걸 보고 고르지 않음).
    ("16", "AI · 저신용 신용(참고)", "빚으로 AI 투자하는 기업 주가와 저신용 스프레드 — 넓은 신용과 비교(2026-10-20, 점수 밖).", [
        ("오라클 ÷ S&P500(AI 부채 투자 대리)", ratio("y_orcl", "y_spy"), "d", -1, ""),
        ("코어위브 주가(AI 인프라 신용 대리)", lvl("y_crwv"), "d", -1, "$"),
        ("하이일드 스프레드(OAS)", lvl("f_hy"), "d", 1, "%p"),
        ("하이일드 스프레드 한 달 변화", chg_n("f_hy", 21), "d", 1, "%p"),
        ("CCC 이하 스프레드", lvl("f_ccc"), "d", 1, "%p"),
        ("CCC − BBB(저신용에만 몰림)", diff("f_ccc", "f_bbb"), "d", 1, "%p"),
        ("투자등급 스프레드(IG, 넓은 신용 기준선)", lvl("f_ig"), "d", 1, "%p")]),
]
SPEC_REF = {   # 라벨 → (형태, 역할, 흐름 원천, 사유) — 이력이 짧은 것은 1년 순위
    "메모리 ETF 한 달": ("L1", "ref", None, "참고 · 2026-04 상장(1년 순위가 차면 계산)"),
    "하이퍼스케일러 4 ÷ S&P500 한 달": ("L3", "ref", None, "참고 · MSFT · META · GOOGL · AMZN 같은 비중"),
    "전력 · 설비 3 ÷ S&P500 한 달": ("L3", "ref", None, "참고 · VRT · CEG · VST 같은 비중"),
    "TSMC ADR 한 달": ("L3", "ref", None, "참고"),
    "반도체 · 미 10년 60일 상관": ("L3", "ref", None, "참고 · − 클수록 금리 오를 때 AI가 약함"),
    "미국 대형주 200일선 위 비율": ("L3", "ref", None, "참고 · VM-SPC_Global 약 270종목"),
    "연준 선물 − EFFR(가까운 인하 −)": ("L1", "ref", None, "참고 · 가까운 달 선물만(FedWatch 대용)"),
    "오라클 ÷ S&P500(AI 부채 투자 대리)": ("L3", "ref", None, "참고 · 3년 중 낮을수록 압박"),
    "코어위브 주가(AI 인프라 신용 대리)": ("L1", "ref", None, "참고 · 2025-03 상장"),
    "하이일드 스프레드(OAS)": ("L3", "ref", None, "참고 · FRED가 최근 3년만 줌"),
    "하이일드 스프레드 한 달 변화": ("L3", "ref", None, "참고"),
    "CCC 이하 스프레드": ("L3", "ref", None, "참고 · FRED가 최근 3년만 줌"),
    "CCC − BBB(저신용에만 몰림)": ("L3", "ref", None, "참고"),
    "투자등급 스프레드(IG, 넓은 신용 기준선)": ("L3", "ref", None, "참고 · 넓은 신용이 같이 오르는지"),
}
CREDIT_HOT = 0.8          # 3년(코어위브 1년) 위험 쪽 상위 10% = 신호 0.8 이상
CREDIT_KEYS = ["오라클 ÷ S&P500(AI 부채 투자 대리)", "코어위브 주가(AI 인프라 신용 대리)", "하이일드 스프레드(OAS)",
               "CCC 이하 스프레드", "CCC − BBB(저신용에만 몰림)"]


def credit_alert(ref_cards) -> dict:
    """AI · 저신용 신용 압박 경보(기계 규칙, 참고): 위 다섯 중 둘 이상이 위험 쪽 상위 10%. 넓은 신용(IG)이 같이 오르는지도 적는다."""
    cs = {c["label"]: c for k in ref_cards if k["no"] == "16" for c in k["checks"]}
    hot = [l for l in CREDIT_KEYS if (cs.get(l) or {}).get("signal", -1) >= CREDIT_HOT]
    ig = (cs.get("투자등급 스프레드(IG, 넓은 신용 기준선)") or {}).get("signal")
    broad = None if ig is None else ("넓은 신용(IG)도 위험 쪽" if ig >= 0.5 else "넓은 신용(IG)은 평소 범위")
    on = len(hot) >= 2
    short = lambda l: l.split("(")[0].strip()
    return {"on": on, "hot": hot, "broad": broad,
            "text": (f"AI · 저신용 쪽 신용 압박 — {' · '.join(short(l) for l in hot)} 위험 쪽 상위 10%(3년, 코어위브는 1년)" + (f", {broad}" if broad else "")) if on else ""}
SPEC.update(SPEC_REF)

# 같은 줄기 — 2016 – 월말 점수 체크 신호끼리 상관 0.7 이상 묶음(2026-10-20 계산: 점수 체크 45개 ≈ 독립 정보 9개 분량).
# 겹친 줄기를 하나로 묶어 다시 계산해도 점수는 거의 같았음(지금 79.4 → 78.1, 과거 상관 0.97) → 점수는 그대로 두고 보기에서만 묶어 보여 준다.
STRANDS = [
    ("유가 · 물가 · 금리 줄기", ["브렌트", "WTI", "디젤(난방유) 선물", "10년 기대인플레(BEI)", "근원 PCE 전년비", "미 10년",
                           "기대 경로 몫(10년 − 기간 프리미엄)", "M2 전년비", "역레포 잔고", "엔/달러"]),
    ("정책금리 · 곡선", ["연준 목표 상단", "10년 − 2년"]),
    ("신용 · 금융 스트레스", ["하이일드 ÷ 국채 ETF 한 달", "세인트루이스 금융스트레스"]),
    ("경기 민감 원자재", ["브렌트 흐름", "구리 ÷ 금 ×1000"]),
]
HIST_PATH = os.path.join(DATA, "checklist_hist.json")
WORD = {"G": "낮음", "A": "높은 편", "R": "높음", "B": "자료 부족", "N": "점수 제외"}
FORM_WORD = lambda f: {"Q": "국면(5년 수준 × 6개월 흐름)"}.get(f, f"{f[1:]}년 순위" if f[0] == "L" else f"{f[1:]}개월 흐름")


def _fmt(v, unit=""):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "–"
    if unit == "$bn":
        return f"{v:,.1f}"
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    return f"{v:.2f}" if abs(v) < 100 else f"{v:.1f}"


# ── 신호 ─────────────────────────────────────────────────────────────────
def _series(df, fn) -> pd.Series:
    s = fn(df).dropna()
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated()].sort_index()


def _flowsrc(df, fn, src) -> tuple[pd.Series, bool]:
    if src is None:
        return _series(df, fn), False
    s = S(df, src[1]) if src[0] == "p" else (S(df, src[1]) / S(df, src[2])).dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index(), True


def _asof(s: pd.Series, t: pd.Timestamp, fq: str, days=None):
    j = s.index.searchsorted(t, side="right")
    if j == 0 or (t - s.index[j - 1]).days > (days or STALE[fq]):
        return None
    return float(s.iloc[j - 1])


def _rank(s: pd.Series, t: pd.Timestamp, fq: str, years: int, days=None):
    j = s.index.searchsorted(t, side="right")
    if j == 0 or (t - s.index[j - 1]).days > (days or STALE[fq]):
        return None
    n = OBS[fq] * years
    w = s.to_numpy(float)[max(0, j - n):j]
    return float((w <= w[-1]).mean()) if len(w) >= n * 0.5 else None


def _months(idx_end: pd.Timestamp, start="2000-01-31") -> pd.DatetimeIndex:
    return pd.date_range(start, idx_end, freq="ME")


def _zchg(src: pd.Series, pct: bool, k: int, t: pd.Timestamp, fq: str, days=None):
    """t 기준 k개월 변화 ÷ (t까지 월말 k개월 변화의 표준편차, 36개 이상)."""
    ms = _months(t)
    f_ = "d" if pct else fq
    mv = pd.Series([_asof(src, m, f_, days) for m in ms], index=ms, dtype=float)
    cur, past = _asof(src, t, f_, days), _asof(src, t - pd.DateOffset(months=k), f_, days)
    if cur is None or past is None:
        return None, None
    ch = (mv / mv.shift(k) - 1) * 100 if pct else mv - mv.shift(k)
    sd = ch.dropna().std() if ch.notna().sum() >= 36 else None
    c = (cur / past - 1) * 100 if pct else cur - past
    return c, (c / sd if sd else None)


def signal(df, fn, fq, d, form, src, t, lag=False, days=None):
    """t 시점 (신호 −1 – 1, 설명 dict). lag = 월 · 분기 지표 발표 지연 1개월(과거 월말 계산용)."""
    s = _series(df, fn)
    if lag and fq in ("m", "q"):
        s.index = s.index + pd.DateOffset(months=1)
    if s.empty:
        return None, {}
    if form[0] == "L":
        p = _rank(s, t, fq, int(form[1:]), days)
        return (None, {}) if p is None else (d * (2 * p - 1), {"rank": round(p, 3)})
    fsrc, pct = _flowsrc(df, fn, src)
    if lag and fq in ("m", "q") and src is None:
        fsrc = s
    if form[0] == "F":
        c, z = _zchg(fsrc, pct, int(form[1:]), t, fq, days)
        return (None, {}) if z is None else (d * float(np.clip(z / 2, -1, 1)), {"chg": round(c, 3), "z": round(z, 2), "pct": pct})
    p = _rank(s, t, fq, 5, days)                                   # Q
    c, _ = _zchg(fsrc, pct, 6, t, fq, days)
    if p is None or c is None:
        return None, {}
    q = (p >= 0.5) + (c > 0)
    return d * (q - 1), {"rank5": round(p, 3), "chg6": round(c, 3), "q": int(q)}


def _streak(df, fn, src, fq, t) -> int | None:
    """6개월 변화 부호가 같은 쪽으로 몇 개월째(월말 기준, + = 상승 · − = 하락)."""
    fsrc, pct = _flowsrc(df, fn, src)
    ms = _months(t)[-60:]
    v = pd.Series([_asof(fsrc, m, "d" if pct else fq) for m in ms], index=ms, dtype=float)
    ch = (v / v.shift(6) - 1) if pct else v - v.shift(6)
    sg = np.sign(ch.dropna())
    if sg.empty or sg.iloc[-1] == 0:
        return None
    n = 0
    for x in sg[::-1]:
        if x != sg.iloc[-1]:
            break
        n += 1
    return int(n * sg.iloc[-1])


def grade(s: float | None, card=False) -> str:
    if s is None:
        return "B"
    hi, mid = (0.35, 0.10) if card else (0.5, 0.15)
    return "R" if s >= hi else ("A" if s >= mid else "G")


def check(df, label, fn, fq, d, unit, today):
    form, role, src, why = SPEC.get(label, (PENDING_FORM, "new", None, "검증 대기(9.337)"))
    s = _series(df, fn)
    out = {"label": label, "unit": unit, "dir": d, "freq": fq, "form": form, "form_txt": FORM_WORD(form), "role": role, "why": why}
    if s.empty:
        return {**out, "grade": "B", "why": why or "값 없음"}
    v, dt = float(s.iloc[-1]), s.index[-1]
    out.update({"value": round(v, 4), "value_txt": _fmt(v, unit), "date": str(dt.date())})
    if (today - dt).days > LABEL_STALE.get(label, STALE[fq]):
        return {**out, "grade": "B", "why": f"마지막 값 {dt:%m-%d}(오래됨)"}
    st = _streak(df, fn, src, fq, today)
    if st:
        out["streak"] = st
    if role in ("off", "new"):
        return {**out, "grade": None}
    sig, info = signal(df, fn, fq, d if d else 1, form, src, today, days=LABEL_STALE.get(label))
    out.update(info)
    if role == "sync":                                       # 동시 지표 — 방향 없이 흐름만
        return {**out, "grade": None}
    if sig is None:
        return {**out, "grade": "B"}
    out["signal"] = round(sig, 3)
    out["grade"] = grade(sig)
    return out


def card(df, no, title, desc, checks, today):
    cs = [check(df, *c, today) for c in checks]
    sc = [c["signal"] for c in cs if c["role"] in ("score", "aux") and "signal" in c]
    if not sc and any(c["role"] == "ref" for c in cs):          # 참고 카드(점수 밖) — 참고 체크 평균으로 등급만
        sc = [c["signal"] for c in cs if c["role"] == "ref" and "signal" in c]
    m = sum(sc) / len(sc) if sc else None
    g = grade(m, card=True) if m is not None else ("N" if cs and all(c["role"] in ("sync", "off") for c in cs) else "B")
    return {"no": no, "title": title, "desc": desc, "grade": g, "word": WORD[g], "mean": round(m, 3) if m is not None else None,
            "checks": cs, "n_scored": len(sc)}


def burden_at(df, t, lag) -> float | None:
    sig = []
    for _, _, _, cs in CARDS:
        for label, fn, fq, d, unit in cs:
            form, role, src, _ = SPEC[label]
            if role != "score":
                continue
            s, _ = signal(df, fn, fq, d, form, src, t, lag=lag, days=LABEL_STALE.get(label))
            if s is not None:
                sig.append(s)
    return float(np.mean(sig) * 50 + 50) if len(sig) >= 10 else None


def burden_hist(df, today) -> pd.Series:
    """2016 – 월말 흐름 부담(발표 지연 1개월) — 1/3 · 2/3 문턱용. 하루 한 번이라 느려도 됨."""
    ms = pd.date_range(HIST0, today, freq="ME")
    return pd.Series([burden_at(df, t, lag=True) for t in ms], index=ms, dtype=float).dropna()


def board(df):
    rows_out = []
    for name, rows in BOARD:
        R = []
        for label, src, fq, d, unit in rows:
            if isinstance(src, tuple) and len(src) == 3:
                s = (S(df, src[0]) / S(df, src[1])).dropna()
            elif isinstance(src, tuple):
                s = (S(df, src[0]) - S(df, src[1])).dropna()
            else:
                s = S(df, src)
            if len(s) < 6:
                continue
            s.index = pd.to_datetime(s.index)
            a, b = float(s.iloc[-6]), float(s.iloc[-1])
            ch = (b - a) * 100 if unit == "bp" else (b / a - 1) * 100
            arrow = "→" if d == 0 or abs(ch) < (2 if unit == "bp" else 0.5) else ("▲" if ch * d > 0 else "▼")
            R.append({"label": label, "from": round(a, 4), "to": round(b, 4), "chg": round(ch, 2), "unit": unit,
                      "from_date": str(s.index[-6].date()), "date": str(s.index[-1].date()), "arrow": arrow})
        up, dn = sum(r["arrow"] == "▲" for r in R), sum(r["arrow"] == "▼" for r in R)
        rows_out.append({"name": name, "rows": R, "summary": "악화 쪽" if up > dn else ("완화 쪽" if dn > up else "엇갈림")})
    return rows_out


def _load_hist() -> dict:
    try:
        with open(HIST_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _snap(r) -> dict:
    ks = r["cards"] + r.get("ref_cards", [])
    return {"burden": r["burden"], "level": r["level"], "alert": (r.get("credit_alert") or {}).get("on"),
            "cards": {k["no"]: [k["grade"], k["mean"], k["title"]] for k in ks},
            "checks": {c["label"]: c["signal"] for k in ks for c in k["checks"] if "signal" in c}}


def change_vs(r, hist: dict, today: str) -> dict | None:
    """직전 기록(오늘 전 가장 최근)과 비교 — 부담 점수 · 카드 등급 · 많이 움직인 체크(2026-10-20)."""
    prev_d = max((d for d in hist if d < today), default=None)
    if not prev_d:
        return None
    p, now = hist[prev_d], _snap(r)
    order = {"G": 0, "A": 1, "R": 2}
    cards = []
    for no, (g, m, title) in now["cards"].items():
        pg = p["cards"].get(no)
        if not pg:
            continue
        dm = None if m is None or pg[1] is None else round(m - pg[1], 3)
        if g != pg[0] or (dm is not None and abs(dm) >= 0.10):
            way = ("▲" if order.get(g, -1) > order.get(pg[0], -1) else "▼") if g != pg[0] else ("▲" if dm > 0 else "▼")
            cards.append({"no": no, "title": title, "from": pg[0], "to": g, "d_mean": dm, "arrow": way})
    dl = [(lab, round(s - p["checks"][lab], 3)) for lab, s in now["checks"].items()
          if s is not None and p["checks"].get(lab) is not None]
    dl.sort(key=lambda x: -abs(x[1]))
    b0 = p.get("burden")
    return {"prev_date": prev_d, "burden_prev": b0, "prev_alert": p.get("alert"),
            "d_burden": None if b0 is None or r["burden"] is None else round(r["burden"] - b0, 1),
            "cards": cards, "checks": [{"label": a, "d": b, "arrow": "▲" if b > 0 else "▼"} for a, b in dl[:6] if abs(b) >= 0.15]}


def events(hist: dict, days: int = 60) -> list[dict]:
    """기록끼리 카드 등급 · 부담 구간이 바뀐 날(추이 그림 표시용)."""
    ds = sorted(hist)
    out = []
    for a, b in zip(ds, ds[1:]):
        A, B = hist[a], hist[b]
        txt = []
        if A.get("level") != B.get("level") and B.get("level"):
            txt.append(f"부담 {A.get('level')}→{B.get('level')}")
        for no, (g, _, title) in B["cards"].items():
            if no in A["cards"] and A["cards"][no][0] != g and g in "GAR" and A["cards"][no][0] in "GAR":
                txt.append(f"{title.split('(')[0].strip()} {A['cards'][no][0]}→{g}")
        if txt:
            out.append({"date": b, "burden": B.get("burden"), "text": " · ".join(txt)})
    cut = (pd.Timestamp(ds[-1]) - pd.Timedelta(days=days)).strftime("%Y-%m-%d") if ds else ""
    return [e for e in out if e["date"] >= cut]


def divergence(r) -> str:
    """상태(부담 구간) vs 가격 반응(1주) — 기계 규칙 한 줄, 방향 판단 없음."""
    lv = r["level"]
    bd = {b["name"]: b["summary"] for b in r["board"]}
    m_, a_ = bd.get("매크로"), bd.get("AI")
    price = f"가격 반응 1주: 매크로 {m_} · AI {a_}"
    if lv == "높음" and m_ == "완화 쪽" and a_ != "악화 쪽":
        return f"괴리 — 상태는 부담 높음인데 {price}(가격이 먼저 풀리는 중)"
    if lv == "낮음" and "악화 쪽" in (m_, a_):
        return f"괴리 — 상태는 부담 낮음인데 {price}(가격이 먼저 반응)"
    if lv == "높음" and "악화 쪽" in (m_, a_):
        return f"같은 방향 — 상태 부담 높음 · {price}"
    if lv == "낮음" and m_ == "완화 쪽":
        return f"같은 방향 — 상태 부담 낮음 · {price}"
    return f"상태 부담 {lv} · {price}"


def strands(cards) -> list[dict]:
    sig = {c["label"]: c.get("signal") for k in cards for c in k["checks"]}
    out = []
    for name, labs in STRANDS:
        v = [sig[l] for l in labs if sig.get(l) is not None]
        if v:
            out.append({"name": name, "n": len(labs), "mean": round(float(np.mean(v)), 3), "grade": grade(float(np.mean(v)), card=True), "labels": labs})
    return out


# ── 쉬운 말로 짚기(2026-10-20 사용자 — "뭔가 변했을 때 어떤 지점이 위험한지 쉬운 말로") ──────────────────
# 기계 규칙 문장. 무엇이 바뀌었나 → 지금 위험한 지점 → 아직 번지지 않은 곳 → 다음에 볼 것. 오를지 · 내릴지는 말하지 않는다.
PLAIN = {   # 카드 번호 → (높을 때 쉬운 말, 다음에 볼 것)
    "1": ("물가 기대가 높게 머물러 금리가 내려오기 어려운 상태", "기대인플레(BEI · 5y5y)가 꺾이는지"),
    "2": ("시장 금리가 정책금리보다 높고 장기금리도 올라 돈 빌리는 비용이 쉽게 안 내려오는 상태", "미 2년 · 10년 금리가 내려오는지"),
    "3": ("신용 낮은 회사들의 자금 사정이 나빠지는 중", "하이일드 ETF가 국채보다 계속 약한지"),
    "4": ("은행이 대출을 조이고 금융 스트레스가 높은 편", "금융스트레스 지수 · 지역은행 주가"),
    "5": ("시장에 도는 돈(역레포 · 재무부 계좌 · 통화량)이 줄어드는 쪽", "역레포 · 재무부 계좌 변화"),
    "6": ("유럽 · 일본 금리나 신흥국 채권 쪽이 흔들리는 중", "일본 10년 · 신흥국 달러채"),
    "7": ("유가가 1년 중 높은 곳이라 물가와 금리를 다시 밀어 올릴 수 있는 자리", "브렌트 한 달 흐름이 꺾이는지"),
    "8": ("엔화 약세 · 한국 주식의 상대 약세 쪽", "엔/달러 · 한국 ÷ S&P500"),
    "9": ("변동성이 커지는 쪽 — 하루하루 흔들림이 큰 구간", "VIX · 채권 변동성(MOVE)"),
    "10": ("반도체 가격이 너무 빨리 올랐거나 시장보다 약해지는 중", "반도체 ÷ S&P500 흐름"),
    "11": ("국내 회사채 · 장단기 금리 쪽 부담", "회사채 AA− · BBB− 스프레드"),
    "12": ("미국 침체 확률 · 정책 불확실성이 높은 편", "침체 확률 · 불확실성 지수"),
    "15": ("AI 관련 가격(메모리 · TSMC · 전력 설비)이 약하고 오르는 종목이 적은 좁은 장", "대형 클라우드 4사가 시장보다 약해지는지 · 200일선 위 종목 비율"),
    "16": ("빚으로 AI에 투자한 기업(오라클 · 코어위브)과 신용 낮은 회사 쪽에서 돈 빌리기가 어려워지는 중",
           "우량 회사채(투자등급) 스프레드가 따라 오르는지 — 오르면 신용 전체로 번지는 것"),
}
GRADE_WORD = {"G": "낮음", "A": "높은 편", "R": "높음"}


def plain_points(r) -> dict:
    ks = r["cards"] + r.get("ref_cards", [])
    title = {k["no"]: k["title"].split("(")[0].strip() for k in ks}
    chk = {c["label"]: c for k in ks for c in k["checks"]}
    ca = r.get("credit_alert") or {}
    changed, risk, ok, watch = [], [], [], []
    ch = r.get("change") or {}
    db = ch.get("d_burden")
    if db is not None and abs(db) >= 3:
        changed.append(f"매크로 부담 점수가 직전({ch['prev_date'][5:]})보다 {abs(db):.0f}점 {'올랐습니다' if db > 0 else '내렸습니다'}.")
    for c in ch.get("cards", []):
        if c["from"] != c["to"] and c["to"] in GRADE_WORD and c["from"] in GRADE_WORD:
            changed.append(f"{title.get(c['no'], c['title'])}: {GRADE_WORD[c['from']]} → {GRADE_WORD[c['to']]}"
                           f"({'나빠짐' if c['arrow'] == '▲' else '나아짐'}).")
    prev_alert = ch.get("prev_alert")
    if ca.get("on") and prev_alert is False:
        changed.append("AI · 저신용 신용 경보가 새로 켜졌습니다.")
    elif not ca.get("on") and prev_alert:
        changed.append("AI · 저신용 신용 경보가 꺼졌습니다.")
    if (r.get("divergence") or "").startswith("괴리"):
        changed.append(r["divergence"].split(" — ")[1] + ".")
    if not changed:
        changed.append("직전과 크게 달라진 곳은 없습니다.")
    hot = [k for k in ks if k["grade"] == "R" and k["no"] in PLAIN]
    hot.sort(key=lambda k: (k["no"] != "16" or not ca.get("on"), -(k["mean"] or 0)))
    for k in hot[:4]:
        risk.append(f"{title[k['no']]} — {PLAIN[k['no']][0]}.")
        watch.append(f"{title[k['no']]}: {PLAIN[k['no']][1]}")
    ig = chk.get("투자등급 스프레드(IG, 넓은 신용 기준선)", {}).get("grade")
    if ca.get("on") and ig == "G":
        ok.append("우량 회사채(투자등급)는 평소 범위 — 신용 문제가 아직 약한 고리에 머물러 있습니다.")
    hy = chk.get("하이퍼스케일러 4 ÷ S&P500 한 달", {}).get("grade")
    if hy == "G" and any(k["no"] in ("15", "16") for k in hot):
        ok.append("대형 클라우드 4사(MSFT · META · GOOGL · AMZN)는 시장보다 강함 — 돈이 AI 전체에서 빠지는 건 아닙니다.")
    calm = [title[k["no"]] for k in r["cards"] if k["grade"] == "G" and k["no"] in PLAIN and not (k["no"] == "3" and ca.get("on"))]
    if ca.get("on") and any(k["no"] == "3" and k["grade"] == "G" for k in r["cards"]):
        ok.append("넓은 하이일드 ETF로 보는 '약한 기업 신용' 카드는 낮음 — 압박이 특정 기업 · 최저 신용(CCC)에 몰려 있다는 뜻입니다.")
    if calm:
        ok.append(f"{' · '.join(calm[:4])} 쪽은 부담 낮음입니다.")
    return {"changed": changed[:4], "risk": risk, "ok": ok[:3], "watch": watch[:4]}


def record(r) -> None:
    """오늘 결과를 data/checklist_hist.json에 한 줄(같은 날 다시 돌면 덮어씀, 최근 400개). export_exchange · main만 부른다."""
    h = _load_hist()
    h[r["made_at"][:10]] = _snap(r)
    h = dict(sorted(h.items())[-400:])
    with open(HIST_PATH, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False)


def build() -> dict:
    df = pd.read_csv(os.path.join(DATA, "macro_ext.csv"), index_col=0, parse_dates=True)
    today = pd.Timestamp(datetime.now(KST).date())
    try:
        df["x_breadth"] = us_breadth()
    except Exception:  # noqa: BLE001 — 없으면 그 체크만 자료 부족
        pass
    df["x_hyper"], df["x_power"] = basket_idx(HYPER)(df), basket_idx(POWER)(df)
    cards = [card(df, *c, today) for c in CARDS]
    ref_cards = [card(df, *c, today) for c in REF_CARDS]
    aux = [card(df, *c, today) for c in AUX]
    pending = [card(df, *c, today) for c in PENDING]
    raw_now = burden_at(df, today, lag=False)
    raw_hist = burden_hist(df, today)
    # 2026-10-15 사용자: 원점수가 사실상 30 – 70 사이라 구분이 약함 → 2016 – 월말 원점수의 하위 5% · 상위 5%를 잘라 그 사이를 0 – 100으로 늘림
    # (순서 · 구간은 그대로, 보기 척도만 바꿈). 원점수(raw)도 함께 남긴다.
    a, b = (float(raw_hist.quantile(0.05)), float(raw_hist.quantile(0.95))) if len(raw_hist) >= 24 else (0.0, 100.0)
    k = 100 / (b - a) if b > a else 1.0
    sc = lambda v: None if v is None else float(np.clip((v - a) * k, 0, 100))
    now, hist = sc(raw_now), raw_hist.map(sc)
    lo, hi = (float(hist.quantile(1 / 3)), float(hist.quantile(2 / 3))) if len(hist) >= 24 else (None, None)
    level = None if now is None or lo is None else ("높음" if now >= hi else ("낮음" if now <= lo else "중간"))
    prev = hist.asof(today - pd.DateOffset(months=6)) if len(hist) >= 7 else None   # 6개월 전 월말(9.336: 방향은 3개월보다 6개월 변화가 정보 있음)
    prev = None if prev is None or pd.isna(prev) else float(prev)
    sync = [c for k_ in cards for c in k_["checks"] if c["role"] == "sync"]
    cnt = {g: sum(k_["grade"] == g for k_ in cards) for g in ("G", "A", "R", "B")}
    r = _assemble(df, today, cards, aux, pending, raw_now, raw_hist, a, b, k, sc, now, hist, lo, hi, level, prev, sync, cnt)
    r["ref_cards"] = ref_cards
    r["credit_alert"] = credit_alert(ref_cards)
    r["strands"] = strands(cards)
    r["divergence"] = divergence(r)
    h = _load_hist()
    r["change"] = change_vs(r, h, r["made_at"][:10])
    h2 = dict(h)
    h2[r["made_at"][:10]] = _snap(r)
    r["events"] = events(h2)
    r["plain"] = plain_points(r)
    return r


def _assemble(df, today, cards, aux, pending, raw_now, raw_hist, a, b, k, sc, now, hist, lo, hi, level, prev, sync, cnt) -> dict:
    return {"made_at": datetime.now(KST).isoformat(timespec="seconds"), "data_to": str(df.index.max().date()),
            "burden": round(now, 1) if now is not None else None, "level": level,
            "cut": [round(lo, 1), round(hi, 1)] if lo is not None else None, "burden_6m_ago": round(prev, 1) if prev is not None else None,
            "neutral": round(sc(50.0), 1), "scale_k": round(k, 4),
            "raw": {"burden": round(raw_now, 1) if raw_now is not None else None, "p5": round(a, 1), "p95": round(b, 1),
                    "range": [round(float(raw_hist.min()), 1), round(float(raw_hist.max()), 1)] if len(raw_hist) else None},
            "hist": {str(d.date()): round(v, 1) for d, v in hist.tail(24).items()},
            "count": cnt, "board": board(df), "cards": cards, "aux": aux, "pending": pending, "sync": sync,
            "rule": ("매크로 부담 점수 = 원점수(점수 체크 신호 평균 × 50 + 50)의 2016 – 월말 하위 5% · 상위 5%를 0 · 100으로 늘린 값, 낮을수록 좋음. 체크 형태 · 방향은 VM-SPC Core 9.334 · 9.335 권고(약함 개선안). "
                     "높음 · 낮음 = 2016 – 월말 흐름 부담의 상위 · 하위 1/3. 카드 · 체크 등급은 보기용(검증 아님). 사람 판단 없음")}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    r = build()
    with open(os.path.join(DATA, "checklist.json"), "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    record(r)
    print(f"흐름 부담 {r['burden']} ({r['level']}, 문턱 {r['cut']}, 6개월 전 {r['burden_6m_ago']}) · 카드 "
          + " · ".join(f"{k}{v}" for k, v in r["count"].items()))
    for b in r["board"]:
        print(f"  [{b['name']}] {b['summary']}: " + " · ".join(f"{x['label']} {x['arrow']}" for x in b["rows"]))
    print("  " + r["divergence"])
    if r["change"]:
        ch = r["change"]
        print(f"  직전({ch['prev_date']}) 대비 부담 {ch['d_burden']} · 카드 " + " · ".join(f"{c['title']} {c['from']}→{c['to']}{c['arrow']}" for c in ch["cards"]))
    for k in r["cards"] + r["ref_cards"] + r["aux"]:
        print(f"  {k['no']:>2}. {k['title']} — {k['word']} ({k['mean']})  "
              + " | ".join(f"{c['label']}[{c['form']}{'' if c['role'] in ('score', 'aux') else '·' + c['role']}] "
                           f"{c.get('signal', '')}{('(' + c['grade'] + ')') if c.get('grade') else ''}" for c in k["checks"]))
    print("  동시 지표: " + " · ".join(f"{c['label']} {c.get('chg', '')}% (z {c.get('z', '')})" for c in r["sync"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
