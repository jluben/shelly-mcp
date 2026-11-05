@echo off
set SHELLY_CONFIG=C:\Users\josh\Projects\shelly-mcp\shelly-config.json
set PYTHONUNBUFFERED=1
cd /d C:\Users\josh\Projects\shelly-mcp
"C:\Users\josh\Projects\shelly-mcp\.venv\Scripts\python.exe" -u -m shelly_mcp
