@echo off
cd /d "%~dp0"
echo Starting server...
start "Django Server" cmd /c "python manage.py runserver 8000"
timeout /t 3 /nobreak >nul
start http://localhost:8000/
echo Browser opened. Close the "Django Server" window to stop.
