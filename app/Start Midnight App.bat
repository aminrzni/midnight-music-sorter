@echo off
chcp 65001 >nul
title Midnight 00:01 - Music Sorter (app)
cd /d "%~dp0"
echo ============================================================
echo  Midnight 00:01 - Music Sorter - starting the app
echo  (the text menu still works: Start Music Manager.bat)
echo ============================================================

rem ---- 1. Python ------------------------------------------------
set "PY="
python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PY (
    echo Python not found. Please run "Start Music Manager.bat" once - it installs Python - then try again.
    pause
    exit /b 1
)

rem ---- 2. Helper libraries (pywebview = the app window) ---------
call %PY% -c "import mutagen, openpyxl, webview, PIL, unidecode" >nul 2>nul
if errorlevel 1 (
    echo Installing helper libraries ^(mutagen, openpyxl, pillow, pywebview, unidecode^)...
    call %PY% -m pip install --upgrade mutagen openpyxl pillow pywebview unidecode || call %PY% -m pip install --user --upgrade mutagen openpyxl pillow pywebview unidecode
)
call %PY% -c "import mutagen, openpyxl, webview, PIL, unidecode" >nul 2>nul
if errorlevel 1 (
    echo Could not install the helper libraries. Copy the messages above and send them to Claude.
    pause
    exit /b 1
)

rem ---- 3. Run (ffmpeg, fpcalc and _cache are found next to this file or up to 3 folders above) ----
echo Opening the app window... keep this window open while you use the app.
call %PY% "%~dp0midnight_app.py"
if errorlevel 1 (
    echo.
    echo The app stopped with an error. Copy the messages above and send them to Claude.
    pause
)
