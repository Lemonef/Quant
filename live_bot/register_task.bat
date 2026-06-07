@echo off
REM Registers a Windows scheduled task that runs the bot every 4 hours.
REM Run this ONCE (right-click -> Run as administrator).
cd /d "%~dp0"
schtasks /Create /TN "QuantPaperBot" /TR "\"%~dp0run.bat\"" /SC HOURLY /MO 4 /F /RL HIGHEST
echo.
echo Created scheduled task "QuantPaperBot" - runs every 4 hours.
echo   View / edit:   taskschd.msc   (look for QuantPaperBot)
echo   Run now:       schtasks /Run /TN QuantPaperBot
echo   Remove:        schtasks /Delete /TN QuantPaperBot /F
echo   Check signals: python status.py
pause
