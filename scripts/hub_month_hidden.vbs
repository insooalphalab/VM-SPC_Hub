' 작업 스케줄러가 wscript.exe 로 실행 — PowerShell 창을 숨겨(0 = SW_HIDE) 끝날 때까지 기다린다(True). hub_pm_hidden.vbs 와 같은 방식.
Set fso = CreateObject("Scripting.FileSystemObject")
ps1Path = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "hub_month.ps1")
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & ps1Path & """"
Set shell = CreateObject("WScript.Shell")
shell.Run cmd, 0, True
