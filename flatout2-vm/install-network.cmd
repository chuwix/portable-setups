@echo off
setlocal
set "LOG=%SystemRoot%\Panther\flatout2-network.log"
echo Installing pinned ARM64 NetKVM package before OOBE > "%LOG%"
"%SystemRoot%\System32\pnputil.exe" /add-driver "%~dp0drivers\NetKVM\netkvm.inf" /install >> "%LOG%" 2>&1
set "RESULT=%ERRORLEVEL%"
echo PnPUtil exit code: %RESULT% >> "%LOG%"
rem Windows Setup OnRequest uses 1 for a successful install needing a reboot.
if "%RESULT%"=="3010" exit /b 1
if not "%RESULT%"=="0" exit /b 10
"%SystemRoot%\System32\pnputil.exe" /enum-devices /class Net /drivers >> "%LOG%" 2>&1
exit /b 0
