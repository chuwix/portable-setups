# Guest-only GOG installation from the read-only FLATOUTGAME CD.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$media = $PSScriptRoot
$computer = Get-CimInstance Win32_ComputerSystem
if ($computer.Manufacturer -notmatch 'QEMU' -and $computer.Model -notmatch 'QEMU') {
    throw 'Run this helper only inside the dedicated QEMU Windows VM.'
}
$drive = Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DeviceID -eq ([IO.Path]::GetPathRoot($media).TrimEnd('\')) }
if (-not $drive -or $drive.DriveType -ne 5 -or $drive.VolumeName -ne 'FLATOUTGAME') {
    throw 'Run install-gog.cmd from the read-only FLATOUTGAME CD.'
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not [Security.Principal.WindowsPrincipal]::new($identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $process = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList @(
        '-NoProfile', '-NoExit', '-ExecutionPolicy', 'RemoteSigned', '-File', ('"' + $PSCommandPath + '"')
    )
    exit $process.ExitCode
}
$root = Join-Path $env:ProgramData 'FlatOut2VM'
New-Item -ItemType Directory -Path $root -Force | Out-Null
$run = Join-Path $root ('install-' + [guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $run | Out-Null
$result = Join-Path $run 'result.json'
$lock = $null
try {
    $lock = [IO.File]::Open((Join-Path $root 'install.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    $expected = @('setup_flatout_2_1.0_(26697).exe', 'setup_flatout_2_1.0_(26697)-1.bin')
    $manifest = Get-Content -Raw -LiteralPath (Join-Path $media 'game-media.json') | ConvertFrom-Json
    $entries = @($manifest.files)
    if ($manifest.schema -ne 1 -or $entries.Count -ne 2 -or
        (($entries.name | Sort-Object) -join '|') -cne (($expected | Sort-Object) -join '|')) {
        throw 'Unexpected installer manifest. Only the supported GOG FlatOut 2 build is accepted.'
    }
    foreach ($entry in $entries) {
        Write-Host "Verifying game CD: $($entry.name)"
        $file = Get-Item -LiteralPath (Join-Path $media $entry.name)
        if ($file.Length -ne $entry.size -or $file.Length -eq 0 -or
            (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash -ine $entry.sha256) {
            throw "Media integrity failure: $($entry.name)"
        }
    }
    $installer = Join-Path $media $expected[0]
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    $publisher = if ($signature.SignerCertificate) {
        $signature.SignerCertificate.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
    } else { '' }
    $publisher = ($publisher -replace '\s+', ' ').Trim()
    if ($signature.Status -ne 'Valid' -or $publisher -notin @('GOG Limited', 'GOG sp. z o.o', 'GOG sp. z o.o.')) {
        throw "GOG signature validation failed: status=$($signature.Status), publisher=$publisher. Do not disable signature checking."
    }
    $payload = Join-Path $run 'payload'
    New-Item -ItemType Directory -Path $payload | Out-Null
    foreach ($entry in $entries) {
        Write-Host "Copying and verifying guest payload: $($entry.name)"
        $copy = Join-Path $payload $entry.name
        Copy-Item -LiteralPath (Join-Path $media $entry.name) -Destination $copy
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $copy).Hash -ine $entry.sha256) {
            throw "Guest copy integrity failure: $($entry.name)"
        }
    }
    $installer = Join-Path $payload $expected[0]
    $destination = 'C:\Games\FlatOut2'
    $game = Join-Path $destination 'FlatOut2.exe'
    $receipt = Join-Path $root 'gog-installed.json'
    $installHash = ($entries | Where-Object name -eq $expected[0]).sha256
    $alreadyInstalled = $false
    if (Test-Path -LiteralPath $receipt) {
        $previous = Get-Content -Raw -LiteralPath $receipt | ConvertFrom-Json
        $alreadyInstalled = $previous.installerSha256 -eq $installHash -and (Test-Path -LiteralPath $game) -and
            $previous.gameSha256 -eq (Get-FileHash -Algorithm SHA256 -LiteralPath $game).Hash
    }
    if (-not $alreadyInstalled) {
        Write-Host "Installing FlatOut 2. Please wait; log: $(Join-Path $run 'gog-install.log')"
        # Inno Setup flags suppress the wizard and automatic reboot, not signature checks.
        $process = Start-Process -FilePath $installer -WorkingDirectory $payload -Wait -PassThru -ArgumentList @(
            '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/RESTARTEXITCODE=3010',
            '/DIR="C:\Games\FlatOut2"', ('/LOG="' + (Join-Path $run 'gog-install.log') + '"')
        )
        if ($process.ExitCode -ne 0 -and $process.ExitCode -ne 3010) {
            throw "GOG installer failed with exit code $($process.ExitCode). See $run"
        }
        if (-not (Test-Path -LiteralPath $game -PathType Leaf)) {
            throw 'Installer exited without the expected FlatOut2.exe. Installation is not verified.'
        }
        @{ installerSha256 = $installHash; gameSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $game).Hash } |
            ConvertTo-Json | Set-Content -LiteralPath $receipt -Encoding UTF8
    }
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'FlatOut 2.lnk'))
    $shortcut.TargetPath = $game
    $shortcut.WorkingDirectory = $destination
    $shortcut.Save()
    @{ status = 'installed'; game = $game; alreadyInstalled = $alreadyInstalled;
        rebootRequired = (-not $alreadyInstalled -and $process.ExitCode -eq 3010);
        gameplayVerified = $false; completed = (Get-Date).ToString('o') } |
        ConvertTo-Json | Set-Content -LiteralPath $result -Encoding UTF8
    Write-Host "Installed. Use the FlatOut 2 desktop shortcut as Player. Logs: $run"
    Write-Host 'Gameplay, sound, saves, and LAN are not verified by installation.'
    foreach ($entry in $entries) {
        Remove-Item -LiteralPath (Join-Path $payload $entry.name)
    }
    Remove-Item -LiteralPath $payload
} catch {
    @{ status = 'failed'; error = $_.Exception.Message; completed = (Get-Date).ToString('o') } |
        ConvertTo-Json | Set-Content -LiteralPath $result -Encoding UTF8
    Write-Host ("Installation failed: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host "Result and logs: $run"
    Read-Host 'Press Enter to close this failed installation' | Out-Null
    exit 1
} finally {
    if ($lock) { $lock.Dispose() }
}
