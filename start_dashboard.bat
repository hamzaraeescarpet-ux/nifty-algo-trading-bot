@echo off
title Nifty 50 Algo Trading Bot - Live Dashboard
echo ========================================================
echo   Launching Nifty 50 Trading Bot Analytics Dashboard
echo ========================================================
echo.
start http://127.0.0.1:5000
python dashboard/app.py
pause
