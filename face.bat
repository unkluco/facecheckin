@echo off
setlocal EnableExtensions
title FaceCheckin Server
chcp 65001 >nul

set "PROJ=%~dp0"
if "%PROJ:~-1%"=="\" set "PROJ=%PROJ:~0,-1%"

REM ============================================================
REM  Tu quan ly .venv voi Python phu hop cho InsightFace
REM ============================================================
set "PYTHON="
set "VENV_DIR=%PROJ%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "BASE_PY="
set "BASE_DESC="
set "PY311_LOCAL=%LocalAppData%\Programs\Python\Python311\python.exe"
set "PY311_MACHINE=%ProgramFiles%\Python311\python.exe"
set "PY311_MACHINE_X86=%ProgramFiles(x86)%\Python311\python.exe"

if exist "%VENV_PY%" (
    call :is_supported_python "%VENV_PY%"
    if not errorlevel 1 (
        set "PYTHON=%VENV_PY%"
        echo [OK] Dung venv noi bo: %VENV_PY%
        goto :found_python
    )
    echo [CANH BAO] .venv hien tai sai version hoac bi hong. Dang tao lai...
    call :create_or_recreate_venv
    if errorlevel 1 goto :python_not_ok
    goto :found_python
)

echo [INFO] Chua co .venv. Dang tao moi...
call :create_or_recreate_venv
if errorlevel 1 goto :python_not_ok

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
REM  Tu dong cai thu vien
REM ============================================================
set "REQ=%BACKEND%\requirements.txt"
if not exist "%REQ%" goto :start_server

echo.
echo [INFO] Dong bo thu vien Python...
"%PYTHON%" -m pip install -r "%REQ%" --quiet
if errorlevel 1 (
    echo [LOI] Cai dat that bai.
    pause
    exit /b 1
)
echo [OK] Thu vien da san sang.

:start_server
echo.
echo ============================================================
echo  FaceCheckin dang khoi dong...
echo  Dashboard: http://localhost:8080
echo ============================================================
echo.

start "" cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:8080"
cd /d "%BACKEND%"
"%PYTHON%" start.py
set "APP_EXIT=%errorlevel%"
if not "%APP_EXIT%"=="0" (
    echo.
    echo [LOI] Server da dung voi ma loi: %APP_EXIT%
    echo       Hay chup/man hinh lai loi phia tren de debug.
    pause
)
exit /b %APP_EXIT%

REM ============================================================
REM  Helper subroutines
REM ============================================================
:is_supported_python
set "CANDIDATE=%~1"
if not exist "%CANDIDATE%" exit /b 1
"%CANDIDATE%" -c "import sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] <= (3,11) else 1)" >nul 2>&1
exit /b %errorlevel%

:pick_base_python
set "BASE_PY="
set "BASE_DESC="
py -3.11 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "BASE_PY=py -3.11"
    set "BASE_DESC=Python Launcher 3.11"
    exit /b 0
)
py -3.10 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "BASE_PY=py -3.10"
    set "BASE_DESC=Python Launcher 3.10"
    exit /b 0
)
python -c "import sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] <= (3,11) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "BASE_PY=python"
    set "BASE_DESC=python tren PATH"
    exit /b 0
)
if exist "%PY311_LOCAL%" (
    call :is_supported_python "%PY311_LOCAL%"
    if not errorlevel 1 (
        set "BASE_PY="%PY311_LOCAL%""
        set "BASE_DESC=Python 3.11 local user"
        exit /b 0
    )
)
if exist "%PY311_MACHINE%" (
    call :is_supported_python "%PY311_MACHINE%"
    if not errorlevel 1 (
        set "BASE_PY="%PY311_MACHINE%""
        set "BASE_DESC=Python 3.11 machine"
        exit /b 0
    )
)
if exist "%PY311_MACHINE_X86%" (
    call :is_supported_python "%PY311_MACHINE_X86%"
    if not errorlevel 1 (
        set "BASE_PY="%PY311_MACHINE_X86%""
        set "BASE_DESC=Python 3.11 machine x86"
        exit /b 0
    )
)
exit /b 1

