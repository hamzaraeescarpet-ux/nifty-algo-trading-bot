@echo off
title Setup Windows Auto-Start
cd /d "%~dp0"
echo ======================================================================
echo   Enabling Windows Boot Auto-Start for Nifty Algo Trading Bot...
echo ======================================================================

set "TARGET_SCRIPT=%~dp0start_bot_hidden.vbs"
set "SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\NiftyAlgoBot.vbs"

copy /y "%TARGET_SCRIPT%" "%SHORTCUT_PATH%" >nul

if %errorlevel% equ 0 (
    echo [SUCCESS] Auto-start successfully configured!
    echo Jab bhi aapka laptop on hoga, ye bot automatic background me start ho jayega.
) else (
    echo [ERROR] Failed to configure auto-start.
)

pause
