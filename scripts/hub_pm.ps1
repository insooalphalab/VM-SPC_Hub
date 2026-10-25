# VM-Hub 마감 리포트 — 평일 16:00 시작, 16:30 텔레그램(2026-10-10 사용자 결정: 장이 열렸을 때만, 처음부터 보내기.
#   처음엔 15:41 시작 · 16:00 전송이었으나 "15:40엔 일봉이 완료 안 됐을 수 있으니 수집 16:00, 리포트 16:30"으로 바꿈)
#
# 순서(약 18분): 5 뉴스 텔레그램 수집 → 테마 묶음 일봉 → VM-SPC_Core 빠른 경로(프로그램매매 → 섹터 ETF 일봉 → 오늘의 후보 → 보유 · 관심)
#   → 2 국내 · 5 뉴스 정리본 → 오늘이 거래일인지 확인 → 16:30까지 기다렸다가 1 코어 리포트 전송.
# - 평일 국내 일봉 · 프로그램 · 섹터 ETF · 후보 · 박스권 페이지는 여기서만 받고 만든다. VM-SPC_Core 16:30 파이프라인은 이 결과를 읽기만 한다
#   (그쪽 run_daily_pipeline.ps1에서 같은 줄을 막고 vm_predict는 --no-fetch — 같은 일봉을 두 번 받지 않게, 2026-10-10 사용자 결정).
# - VM-SPC_Core 코드는 고치지 않고 그 스크립트를 실행만 한다. VM-SPC_Core 정규 파이프라인(16:30)은 텔레그램 수집 줄만 막고 그대로 돈다.
# - 텔레그램 원문 · 표 · 로그인 세션은 5_news가 가진다(2026-10-10 이관). Core의 data\_reports는 5_news로 가는 정션이라 Core 화면은 그대로 읽는다.
# - 16:00의 투자자별 수급은 KRX 잠정치일 수 있다(확정은 저녁) — 보유 판단 수급 줄은 그 시점 값.
# - 이 파일은 UTF-8 BOM 포함으로 저장한다(PowerShell 5.1 한글 경로).

$hub  = "C:\Users\USER\Desktop\New toy\VM-Hub"
$core = "C:\Users\USER\Desktop\New toy\VM-SPC_Core"
$pythonExe = "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe"
$logDir = Join-Path $hub "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "hub_pm_$stamp.log"
$env:PYTHONIOENCODING = "utf-8"

$script:fails = @()   # 실패한 단계(종료 코드 0 아님) — 리포트 맨 위 ⚠ 줄 · 못 보낸 날 알림에 씀(2026-10-11)

function Write-Utf8Line($text) {
    [System.IO.File]::AppendAllText($logFile, "$text`r`n", [System.Text.Encoding]::UTF8)
}

