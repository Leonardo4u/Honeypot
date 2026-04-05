@echo off
setlocal
cd /d %~dp0
set PYTHONIOENCODING=utf-8
set EDGE_DISABLE_OPERATIONAL_ALERTS_TELEGRAM=1
python scheduler.py
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
  echo.
  echo Scheduler encerrou com erro (codigo %EXIT_CODE%).
  echo Verifique as mensagens acima.
  pause
)
endlocal
