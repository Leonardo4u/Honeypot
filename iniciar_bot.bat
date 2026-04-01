@echo off
setlocal
cd /d %~dp0
python scheduler.py
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
  echo.
  echo Scheduler encerrou com erro (codigo %EXIT_CODE%).
  echo Verifique as mensagens acima.
  pause
)
endlocal
