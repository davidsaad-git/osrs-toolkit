@echo off
title Refresh OSRS Ledger
cd /d "%~dp0src"
echo Refreshing hiscores + collection logs...
echo.
python refresh_data.py 2>nul || py refresh_data.py
echo.
cd /d "%~dp0"
git add -A >nul 2>nul
git commit -m "Refresh snapshot" >nul 2>nul && (
  git push >nul 2>nul && echo Website updated: https://davidsaad-git.github.io/osrs-toolkit/ || echo Local files updated. Push to GitHub failed - check your internet.
) || echo Local files updated. No data changes to publish.
echo Reload OSRS Toolkit.html or the website to see the new snapshot.
pause
