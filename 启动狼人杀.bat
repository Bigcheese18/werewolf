@echo off
cd /d C:\Users\21238\Desktop\werewolf
start /B uvicorn werewolf_server:app --host 0.0.0.0 --port 8081
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8081
echo http://127.0.0.1:8081
pause
