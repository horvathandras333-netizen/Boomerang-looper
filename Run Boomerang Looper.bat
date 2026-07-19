@echo off
setlocal
cd /d "%~dp0"

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "Boomerang_Looper.py"
    goto :eof
)

where python >nul 2>nul
if %errorlevel%==0 (
    start "" python "Boomerang_Looper.py"
    goto :eof
)

echo Python was not found on PATH. Please install Python 3 and try again.
pause
