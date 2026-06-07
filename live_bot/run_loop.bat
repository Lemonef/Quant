@echo off
REM Alternative to Task Scheduler: runs forever, one cycle every 4h. Keep window open.
cd /d "%~dp0"
python paper_bot.py --loop
