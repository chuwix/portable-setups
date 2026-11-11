# Bounded Player-login dispatcher. Never launch the game with an elevated token.
[CmdletBinding()]
param([switch]$Retry, [switch]$PlayOnly, [switch]$Diagnostics, [switch]$Automatic, [string]$MediaRoot)
$ErrorActionPreference = 'Stop'

function Initialize-GuestStartupLog {
    $script:startupRunId = [guid]::NewGuid().ToString()
    $script:startupClock = [Diagnostics.Stopwatch]::StartNew()
    $script:startupMode = if ($Diagnostics) { 'diagnostics' } elseif ($Retry) { 'retry' } elseif ($PlayOnly) { 'play-only' } elseif ($Automatic) { 'automatic' } else { 'interactive' }
}

function Get-GuestStartupError($Exception) {
    $chain = @()
    $cancelled = $false
    # Bound exception inspection; never persist messages, command lines or payload data.
    foreach ($depth in 0..7) {
        if ($null -eq $Exception) { break }
        $native = $null
        if ($Exception -is [ComponentModel.Win32Exception]) {
            $native = $Exception.NativeErrorCode
            if ($native -eq 1223) { $cancelled = $true }
        }
        $chain += [ordered]@{ type = $Exception.GetType().FullName; hresult = $Exception.HResult; nativeErrorCode = $native }
        $Exception = $Exception.InnerException
    }
    return [pscustomobject]@{ cancelled = $cancelled; chain = $chain }
}

function Write-GuestStartupStage([string]$Stage, [string]$Progress, $Exception = $null) {
    # Best-effort Player-local diagnostics only. Nothing reads this log to authorize
    # installation, retries or launch; receipts and durable attempt markers still do that.
    try {
        $entry = [ordered]@{
            timestamp = [DateTime]::UtcNow.ToString('o'); mode = $script:startupMode
            runId = $script:startupRunId; pid = $PID; session = [Diagnostics.Process]::GetCurrentProcess().SessionId
            elapsedMs = $script:startupClock.ElapsedMilliseconds; stage = $Stage
        }
        if ($Exception) { $entry.error = Get-GuestStartupError $Exception }
        $directory = Join-Path $env:LOCALAPPDATA 'FlatOut2VM'
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        $entry | ConvertTo-Json -Depth 8 -Compress | Add-Content -LiteralPath (Join-Path $directory 'dispatcher-stages.jsonl') -Encoding UTF8
    } catch { # Diagnostic failures must not change dispatcher state or retry behavior.
    }
    if ($Progress) { Write-Host $Progress }
}

function Start-ReceiptGame($Installed) {
    if ($Installed.state -eq 'restart-required') {
        Write-GuestStartupStage 'restart-required'
        Write-Host 'Installation requires a normal Windows restart. Save your work and restart Windows; the next Player login will revalidate and launch the game.'
        return $false
    }
    Write-GuestStartupStage 'launch-game' 'Starting FlatOut 2 as Player.'
    Start-Process -FilePath $script:FlatOutGame -WorkingDirectory $script:FlatOutDestination | Out-Null
    Write-GuestStartupStage 'game-process-started'
    return $true
}

function Write-GuestStartupFailure([string]$Message) {
    $directory = Join-Path $env:LOCALAPPDATA 'FlatOut2VM'
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $report = Join-Path $directory 'startup-failure.txt'
    @((Get-Date).ToString('o'), $Message,
        ('Informational dispatcher stages (not proof of installation): ' + (Join-Path $directory 'dispatcher-stages.jsonl')),
        'Check the FLATOUTGAME CD and installer logs under C:\ProgramData\FlatOut2VM.',
        'After correcting the problem, use Retry FlatOut 2 installation on the desktop.',
        'If a restart is required, save your work and restart Windows normally. No automatic reboot was requested.') |
        Set-Content -LiteralPath $report -Encoding UTF8
    # A separate viewer must not hold the automatic dispatcher open.
    Start-Process notepad.exe -ArgumentList ('"' + $report + '"') | Out-Null
}

