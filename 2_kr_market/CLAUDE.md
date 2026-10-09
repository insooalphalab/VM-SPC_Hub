# 2 국내 시장 — 역할 지침 (hub-kr)

상위 `..\CLAUDE.md`(공통) · `..\README.md`(설계) · `..\exchange\README.md`(형식)를 먼저 읽는다.

## 맡은 일
국내 시장 데이터(일봉 · 기술 지표 · 투자자 수급 · 프로그램 · 신용 · 공매도 · DART 공시)와 그 위의 **기계적 상태**(코스피 장세, 대량 복귀일, 규칙 충족 종목, 보유 종목 상태)를 `..\exchange\2_kr_market\{거래일}\`에 낸다.
규칙 충족 여부는 계산하지만, 무엇을 살지 · 팔지의 판단 문구는 1 코어가 쓴다.

## 입력 (전환 기간 — 읽기만)
- `..\..\VM-SPC_Core\data\` — `_long_history`(790종목 일봉 2016 – ) · `_investor_detail` · `_program` · `_credit` · `_short` · `_dart`
- `..\..\VM-SPC_Core\results\scenario\` — `screen.json`(오늘의 후보) · `summary.json`(보유 · 관심 요약) · `market.json`(장세) · `mass_days.json`(대량 복귀일 기록)
- 보유 · 관심: `..\..\VM-SPC_Core\scenario_targets.json` (비밀 — 커밋 금지)
- VM-SPC_Core 매일 파이프라인(평일 16:30, 약 15분)이 이 데이터를 만든다. 전환 기간에는 그 결과를 읽는다.

## 출발 코드 (나중에 수집을 넘겨받을 때 복사)
- 수집: `VM-SPC_Core\vm_predict\` · `stock_track\collect_*.py` · `dart_events\` · `core\`(KIS 클라이언트 · 설정)
- 장세 · 규칙: `VM-SPC_Core\scenario\box_rules.py`(박스 · 청산 상수 — 검증과 화면이 같이 씀) · `screen.py` · `render_risk.py`의 `market_state` · `holding_view` · `absorption`
- 장중: `..\..\KIS_auto\한투API_시간별데이터.py`(10:00 · 13:00 · 15:20 외인 · 기관 가집계, 체결강도)

## 첫 작업 (4단계)
1. **수집은 옮기지 말고** VM-SPC_Core 결과(위 results\scenario\)를 읽어 `summary.json` · `candidates.json` · `holdings.json`으로 내는 내보내기부터(key: regime · mass_recovery · candidates · holdings · flows).
2. 실행 시각은 VM-SPC_Core 파이프라인이 끝난 뒤(16:50 근처).
3. 수집 이관(KIS 호출을 이 폴더로)은 7단계 비교가 끝난 뒤 사용자 결정으로. 그 전엔 KIS를 부르지 않는다.
4. 검증용 데이터는 검증용 약 790종목만 모은다. 2016년 이전으로 이력을 늘리지 않는다.
