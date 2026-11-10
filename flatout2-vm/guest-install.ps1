# Shared guest contracts. Dot-source this file; it performs no installation.
$script:FlatOutFiles = @('setup_flatout_2_1.0_(26697).exe', 'setup_flatout_2_1.0_(26697)-1.bin')
$script:FlatOutDestination = 'C:\Games\FlatOut2'
$script:FlatOutGame = 'C:\Games\FlatOut2\FlatOut2.exe'

function Test-GuestAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-GuestMachine {
    $computer = Get-CimInstance Win32_ComputerSystem
    if ($computer.Manufacturer -notmatch 'QEMU' -and $computer.Model -notmatch 'QEMU') {
        throw 'Run this helper only inside the dedicated QEMU Windows VM.'
    }
}

function Assert-NoReparsePoint([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    while ($null -ne $item) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing redirected path: $Path" }
        if ($item -is [IO.FileInfo]) { $item = $item.Directory } else { $item = $item.Parent }
    }
}

function Get-ManifestIdentity($Files) {
    $canonical = (@($Files | Sort-Object name | ForEach-Object {
        '{0}|{1}|{2}' -f $_.name, ([long]$_.size).ToString([Globalization.CultureInfo]::InvariantCulture), $_.sha256.ToLowerInvariant()
    }) -join "`n")
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($canonical)))).Replace('-', '').ToLowerInvariant() }
    finally { $hash.Dispose() }
}

function Assert-ManifestFiles($Files) {
    $entries = @($Files)
    if ($entries.Count -ne 2 -or
        (($entries.name | Sort-Object) -join '|') -cne (($script:FlatOutFiles | Sort-Object) -join '|')) {
        throw 'Unexpected installer manifest. Only the supported GOG FlatOut 2 build is accepted.'
    }
    foreach ($entry in $entries) {
        if ($entry.size -isnot [ValueType] -or $entry.size -is [bool] -or
            [decimal]$entry.size -le 0 -or [decimal]$entry.size -gt [long]::MaxValue -or
            [decimal]$entry.size -ne [math]::Truncate([decimal]$entry.size) -or
            $entry.sha256 -isnot [string] -or $entry.sha256 -cnotmatch '^[0-9a-fA-F]{64}$') {
            throw 'Invalid manifest size or SHA256.'
        }
    }
}

