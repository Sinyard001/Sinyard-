@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

set "PYEXE=C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

echo.
echo  ============================================
echo   My Notes - Resume Workbench  starting...
echo  ============================================
echo.

echo  Closing any previous instance...
powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue; if($c){ $c | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue } }"

start "" /min "%PYEXE%" server.py

powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 24;$i++){ try{ $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 'http://127.0.0.1:8787/api/health' -ErrorAction Stop; if($r.StatusCode -eq 200){ $ok=$true; break } } catch {}; Start-Sleep -Milliseconds 700 }; if($ok){ Start-Process 'http://127.0.0.1:8787'; exit 0 } else { exit 1 }"

if errorlevel 1 goto fail

echo.
echo  Started OK. The app is now open in your browser.
echo  Keep this window open while using it.
echo  Close this window to stop the app.
echo.
exit /b 0

:fail
echo.
echo  Failed to start. Possible reasons:
echo    1) Port 8787 is already in use.
echo    2) Python is not installed on this computer.
echo.
echo  Keep this window open and send a screenshot to the assistant.
echo.
pause
exit /b 1
