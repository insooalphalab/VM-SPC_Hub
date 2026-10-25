# VM-Hub 아침(글로벌) 리포트 — 월 – 토 07:15 시작, 08:00 텔레그램(2026-10-10 사용자 결정: "글로벌은 08:00에")
# 월요일 = 주말 정리판(2026-10-12 사용자 요청): 금요일 미국 마감 + 토 00:00 – 월 아침 뉴스 묶음(5_news --since 토요일, build_report --weekend).
#
# 순서(약 3분): 5 뉴스 텔레그램 수집(밤사이 · 아침 시황) → 5 뉴스(am) · 3 해외 · 4 매크로 정리본
#   → 미국 거래일인지 확인 → 08:00까지 기다렸다가 1 코어 아침 리포트 전송.
# - 07:15 시작 이유: VM-SPC_Global(07:00)이 미국 일봉 수집 · 예측을 약 6분에 끝낸다. 3 해외는 그 결과를 읽기만 한다.
# - 미국 휴장 다음 날(Global이 새 거래일을 못 받은 날)은 보내지 않는다.
# - 텔레그램 원문 · 표 · 로그인 세션은 5_news가 가진다(2026-10-10 이관). VM-SPC_Core\data\_reports는 5_news\data\_reports로 가는 정션.
#   V2_DATA_DIR = Core data는 종목 이름 · 일봉을 읽으려는 것(쓰는 _reports는 정션을 거쳐 5_news에 저장됨).
# - 이 파일은 UTF-8 BOM 포함으로 저장한다(PowerShell 5.1 한글 경로).

$hub  = "C:\Users\USER\Desktop\New toy\VM-Hub"
$core = "C:\Users\USER\Desktop\New toy\VM-SPC_Core"
$glob = "C:\Users\USER\Desktop\New toy\VM-SPC_Global"
$pythonExe = "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe"
$logDir = Join-Path $hub "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "hub_am_$stamp.log"
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

$weekend = (Get-Date).DayOfWeek -eq [System.DayOfWeek]::Monday
$newsArgs = @("--slot", "am")
if ($weekend) { $newsArgs += @("--since", (Get-Date).AddDays(-2).ToString("yyyy-MM-dd")) }

# 1) 원문 · 정리본
Run-Step "5_news: telegram collect" (Join-Path $hub "5_news") "reports\run.py" @() @{ V2_DATA_DIR = (Join-Path $core "data") } | Out-Null
Run-Step "5_news digest am" (Join-Path $hub "5_news") "reports\news_digest.py" $newsArgs @{ V2_DATA_DIR = (Join-Path $core "data") } | Out-Null
Run-Step "3_us_market export" (Join-Path $hub "3_us_market") "export_exchange.py" @() @{ V2_RESULTS_DIR = (Join-Path $glob "results"); V2_DATA_DIR = (Join-Path $glob "data") } | Out-Null
Run-Step "4_macro export" (Join-Path $hub "4_macro") "export_exchange.py" | Out-Null

# 국내 개장일 달력(KIS 휴장일조회, 앞으로 14일이 있으면 부르지 않음) — Global 07:00 KIS 호출과 10분 넘게 떨어뜨려 07:20 뒤에(2026-10-12)
$calAt = (Get-Date).Date.AddHours(7).AddMinutes(20)
$calWait = ($calAt - (Get-Date)).TotalSeconds
if ($calWait -gt 0) { Start-Sleep -Seconds ([int]$calWait) }
Run-Step "2_kr_market calendar" (Join-Path $hub "2_kr_market") "kr_calendar.py" | Out-Null

# 2) 미국 거래일 확인 — 3 해외 정리본 기준일이 어제(미국 현지)여야 새 거래일. 월요일은 직전 금요일
$us = Get-Content (Join-Path $hub "exchange\3_us_market\latest.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$back = -1
if ($weekend) { $back = -3 }
$yesterday = (Get-Date).AddDays($back).ToString("yyyy-MM-dd")
if ($us.date -ne $yesterday) {
    Write-Utf8Line "`n미국 새 거래일 없음(해외 기준일 $($us.date), 기대 $yesterday) — 아침 리포트를 보내지 않음"
    # 미국 휴장일(1년 9일 안팎)에도 한 줄 온다 — 휴장이 아니면 Global 07:00 수집이 실패한 것
    $f = ""; if ($script:fails.Count -gt 0) { $f = " · 실패: $($script:fails -join ' · ')" }
    Send-Alert "⚠ 아침 리포트 안 보냄 — 미국 새 거래일 없음(해외 기준일 $($us.date))$f. 미국 휴장일이 아니면 VM-SPC Global 07:00 수집 확인"
    exit 0
}

# 3) 08:00까지 기다렸다가 전송
$sendAt = (Get-Date).Date.AddHours(8)
$wait = ($sendAt - (Get-Date)).TotalSeconds
if ($wait -gt 0) { Write-Utf8Line "08:00까지 $([int]$wait)초 대기"; Start-Sleep -Seconds ([int]$wait) }
$warnArgs = @()
if ($script:fails.Count -gt 0) { $warnArgs = @("--warn", ('"' + ($script:fails -join ' · ') + '"')) }
if ($weekend) { $warnArgs += @("--weekend") }
$rc = Run-Step "1_core report am --send" (Join-Path $hub "1_core") "build_report.py" (@("--slot", "am", "--send") + $warnArgs)
if ($rc -ne 0) { Send-Alert "⚠ 아침 리포트 못 보냄 — 리포트 만들기 실패 (로그 hub_am_$stamp.log)" }
Write-Utf8Line "`nALL DONE $(Get-Date -Format o)"
