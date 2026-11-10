@echo off
setlocal
set "LOG=%SystemRoot%\Panther\flatout2-privacy.log"
echo Applying guest privacy defaults before OOBE > "%LOG%"
call :policy "HKLM\SOFTWARE\Policies\Microsoft\Windows\LocationAndSensors" DisableLocation 1
if errorlevel 1 exit /b 10
call :policy "HKLM\SOFTWARE\Policies\Microsoft\FindMyDevice" AllowFindMyDevice 0
if errorlevel 1 exit /b 10
call :policy "HKLM\SOFTWARE\Policies\Microsoft\Windows\AdvertisingInfo" DisabledByGroupPolicy 1
if errorlevel 1 exit /b 10
call :policy "HKLM\SOFTWARE\Policies\Microsoft\Windows\DataCollection" AllowTelemetry 1
if errorlevel 1 exit /b 10
call :policy "HKLM\SOFTWARE\Policies\Microsoft\InputPersonalization" AllowInputPersonalization 0
if errorlevel 1 exit /b 10
rem Seed the user-scoped tailored-experiences policy for newly created accounts.
reg load HKU\FlatOut2Default "%SystemDrive%\Users\Default\NTUSER.DAT" >> "%LOG%" 2>&1
if errorlevel 1 exit /b 10
call :policy "HKU\FlatOut2Default\Software\Policies\Microsoft\Windows\CloudContent" DisableTailoredExperiencesWithDiagnosticData 1
set "RESULT=%ERRORLEVEL%"
reg unload HKU\FlatOut2Default >> "%LOG%" 2>&1
if errorlevel 1 exit /b 10
if not "%RESULT%"=="0" exit /b 10
rem Hide the choice screen only after all privacy defaults have been applied.
call :policy "HKLM\SOFTWARE\Policies\Microsoft\Windows\OOBE" DisablePrivacyExperience 1
if errorlevel 1 exit /b 10
echo Privacy defaults applied successfully. >> "%LOG%"
exit /b 0

:policy
reg add "%~1" /v "%~2" /t REG_DWORD /d "%~3" /f >> "%LOG%" 2>&1
exit /b %ERRORLEVEL%