function Invoke-GuestStartCore {
    if ($env:USERNAME -ine 'Player') { return }
    Write-GuestStartupStage 'validate-player'
    Assert-GuestMachine
    if (Test-GuestAdministrator) { throw 'Open FlatOut 2 as Player normally, not with Run as administrator.' }
    if ($Diagnostics) {
        Write-GuestStartupStage 'diagnostics'
        $status = Join-Path $PSScriptRoot 'guest-status.cmd'
        if (Test-Path -LiteralPath $status) { & $status; return }
        $local = Join-Path $env:LOCALAPPDATA 'FlatOut2VM'
        New-Item -ItemType Directory -Path $local -Force | Out-Null
        $report = Join-Path $local 'status.txt'
        @('FlatOut 2 VM diagnostics', ('Generated: ' + (Get-Date).ToString('o')),
            'Installation is not proof of gameplay, sound, saves or LAN compatibility.',
            ('Installer logs/results: ' + (Join-Path $env:ProgramData 'FlatOut2VM')),
            'Repair preserves previous saves in C:\Games\FlatOut2-saves-GUID\Savegame. Close the game and restore selected save files as Player, never as administrator; do not restore links or executables.',
            'Use Retry FlatOut 2 installation after correcting a failed installation or UAC denial.',
            (Get-CimInstance Win32_VideoController | Format-List Name, DriverVersion | Out-String)) |
            Set-Content -LiteralPath $report -Encoding UTF8
        Start-Process notepad.exe -ArgumentList ('"' + $report + '"') | Out-Null
        return
    }
    $root = Join-Path $env:ProgramData 'FlatOut2VM'
    $bootId = Get-GuestBootId
    $installed = $null
    Write-GuestStartupStage 'validate-receipt' 'Checking the installed game and receipt; hash verification may take a while.'
    try { $installed = Read-InstalledGame $root $bootId }
    catch { if (-not $Retry) { throw }; Write-Host ('Retrying after invalid receipt: ' + $_.Exception.Message) }
    if ($installed -and -not $Retry) {
        if (-not (Start-ReceiptGame $installed)) { throw 'Restart required; no game was launched.' }
        return
    }
    if ($PlayOnly) { throw 'No validated installation. Attach the FLATOUTGAME CD and use Retry FlatOut 2 installation.' }
    Write-GuestStartupStage 'find-media' 'Looking for the FLATOUTGAME CD.'
    $media = Get-GameMedia $MediaRoot
    Write-GuestStartupStage 'verify-media' 'Verifying CD payload hashes; this may take several minutes before UAC appears.'
    $manifest = Read-GameManifest $media -VerifyPayload
    # A matching receipt is checked before any copy, including explicit retries.
    $matching = $null
    Write-GuestStartupStage 'validate-matching-receipt'
    try { $matching = Read-InstalledGame $root $bootId $manifest.identity } catch { Write-Host $_.Exception.Message }
    if ($matching) {
        if (-not (Start-ReceiptGame $matching)) { throw 'Restart required; no game was launched.' }
        return
    }
    $local = Join-Path (Join-Path $env:LOCALAPPDATA 'FlatOut2VM') 'attempts'
    $sessionLock = $null
    New-Item -ItemType Directory -Path $local -Force | Out-Null
    try {
        Write-GuestStartupStage 'acquire-lock'
        try { $sessionLock = [IO.File]::Open((Join-Path $local 'dispatcher.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
        catch [IO.IOException] { Write-GuestStartupStage 'dispatcher-busy'; return }
        Write-GuestStartupStage 'register-attempt'
        if (-not (Register-GuestAttempt $local $manifest.identity -Retry:$Retry)) {
            throw 'This media was already attempted. Use Retry FlatOut 2 installation after checking the failure or UAC denial.'
        }
        $runId = $script:startupRunId
        Write-GuestStartupStage 'request-elevation'
        Write-Host 'Windows will ask for Yes/No UAC consent to install FlatOut 2. No password should be required for Player.'
        try {
            $process = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList @(
                '-NoProfile', '-ExecutionPolicy', 'RemoteSigned', '-File', ('"' + (Join-Path $media 'install-gog.ps1') + '"'),
                '-Elevated', '-RunId', $runId, '-ManifestIdentity', $manifest.identity
            )
        } catch {
            $details = Get-GuestStartupError $_.Exception
            $message = if ($details.cancelled) {
                'The elevation request was cancelled or not completed (Windows error 1223). No validated installation was confirmed. Use Retry FlatOut 2 installation explicitly when ready.'
            } else {
                'The installation helper could not be started. Check the local dispatcher stage log for exception types and native error codes; use Retry FlatOut 2 installation explicitly after correcting the problem.'
            }
            throw [Exception]::new($message, $_.Exception)
        }
        Write-GuestStartupStage 'helper-exited'
        if ($process.ExitCode -ne 0) { throw "Installation failed (helper exit $($process.ExitCode)). Logs: $root\install-$runId. Use Retry explicitly." }
        Write-GuestStartupStage 'validate-helper-result' "Rechecking the installed game hashes and this run's result before launch."
        $installed = Read-InstalledGame $root $bootId $manifest.identity
        if (-not $installed -or $installed.receipt.runId -cne $runId) { throw 'Installer did not publish a validated result for this run. No game was launched.' }
        if (-not (Start-ReceiptGame $installed)) { throw 'Restart required; no game was launched.' }
    } finally { if ($sessionLock) { $sessionLock.Dispose() } }
}

function Invoke-GuestStart {
    param([switch]$ContinueStartupLog)
    if (-not $ContinueStartupLog) { Initialize-GuestStartupLog }
    Write-GuestStartupStage 'start'
    try {
        Invoke-GuestStartCore
    } catch {
        Write-GuestStartupStage 'failed' -Exception $_.Exception
        throw
    } finally { Write-GuestStartupStage 'finished' }
}

Initialize-GuestStartupLog
try {
    if ($MyInvocation.InvocationName -ne '.') { Write-GuestStartupStage 'load-installer-support' }
    . (Join-Path $PSScriptRoot 'guest-install.ps1')
    if ($MyInvocation.InvocationName -ne '.') { Invoke-GuestStart -ContinueStartupLog }
} catch {
    if ($MyInvocation.InvocationName -eq '.') { throw }
    Write-GuestStartupStage 'startup-failed' -Exception $_.Exception
    $message = 'FlatOut 2: ' + $_.Exception.Message
    Write-Host $message -ForegroundColor Red
    if ($Automatic) {
        try { Write-GuestStartupFailure $message } catch { Write-Warning 'Could not save startup failure report.' }
    }
    exit 1
}
