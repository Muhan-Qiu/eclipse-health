@echo off
setlocal
rem Start the V4.3 backend on 8766 and point the Vite dev server at it.
start "eclipse health V4.3 backend 8766" cmd /k "%~dp0run-backend-8766.cmd"
cd /d "%~dp0"
set "VITE_API_BASE=http://127.0.0.1:8766/api/v1"
npm run dev
