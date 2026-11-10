@echo off
setlocal
if /i not "%USERNAME%"=="Player" exit /b 0
set "OUT=%LOCALAPPDATA%\FlatOut2VM"
if not exist "%OUT%" mkdir "%OUT%"
if not exist "%OUT%" exit /b 1
set "REPORT=%OUT%\status.txt"
> "%REPORT%" echo FlatOut 2 VM - Windows startup diagnostics
>> "%REPORT%" echo Game compatibility is NOT verified. This is not a game-ready status.
>> "%REPORT%" echo Generated: %DATE% %TIME%
>> "%REPORT%" echo Startup run ID: %RANDOM%-%RANDOM%
>> "%REPORT%" echo.
whoami /user >> "%REPORT%" 2>&1
whoami /groups >> "%REPORT%" 2>&1
>> "%REPORT%" echo.
>> "%REPORT%" echo NETWORK CONFIGURATION - addresses do not prove internet or LAN game connectivity
ipconfig /all >> "%REPORT%" 2>&1
>> "%REPORT%" echo.
>> "%REPORT%" echo DISPLAY DEVICES - Basic Display Driver is not proof of graphics acceleration
pnputil /enum-devices /class Display /drivers >> "%REPORT%" 2>&1
>> "%REPORT%" echo If PnP lists no display devices, use the DirectX adapter details below.
>> "%REPORT%" echo.
>> "%REPORT%" echo DirectX report: %OUT%\dxdiag.txt
if exist "%OUT%\dxdiag.txt" del "%OUT%\dxdiag.txt"
if exist "%OUT%\dxdiag.txt" (
    >> "%REPORT%" echo ERROR: Cannot remove the previous DirectX report. Refusing stale results.
    start "" "%SystemRoot%\System32\notepad.exe" "%REPORT%"
    exit /b 1
)
start "" /wait "%SystemRoot%\System32\dxdiag.exe" /whql:off /t "%OUT%\dxdiag.txt"
if errorlevel 1 >> "%REPORT%" echo WARNING: dxdiag failed.
if not exist "%OUT%\dxdiag.txt" >> "%REPORT%" echo WARNING: DirectX report was not created.
if exist "%OUT%\dxdiag.txt" (
    >> "%REPORT%" echo DIRECTX ADAPTER DETAILS - feature levels alone do not prove hardware acceleration
    findstr /c:"Card name:" /c:"Driver Name:" /c:"Driver Model:" /c:"Feature Levels:" /c:"DDI Version:" "%OUT%\dxdiag.txt" >> "%REPORT%"
)
>> "%REPORT%" echo.
>> "%REPORT%" echo Setup logs: C:\Windows\Panther\flatout2-network.log and flatout2-privacy.log
>> "%REPORT%" echo Store sign-in and game installation are not automated yet.
start "" "%SystemRoot%\System32\notepad.exe" "%REPORT%"
exit /b 0
