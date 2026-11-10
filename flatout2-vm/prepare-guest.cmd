@echo off
call "%~dp0configure-privacy.cmd"
if errorlevel 1 exit /b 10
if not exist "%ProgramFiles%\FlatOut2VM" mkdir "%ProgramFiles%\FlatOut2VM"
if errorlevel 1 exit /b 10
copy /y "%~dp0guest-status.cmd" "%ProgramFiles%\FlatOut2VM\guest-status.cmd" >nul
if errorlevel 1 exit /b 10
for %%F in (guest-start.cmd guest-start.ps1 guest-install.ps1) do (
    copy /y "%~dp0%%F" "%ProgramFiles%\FlatOut2VM\%%F" >nul
    if errorlevel 1 exit /b 10
)
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -Command ". '%ProgramFiles%\FlatOut2VM\guest-install.ps1'; Install-GuestDispatcher '%~dp0.'"
if errorlevel 1 exit /b 10
set "STARTUP=%ProgramData%\Microsoft\Windows\Start Menu\Programs\Startup"
if not exist "%STARTUP%" mkdir "%STARTUP%"
if errorlevel 1 exit /b 10
> "%STARTUP%\FlatOut2VM.cmd" echo @call "%%ProgramFiles%%\FlatOut2VM\guest-start.cmd" -Automatic
if errorlevel 1 exit /b 10
call "%~dp0install-network.cmd"
exit /b %ERRORLEVEL%
