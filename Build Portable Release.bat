@echo off
title Building Boomerang Looper Portable Release...
python build_portable.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Build failed with error code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)
echo.
echo Build succeeded! Check the 'dist' directory for BoomerangLooper.exe and BoomerangLooper_Portable.zip.
pause
