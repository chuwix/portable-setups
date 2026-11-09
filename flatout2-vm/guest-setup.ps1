# Run only inside the Windows guest, in an elevated PowerShell window.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('GOG', 'Steam')]
    [string]$Store,
    [string]$GogInstaller,
    [string]$GameExe
)

$ErrorActionPreference = 'Stop'
$computer = Get-CimInstance Win32_ComputerSystem
if ($computer.Manufacturer -notmatch 'QEMU' -and $computer.Model -notmatch 'QEMU') {
    throw 'This helper is restricted to the dedicated QEMU guest.'
}
if (-not [Security.Principal.WindowsPrincipal]::new(
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script as VMAdmin inside the dedicated VM. Never run it on a physical Windows host.'
}

function Assert-SignedFile([string]$Path, [string]$Publisher) {
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch $Publisher) {
        throw "Installer signature is invalid or unexpected: $Path"
    }
}

Set-NetFirewallProfile -Profile Domain, Private, Public -Enabled True

if ($Store -eq 'Steam') {
    $installer = Join-Path $env:TEMP 'FlatOut2-SteamSetup.exe'
    Invoke-WebRequest 'https://cdn.akamai.steamstatic.com/client/installer/SteamSetup.exe' -OutFile $installer
    Assert-SignedFile $installer 'Valve'
    Start-Process -FilePath $installer -Wait
    Write-Host 'Sign into Steam as Player, then install FlatOut 2 (app 2990).'
} else {
    if (-not $GogInstaller) { throw 'Supply -GogInstaller with your downloaded GOG offline installer.' }
    $installer = (Resolve-Path -LiteralPath $GogInstaller).Path
    Assert-SignedFile $installer 'GOG'
    Start-Process -FilePath $installer -Wait
    Write-Host 'Use the GOG installer to install into C:\Games\FlatOut2.'
}

if ($GameExe) {
    $exe = (Resolve-Path -LiteralPath $GameExe).Path
    if ([IO.Path]::GetFileName($exe) -ine 'flatout2.exe') {
        throw 'GameExe must point to flatout2.exe.'
    }
    if (-not $exe.StartsWith('C:\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'The game must be installed on the guest C: drive.'
    }
    Remove-NetFirewallRule -Name 'FlatOut2-LAN' -ErrorAction SilentlyContinue
    New-NetFirewallRule -Name 'FlatOut2-LAN' -DisplayName 'FlatOut 2 LAN (local subnet)' `
        -Direction Inbound -Action Allow -Program $exe -Profile Private -RemoteAddress LocalSubnet | Out-Null
    Write-Host 'LAN rule added for this executable on Private networks, local subnet only.'
}

Write-Host 'Finish installation, then sign out of VMAdmin and play using the standard Player account.'
