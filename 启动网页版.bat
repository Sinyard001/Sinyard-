@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

rem 如果服务已经在运行，直接打开浏览器，不再重复启动
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8765/api/health' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if %errorlevel%==0 (
  echo 服务已在运行，正在打开页面...
  start "" "http://127.0.0.1:8765"
  goto :end
)

where python >nul 2>nul
if %errorlevel%==0 (
  python webapp.py
  goto :end
)

set "BUNDLED_PY=C:\Users\admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%BUNDLED_PY%" (
  "%BUNDLED_PY%" webapp.py
  goto :end
)

echo 未找到 Python 运行环境，请先安装 Python 3.10+，或在命令行运行：
echo python webapp.py

:end
endlocal
pause
