@echo off
chcp 65001 >nul
title Midnight 00:01 - Music Sorter
cd /d "%~dp0"
echo ============================================================
echo  Midnight 00:01 - Music Sorter - checking setup
echo ============================================================

rem ---- 1. Python ------------------------------------------------
set "PY="
python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY (
    echo.
    echo Python not found - installing Python 3.12 from python.org via winget...
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PY (
    echo.
    echo Could not install Python automatically.
    echo Please install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^),
    echo then double-click this file again.
    pause
    exit /b 1
)
echo Python: OK

rem ---- 2. Helper libraries ---------------------------------------
call %PY% -c "import mutagen, openpyxl" >nul 2>nul
if errorlevel 1 (
    echo Installing helper libraries ^(mutagen, openpyxl, pillow^)...
    call %PY% -m pip install --upgrade mutagen openpyxl pillow || call %PY% -m pip install --user --upgrade mutagen openpyxl pillow
)
call %PY% -c "import mutagen, openpyxl" >nul 2>nul
if errorlevel 1 (
    echo Could not install the helper libraries. Copy the messages above and send them to Claude.
    pause
    exit /b 1
)
echo Libraries: OK

rem ---- 3. ffmpeg -------------------------------------------------
if not exist "%~dp0ffmpeg.exe" if not exist "%~dp0..\ffmpeg.exe" if not exist "%~dp0..\..\ffmpeg.exe" (
    where ffmpeg >nul 2>nul
    if errorlevel 1 (
        echo Downloading ffmpeg from gyan.dev ^(about 90 MB^)...
        curl -L --fail -o "%TEMP%\mlm_ffmpeg.zip" https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
        if exist "%TEMP%\mlm_ffmpeg.zip" (
            powershell -NoProfile -Command "Expand-Archive -Force -LiteralPath '%TEMP%\mlm_ffmpeg.zip' -DestinationPath '%TEMP%\mlm_ffmpeg'; $f = Get-ChildItem '%TEMP%\mlm_ffmpeg' -Recurse -Filter ffmpeg.exe | Select-Object -First 1; Copy-Item -LiteralPath $f.FullName -Destination '%~dp0'"
        )
    )
)
if exist "%~dp0ffmpeg.exe" (echo ffmpeg: OK) else if exist "%~dp0..\ffmpeg.exe" (echo ffmpeg: OK ^(folder above^)) else if exist "%~dp0..\..\ffmpeg.exe" (echo ffmpeg: OK ^(two folders above^)) else (where ffmpeg >nul 2>nul && echo ffmpeg: OK || echo ffmpeg: not available - audio checks limited to MP3/FLAC/WAV/AIFF)

rem ---- 4. fpcalc (identify songs by sound) ----------------------
if not exist "%~dp0fpcalc.exe" if not exist "%~dp0..\fpcalc.exe" if not exist "%~dp0..\..\fpcalc.exe" (
    echo Downloading fpcalc ^(Chromaprint, about 3 MB^)...
    curl -L --fail -o "%TEMP%\mlm_fpcalc.zip" https://github.com/acoustid/chromaprint/releases/download/v1.6.1/chromaprint-fpcalc-1.6.1-windows-x86_64.zip
    if exist "%TEMP%\mlm_fpcalc.zip" (
        powershell -NoProfile -Command "Expand-Archive -Force -LiteralPath '%TEMP%\mlm_fpcalc.zip' -DestinationPath '%TEMP%\mlm_fpcalc'; $f = Get-ChildItem '%TEMP%\mlm_fpcalc' -Recurse -Filter fpcalc.exe | Select-Object -First 1; Copy-Item -LiteralPath $f.FullName -Destination '%~dp0'"
    )
)
if exist "%~dp0fpcalc.exe" (echo fpcalc: OK) else if exist "%~dp0..\fpcalc.exe" (echo fpcalc: OK ^(folder above^)) else if exist "%~dp0..\..\fpcalc.exe" (echo fpcalc: OK ^(two folders above^)) else (echo fpcalc: not available - identify by sound is off)

rem ---- 5. Run ----------------------------------------------------
echo.
call %PY% "%~dp0music_manager.py"
echo.
pause
