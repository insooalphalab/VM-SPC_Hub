# VM-Hub 월말 실전 추적 — 평일 18:30(2026-10-15 사용자 결정: "실전 추적으로 진행")
#
# 9.332 "최근 20일 상승 상위 1/3 ∧ 개인 20일 누적 상위 1/3 사기"를 리포트에 넣지 않고 월말마다 목록만 기록 · 성과를 쌓는다.
# - 매일: 1_core\track_retail_mom.py 로 20거래일이 지난 기록의 결과만 채운다(일봉 읽기만, 몇십 초).
# - 그달 마지막 국내 거래일만: VM-SPC_Core 투자자별 수집(--validation, 약 790종목 증분) → 그날 목록 기록.
#   마지막 거래일 판단 = 2_kr kr_calendar.json 의 다음 개장일이 다른 달(달력이 없으면 다음 평일이 다른 달) ∧ 오늘 장세 기준일이 오늘(장이 열림).
# - 18:30 = 투자자별 확정치 뒤 · hub_pm(16:00) · Core 16:30(금요일 수집 포함)과 KIS 호출 간격.
# - 텔레그램은 보내지 않는다. 결과 파일 1_core\results\track_retail_mom.json, 로그 logs\hub_month_*.log.
# - 이 파일은 UTF-8 BOM 포함으로 저장한다(PowerShell 5.1 한글 경로).

$hub  = "C:\Users\USER\Desktop\New toy\VM-Hub"
$core = "C:\Users\USER\Desktop\New toy\VM-SPC_Core"
$pythonExe = "C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe"
$logDir = Join-Path $hub "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "hub_month_$stamp.log"
$env:PYTHONIOENCODING = "utf-8"

function Write-Utf8Line($text) {
    [System.IO.File]::AppendAllText($logFile, "$text`r`n", [System.Text.Encoding]::UTF8)
}

function Run-Step($label, $workDir, $script, $extraArgs = @()) {
    Write-Utf8Line "`n===== [$label] START $(Get-Date -Format o) ====="
    $tmpOut = Join-Path $logDir "_tmp_$stamp`_out.log"
    $tmpErr = Join-Path $logDir "_tmp_$stamp`_err.log"
    $argStr = '"' + (Join-Path $workDir $script) + '"'
    foreach ($a in $extraArgs) { $argStr += " $a" }
    $proc = Start-Process -FilePath $pythonExe -ArgumentList $argStr -WorkingDirectory $workDir `
        -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput $tmpOut -RedirectStandardError $tmpErr
    foreach ($t in @($tmpOut, $tmpErr)) {
        if (Test-Path $t) {
            Get-Content $t -Raw -Encoding UTF8 | ForEach-Object { [System.IO.File]::AppendAllText($logFile, $_, [System.Text.Encoding]::UTF8) }
            Remove-Item $t -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Utf8Line "===== [$label] END (exit=$($proc.ExitCode)) $(Get-Date -Format o) ====="
    return $proc.ExitCode
}

$today = Get-Date
$todayStr = $today.ToString("yyyy-MM-dd")

# 1) 오늘 장이 열렸나(hub_pm이 만든 장세 기준일)
$mkt = Get-Content (Join-Path $core "results\scenario\market.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$open = ($mkt.date -eq $todayStr)

# 2) 다음 개장일이 다른 달인가
$next = $null
$calFile = Join-Path $hub "exchange\2_kr_market\kr_calendar.json"
if (Test-Path $calFile) {
    $cal = (Get-Content $calFile -Raw -Encoding UTF8 | ConvertFrom-Json).days
    $next = $cal.PSObject.Properties | Where-Object { $_.Name -gt $todayStr -and $_.Value -eq $true } |
        Sort-Object Name | Select-Object -First 1 -ExpandProperty Name
}
if (-not $next) {   # 달력이 없거나 짧으면 다음 평일
    $d = $today.AddDays(1)
    while ($d.DayOfWeek -eq [DayOfWeek]::Saturday -or $d.DayOfWeek -eq [DayOfWeek]::Sunday) { $d = $d.AddDays(1) }
    $next = $d.ToString("yyyy-MM-dd")
}
$monthEnd = $open -and ($next.Substring(0, 7) -ne $todayStr.Substring(0, 7))
Write-Utf8Line "오늘 $todayStr · 장 열림 $open · 다음 개장일 $next · 월말 $monthEnd"

# 3) 월말이면 전 종목 투자자별 수집 → 목록 기록
if ($monthEnd) {
    $rc = Run-Step "core: investor detail (validation)" $core "stock_track\collect_investor_detail.py" @("--validation")
    if ($rc -eq 0) {
        Run-Step "1_core: track record" (Join-Path $hub "1_core") "track_retail_mom.py" @("--date", $todayStr) | Out-Null
        # 9.355 종목 합성 피하기 실전 기록(2026-10-21 사용자: "기록만") — Core research\track_stock_combo.py 실행만. 리포트에 안 넣음.
        # 순서(Core 안내): 공매도 증분 → DART 분기 재무 → 잠정실적 공시일 → 그 월말 세 목록 기록(① 걷는 앞 합성 하위 1/5 ② 9.325 합집합 ③ 9.332)
        $rcS = Run-Step "core: short (update)" $core "stock_track\collect_short.py" @("--update")
        Run-Step "core: dart financials (validation)" $core "dart_events\collect.py" @("--validation") | Out-Null
        Run-Step "core: dart prelim (validation)" $core "dart_events\collect.py" @("--validation-prelim") | Out-Null
        $rcC = Run-Step "core: track stock combo" $core "research\track_stock_combo.py" @("--date", $todayStr)
        if ($rcS -ne 0 -or $rcC -ne 0) {
            Run-Step "alert" (Join-Path $hub "1_core") "alert.py" @('"⚠ 9.355 월말 기록 확인 필요 — 공매도 증분 또는 기록 단계 실패 (로그 hub_month_' + $stamp + '.log)"') | Out-Null
        }
    } else {
        Run-Step "alert" (Join-Path $hub "1_core") "alert.py" @('"⚠ 월말 실전 추적 못 함 — 투자자별 수집 실패 (로그 hub_month_' + $stamp + '.log)"') | Out-Null
    }
}

# 3-2) 분기 말(3 · 6 · 9 · 12월 마지막 거래일): 테마 흐름 소속표 다시 만들기(2_kr theme_map.py — 같이 움직이는 종목끼리, 2026-10-15)
if ($monthEnd -and (@(3, 6, 9, 12) -contains $today.Month)) {
    Run-Step "2_kr: theme map (quarterly)" (Join-Path $hub "2_kr_market") "theme_map.py" | Out-Null
}

# 4) 매일: 결과 채우기
Run-Step "1_core: track fill" (Join-Path $hub "1_core") "track_retail_mom.py" | Out-Null
Run-Step "core: track stock combo fill" $core "research\track_stock_combo.py" | Out-Null   # 9.355 기록 결과 채우기(20 · 60거래일 지난 것)

# 로그 60일 이상 지난 건 정리
Get-ChildItem -Path $logDir -Filter "hub_month_*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-60) } |
    Remove-Item -Force -ErrorAction SilentlyContinue
Write-Utf8Line "`nALL DONE $(Get-Date -Format o)"
