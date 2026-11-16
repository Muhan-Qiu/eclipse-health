@echo off
setlocal
rem Start the V4.3 backend in a new window, then run the Vite dev server here.
start "eclipse health V4.3 backend" cmd /k "%~dp0run-backend.cmd"
cd /d "%~dp0"
npm run dev
