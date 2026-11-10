@echo off
setlocal
rem RemoteSigned applies to this helper process only; saved Windows policy is unchanged.
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0guest-start.ps1" -Retry -MediaRoot "%~dp0."
if errorlevel 1 (
    echo Installation failed. Read the error and logs before retrying.
    pause
    exit /b 1
)