function Run-Step($label, $workDir, $script, $extraArgs = @(), $envVars = @{}) {
    Write-Utf8Line "`n===== [$label] START $(Get-Date -Format o) ====="
    $tmpOut = Join-Path $logDir "_tmp_$stamp`_out.log"
    $tmpErr = Join-Path $logDir "_tmp_$stamp`_err.log"
    foreach ($k in $envVars.Keys) { Set-Item -Path "Env:$k" -Value $envVars[$k] }
    $argStr = '"' + (Join-Path $workDir $script) + '"'
    foreach ($a in $extraArgs) { $argStr += " $a" }
    $proc = Start-Process -FilePath $pythonExe -ArgumentList $argStr -WorkingDirectory $workDir `
        -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput $tmpOut -RedirectStandardError $tmpErr
    foreach ($k in $envVars.Keys) { Remove-Item -Path "Env:$k" -ErrorAction SilentlyContinue }
    foreach ($t in @($tmpOut, $tmpErr)) {
        if (Test-Path $t) {
            Get-Content $t -Raw -Encoding UTF8 | ForEach-Object { [System.IO.File]::AppendAllText($logFile, $_, [System.Text.Encoding]::UTF8) }
            Remove-Item $t -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Utf8Line "===== [$label] END (exit=$($proc.ExitCode)) $(Get-Date -Format o) ====="
    if ($proc.ExitCode -ne 0) { $script:fails += $label }
    return $proc.ExitCode
}

function Send-Alert($text) {
    Run-Step "alert" (Join-Path $hub "1_core") "alert.py" @('"' + $text + '"') | Out-Null
}

# 1) VM-SPC_Core 빠른 경로 — 리포트에 필요한 것만
Run-Step "5_news: telegram collect" (Join-Path $hub "5_news") "reports\run.py" @() @{ V2_DATA_DIR = (Join-Path $core "data") } | Out-Null
# 테마 묶음(바스켓) 종목 일봉 — 보유 종목 · 테마 표가 여기 들어 있다. 원래 Core 16:30에서만 갱신돼 16시 전엔 전날 봉이었음(2026-10-10)
$baskets = (Get-Content (Join-Path $core "basket_watchlist.json") -Raw -Encoding UTF8 | ConvertFrom-Json).themes.PSObject.Properties |
    ForEach-Object { $_.Value.basket_name } | Select-Object -Unique
foreach ($b in $baskets) { Run-Step "core: basket bars $b" $core "vm_predict\v2_data_collector.py" @("--basket", $b) | Out-Null }
Run-Step "core: program (screen)"   $core "stock_track\collect_program.py" @("--screen") | Out-Null
Run-Step "core: sector ETF bars"    $core "scenario\sector_map.py" @("--bars") | Out-Null
Run-Step "core: screen candidates"  $core "scenario\screen.py" | Out-Null
Run-Step "core: holdings page"      $core "scenario\render_risk.py" | Out-Null
# 코스피 시장 투자자별(외국인 등, 2026-10-15 사용자: 매일 갱신) — 원래 Core 금요일 단계였던 것을 허브가 매일 실행(Core 줄은 막음). 300거래일씩 받아 가벼움
Run-Step "core: market investor (KOSPI)" $core "stock_track\collect_market_investor.py" | Out-Null
# VKOSPI 일별(KIS 업종 0503, 2_kr) — 4_macro 유동성 · 신용 모니터가 읽음
Run-Step "2_kr_market vkospi"       (Join-Path $hub "2_kr_market") "vkospi.py" | Out-Null
# 테마 흐름 보조(2026-10-15) — 넓힘 종목 일봉(Core _scenario에 없을 때만) · 상장주식수(30일마다, 시총 층용). 실패해도 0
Run-Step "2_kr_market theme extra"  (Join-Path $hub "2_kr_market") "theme_extra.py" | Out-Null
# 개인 쏠림 ETF(레버리지 · 인버스) 일봉 + 상장좌수 스냅샷(2026-10-15, 9.344 검토용 — 좌수는 이력 API가 없어 매일 쌓음). 실패해도 0
Run-Step "2_kr_market retail etf"   (Join-Path $hub "2_kr_market") "retail_etf.py" | Out-Null
# 코스피200 선물 투자자별 순매수(2026-10-21 사용자 가설 — 선물 · 현물 흐름 비교). KIS가 그날 값만 줘서 매일 쌓음. 15:50 뒤 · 휴장일 아님만 기록, 실패해도 0
Run-Step "2_kr_market futures investor" (Join-Path $hub "2_kr_market") "futures_investor.py" | Out-Null

# 2) 정리본
Run-Step "2_kr_market export" (Join-Path $hub "2_kr_market") "export_exchange.py" | Out-Null
Run-Step "5_news digest pm"   (Join-Path $hub "5_news") "reports\news_digest.py" @("--slot", "pm") @{ V2_DATA_DIR = (Join-Path $core "data") } | Out-Null

# 3) 거래일 확인 — 오늘 봉이 들어온 날만(휴장일 · 주말이면 보내지 않음)
$today = Get-Date -Format "yyyy-MM-dd"
$mkt = Get-Content (Join-Path $core "results\scenario\market.json") -Raw -Encoding UTF8 | ConvertFrom-Json
if ($mkt.date -ne $today) {
    Write-Utf8Line "`n오늘($today)은 거래일이 아님(장세 기준일 $($mkt.date)) — 리포트를 보내지 않음"
    # 휴장일이면 실패도 없다 — 실패가 있으면 수집이 깨져 거래일을 못 알아본 것일 수 있으니 알림
    if ($script:fails.Count -gt 0) { Send-Alert "⚠ 마감 리포트 못 보냄 — 실패: $($script:fails -join ' · ') (로그 hub_pm_$stamp.log)" }
    exit 0
}

# 4) 16:30까지 기다렸다가 전송(늦으면 바로)
$sendAt = (Get-Date).Date.AddHours(16.5)
$wait = ($sendAt - (Get-Date)).TotalSeconds
if ($wait -gt 0) { Write-Utf8Line "16:30까지 $([int]$wait)초 대기"; Start-Sleep -Seconds ([int]$wait) }
$warnArgs = @()
if ($script:fails.Count -gt 0) { $warnArgs = @("--warn", ('"' + ($script:fails -join ' · ') + '"')) }
$rc = Run-Step "1_core report pm --send" (Join-Path $hub "1_core") "build_report.py" (@("--date", $today, "--slot", "pm", "--send") + $warnArgs)
if ($rc -ne 0) { Send-Alert "⚠ 마감 리포트 못 보냄 — 리포트 만들기 실패 (로그 hub_pm_$stamp.log)" }
Write-Utf8Line "`nALL DONE $(Get-Date -Format o)"
