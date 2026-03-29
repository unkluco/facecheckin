@echo off
title FaceCheckin Server
chcp 65001 >nul

REM -- Detect project root (folder containing this .bat file)
set "PROJ=%~dp0"
REM Remove trailing backslash
if "%PROJ:~-1%"=="\" set "PROJ=%PROJ:~0,-1%"

REM ============================================================
REM  Tim Python: uu tien .venv BEN TRONG thu muc final
REM  Neu khong co, dung Python he thong (PATH)
REM ============================================================
set "PYTHON="

REM 1. Kiem tra .venv ben trong chinh thu muc final
set "PY_LOCAL=%PROJ%\.venv\Scripts\python.exe"
if exist "%PY_LOCAL%" (
    set "PYTHON=%PY_LOCAL%"
    echo [OK] Dung venv noi bo: %PY_LOCAL%
    goto :found_python
)

REM 2. Fallback: dung Python he thong
where python >nul 2>&1
if %ERRORLEVEL%==0 (
    for /f "tokens=*" %%i in ('where python') do (
        set "PYTHON=%%i"
        goto :found_python
    )
)

REM 3. Thu python3
where python3 >nul 2>&1
if %ERRORLEVEL%==0 (
    for /f "tokens=*" %%i in ('where python3') do (
        set "PYTHON=%%i"
        goto :found_python
    )
)

echo [LOI] Khong tim thay Python. Vui long cai Python 3.x va them vao PATH.
echo       Tai tai: https://www.python.org/downloads/
pause
exit /b 1

:found_python
echo [OK] Python: %PYTHON%

REM ============================================================
REM  Kiem tra thu muc backend
REM ============================================================
set "BACKEND=%PROJ%\backend"
if not exist "%BACKEND%\start.py" (
    echo [LOI] Khong tim thay: %BACKEND%\start.py
    pause
    exit /b 1
)
echo [OK] Backend: %BACKEND%

REM ============================================================
REM  Tu dong cai thu vien neu thieu
REM ============================================================
set "REQ=%BACKEND%\requirements.txt"
if exist "%REQ%" (
    echo.
    echo [INFO] Kiem tra thu vien Python...
    "%PYTHON%" -c "import aiohttp, aiofiles, deepface, cv2, numpy" >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo [INFO] Dang cai dat thu vien can thiet...
        "%PYTHON%" -m pip install -r "%REQ%" --quiet
        if %ERRORLEVEL% NEQ 0 (
            echo [CANH BAO] Mot so thu vien co the chua duoc cai. Thu chay server...
        ) else (
            echo [OK] Cai dat thu vien thanh cong.
        )
    ) else (
        echo [OK] Thu vien da co day du.
    )
)

REM ============================================================
REM  Khoi dong server
REM ============================================================
echo.
echo ============================================================
echo  FaceCheckin dang khoi dong...
echo  Dashboard: http://localhost:8080
echo ============================================================
echo.

REM -- Mo trinh duyet sau 4 giay
start "" cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:8080"

REM -- Chay server (cd vao backend de cac duong dan tuong doi hoat dong)
cd /d "%BACKEND%"
"%PYTHON%" start.py

pause
