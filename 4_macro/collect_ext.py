"""매크로 확장 수집 — 체크리스트(checklist.py)용 FRED · yfinance 시리즈를 data/macro_ext.csv(일별 누적, 2000 – )에 쌓는다.
2026-10-15 사용자 결정: "FRED나 야후파이낸스에서 가져올 수 있는 데이터는 전부 가져와서 체크리스트를 만들 수 있게".

  python collect_ext.py            # 처음엔 2000-01 – 전부, 그 뒤엔 최근 400일만 다시 받아 합침
  python collect_ext.py --full     # 처음부터 다시

- 기존 macro_daily.csv(리포트 숫자 · 분기 국면)는 건드리지 않는다. 같은 지표가 겹쳐도 여기 따로 둔다(원천 · 칸 이름 고정).
- 월 · 주 단위 FRED 시리즈는 발표 날짜(관측일)에 값이 찍힌다 — 체크리스트는 "마지막 값 + 그 날짜"로 쓴다.
- FRED 키는 평소 수집과 같은 방식(월간_매크로섹터분석의 FRED_API_KEY, 이 폴더 .env). 실패한 시리즈는 건너뛰고 옛 값은 유지.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

import 월간_매크로섹터분석 as m

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PATH = os.path.join(DATA, "macro_ext.csv")
START = "2000-01-01"   # 2026-10-15: 10년 창 순위 · 흐름 분석용 기준선(평가 표본은 2016 – 그대로)

# 칸 이름: (원천 코드, 설명) — 칸 이름 앞 f_ = FRED, y_ = yfinance
FRED = {
    # 금리 · 정책
    "f_dgs3mo": ("DGS3MO", "미 3개월 국채"), "f_dgs2": ("DGS2", "미 2년"), "f_dgs5": ("DGS5", "미 5년"),
    "f_dgs10": ("DGS10", "미 10년"), "f_dgs30": ("DGS30", "미 30년"),
    "f_fedup": ("DFEDTARU", "연준 목표 상단"), "f_effr": ("EFFR", "EFFR"), "f_sofr": ("SOFR", "SOFR"), "f_iorb": ("IORB", "IORB"),
    "f_t10y2y": ("T10Y2Y", "10Y-2Y"), "f_t10y3m": ("T10Y3M", "10Y-3M"),
    "f_tp10": ("THREEFYTP10", "10년 기간 프리미엄(김-라이트)"),
    # 실질금리 · 기대인플레 · 물가(월)
    "f_real10": ("DFII10", "10년 실질금리(TIPS)"), "f_real5": ("DFII5", "5년 실질금리"),
    "f_bei10": ("T10YIE", "10년 기대인플레(BEI)"), "f_bei5": ("T5YIE", "5년 BEI"), "f_5y5y": ("T5YIFR", "5y5y 선도 기대인플레"),
    "f_mich": ("MICH", "미시간 1년 기대인플레(월)"), "f_cpi": ("CPIAUCSL", "CPI(월)"), "f_core_cpi": ("CPILFESL", "근원 CPI(월)"),
    "f_core_pce": ("PCEPILFE", "근원 PCE(월)"), "f_umcsent": ("UMCSENT", "미시간 심리(월)"),
    # 신용
    "f_hy": ("BAMLH0A0HYM2", "HY OAS"), "f_bb": ("BAMLH0A1HYBB", "BB OAS"), "f_b": ("BAMLH0A2HYB", "B OAS"),
    "f_ccc": ("BAMLH0A3HYC", "CCC 이하 OAS"), "f_ig": ("BAMLC0A0CM", "IG OAS"), "f_bbb": ("BAMLC0A4CBBB", "BBB OAS"),
    # 금융여건 · 유동성 · 대출
    "f_nfci": ("NFCI", "시카고 연준 금융여건(주)"), "f_stlfsi": ("STLFSI4", "세인트루이스 금융스트레스(주)"),
    "f_walcl": ("WALCL", "연준 총자산(주)"), "f_rrp": ("RRPONTSYD", "역레포 잔고"), "f_tga": ("WTREGEN", "재무부 TGA(주)"),
    "f_m2": ("M2SL", "M2(월)"), "f_sloos_l": ("DRTSCILM", "SLOOS 대기업 C&I 긴축(분기)"),
    "f_sloos_s": ("DRTSCIS", "SLOOS 중소기업 C&I 긴축(분기)"),
    # 고용 · 성장
    "f_icsa": ("ICSA", "신규 실업수당 청구(주)"), "f_unrate": ("UNRATE", "실업률(월)"), "f_payems": ("PAYEMS", "비농업 고용(월)"),
    "f_indpro": ("INDPRO", "산업생산(월)"),
    # 에너지 · 환율 · 해외 금리(월)
    "f_brent": ("DCOILBRENTEU", "브렌트 현물"), "f_dtwex": ("DTWEXBGS", "광의 달러지수"),
    "f_de10": ("IRLTLT01DEM156N", "독일 10년(월)"), "f_fr10": ("IRLTLT01FRM156N", "프랑스 10년(월)"),
    "f_it10": ("IRLTLT01ITM156N", "이탈리아 10년(월)"), "f_jp10": ("IRLTLT01JPM156N", "일본 10년(월)"),
    "f_kr10": ("IRLTLT01KRM156N", "한국 10년(월)"), "f_gb10": ("IRLTLT01GBM156N", "영국 10년(월)"),
    # 2026-10-15 추가(경기 · 침체 · 불확실성 · 중국 · 한국 OECD) — OECD 선행지수(…LOLITONOSTSAM)는 FRED가 2024-01에 멈춰 뺌
    "f_sahm": ("SAHMREALTIME", "샴 규칙 실시간(월)"), "f_recprob": ("RECPROUSM156N", "미 침체 확률(월)"),
    "f_epu": ("USEPUINDXD", "미 경제정책 불확실성(일)"), "f_gepu": ("GEPUCURRENT", "글로벌 경제정책 불확실성(월)"),
    "f_cn_imp": ("XTIMVA01CNM667S", "중국 수입(월)"), "f_cn_exp": ("XTEXVA01CNM667S", "중국 수출(월)"),
    "f_kr_unemp": ("LRHUTTTTKRM156S", "한국 실업률(월)"), "f_kr_bci": ("BSCICP02KRM460S", "한국 기업심리(OECD, 월)"),
    "f_permit": ("PERMIT", "미 건축허가(월)"), "f_cc_delinq": ("DRCCLACBS", "미 신용카드 연체율(분기)"),
}
# 한국은행 ECOS — (통계표, 주기, 항목) · 관세청 반도체 수출(HS 8542 + 8541, 월, 달러)
ECOS = {
    "k_base": ("722Y001", "D", "0101000", "한국 기준금리"), "k_ktb3": ("817Y002", "D", "010200000", "국고 3년"),
    "k_ktb10": ("817Y002", "D", "010210000", "국고 10년"), "k_cd91": ("817Y002", "D", "010502000", "CD 91일"),
    "k_cp91": ("817Y002", "D", "010503000", "CP 91일"),
    "k_aa": ("817Y002", "D", "010300000", "회사채 3년 AA−"), "k_bbb": ("817Y002", "D", "010320000", "회사채 3년 BBB−"),
    "k_cpi": ("901Y009", "M", "0", "한국 소비자물가지수(월)"),
    "k_lead": ("901Y067", "M", "I16E", "한국 선행지수 순환변동치(월)"), "k_coin": ("901Y067", "M", "I16D", "한국 동행지수 순환변동치(월)"),
    "k_exp": ("901Y118", "M", "T002", "한국 수출금액(월)"), "k_imp": ("901Y118", "M", "T004", "한국 수입금액(월)"),
    # 2026-10-15 외국인 시선 해설(원화 괴리의 원인 후보 근거) — 국제수지 금융계정(백만 달러, + = 순유출입 증가) · 외환보유액
    "k_ca": ("301Y013", "M", "000000", "경상수지(월)"),
    "k_bop_fstk": ("301Y013", "M", "BOPF22100000", "외국인 국내 주식투자(증권투자 부채 · 주식, 월)"),
    "k_bop_rstk": ("301Y013", "M", "BOPF21100000", "내국인 해외 주식투자(증권투자 자산 · 주식, 월)"),
    "k_bop_oia": ("301Y013", "M", "BOPF41000000", "기타투자 자산(거주자 해외 예금 등, 월)"),
    "k_fxres": ("732Y001", "M", "99", "외환보유액 합계(월)"),
    # 증시 주변 자금 · 시장 규모(2026-10-15, 국장 흐름 아이템 검토 — 9.344)
    "k_deposit": ("901Y056", "M", "S23A", "투자자 예탁금(월)"), "k_margin": ("901Y056", "M", "S23E", "신용융자 잔고(월)"),
    "k_misu": ("901Y056", "M", "S23D", "위탁매매 미수금(월)"),
    "k_kospi_cap": ("802Y001", "D", "0183000", "유가증권시장 시가총액"), "k_kospi_tv": ("802Y001", "D", "0088000", "유가증권시장 거래대금"),
    "k_kosdaq_tv": ("802Y001", "D", "0091000", "코스닥 거래대금"),
}
# 금융투자협회 FreeSIS 증시 주변 자금 일별(2026-10-22 사용자 — 한국은행 월 단위 대신 일별, 1998 – , 단위 백만 원, 다음 영업일 공표)
# 웹 화면이 쓰는 JSON 주소(인증 없음, 화면을 한 번 열어 세션 쿠키를 받아야 함). 매번 전체 기간을 받아도 1초 안쪽.
FREESIS_PAGE = "https://freesis.kofia.or.kr/stat/FreeSIS.do?parentDivId=MSIS10000000000000&serviceId=STATSCU0100000060"
FREESIS_API = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"
FREESIS = {
    "STATSCU0100000060BO": {"TMPV2": ("s_deposit", "투자자 예탁금"), "TMPV3": ("s_deriv_dep", "장내파생 거래예수금"),
                            "TMPV4": ("s_rp", "대고객 RP 매도잔고"), "TMPV5": ("s_unpaid", "위탁매매 미수금"),
                            "TMPV6": ("s_forced", "미수금 대비 실제 반대매매금액"), "TMPV7": ("s_forced_pct", "미수금 대비 반대매매 비중(%)")},
    "STATSCU0100000070BO": {"TMPV2": ("s_credit", "신용거래융자 전체"), "TMPV3": ("s_credit_kospi", "신용거래융자 유가증권"),
                            "TMPV4": ("s_credit_kosdaq", "신용거래융자 코스닥"), "TMPV9": ("s_collat", "예탁증권 담보융자")},
    # 2026-10-23 사용자("받을 수 있으면 받아서 검증") — 시장별 시가총액 · 외국인 보유 시가총액 · 비중(KRX 원천, 일별, 백만 원 · %)
    "STATSCU0100000020BO": {"TMPV5": ("s_kospi_mcap", "유가증권 시가총액"), "TMPV6": ("s_kospi_fmcap", "유가증권 외국인 보유 시가총액"),
                            "TMPV7": ("s_kospi_fpct", "유가증권 외국인 보유 비중(%)")},
    "STATSCU0100000030BO": {"TMPV5": ("s_kosdaq_mcap", "코스닥 시가총액"), "TMPV6": ("s_kosdaq_fmcap", "코스닥 외국인 보유 시가총액"),
                            "TMPV7": ("s_kosdaq_fpct", "코스닥 외국인 보유 비중(%)")},
}
CUSTOMS = {"c_semi_exp": (("8542", "8541"), "한국 반도체 수출(HS 8542 · 8541, 월)")}
YF = {
    # 금리 · 변동성
    "y_irx": ("^IRX", "미 13주"), "y_fvx": ("^FVX", "미 5년"), "y_tnx": ("^TNX", "미 10년"), "y_tyx": ("^TYX", "미 30년"),
    "y_vix": ("^VIX", "VIX"), "y_vix3m": ("^VIX3M", "VIX 3개월"), "y_vvix": ("^VVIX", "VVIX"), "y_move": ("^MOVE", "MOVE(채권 변동성)"), "y_skew": ("^SKEW", "SKEW"),
    # 원자재 · 크립토
    "y_brent": ("BZ=F", "브렌트 선물"), "y_wti": ("CL=F", "WTI 선물"), "y_ho": ("HO=F", "난방유(디젤) 선물"),
    "y_ng": ("NG=F", "천연가스"), "y_gold": ("GC=F", "금"), "y_silver": ("SI=F", "은"), "y_copper": ("HG=F", "구리"),
    "y_btc": ("BTC-USD", "비트코인"), "y_eth": ("ETH-USD", "이더리움"),
    # 환율
    "y_dxy": ("DX-Y.NYB", "달러인덱스"), "y_krw": ("KRW=X", "원/달러"), "y_jpy": ("JPY=X", "엔/달러"),
    "y_eur": ("EURUSD=X", "유로/달러"), "y_cny": ("CNY=X", "위안/달러"), "y_twd": ("TWD=X", "대만달러/달러"),
    # 국가 · 지수 ETF
    "y_spy": ("SPY", "S&P500"), "y_rsp": ("RSP", "S&P500 동일가중"), "y_qqq": ("QQQ", "나스닥100"), "y_iwm": ("IWM", "러셀2000"),
    "y_ks11": ("^KS11", "코스피"), "y_n225": ("^N225", "닛케이225"), "y_twii": ("^TWII", "대만 가권"), "y_hsi": ("^HSI", "항셍"),
    "y_sse": ("000001.SS", "상해 종합"), "y_ewh": ("EWH", "홍콩"), "y_mchi": ("MCHI", "중국"), "y_ewy": ("EWY", "한국"), "y_ewt": ("EWT", "대만"), "y_ewj": ("EWJ", "일본"), "y_fxi": ("FXI", "중국"),
    "y_inda": ("INDA", "인도"), "y_ewz": ("EWZ", "브라질"), "y_vgk": ("VGK", "유럽"), "y_eem": ("EEM", "신흥국"),
    # 섹터 · 반도체
    "y_xlk": ("XLK", "기술"), "y_xlp": ("XLP", "필수소비"), "y_xlf": ("XLF", "금융"), "y_xle": ("XLE", "에너지"),
    "y_xlu": ("XLU", "유틸리티"), "y_soxx": ("SOXX", "반도체"), "y_smh": ("SMH", "반도체(SMH)"), "y_mu": ("MU", "마이크론"),
    "y_nvda": ("NVDA", "엔비디아"),
    # 채권 · 신용 ETF
    "y_tlt": ("TLT", "미 장기채"), "y_ief": ("IEF", "미 7-10년채"), "y_shy": ("SHY", "미 1-3년채"), "y_hyg": ("HYG", "하이일드"),
    "y_lqd": ("LQD", "투자등급"), "y_bkln": ("BKLN", "레버리지론"), "y_bizd": ("BIZD", "BDC"), "y_kre": ("KRE", "지역은행"),
    "y_emb": ("EMB", "신흥국 달러채"),
    # 2026-10-20 AI 투자 · 인프라 참고 카드(checklist.py 카드 15, 점수 밖) · 연준 경로
    "y_crwv": ("CRWV", "코어위브"), "y_orcl": ("ORCL", "오라클"), "y_tsm": ("TSM", "TSMC ADR"), "y_dram": ("DRAM", "메모리 ETF"),
    "y_msft": ("MSFT", "마이크로소프트"), "y_meta": ("META", "메타"), "y_googl": ("GOOGL", "알파벳"), "y_amzn": ("AMZN", "아마존"),
    "y_vrt": ("VRT", "버티브"), "y_ceg": ("CEG", "컨스텔레이션 에너지"), "y_vst": ("VST", "비스트라"),
    "y_zq": ("ZQ=F", "연방기금 선물(가까운 달)"),
}


def _norm(s: pd.Series) -> pd.Series:
    s = s.dropna()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize() if getattr(s.index, "tz", None) else pd.to_datetime(s.index).normalize()
    return s.astype(float)


def _ecos(stat: str, cyc: str, item: str, start: str) -> pd.Series:
    """ECOS StatisticSearch — 일별은 5년씩 나눠 받음(한 번에 1만 행). 키가 URL에 있어 오류 원문은 찍지 않는다."""
    key = os.environ.get("ECOS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ECOS_API_KEY 없음")
    s0, now = pd.Timestamp(start), pd.Timestamp(datetime.now().date())
    spans = []
    if cyc == "D":
        a = s0
        while a <= now:
            b = min(a + pd.DateOffset(years=5) - pd.Timedelta(days=1), now)
            spans.append((a.strftime("%Y%m%d"), b.strftime("%Y%m%d")))
            a = b + pd.Timedelta(days=1)
    else:
        spans.append((s0.strftime("%Y%m"), now.strftime("%Y%m")))
    out = {}
    for a, b in spans:
        r = m.requests.get(f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/10000/{stat}/{cyc}/{a}/{b}/{item}", timeout=40)
        r.encoding = "utf-8"
        for x in r.json().get("StatisticSearch", {}).get("row", []):
            t = x["TIME"]
            d = pd.Timestamp(t) if cyc == "D" else pd.Timestamp(f"{t[:4]}-{t[4:6]}-01")
            out[d] = float(x["DATA_VALUE"])
    return pd.Series(out, dtype=float).sort_index()


def _customs(hs_list: tuple, start: str) -> pd.Series:
    """관세청 품목별 수출입(getItemtradeList) — 한 번에 1년까지라 해마다 1 – 12월로 나눠 받아 HS를 더함(달러)."""
    import xml.etree.ElementTree as ET
    key = getattr(m, "CUSTOMS_ENCODING_KEY", None) or os.environ.get("CUSTOMS_API_KEY", "")
    if not key:
        raise RuntimeError("CUSTOMS 키 없음")
    tot: dict[pd.Timestamp, float] = {}
    for y in range(pd.Timestamp(start).year, datetime.now().year + 1):
        for hs in hs_list:
            url = (f"https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList?serviceKey={key}"
                   f"&strtYymm={y}01&endYymm={y}12&hsSgn={hs}&numOfRows=500&pageNo=1&type=xml")
            res = m.requests.get(url, timeout=40)
            root = ET.fromstring(res.content)
            for it in root.findall(".//item"):
                yr = (it.findtext("year") or "").replace(".", "")
                if len(yr) != 6 or not yr.isdigit():
                    continue
                d = pd.Timestamp(f"{yr[:4]}-{yr[4:]}-01")
                tot[d] = tot.get(d, 0.0) + float(it.findtext("expDlr") or 0)
    s = pd.Series(tot, dtype=float).sort_index()
    return s[s > 0]


def _freesis() -> dict[str, pd.Series]:
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Referer": FREESIS_PAGE})
    s.get(FREESIS_PAGE, timeout=30)
    out = {}
    for obj, cols in FREESIS.items():
        body = {"dmSearch": {"tmpV40": "1000000", "tmpV41": "1", "tmpV1": "D", "tmpV45": "19980101",
                             "tmpV46": datetime.now().strftime("%Y%m%d"), "OBJ_NM": obj}}
        rows = s.post(FREESIS_API, json=body, timeout=60).json()["ds1"]
        idx = pd.to_datetime([r["TMPV1"] for r in rows], format="%Y%m%d")
        for k, (col, _) in cols.items():
            out[col] = _norm(pd.Series([r.get(k) for r in rows], index=idx, dtype=float))
    return out


def collect(start: str) -> tuple[pd.DataFrame, list[str]]:
    new, fail = {}, []
    try:
        new.update(_freesis())
    except Exception as e:  # noqa: BLE001
        fail.append(f"FreeSIS({type(e).__name__})")
    for col, (stat, cyc, item, _) in ECOS.items():
        try:
            new[col] = _norm(_ecos(stat, cyc, item, start))
        except Exception as e:  # noqa: BLE001
            fail.append(f"ECOS {stat}/{item}({type(e).__name__})")
    for col, (hs, _) in CUSTOMS.items():
        try:
            new[col] = _norm(_customs(hs, start))
        except Exception as e:  # noqa: BLE001
            fail.append(f"관세청 {'+'.join(hs)}({type(e).__name__})")
    if m.FRED_AVAILABLE:
        fred = m.Fred(api_key=m.FRED_API_KEY)
        for col, (sid, _) in FRED.items():
            try:
                new[col] = _norm(fred.get_series(sid, observation_start=start))
            except Exception as e:  # noqa: BLE001 — 키가 URL에 있어 원문은 찍지 않음
                fail.append(f"FRED {sid}({type(e).__name__})")
    else:
        fail.append("FRED 키 없음")
    tick = {v[0]: k for k, v in YF.items()}
    try:
        raw = yf.download(list(tick), start=start, progress=False, auto_adjust=True, group_by="column", threads=True)
        close = raw["Close"]
        for t, col in tick.items():
            if t in close and close[t].notna().any():
                new[col] = _norm(close[t])
            else:
                fail.append(f"yf {t}")
    except Exception as e:  # noqa: BLE001
        fail.append(f"yfinance 전체({type(e).__name__}: {e})")
    return pd.DataFrame(new), fail


SHARE_ETFS = ["EWY", "EWT", "EEM", "QQQ", "EWZ", "INDA", "EWJ", "FXI", "VGK", "SPY", "SOXX", "SMH"]


def snap_etf_shares() -> int:
    """ETF 주식 수 · 기준가 · 순자산 스냅샷을 data/etf_shares.csv에 하루 한 줄씩 쌓는다(2026-10-15 — 자금 유출입 = 주식 수 변화 × 기준가).
    yfinance가 과거 주식 수를 주지 않아 오늘부터 쌓임. 같은 날 다시 돌면 덮어씀."""
    path = os.path.join(DATA, "etf_shares.csv")
    today = datetime.now().strftime("%Y-%m-%d")
    rows = []
    for t in SHARE_ETFS:
        try:
            i = yf.Ticker(t).info
            rows.append({"date": today, "ticker": t, "shares": i.get("sharesOutstanding"), "nav": i.get("navPrice"),
                         "price": i.get("regularMarketPreviousClose") or i.get("previousClose"), "aum": i.get("totalAssets")})
        except Exception as e:  # noqa: BLE001
            print(f"  ETF 주식 수 {t} 실패: {type(e).__name__}")
    if not rows:
        return 0
    new = pd.DataFrame(rows)
    if os.path.exists(path):
        old = pd.read_csv(path)
        new = pd.concat([old[old.date != today], new])
    new.sort_values(["date", "ticker"]).to_csv(path, index=False, encoding="utf-8")
    return len(rows)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        print(f"ETF 주식 수 스냅샷 {snap_etf_shares()}개")
    except Exception as e:  # noqa: BLE001
        print(f"ETF 주식 수 스냅샷 실패: {type(e).__name__}")
    full = "--full" in sys.argv or not os.path.exists(PATH)
    start = START if full else (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
    add, fail = collect(start)
    if os.path.exists(PATH) and not full:
        old = pd.read_csv(PATH, index_col=0, parse_dates=True)
        new_cols = [c for c in YF if c not in old.columns]       # 새로 더한 yfinance 칸은 처음부터 받음(2026-10-20)
        if new_cols:
            raw = yf.download([YF[c][0] for c in new_cols], start=START, progress=False, auto_adjust=True, group_by="column")["Close"]
            extra = {c: _norm(raw[YF[c][0]]) for c in new_cols if YF[c][0] in raw and raw[YF[c][0]].notna().any()}
            if extra:
                add = add.drop(columns=list(extra), errors="ignore").join(pd.DataFrame(extra), how="outer")
        df = add.combine_first(old)          # 새로 받은 값 우선(FRED 수정치 반영), 못 받은 옛 값은 유지
    else:
        df = add
    sis = [c for v in FREESIS.values() for c, _ in v.values()]
    cols = [c for c in list(FRED) + list(YF) + list(ECOS) + list(CUSTOMS) + sis if c in df.columns]
    df = df.sort_index()[cols].round(5)
    df.index = pd.to_datetime(df.index).date
    df.index.name = "date"
    os.makedirs(DATA, exist_ok=True)
    df.to_csv(PATH, encoding="utf-8")
    print(f"macro_ext.csv: {len(cols)}칸 · {df.index.min()} – {df.index.max()} · 받은 칸 {add.shape[1]}")
    if fail:
        print("실패: " + ", ".join(fail))
    return 0 if add.shape[1] else 1


if __name__ == "__main__":
    sys.exit(main())
