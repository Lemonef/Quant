@echo off
REM One-time setup: install Python libs the bot needs.
cd /d "%~dp0"
echo Installing dependencies...
python -m pip install --upgrade pip
python -m pip install requests pandas numpy
echo.
echo Testing one cycle...
python paper_bot.py
echo.
echo Setup done. Next: run register_task.bat to schedule it every 4h.
pause
