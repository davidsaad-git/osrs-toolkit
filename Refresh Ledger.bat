@echo off
setlocal
title Refresh Quit Smoking Ledger
cd /d "%~dp0"

rem Pick an interpreter once, so a script failure can't cause a second full run.
set "PY="
python --version >nul 2>nul && set "PY=python"
if not defined PY py --version >nul 2>nul && set "PY=py"
if not defined PY (
  echo Python was not found. Install it from python.org, then run this again.
  echo.
  pause
  exit /b 1
)

echo Refreshing hiscores, collection logs, quests and achievements...
echo.
%PY% "%~dp0src\refresh_data.py"
if errorlevel 1 (
  echo.
  echo Refresh failed - see the messages above. Your existing data was left alone.
  echo Trying again usually works if it was a network problem.
  echo.
  pause
  exit /b 1
)

echo.
git add -A >nul 2>nul
git diff --cached --quiet >nul 2>nul
if errorlevel 1 (
  git commit -m "Refresh snapshot" >nul 2>nul
  git pull --rebase >nul 2>nul
  git push >nul 2>nul
  if errorlevel 1 (
    echo Local files updated. Publishing to the website failed - check your internet.
  ) else (
    echo Website updated: https://davidsaad-git.github.io/osrs-toolkit/
  )
) else (
  echo Local files updated. No data changes to publish.
)
echo Reload the toolkit in your browser to see the new snapshot.
echo.
pause
