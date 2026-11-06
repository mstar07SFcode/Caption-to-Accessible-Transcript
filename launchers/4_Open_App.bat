@echo off
rem ============================================================
rem   OPEN THE APP (Windows)
rem   Double-click to launch the Caption Transcripts window.
rem   Does every step - clean, review, publish - in one place.
rem   The first run installs what it needs and takes a minute.
rem
rem   This is the twin of 4_Open_App.command, which does the same
rem   job on a Mac. Keep the two in step.
rem ============================================================

setlocal

rem %~dp0 is this file's folder, with a trailing backslash. Resolving
rem the parent through a for-loop gives a clean absolute path instead
rem of one with a literal ".." in the middle, so the error messages
rem below name something a person can actually go and look at.
for %%I in ("%~dp0..") do set "PIPELINE=%%~fI"

echo ============================================
echo   Caption Transcripts
echo ============================================
echo.

rem ---- Python -------------------------------------------------
rem The py launcher is what python.org's installer puts on PATH, and it
rem picks the newest interpreter itself. Plain python.exe is the fallback.
rem Both are probed by running them: a Microsoft Store stub answers on
rem PATH but exits non-zero, and this filters it out.
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo ERROR: Python 3 is not installed, or is not on PATH.
  echo.
  echo Install it from https://www.python.org/downloads/ and tick
  echo "Add python.exe to PATH" in the installer, then try again.
  echo.
  pause
  exit /b 1
)

rem ---- Pipeline location --------------------------------------
if not exist "%PIPELINE%\pipeline\batch.py" (
  echo ERROR: cannot find the pipeline code.
  echo Looked for "pipeline\batch.py" in:
  echo   %PIPELINE%
  echo.
  echo Keep this launcher inside the project folder, next to "pipeline".
  echo.
  pause
  exit /b 1
)

set "VENV=%PIPELINE%\.venv"
set "VPY=%VENV%\Scripts\python.exe"

rem The window needs FastAPI and a webview, which the command-line steps
rem do not. They live in their own .venv so the pipeline itself keeps
rem working with plain system Python.
if not exist "%VPY%" (
  echo First run - creating the app environment...
  %PY% -m venv "%VENV%"
  if errorlevel 1 (
    echo.
    echo ERROR: could not create the app environment.
    pause
    exit /b 1
  )
)

"%VPY%" -c "import fastapi, uvicorn, keyring, docx" >nul 2>&1
if errorlevel 1 (
  echo Installing app components ^(needs internet^)...
  "%VPY%" -m pip install --upgrade pip >nul 2>&1
  "%VPY%" -m pip install -r "%PIPELINE%\requirements-gui.txt"
  if errorlevel 1 (
    echo.
    echo ERROR: install failed. Check your internet connection and try again.
    pause
    exit /b 1
  )
  echo.
)

echo Opening the window...
echo Leave this window open while you work - closing it quits the app.
echo.

cd /d "%PIPELINE%"
"%VPY%" -m gui.main

echo.
pause
