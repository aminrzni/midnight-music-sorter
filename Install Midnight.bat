@echo off
chcp 65001 >nul
title Midnight 00:01 - Setup
setlocal EnableExtensions
set "SRC=%~dp0app"
set "DEST=%LOCALAPPDATA%\Midnight 00-01"
echo ============================================================
echo  Midnight 00:01 - Music Sorter - setup
echo  Installs the app for this Windows user. Your music is never
echo  touched: the app only copies, and only when you approve.
echo ============================================================
echo.
if not exist "%SRC%\midnight_app.py" (
    echo The "app" folder is missing next to this file. Unzip the WHOLE package first, then run this again.
    pause
    exit /b 1
)

rem ---- 1. Python ------------------------------------------------
set "PY="
python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PY (
    echo Python was not found on this computer.
    choice /c YN /m "Install Python 3.12 now from python.org through winget"
    if errorlevel 2 (
        echo Install Python from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) and run this setup again.
        pause
        exit /b 1
    )
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PY (
    echo Python could not be installed here. Install it from https://www.python.org/downloads/ and run this setup again.
    pause
    exit /b 1
)
echo Python found: %PY%

rem ---- 2. Copy the app ----------------------------------------------
echo.
echo Copying the app to "%DEST%\app" ...
xcopy "%SRC%" "%DEST%\app\" /E /I /Y /Q >nul
if errorlevel 1 (
    echo Could not copy the app. Copy the messages above and send them to Claude.
    pause
    exit /b 1
)

rem ---- 3. Helper libraries ------------------------------------------
echo.
echo Installing helper libraries ^(mutagen, openpyxl, pillow, pywebview, unidecode^)...
call %PY% -m pip install --upgrade mutagen openpyxl pillow pywebview unidecode || call %PY% -m pip install --user --upgrade mutagen openpyxl pillow pywebview unidecode
call %PY% -c "import mutagen, openpyxl, webview, PIL, unidecode" >nul 2>nul
if errorlevel 1 (
    echo Could not install the helper libraries. Copy the messages above and send them to Claude.
    pause
    exit /b 1
)

rem ---- 4. ffmpeg (recommended: exact duplicate checks for every format) ----
echo.
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo ffmpeg was not found.
    choice /c YN /m "Install ffmpeg now through winget (recommended)"
    if not errorlevel 2 winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
) else (
    echo ffmpeg found.
)

rem ---- 5. Shortcuts --------------------------------------------------
echo.
choice /c YN /m "Put shortcuts on the Desktop and in the Start menu"
if not errorlevel 2 (
    powershell -NoProfile -Command "$w=New-Object -ComObject WScript.Shell; foreach($d in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Programs'))){ $s=$w.CreateShortcut($d+'\Midnight 00-01.lnk'); $s.TargetPath='%DEST%\app\Start Midnight App.bat'; $s.WorkingDirectory='%DEST%\app'; $s.WindowStyle=7; $s.Description='Midnight 00:01 - Music Sorter'; $s.Save() }"
    echo Shortcuts created: "Midnight 00-01".
)

echo.
echo ============================================================
echo  Done. Start the app with the "Midnight 00-01" shortcut,
echo  or "%DEST%\app\Start Midnight App.bat".
echo  If ffmpeg was just installed and the app does not see it,
echo  sign out of Windows once and start the app again.
echo ============================================================
choice /c YN /m "Start the app now"
if not errorlevel 2 start "" "%DEST%\app\Start Midnight App.bat"
pause
