@echo off
chcp 65001 >nul
title Midnight 00:01 - Remove
set "DEST=%LOCALAPPDATA%\Midnight 00-01"
echo This removes the app and its shortcuts from this Windows user.
echo Your music, your libraries and their _logs / _cache folders are NOT touched.
choice /c YN /m "Remove Midnight 00:01 now"
if errorlevel 2 exit /b 0
powershell -NoProfile -Command "foreach($d in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Programs'))){ $f=$d+'\Midnight 00-01.lnk'; if(Test-Path $f){Remove-Item $f} }"
if exist "%DEST%" rmdir /s /q "%DEST%"
echo Removed.
pause
