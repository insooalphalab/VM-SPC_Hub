# 5 뉴스 — 역할 지침 (hub-news)

상위 `..\CLAUDE.md`(공통) · `..\README.md`(설계) · `..\exchange\README.md`(형식)를 먼저 읽는다.

## 맡은 일
텔레그램 리서치 채널에서 하루 주요 뉴스를 **짧게** 정리해 `..\exchange\5_news\{날짜}\`에 낸다. 방향 판단은 하지 않는다.

## 입력 (전환 기간 — 읽기만)
- 원문: `..\..\VM-SPC_Core\data\_reports\raw\{채널}.jsonl` (butler_works · ked_epic_ai · aicorporateanalysisdeepdive · shmstory · darthacking · easobi)
- 표: `..\..\VM-SPC_Core\data\_reports\reports.csv`(증권사 의견 · 목표가 · 방향) · `news.csv`(기사 ↔ 종목 코드)
- 보유 · 관심 종목: `..\..\VM-SPC_Core\scenario_targets.json`
- 수집은 아직 VM-SPC_Core가 매일 한다(텔레그램 세션 파일 공유 금지). 수집 이관은 나중 단계.

## 출발 코드 (복사해서 시작)
- `..\..\VM-SPC_Core\reports\news_digest.py` — 원문 문장 그대로 뽑는 시범본(사용자: "하루치 치고 너무 길다")
- `..\..\VM-SPC_Core\reports\export_md.py` — 날짜별 원문 Markdown
- `..\..\VM-SPC_Core\reports\parse.py` 의 `load_raw`

## 첫 작업 (2단계)
1. 출력을 **10줄 안**으로: 미국 시황 제목 1 · 국내 마감 시황 제목 1 · 오늘의 이슈 상위 5 · 리포트 1줄 · 보유 종목 기사 최대 3.
2. 이슈 순위 = **여러 채널이 같은 이슈를 다뤘는지**(채널 수) + 글 무게. 2026-10-09 시험에서 드러난 문제를 고친다:
   - 리포트 채널(butler_works · ked_epic_ai 리포트 요약)은 이슈 순위에서 빼고 "리포트" 줄로 따로.
   - 아침 시황처럼 여러 이슈를 담은 긴 글은 이슈마다 가볍게(1 ÷ 이슈 수).
   - 대표 제목은 이슈 이름이 제목에 직접 들어간 글에서만 고른다.
   - 너무 넓은 단어(실적 · AI · 반도체 · 메모리 · 바이오)와 증권사 이름은 이슈로 세지 않는다.
3. 채널이 5개뿐이라 중요도가 잘 안 갈린다 — 사용자가 채널 주소를 주면 수집 목록에 더한다(그 전엔 지금 채널로).
4. `summary.json` · `summary.md`(`..\exchange\README.md` 형식, key: us_brief · kr_close · issues · reports · holdings_news), 아침 · 마감 두 번(am · pm).
