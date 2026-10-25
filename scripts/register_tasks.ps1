# VM-Hub 예약 작업 3개 등록(한 번만 실행, 다시 실행해도 덮어씀). 사용자가 PowerShell에서 직접:
#   powershell -ExecutionPolicy Bypass -File "C:\Users\USER\Desktop\New toy\VM-Hub\scripts\register_tasks.ps1"
# 지우기: Unregister-ScheduledTask -TaskName "VM-Hub 아침 리포트" -Confirm:$false  (마감도 같은 방식)
# 이 파일은 UTF-8 BOM 포함으로 저장한다.

$dir = "C:\Users\USER\Desktop\New toy\VM-Hub\scripts"
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew

$jobs = @(
    @{ Name = "VM-Hub 아침 리포트"; Vbs = "hub_am_hidden.vbs"; At = "07:15";
       Days = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"); Desc = "3 해외 · 4 매크로 · 5 뉴스 정리 → 08:00 아침 리포트 텔레그램(미국 거래일만, 월요일은 주말 정리판)" },
    @{ Name = "VM-Hub 마감 리포트"; Vbs = "hub_pm_hidden.vbs"; At = "16:00";
       Days = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"); Desc = "테마 묶음 일봉 · VM-SPC_Core 빠른 경로 → 2 국내 · 5 뉴스 정리 → 16:30 마감 리포트 텔레그램(국내 거래일만)" },
    @{ Name = "VM-Hub 월말 실전 추적"; Vbs = "hub_month_hidden.vbs"; At = "18:30";
       Days = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"); Desc = "9.332 개인 누적 × 20일 상승 목록 — 그달 마지막 거래일만 전 종목 투자자별 수집 · 기록, 매일 결과 채우기(텔레그램 없음)" }
)
foreach ($j in $jobs) {
    $action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument ('"' + (Join-Path $dir $j.Vbs) + '"')
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $j.Days -At $j.At
    Register-ScheduledTask -TaskName $j.Name -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
        -Description $j.Desc -Force | Out-Null
    Write-Output "등록: $($j.Name) — $($j.Days -join ', ') $($j.At)"
}
Get-ScheduledTask -TaskName "VM-Hub*" | Select-Object TaskName, State
