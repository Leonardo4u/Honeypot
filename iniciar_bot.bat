@echo off
setlocal
cd /d %~dp0
set PYTHONIOENCODING=utf-8
set EDGE_DISABLE_OPERATIONAL_ALERTS_TELEGRAM=1

echo [startup] Sync DB -> CSV (best-effort)...
python picks_log.py --sync-db data/edge_protocol.db > logs\picks_sync_on_startup.log 2>&1
if not "%ERRORLEVEL%"=="0" (
  echo [startup][WARN] sync inicial falhou. Continuando boot do scheduler.
)

python scheduler.py
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
  echo.
  echo Scheduler encerrou com erro (codigo %EXIT_CODE%).
  echo Verifique as mensagens acima.
  pause
)
endlocal
