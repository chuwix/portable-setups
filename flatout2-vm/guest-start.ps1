# Bounded Player-login dispatcher. Never launch the game with an elevated token.
[CmdletBinding()]
param([switch]$Retry, [switch]$PlayOnly, [switch]$Diagnostics, [switch]$Automatic, [string]$MediaRoot)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'guest-install.ps1')

function Start-ReceiptGame($Installed) {
    if ($Installed.state -eq 'restart-required') {
        Write-Host 'Installation requires a normal Windows restart. Save your work and restart Windows; the next Player login will revalidate and launch the game.'
        return $false
    }
    Start-Process -FilePath $script:FlatOutGame -WorkingDirectory $script:FlatOutDestination | Out-Null
    return $true
}

function Write-GuestStartupFailure([string]$Message) {
    $directory = Join-Path $env:LOCALAPPDATA 'FlatOut2VM'
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $report = Join-Path $directory 'startup-failure.txt'
    @((Get-Date).ToString('o'), $Message,
        'Check the FLATOUTGAME CD and installer logs under C:\ProgramData\FlatOut2VM.',
        'After correcting the problem, use Retry FlatOut 2 installation on the desktop.',
        'If a restart is required, save your work and restart Windows normally. No automatic reboot was requested.') |
        Set-Content -LiteralPath $report -Encoding UTF8
    # A separate viewer must not hold the automatic dispatcher open.
    Start-Process notepad.exe -ArgumentList ('"' + $report + '"') | Out-Null
}

function Invoke-GuestStart {
    if ($env:USERNAME -ine 'Player') { return }
    Assert-GuestMachine
    if (Test-GuestAdministrator) { throw 'Open FlatOut 2 as Player normally, not with Run as administrator.' }
    if ($Diagnostics) {
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
    try { $installed = Read-InstalledGame $root $bootId }
    catch { if (-not $Retry) { throw }; Write-Host ('Retrying after invalid receipt: ' + $_.Exception.Message) }
    if ($installed -and -not $Retry) {
        if (-not (Start-ReceiptGame $installed)) { throw 'Restart required; no game was launched.' }
        return
    }
    if ($PlayOnly) { throw 'No validated installation. Attach the FLATOUTGAME CD and use Retry FlatOut 2 installation.' }
    $media = Get-GameMedia $MediaRoot
    $manifest = Read-GameManifest $media -VerifyPayload
    # A matching receipt is checked before any copy, including explicit retries.
    $matching = $null
    try { $matching = Read-InstalledGame $root $bootId $manifest.identity } catch { Write-Host $_.Exception.Message }
    if ($matching) {
        if (-not (Start-ReceiptGame $matching)) { throw 'Restart required; no game was launched.' }
        return
    }
    $local = Join-Path (Join-Path $env:LOCALAPPDATA 'FlatOut2VM') 'attempts'
    $sessionLock = $null
    New-Item -ItemType Directory -Path $local -Force | Out-Null
    try {
        try { $sessionLock = [IO.File]::Open((Join-Path $local 'dispatcher.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
        catch [IO.IOException] { return }
        if (-not (Register-GuestAttempt $local $manifest.identity -Retry:$Retry)) {
            throw 'This media was already attempted. Use Retry FlatOut 2 installation after checking the failure or UAC denial.'
        }
        $runId = [guid]::NewGuid().ToString()
        Write-Host 'Windows will ask for Yes/No UAC consent to install FlatOut 2. No password should be required for Player.'
        $process = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'RemoteSigned', '-File', ('"' + (Join-Path $media 'install-gog.ps1') + '"'),
            '-Elevated', '-RunId', $runId, '-ManifestIdentity', $manifest.identity
        )
        if ($process.ExitCode -ne 0) { throw "Installation failed (helper exit $($process.ExitCode)). Logs: $root\install-$runId. Use Retry explicitly." }
        $installed = Read-InstalledGame $root $bootId $manifest.identity
        if (-not $installed -or $installed.receipt.runId -cne $runId) { throw 'Installer did not publish a validated result for this run. No game was launched.' }
        if (-not (Start-ReceiptGame $installed)) { throw 'Restart required; no game was launched.' }
    } finally { if ($sessionLock) { $sessionLock.Dispose() } }
}

if ($MyInvocation.InvocationName -ne '.') {
    try { Invoke-GuestStart }
    catch {
        $message = 'FlatOut 2: ' + $_.Exception.Message
        Write-Host $message -ForegroundColor Red
        if ($Automatic) {
            try { Write-GuestStartupFailure $message } catch { Write-Warning 'Could not save startup failure report.' }
        }
        exit 1
    }
}
