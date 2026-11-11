@echo off
title Google Sheets Re-Authentication & Cloud Sync
cd /d "%~dp0"
echo ========================================================
echo Google Sheets Re-Authentication & GitHub Secrets Update
echo ========================================================
echo.
python scripts\refresh_google_token.py
echo.
echo ========================================================
echo Done! You can press any key to close this window.
echo ========================================================
pause
