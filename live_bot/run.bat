@echo off
REM Runs ONE bot cycle. Called by Task Scheduler every 4h. Logs to bot_run.log.
cd /d "%~dp0"
python paper_bot.py >> bot_run.log 2>&1
