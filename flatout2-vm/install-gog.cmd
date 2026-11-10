@echo off
setlocal
rem RemoteSigned applies to this helper process only; saved Windows policy is unchanged.
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0install-gog.ps1"
if errorlevel 1 echo Installation failed. Read the error and logs before retrying.
pause