function Read-GameManifest([string]$Media, [switch]$VerifyPayload) {
    $manifest = Get-Content -Raw -LiteralPath (Join-Path $Media 'game-media.json') | ConvertFrom-Json
    if ($manifest.schema -ne 1) { throw 'Unsupported game media schema.' }
    Assert-ManifestFiles $manifest.files
    if ($VerifyPayload) {
        foreach ($entry in $manifest.files) {
            $file = Get-Item -LiteralPath (Join-Path $Media $entry.name)
            if ($file -isnot [IO.FileInfo] -or $file.Length -ne $entry.size -or
                (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash -ine $entry.sha256) {
                throw "Media integrity failure: $($entry.name)"
            }
        }
    }
    return [pscustomobject]@{ files = @($manifest.files); identity = (Get-ManifestIdentity $manifest.files) }
}

function Get-GameMedia([string]$RequestedMedia) {
    $candidates = @(Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -eq 5 -and $_.VolumeName -ceq 'FLATOUTGAME' })
    if ($candidates.Count -ne 1) { throw 'Attach exactly one read-only FLATOUTGAME CD, then use Retry FlatOut 2 installation.' }
    $media = $candidates[0].DeviceID + '\'
    if ($RequestedMedia -and [IO.Path]::GetFullPath($RequestedMedia).TrimEnd('\') -ine $media.TrimEnd('\')) {
        throw 'Run install-gog.cmd from the read-only FLATOUTGAME CD root.'
    }
    return $media
}

function Get-GuestBootId {
    return (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')
}

function Protect-GuestDirectory([string]$Path) {
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
    Assert-NoReparsePoint $Path
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
    foreach ($sid in @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-32-545')) {
        $rights = if ($sid -eq 'S-1-5-32-545') { 'ReadAndExecute' } else { 'FullControl' }
        $rule = [Security.AccessControl.FileSystemAccessRule]::new(
            [Security.Principal.SecurityIdentifier]::new($sid), $rights, 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Assert-ProtectedGuestPath([string]$Path) {
    Assert-NoReparsePoint $Path
    $acl = Get-Acl -LiteralPath $Path
    $trusted = @('S-1-5-18', 'S-1-5-32-544')
    if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $trusted) { throw "Untrusted owner: $Path" }
    $writeMask = [Security.AccessControl.FileSystemRights]'Write,Delete,DeleteSubdirectoriesAndFiles,ChangePermissions,TakeOwnership'
    foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
        if ($rule.AccessControlType -eq 'Allow' -and ($rule.FileSystemRights -band $writeMask) -and
            $rule.IdentityReference.Value -notin $trusted) { throw "Unprotected receipt/helper path: $Path" }
    }
}

function Protect-GuestFile([string]$Path) {
    Assert-NoReparsePoint $Path
    $acl = [Security.AccessControl.FileSecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
    foreach ($sid in @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-32-545')) {
        $rights = if ($sid -eq 'S-1-5-32-545') { 'ReadAndExecute' } else { 'FullControl' }
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            [Security.Principal.SecurityIdentifier]::new($sid), $rights, 'Allow'))
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Get-DestinationSecurity([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    $acl = Get-Acl -LiteralPath $Path
    $raw = [Security.AccessControl.RawSecurityDescriptor]::new($acl.GetSecurityDescriptorBinaryForm(), 0)
    return [pscustomobject]@{
        reparse = [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
        directory = $item.PSIsContainer
        owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
        nullDacl = ($null -eq $raw.DiscretionaryAcl)
        rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]) | ForEach-Object {
            [pscustomobject]@{ sid = $_.IdentityReference.Value; allow = ($_.AccessControlType -eq 'Allow')
                rights = [long]$_.FileSystemRights; inheritOnly = [bool]($_.PropagationFlags -band 2) }
        })
    }
}

function Assert-DestinationSecurity([string]$Path, [switch]$VolumeRoot) {
    $security = Get-DestinationSecurity $Path
    $trusted = @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')
    $failure = 'Preserve/back up existing data and ask an administrator to review the destination offline. No ownership or ACL takeover was attempted.'
    if ($security.reparse) { throw "Redirected destination/ancestor: $Path. $failure" }
    if ($security.nullDacl) { throw "Missing destination DACL: $Path. $failure" }
    if ($security.owner -notin $trusted) { throw "Untrusted destination owner: $Path. $failure" }
    # On the volume root only, CreateDirectories cannot replace an existing protected child.
    $writeMask = 0xD0156
    if ($VolumeRoot) { $writeMask = $writeMask -band (-bnot 4) }
    foreach ($rule in $security.rules) {
        if ($rule.allow -and -not $rule.inheritOnly -and $rule.sid -notin $trusted -and
            ($rule.rights -band $writeMask)) { throw "Writable destination/ancestor: $Path. $failure" }
    }
}

function New-SecureGameDirectory([string]$Path) {
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
    foreach ($sid in @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-32-545')) {
        $rights = if ($sid -eq 'S-1-5-32-545') { 'ReadAndExecute' } else { 'FullControl' }
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            [Security.Principal.SecurityIdentifier]::new($sid), $rights, 'ContainerInherit,ObjectInherit', 'None', 'Allow'))
    }
    # CreateDirectory fails on a raced-in existing name and applies security at creation.
    if (-not ('FlatOut2SecureDirectory' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class FlatOut2SecureDirectory {
    [StructLayout(LayoutKind.Sequential)]
    public struct SecurityAttributes { public int Length; public IntPtr Descriptor; public int Inherit; }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool CreateDirectory(string path, ref SecurityAttributes attributes);
}
'@
    }
    $bytes = $acl.GetSecurityDescriptorBinaryForm()
    $descriptor = [Runtime.InteropServices.Marshal]::AllocHGlobal($bytes.Length)
    try {
        [Runtime.InteropServices.Marshal]::Copy($bytes, 0, $descriptor, $bytes.Length)
        $attributes = [FlatOut2SecureDirectory+SecurityAttributes]::new()
        $attributes.Length = [Runtime.InteropServices.Marshal]::SizeOf($attributes)
        $attributes.Descriptor = $descriptor
        if (-not [FlatOut2SecureDirectory]::CreateDirectory($Path, [ref]$attributes)) {
            throw "Could not securely create destination $Path (Windows error $([Runtime.InteropServices.Marshal]::GetLastWin32Error())). Existing data was not taken over."
        }
    } finally { [Runtime.InteropServices.Marshal]::FreeHGlobal($descriptor) }
    Assert-DestinationSecurity $Path
}

function Initialize-GameDestination {
    $paths = [Collections.Generic.List[string]]::new()
    $path = $script:FlatOutDestination
    while ($path) {
        $paths.Insert(0, $path)
        $parent = Split-Path -Parent $path
        if ($parent -eq $path) { break }
        $path = $parent
    }
    foreach ($path in $paths) {
        if (Test-Path -LiteralPath $path) {
            Assert-DestinationSecurity $path -VolumeRoot:($path -eq $paths[0])
            if (-not (Get-Item -LiteralPath $path -Force).PSIsContainer) { throw "Destination ancestor is not a directory: $path" }
        } else {
            # The already-validated parent cannot delete or replace this child as Player.
            New-SecureGameDirectory $path
        }
    }
    Preserve-RepairSavegame
    Assert-GameTree $script:FlatOutDestination
    # Only a fully validated trusted tree may have its destination ACL protected.
    Protect-GuestDirectory $script:FlatOutDestination
    Assert-DestinationSecurity $script:FlatOutDestination
}

function Get-PlayerSid {
    return ([Security.Principal.NTAccount]::new($env:COMPUTERNAME, 'Player')).Translate([Security.Principal.SecurityIdentifier]).Value
}

function Assert-RepairSaveRoot([string]$Path) {
    $security = Get-DestinationSecurity $Path
    if ($security.reparse -or -not $security.directory -or $security.nullDacl -or
        $security.owner -notin @('S-1-5-18', 'S-1-5-32-544')) {
        throw 'Savegame root is redirected or untrusted. Export saves deliberately as Player and ask an administrator to review; no data was changed.'
    }
    $player = Get-PlayerSid
    foreach ($rule in $security.rules) {
        if (-not $rule.allow -or $rule.sid -in @('S-1-5-18', 'S-1-5-32-544')) { continue }
        $allowed = if ($rule.sid -eq $player) {
            if ($rule.inheritOnly) { 0x1301bf } else { 0x1201ff }
        } else { 0x1200a9 }
        if ($rule.rights -band (-bnot $allowed)) {
            throw 'Savegame ACL exceeds the narrow Player-save policy. Preserve/export saves and request administrator review.'
        }
    }
}

function Open-SaveInspectionHandle([string]$Path, [switch]$RenameRoot) {
    if (-not ('FlatOut2SaveInspection' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class FlatOut2SaveInspection {
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern SafeFileHandle CreateFile(string path, uint access, uint share, IntPtr security, uint disposition, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool GetFileInformationByHandleEx(SafeFileHandle file, int kind, out AttributeTag data, uint size);
    public struct AttributeTag { public uint Attributes; public uint Tag; }
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    public struct RenameInfo { public uint Replace; public IntPtr Root; public uint Length; public char Name; }
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool SetFileInformationByHandle(SafeFileHandle file, int kind, IntPtr data, uint size);
    public static void Rename(SafeFileHandle file, string destination) {
        byte[] name = System.Text.Encoding.Unicode.GetBytes(destination);
        int offset = (int)Marshal.OffsetOf(typeof(RenameInfo), "Name");
        int size = offset + name.Length;
        IntPtr buffer = Marshal.AllocHGlobal(size);
        try {
            for (int i=0; i<size; i++) Marshal.WriteByte(buffer, i, 0);
            Marshal.WriteInt32(buffer, (int)Marshal.OffsetOf(typeof(RenameInfo), "Length"), name.Length);
            Marshal.Copy(name, 0, IntPtr.Add(buffer, offset), name.Length);
            if (!SetFileInformationByHandle(file, 3, buffer, (uint)size))
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        } finally { Marshal.FreeHGlobal(buffer); }
    }
}
'@
    }
    # Pin names and deny concurrent write handles (including reparse/ACL mutation).
    # The root's DELETE access is used only for handle-based rename, never child writes.
    $access = if ($RenameRoot) { 0x10000 } else { 0 }
    $handle = [FlatOut2SaveInspection]::CreateFile($Path, $access, 1, [IntPtr]::Zero, 3, 0x02200000, [IntPtr]::Zero)
    try {
        if ($handle.IsInvalid) { throw "Save inspection could not pin $Path. Close the game and retry; saves were preserved." }
        $tag = [FlatOut2SaveInspection+AttributeTag]::new()
        if (-not [FlatOut2SaveInspection]::GetFileInformationByHandleEx($handle, 9, [ref]$tag, 8) -or ($tag.Attributes -band 0x400)) {
            throw "Save inspection rejected a redirect or inaccessible entry: $Path. No installer was started."
        }
        return $handle
    } catch { $handle.Dispose(); throw }
}

function Assert-BoundedSaveTree([string]$Path, [switch]$RootPinned) {
    $handles = [Collections.Generic.List[IDisposable]]::new()
    $pending = [Collections.Generic.Queue[object]]::new()
    $pending.Enqueue(@($Path, 0))
    $count = 0
    try {
        while ($pending.Count) {
            $entry = $pending.Dequeue()
            $count++
            if ($count -gt 4096 -or $entry[1] -gt 16) {
                throw 'Save export exceeds 4096 entries or 16 levels. Export deliberately as Player before repair; no installer was started.'
            }
            if (-not ($RootPinned -and $count -eq 1)) { $handles.Add((Open-SaveInspectionHandle $entry[0])) }
            $item = Get-Item -LiteralPath $entry[0] -Force
            if ($item.PSIsContainer) {
                foreach ($child in Get-ChildItem -LiteralPath $entry[0] -Force) {
                    if (($count + $pending.Count) -ge 4096) {
                        throw 'Save export exceeds 4096 entries. Export deliberately as Player before repair; no installer was started.'
                    }
                    $pending.Enqueue(@($child.FullName, ($entry[1] + 1)))
                }
            }
        }
    } finally { foreach ($handle in $handles) { $handle.Dispose() } }
}

function Move-PinnedSaveRoot($Handle, [string]$Source, [string]$Destination) {
    [FlatOut2SaveInspection]::Rename($Handle, $Destination)
}

function Preserve-RepairSavegame {
    $save = Join-Path $script:FlatOutDestination 'Savegame'
    if (-not (Test-Path -LiteralPath $save)) { return }
    # Root cannot be replaced by Player: protected game parent, trusted root owner, no DELETE.
    Assert-DestinationSecurity $script:FlatOutDestination
    $handle = Open-SaveInspectionHandle $save -RenameRoot
    try {
        Assert-RepairSaveRoot $save
        Assert-BoundedSaveTree $save -RootPinned
        $parent = Split-Path -Parent $script:FlatOutDestination
        Assert-DestinationSecurity $parent
        $archive = Join-Path $parent ('FlatOut2-saves-' + [guid]::NewGuid().ToString())
        New-SecureGameDirectory $archive
        # Rename only the pinned root. Never copy, change ACLs, or write in Player content.
        # Later descendant changes remain inert in the archive, never an elevated restore source.
        Move-PinnedSaveRoot $handle $save (Join-Path $archive 'Savegame')
        $script:PreservedSavegame = Join-Path $archive 'Savegame'
    } finally { $handle.Dispose() }
    Write-Host "Saves preserved without overwriting at $archive\Savegame. After repair, close the game and restore selected save files as Player (never as administrator). Do not restore links or executables."
}

function Assert-GameTree([string]$Path) {
    Assert-DestinationSecurity $Path
    foreach ($child in @(Get-ChildItem -LiteralPath $Path -Force)) {
        # Inspect before recursion; never follow an existing junction, including Savegame.
        Assert-DestinationSecurity $child.FullName
        if ($child.PSIsContainer) { Assert-GameTree $child.FullName }
    }
}

function Enable-PlayerSavegame {
    $save = Join-Path $script:FlatOutDestination 'Savegame'
    if (-not (Test-Path -LiteralPath $save)) { New-SecureGameDirectory $save }
    Assert-GameTree $save
    $player = ([Security.Principal.NTAccount]::new($env:COMPUTERNAME, 'Player')).Translate([Security.Principal.SecurityIdentifier])
    $acl = Get-Acl -LiteralPath $save
    # Children may be replaced for saving; the Savegame root itself cannot be deleted by Player.
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($player,
        'ReadAndExecute,Write,DeleteSubdirectoriesAndFiles', 'Allow'))
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($player,
        'Modify', 'ContainerInherit,ObjectInherit', 'InheritOnly', 'Allow'))
    Set-Acl -LiteralPath $save -AclObject $acl
}

function Assert-GameLaunchPaths {
    $path = $script:FlatOutGame
    while ($path) {
        $parent = Split-Path -Parent $path
        Assert-DestinationSecurity $path -VolumeRoot:([string]::IsNullOrEmpty($parent) -or $parent -eq $path)
        if ($parent -eq $path) { break }
        $path = $parent
    }
}

function Write-GuestJson([string]$Path, $Value) {
    $temporary = $Path + '.' + [guid]::NewGuid().ToString() + '.tmp'
    $Value | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Protect-GuestFile $temporary
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Get-ReceiptState($Receipt, [string]$BootId, [string]$ExpectedIdentity = '') {
    if ($Receipt.schema -ne 2) { throw 'Unsupported installed-game receipt.' }
    Assert-ManifestFiles $Receipt.files
    $identity = Get-ManifestIdentity $Receipt.files
    $parsedRun = [guid]::Empty
    if ($Receipt.manifestIdentity -cne $identity -or ($ExpectedIdentity -and $identity -cne $ExpectedIdentity) -or
        -not [guid]::TryParse([string]$Receipt.runId, [ref]$parsedRun) -or $parsedRun -eq [guid]::Empty -or
        $Receipt.destination -cne $script:FlatOutDestination -or $Receipt.game -cne $script:FlatOutGame -or
        $Receipt.gameSha256 -cnotmatch '^[0-9a-f]{64}$' -or $Receipt.installerExitCode -notin @(0, 3010) -or
        $Receipt.rebootRequired -isnot [bool] -or $Receipt.rebootRequired -ne ($Receipt.installerExitCode -eq 3010)) {
        throw 'Invalid installed-game receipt binding.'
    }
    # PowerShell 7.5+ deserializes ISO JSON dates; Windows PowerShell returns strings.
    $receiptBoot = if ($Receipt.bootId -is [datetime]) { $Receipt.bootId.ToUniversalTime().ToString('o') } else { [string]$Receipt.bootId }
    $installedBoot = [DateTimeOffset]::ParseExact($receiptBoot, 'o', [Globalization.CultureInfo]::InvariantCulture)
    $currentBoot = [DateTimeOffset]::ParseExact($BootId, 'o', [Globalization.CultureInfo]::InvariantCulture)
    if ($currentBoot -lt $installedBoot) { throw 'Receipt boot time is in the future.' }
    if ($Receipt.rebootRequired -and $currentBoot -le $installedBoot) { return 'restart-required' }
    return 'ready'
}

function Read-InstalledGame([string]$Root, [string]$BootId, [string]$ExpectedIdentity = '') {
    $path = Join-Path $Root 'gog-installed.json'
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    Assert-ProtectedGuestPath $Root
    Assert-ProtectedGuestPath $path
    $receipt = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
    $state = Get-ReceiptState $receipt $BootId $ExpectedIdentity
    Assert-GameLaunchPaths
    Assert-NoReparsePoint $script:FlatOutGame
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $script:FlatOutGame).Hash -ine $receipt.gameSha256) {
        throw 'Installed game hash does not match its protected receipt. Use explicit Retry.'
    }
    $resultPath = Join-Path (Join-Path $Root ('install-' + $receipt.runId)) 'result.json'
    Assert-ProtectedGuestPath (Split-Path -Parent $resultPath)
    Assert-ProtectedGuestPath $resultPath
    $result = Get-Content -Raw -LiteralPath $resultPath | ConvertFrom-Json
    if ($result.schema -ne 2 -or $result.status -cne 'installed' -or $result.runId -cne $receipt.runId -or
        $result.manifestIdentity -cne $receipt.manifestIdentity -or $result.installerExitCode -ne $receipt.installerExitCode -or
        $result.rebootRequired -ne $receipt.rebootRequired) { throw 'Missing or inconsistent successful installer result.' }
    return [pscustomobject]@{ receipt = $receipt; state = $state }
}

function Register-GuestAttempt([string]$Directory, [string]$Identity, [switch]$Retry) {
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    $path = Join-Path $Directory ($Identity + '.json')
    if ((Test-Path -LiteralPath $path) -and -not $Retry) { return $false }
    $mode = if ($Retry) { [IO.FileMode]::Create } else { [IO.FileMode]::CreateNew }
    try { $stream = [IO.File]::Open($path, $mode, [IO.FileAccess]::Write, [IO.FileShare]::None) }
    catch [IO.IOException] { return $false }
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes(('{"manifestIdentity":"' + $Identity + '","attempted":"' + (Get-Date).ToString('o') + '"}'))
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally { $stream.Dispose() }
    return $true
}

function Install-GuestDispatcher([string]$Source) {
    $target = Join-Path $env:ProgramFiles 'FlatOut2VM'
    Protect-GuestDirectory $target
    foreach ($name in @('guest-start.cmd', 'guest-start.ps1', 'guest-install.ps1')) {
        Assert-ProtectedGuestPath $target
        if (Test-Path -LiteralPath (Join-Path $target $name)) { Assert-ProtectedGuestPath (Join-Path $target $name) }
        Copy-Item -LiteralPath (Join-Path $Source $name) -Destination (Join-Path $target $name) -Force
        Protect-GuestFile (Join-Path $target $name)
        Assert-ProtectedGuestPath (Join-Path $target $name)
    }
    $startup = Join-Path ([Environment]::GetFolderPath('CommonStartup')) 'FlatOut2VM.cmd'
    ('@call "' + (Join-Path $target 'guest-start.cmd') + '" -Automatic') | Set-Content -LiteralPath $startup -Encoding ASCII
    Set-GuestShortcuts
}

function Set-GuestShortcuts {
    $target = Join-Path $env:ProgramFiles 'FlatOut2VM'
    Assert-ProtectedGuestPath $target
    $shell = New-Object -ComObject WScript.Shell
    foreach ($action in @(@('FlatOut 2', '-PlayOnly'), @('Retry FlatOut 2 installation', '-Retry'), @('FlatOut 2 diagnostics', '-Diagnostics'))) {
        $desktop = [Environment]::GetFolderPath('CommonDesktopDirectory')
        Assert-NoReparsePoint $desktop
        $shortcutPath = Join-Path $desktop ($action[0] + '.lnk')
        if (Test-Path -LiteralPath $shortcutPath) { Assert-NoReparsePoint $shortcutPath }
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $env:ComSpec
        $command = 'guest-start.cmd'
        $argument = ' ' + $action[1]
        $shortcut.Arguments = '/d /c ""' + (Join-Path $target $command) + '"' + $argument + '"'
        $shortcut.WorkingDirectory = $target
        $shortcut.Save()
    }
}
