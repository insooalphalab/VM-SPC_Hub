# 5 뉴스 — 역할 지침 (hub-news)

상위 `..\CLAUDE.md`(공통) · `..\README.md`(설계) · `..\exchange\README.md`(형식)를 먼저 읽는다.

## 맡은 일
텔레그램 리서치 채널에서 하루 주요 뉴스를 **짧게** 정리해 `..\exchange\5_news\{날짜}\`에 낸다. 방향 판단은 하지 않는다.

## 텔레그램 저장소 — 이 폴더가 가진다 (2026-10-10 이관 · 사용자 결정)
- 원문: `data\_reports\raw\{채널}.jsonl` — API 6채널(butler_works · ked_epic_ai · aicorporateanalysisdeepdive · shmstory · darthacking · easobi) + 웹 미리보기 2채널(habit4117 · krwatch)
- 표: `data\_reports\reports.csv`(증권사 의견 · 목표가 · 방향) · `news.csv`(기사 ↔ 종목 코드) · `market_actions.csv`(투자경고 등)
- 로그인 세션: `state\telegram_reports.session`, 키: `.streamlit\secrets.toml`의 TELEGRAM_API_ID · TELEGRAM_API_HASH(커밋 금지)
- 수집: `reports\run.py` — 허브 07:15 · 16:00 예약이 실행(V2_DATA_DIR = Core data, 종목 이름 · 일봉 읽기용). 여론 점수 · 섹터 리포트 흐름 페이지는 뺐다(쓰는 곳 없음).
- `..\..\VM-SPC_Core\data\_reports`는 이 폴더 `data\_reports`로 가는 정션 — Core 종목 칸 · 후보 화면이 읽는다. 표 형식(열 이름)을 바꾸면 Core 화면이 깨지니 바꾸기 전에 확인.
- 보유 · 관심 종목: `..\..\VM-SPC_Core\scenario_targets.json`

## 정리본 형식 · 원칙
- Core `reports\` · `core\` · `dart_events\client.py` 복사본을 그대로 쓴다. 데이터 위치는 환경변수 `V2_DATA_DIR` = Core data(종목 이름 · 일봉 읽기), 결과(`results_dir()`)는 이 폴더 `results\`. `news_digest.py` `my_news()`만 `..\..\VM-SPC_Core\scenario_targets.json`을 직접 읽게 고쳤다.
- 출력은 10줄 안: 미국 시황 제목 1 · 국내 마감 시황 제목 1 · 오늘의 이슈 상위 5 · 리포트 1줄 · 보유 종목 기사 최대 3 (key: us_brief · kr_close · issues · reports · holdings_news · theme_news), 아침 · 마감 두 번(am · pm).
- 이슈 순위 = 여러 채널이 같은 이슈를 다뤘는지(채널 수) + 글 무게. 리포트 채널(butler_works · ked_epic_ai 리포트 요약)은 이슈에서 빼고 "리포트" 줄로, 여러 이슈를 담은 긴 글은 이슈마다 1 ÷ 이슈 수, 대표 제목은 이슈 이름이 제목에 직접 들어간 글에서만, 너무 넓은 단어(실적 · AI · 반도체 · 메모리 · 바이오) · 증권사 이름은 이슈로 세지 않는다.
- 채널을 더하려면 사용자가 주소를 준다.
- 파일 구성은 `README.md`. (처음 시험본 `digest.py` · 여론 점수 `reports\sentiment.py`는 2026-10-19 지움.)

## 이슈 낱말 기준 — 몇 주 지켜보며 정함 (2026-10-10 사용자 결정)
- 2026-10-10 반영: 겹친 기사가 작은 쪽의 70% 이상이면 같은 이슈로 묶음, 대표 제목은 묶인 이름이 다 나온 글 먼저, `BROAD`에 기능어 약 270개 추가(사건 낱말 확보 · 입찰 · 인수 등은 넣지 않음).
- 채널 형식(2026-10-10): 대화형 채널(`CHAT_CH` = krwatch)과 habit4117의 링크 없는 글은 "chat" — 이슈 낱말 · 대표 제목을 만들지 않고, 형식 채널이 낸 이슈에 채널 수만 보탠다. 자연어 · 톡 형식 채널을 더할 때는 `CHAT_CH`에 넣는다.
- 남은 결정: 기존 `BROAD`의 사건 낱말(수주 · 계약 · 공급 · 체결 · 진출 · 돌파 · 협력 · 확대 · 발표 · 공개)을 살릴지. 한꺼번에 정하지 않고, 사용자가 요약에서 겹치는 뉴스나 이상한 이슈 이름을 알려 줄 때마다 그 사례로 고친다.

## 테마별 뉴스 언급 (2026-10-10 사용자 결정)
- `news_digest.py --since 토요일`(2026-10-12 주말판): 창 = 그날 00:00 – 월 아침, 이슈 상위 10, 리포트 · 보유 종목 기사도 기간 묶음 → `summary_am.json`에 `weekend` 표시. 1_core 주말 정리판이 읽음.
- `news_digest.py` `theme_news()`: `..\exchange\2_kr_market\{날짜}\themes.json`(기준일 이하 최근)의 테마 · 종목 이름 · 키워드로, 그 시간대 글 중 테마를 다룬 채널 수 · 글 수 · 대표 제목을 센다 → item `theme_news`.
- 기사 · 시황은 제목, 대화 채널은 본문에서 찾는다. 공시 · 가격 알림은 빼고(가격은 2 국내 테마 표), 증권사 이름은 리포트 출처라 빼고, 여러 테마에 든 종목은 GROUPS 순서로 처음 테마 하나에만 센다.

## 할 일
- us_brief 항목에 "KOSPI200 야간선물" 퍼센트를 따로(value.night_futures, 없으면 null) — 미국 모닝 시황의 "국장 영향" · "주요 지수 종합" 줄에 있음. 이게 없어서 1 코어 리포트에 야간선물 줄이 안 나온다(1_core `build_report.py`는 3_us · 5_news `night_futures` 항목을 이미 읽게 돼 있음).
