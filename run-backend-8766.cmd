@echo off
setlocal
rem V4.3 backend on port 8766, for testing while another eclipse health backend
rem (for example an installed V4.2 build) is still using the default 8765.
set "ROOT=%~dp0"
set "PYTHONPATH=%ROOT%backend\src"
"%ROOT%backend\.venv\Scripts\python.exe" -m uvicorn eclipse_health_backend.app:app --host 127.0.0.1 --port 8766
