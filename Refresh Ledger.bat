@echo off
title Refresh OSRS Ledger
cd /d "%~dp0src"
echo Refreshing hiscores + collection logs...
echo.
python refresh_data.py 2>nul || py refresh_data.py
echo.
echo Done. Reload OSRS Toolkit.html in your browser (F5) to see the new snapshot.
pause
