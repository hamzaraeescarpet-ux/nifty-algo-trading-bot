@echo off
echo Stopping background Algo Trading Bot...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*run_bot.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host 'Stopped Bot Process PID:' $_.ProcessId }"
echo Bot stopped.
pause
