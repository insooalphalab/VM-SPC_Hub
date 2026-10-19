# 5_news — 텔레그램 뉴스 · 리서치

텔레그램 리서치 채널 원문을 모으고(허브의 유일한 텔레그램 수집처), 하루 주요 뉴스를 짧게 정리해 `..\exchange\5_news\{날짜}\`에 낸다. 방향 판단은 하지 않는다.
작업 규칙 · 결정은 `CLAUDE.md`.

## 폴더

```
5_news/
  reports/               수집 · 정리 코드(Core reports/ 복사본 + news_digest)
  core/                  Core 복사본: v2_config · kis_client · kis_auth · secrets_loader
  dart_events/           Core 복사본: client.py(종목 이름 조회용)
  data/_reports/         텔레그램 원문 · 표(git 제외, 약 130MB) — Core가 정션으로 읽음
  results/               날짜별 원문 Markdown · 시황 한 줄 · 뉴스 요약(git 제외)
  state/                 텔레그램 로그인 세션(비밀 — 커밋 금지)
  .streamlit/secrets.toml  TELEGRAM_API_ID · TELEGRAM_API_HASH(비밀 — 커밋 금지)
```

## reports\ 파일

| 파일 | 하는 일 | 실행 |
|---|---|---|
| `run.py` | 매일 수집 묶음: tg_collect · collect_web → parse · news · market_brief · market_actions · export_md | hub_am 07:15 · hub_pm 16:00 (`V2_DATA_DIR` = Core data) |
| `news_digest.py` | 하루 요약(미국 · 국내 시황 제목 · 이슈 상위 · 리포트 · 보유 종목 기사 · 테마 언급) → `summary_am\|pm.json · .md` + `latest.json` | hub_am(`--slot am`, 월요일 `--since 토요일`) · hub_pm(`--slot pm`) |
| `tg_collect.py` · `tg_client.py` | API 6채널 원문 → `data\_reports\raw\{채널}.jsonl` | run이 부름 |
| `collect_web.py` | 웹 미리보기 2채널(habit4117 · krwatch) | run이 부름 |
| `parse.py` | 리포트 요약 → `reports.csv`(의견 · 목표가 · 방향) | run이 부름 |
| `news.py` | 기사 ↔ 종목 → `news.csv` | run이 부름 |
| `market_actions.py` | 투자경고 등 → `market_actions.csv` | run이 부름 |
| `market_brief.py` | 시황 한 줄 → `results\reports\market_brief.json` | run이 부름 |
| `export_md.py` | 날짜별 원문 Markdown → `results\research_md\{날짜}\{채널}.md` | run이 부름 |
| `tg_login.py` | 첫 로그인(사용자가 직접, 1회) | 손으로 |

## 옮기지 말 것 (다른 곳이 경로로 읽음)

| 경로 | 읽는 곳 |
|---|---|
| `data\_reports\` | `..\..\VM-SPC_Core\data\_reports`가 이리 오는 **정션** — Core 종목 칸 · 후보 화면 · 검증 스크립트. 폴더를 옮기거나 표 열 이름을 바꾸면 Core가 깨진다 |
| `state\telegram_reports.session` | 로그인 세션 한 벌뿐. 두 곳이 동시에 쓰면 충돌 |
| `reports\` · `core\` | Core `research\validate_hub_themes2.py`가 import |
