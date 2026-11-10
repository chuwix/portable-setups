# Guest-only GOG installation from the read-only FLATOUTGAME CD.
[CmdletBinding()]
param([switch]$Elevated, [string]$RunId, [string]$ManifestIdentity)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'guest-install.ps1')

function Invoke-GuestInstall {
    $script:PreservedSavegame = $null
    Assert-GuestMachine
    $media = Get-GameMedia $PSScriptRoot
    if (-not $Elevated) {
        & (Join-Path $media 'guest-start.ps1') -MediaRoot $media -Retry
        exit 0
    }
    if (-not (Test-GuestAdministrator)) { throw 'Installation requires normal UAC consent.' }
    $parsedRun = [guid]::Empty
    if (-not [guid]::TryParse($RunId, [ref]$parsedRun) -or $parsedRun -eq [guid]::Empty -or
        $ManifestIdentity -cnotmatch '^[0-9a-f]{64}$') { throw 'Invalid installation run identity.' }
    $manifest = Read-GameManifest $media -VerifyPayload
    if ($manifest.identity -cne $ManifestIdentity) { throw 'Game media changed before elevation. Use explicit Retry.' }
    $root = Join-Path $env:ProgramData 'FlatOut2VM'
    Protect-GuestDirectory $root
    $lock = $null
    $run = $null
    try {
        $lockPath = Join-Path $root 'install.lock'
        if (Test-Path -LiteralPath $lockPath) { Assert-NoReparsePoint $lockPath }
        $lock = [IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None')
        Install-GuestDispatcher $media
        $bootId = Get-GuestBootId
        # Never stage payload when both-file identity and the game receipt already match.
        try { $previous = Read-InstalledGame $root $bootId $manifest.identity }
        catch { $previous = $null }
        if ($previous) {
            Set-GuestShortcuts
            Write-Host 'The existing installation is receipt-validated; no payload was copied. Use the Player shortcut.'
            return
        }
        $run = Join-Path $root ('install-' + $RunId)
        if (Test-Path -LiteralPath $run) { throw 'Installation run already exists. Use a new explicit Retry.' }
        Protect-GuestDirectory $run
        $resultPath = Join-Path $run 'result.json'
        $installer = Join-Path $media $script:FlatOutFiles[0]
        $signature = Get-AuthenticodeSignature -LiteralPath $installer
        $publisher = if ($signature.SignerCertificate) {
            $signature.SignerCertificate.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
        } else { '' }
        $publisher = ($publisher -replace '\s+', ' ').Trim()
        if ($signature.Status -ne 'Valid' -or $publisher -notin @('GOG Limited', 'GOG sp. z o.o', 'GOG sp. z o.o.')) {
            throw "GOG signature validation failed: status=$($signature.Status), publisher=$publisher. Do not disable signature checking."
        }
        $payload = Join-Path $run 'payload'
        Protect-GuestDirectory $payload
        foreach ($entry in $manifest.files) {
            Write-Host "Copying and verifying guest payload: $($entry.name)"
            $copy = Join-Path $payload $entry.name
            Copy-Item -LiteralPath (Join-Path $media $entry.name) -Destination $copy
            if ((Get-Item -LiteralPath $copy).Length -ne $entry.size -or
                (Get-FileHash -Algorithm SHA256 -LiteralPath $copy).Hash -ine $entry.sha256) {
                throw "Guest copy integrity failure: $($entry.name)"
            }
        }
        $installer = Join-Path $payload $script:FlatOutFiles[0]
        Initialize-GameDestination
        Write-Host "Installing FlatOut 2. Please wait; logs: $run"
        $process = Start-Process -FilePath $installer -WorkingDirectory $payload -Wait -PassThru -ArgumentList @(
            '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/RESTARTEXITCODE=3010',
            '/DIR="C:\Games\FlatOut2"', ('/LOG="' + (Join-Path $run 'gog-install.log') + '"')
        )
        if ($process.ExitCode -ne 0 -and $process.ExitCode -ne 3010) {
            throw "GOG installer failed with exit code $($process.ExitCode). See $run"
        }
        if (-not (Test-Path -LiteralPath $script:FlatOutGame -PathType Leaf)) {
            throw 'Installer exited without the expected FlatOut2.exe. Installation is not verified.'
        }
        Assert-NoReparsePoint $script:FlatOutGame
        Assert-GameTree $script:FlatOutDestination
        Enable-PlayerSavegame
        $receipt = [ordered]@{
            schema = 2; files = @($manifest.files); manifestIdentity = $manifest.identity
            destination = $script:FlatOutDestination; game = $script:FlatOutGame
            gameSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $script:FlatOutGame).Hash.ToLowerInvariant()
            runId = $RunId; installerExitCode = $process.ExitCode
            rebootRequired = ($process.ExitCode -eq 3010); bootId = $bootId
        }
        $result = @{
            schema = 2; status = 'installed'; runId = $RunId; manifestIdentity = $manifest.identity
            installerExitCode = $process.ExitCode; rebootRequired = ($process.ExitCode -eq 3010)
            preservedSavegame = $script:PreservedSavegame
            gameplayVerified = $false; completed = (Get-Date).ToString('o')
        }
        Write-GuestJson $resultPath $result
        Write-GuestJson (Join-Path $root 'gog-installed.json') $receipt
        Set-GuestShortcuts
        Write-Host 'The known FlatOut 2 desktop shortcut is guarded. Other GOG/Start menu shortcuts may launch directly; use the FlatOut 2 desktop shortcut. Unknown shortcuts were not deleted.'
        Write-Host "Installation validated. The unelevated Player window handles launch. Logs: $run"
        foreach ($entry in $manifest.files) { Remove-Item -LiteralPath (Join-Path $payload $entry.name) }
        Remove-Item -LiteralPath $payload
    } catch {
        if ($run -and (Test-Path -LiteralPath $run)) {
            Write-GuestJson (Join-Path $run 'result.json') @{
                schema = 2; status = 'failed'; runId = $RunId; manifestIdentity = $ManifestIdentity
                error = $_.Exception.Message; completed = (Get-Date).ToString('o')
                preservedSavegame = $script:PreservedSavegame
            }
        }
        throw
    } finally { if ($lock) { $lock.Dispose() } }
}

if ($MyInvocation.InvocationName -ne '.') {
    try { Invoke-GuestInstall }
    catch { Write-Host ('Installation failed: ' + $_.Exception.Message) -ForegroundColor Red; exit 1 }
}
