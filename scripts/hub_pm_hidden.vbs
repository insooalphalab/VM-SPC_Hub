' 작업 스케줄러가 wscript.exe 로 실행 — PowerShell 창을 숨겨서(0 = SW_HIDE) 끝날 때까지 기다린다(True).
' VM-SPC_Core scripts/run_daily_pipeline_hidden.vbs 와 같은 방식(-WindowStyle Hidden 은 스케줄러에서 누락되는 문제).
Set fso = CreateObject("Scripting.FileSystemObject")
ps1Path = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "hub_pm.ps1")
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & ps1Path & """"
Set shell = CreateObject("WScript.Shell")
shell.Run cmd, 0, True
