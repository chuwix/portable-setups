@echo off
setlocal
set "AUTOMATIC="
if /i "%~1"=="-Automatic" set "AUTOMATIC=1"
rem RemoteSigned applies to this process only, not saved Windows policy.
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0guest-start.ps1" %*
if errorlevel 1 (
    echo FlatOut 2 did not start. Read the message above; use Retry after correcting the problem.
    if not defined AUTOMATIC pause
    exit /b 1
)
