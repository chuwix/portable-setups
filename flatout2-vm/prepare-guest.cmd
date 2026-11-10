@echo off
call "%~dp0configure-privacy.cmd"
if errorlevel 1 exit /b 10
if not exist "%ProgramFiles%\FlatOut2VM" mkdir "%ProgramFiles%\FlatOut2VM"
if errorlevel 1 exit /b 10
copy /y "%~dp0guest-status.cmd" "%ProgramFiles%\FlatOut2VM\guest-status.cmd" >nul
if errorlevel 1 exit /b 10
set "STARTUP=%ProgramData%\Microsoft\Windows\Start Menu\Programs\Startup"
if not exist "%STARTUP%" mkdir "%STARTUP%"
if errorlevel 1 exit /b 10
> "%STARTUP%\FlatOut2VM.cmd" echo @call "%%ProgramFiles%%\FlatOut2VM\guest-status.cmd"
if errorlevel 1 exit /b 10
call "%~dp0install-network.cmd"
exit /b %ERRORLEVEL%
