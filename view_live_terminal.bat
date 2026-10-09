@echo off
title Nifty 50 Bot - Live Terminal Feed
cd /d "%~dp0"
echo ======================================================================
echo   Streaming Live Bot Output (Press Ctrl+C to close viewer)
echo ======================================================================
powershell -Command "if (Test-Path 'logs\bot.log') { Get-Content 'logs\bot.log' -Wait -Tail 30 } else { echo 'No logs yet. Bot is starting up...'; pause }"
