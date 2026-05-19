@echo off
setlocal EnableExtensions
title Stop FaceCheckin Server
chcp 65001 >nul

set "PROJ=%~dp0"
if "%PROJ:~-1%"=="\" set "PROJ=%PROJ:~0,-1%"
set "VENV_DIR=%PROJ%\.venv"

echo [INFO] Dang tim va tat FaceCheckin server...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; $project='%PROJ%'; $venv='%VENV_DIR%'; $pids=@(); $pids += Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python' -and $_.CommandLine -match 'start\.py' -and (($_.ExecutablePath -like ($venv + '*')) -or ($_.CommandLine -like ('*' + $project + '*'))) } | Select-Object -ExpandProperty ProcessId; $pids += Get-NetTCPConnection -LocalPort 8080 -State Listen | Select-Object -ExpandProperty OwningProcess; $pids = $pids | Sort-Object -Unique; if (-not $pids) { Write-Host '[OK] Khong thay FaceCheckin server dang chay.'; exit 0 }; $pids | ForEach-Object { Write-Host ('[INFO] Tat PID ' + $_); Stop-Process -Id $_ -Force }; Write-Host '[OK] Da tat FaceCheckin server.'"

echo.
pause
