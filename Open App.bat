@echo off
title Herbie Creative
cd /d "%~dp0"
setlocal EnableExtensions EnableDelayedExpansion

REM Already running? Just open the browser.
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
  echo Herbie Creative is already running. Opening browser...
  start "" "http://127.0.0.1:8000/"
  exit /b 0
)

echo Starting Herbie Creative...
echo Checking Python 3.12+ ...
echo.

set "VENV_PY=%~dp0backend\.venv\Scripts\python.exe"
set "APP_PY="

REM 1) Prefer existing project venv
if exist "%VENV_PY%" (
  call :check_py_version "%VENV_PY%"
  if not errorlevel 1 (
    set "APP_PY=%VENV_PY%"
    goto :python_ready
  )
  echo Existing venv Python is too old. Recreating with a newer system Python.
)

REM 2) Find system Python 3.12+ (PATH, common folders, registry)
call :resolve_system_python
if defined APP_PY goto :python_ready

echo Python 3.12+ was not found on this computer.
echo.
echo On public PCs, winget often fails on the Microsoft Store source.
echo Trying winget community source, then a per-user python.org install...
echo.

set "WINGET_ARCH="
echo %PROCESSOR_ARCHITECTURE% | findstr /I "ARM" >nul
if not errorlevel 1 set "WINGET_ARCH=--architecture x64"

where winget >nul 2>&1
if not errorlevel 1 (
  echo Installing Python 3.12 with winget --source winget ...
  winget install -e --id Python.Python.3.12 --source winget --accept-package-agreements --accept-source-agreements --disable-interactivity %WINGET_ARCH%
  call :refresh_path
  call :resolve_system_python
  if defined APP_PY goto :python_ready
)

echo Installing Python 3.12 for the current user from python.org...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_python_windows.ps1" -Method pythonorg
call :refresh_path
call :resolve_system_python
if defined APP_PY goto :python_ready

echo.
echo Could not find or install Python 3.12+ for this user.
echo On a public computer, install from https://www.python.org/downloads/
echo choose "Install for current user", check "Add python.exe to PATH",
echo then close this window and run Open App.bat again.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:python_ready
echo Python OK
echo.
cd /d "%~dp0"

REM One window only: install + server run here so progress and errors stay visible.
REM Keep this window open while you use the app. Close it or use Close App.bat to stop.
if not exist "%~dp0backend\.venv\.deps-installed" (
  echo First launch will install packages in this window. That can take a few minutes.
) else (
  echo Starting server in this window. Browser opens when ready.
)
echo.

"!APP_PY!" run_app.py
set "ERR=!ERRORLEVEL!"
if not "!ERR!"=="0" (
  echo.
  echo Herbie Creative exited with an error ^(!ERR!^).
  if exist "%~dp0herbie.log" (
    echo ---- last lines of herbie.log ----
    powershell -NoProfile -Command "Get-Content -LiteralPath '%~dp0herbie.log' -Tail 40"
  )
  pause
  exit /b !ERR!
)
exit /b 0

REM --- helpers ---

:refresh_path
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%%P"
set "PATH=%LOCALAPPDATA%\Programs\Python\Python314;%LOCALAPPDATA%\Programs\Python\Python314\Scripts;%LOCALAPPDATA%\Programs\Python\Python313;%LOCALAPPDATA%\Programs\Python\Python313\Scripts;%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%LOCALAPPDATA%\Programs\Python\Launcher;%ProgramFiles%\Python314;%ProgramFiles%\Python313;%ProgramFiles%\Python312;%PATH%"
exit /b 0

:resolve_system_python
set "APP_PY="
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\find_python.ps1"`) do (
  set "APP_PY=%%I"
  goto :resolve_done
)
:resolve_done
exit /b 0

:check_py_version
set "CHECK_EXE=%~1"
set "PYVER="
for /f "delims=" %%V in ('"%CHECK_EXE%" -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2^>nul') do set "PYVER=%%V"
if not defined PYVER exit /b 1
for /f "tokens=1,2 delims=." %%A in ("%PYVER%") do (
  if %%A LSS 3 exit /b 1
  if %%A GTR 3 exit /b 0
  if %%B LSS 12 exit /b 1
)
exit /b 0
