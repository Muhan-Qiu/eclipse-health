@echo off
setlocal
rem V4.3 backend: force the V4.3 source tree, not the V4.2 editable path
rem recorded in the shared backend\.venv.
set "ROOT=%~dp0"
set "PYTHONPATH=%ROOT%backend\src"
"%ROOT%backend\.venv\Scripts\python.exe" -m uvicorn eclipse_health_backend.app:app --host 127.0.0.1 --port 8765