:create_or_recreate_venv
call :ensure_base_python
if errorlevel 1 (
    echo [LOI] Khong tim thay Python 3.10/3.11 de tao .venv.
    exit /b 1
)
if exist "%VENV_DIR%" (
    call :remove_dir_safe "%VENV_DIR%" "%PROJ%"
    if errorlevel 1 exit /b 1
)
echo [INFO] Tao .venv bang %BASE_DESC%...
%BASE_PY% -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo [LOI] Tao .venv that bai.
    exit /b 1
)
if not exist "%VENV_PY%" (
    echo [LOI] Tao .venv xong nhung khong tim thay python.exe trong venv.
    exit /b 1
)
call :is_supported_python "%VENV_PY%"
if errorlevel 1 (
    echo [LOI] Python trong .venv khong nam trong range 3.10/3.11.
    call :remove_dir_safe "%VENV_DIR%" "%PROJ%" >nul 2>&1
    exit /b 1
)
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel --quiet
if errorlevel 1 (
    echo [CANH BAO] Khong the nang cap pip/setuptools/wheel, se tiep tuc.
)
set "PYTHON=%VENV_PY%"
echo [OK] Da tao moi .venv phu hop.
exit /b 0

:ensure_base_python
call :pick_base_python
if not errorlevel 1 exit /b 0

if /I "%FACECHECKIN_SKIP_AUTOPY_INSTALL%"=="1" (
    echo [CANH BAO] Bo qua auto-cai Python vi FACECHECKIN_SKIP_AUTOPY_INSTALL=1
    exit /b 1
)

echo [INFO] Khong tim thay Python 3.10/3.11. Dang thu tu cai Python 3.11...
call :auto_install_python311
if errorlevel 1 exit /b 1

call :pick_base_python
if not errorlevel 1 exit /b 0
exit /b 1

:auto_install_python311
where winget >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong co winget tren may de tu dong cai Python.
    exit /b 1
)
echo [INFO] Chay winget cai Python 3.11 (co the mat vai phut)...
winget install -e --id Python.Python.3.11 --scope user --accept-package-agreements --accept-source-agreements --disable-interactivity --silent
if errorlevel 1 (
    echo [LOI] Winget cai Python 3.11 that bai.
    exit /b 1
)
echo [OK] Da cai Python 3.11 qua winget.
exit /b 0

:remove_dir_safe
set "TARGET=%~1"
set "ROOT=%~2"
for %%I in ("%TARGET%") do set "TARGET_FULL=%%~fI"
for %%I in ("%ROOT%") do set "ROOT_FULL=%%~fI"
set "ALLOWED_VENV=%ROOT_FULL%\.venv"
if /I not "%TARGET_FULL%"=="%ALLOWED_VENV%" (
    echo [LOI] Tu choi xoa duong dan khong hop le: %TARGET_FULL%
    echo       Chi duoc xoa: %ALLOWED_VENV%
    exit /b 1
)
if exist "%TARGET_FULL%" rmdir /s /q "%TARGET_FULL%"
if exist "%TARGET_FULL%" (
    echo [LOI] Khong xoa duoc thu muc: %TARGET_FULL%
    exit /b 1
)
exit /b 0

:python_not_ok
echo [LOI] Can Python 3.10 hoac 3.11 de cai InsightFace tren Windows.
echo       Python hien co tren may:
py -0p 2>nul
echo.
echo       Cach sua nhanh:
echo       1. Chay lai face.bat (script se tu cai Python 3.11 bang winget neu co).
echo       2. Neu winget khong hoat dong, cai thu cong Python 3.11:
echo          https://www.python.org/downloads/release/python-3119/
echo       3. Chay lai face.bat. Script se tu tao .venv cho du an.
echo.
echo       Ly do: Python 3.13+ bat pip build insightface tu source va can Microsoft C++ Build Tools.
pause
exit /b 1
