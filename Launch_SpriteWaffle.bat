@echo off
cd /d "%~dp0"
start "SpriteWaffle server" cmd /k ".venv\Scripts\spritewaffle.exe ui"
timeout /t 5 /nobreak >nul
start "" http://127.0.0.1:8765
