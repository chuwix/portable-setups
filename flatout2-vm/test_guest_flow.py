"""Execute guest state transitions with real PowerShell and mocked Windows boundaries."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
PWSH = shutil.which('pwsh')
FILES = ('setup_flatout_2_1.0_(26697).exe', 'setup_flatout_2_1.0_(26697)-1.bin')


@unittest.skipUnless(PWSH, 'PowerShell is not available')
class GuestFlowTests(unittest.TestCase):
    def run_ps(self, body: str, *, mock_media: bool = True) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            media = root / 'media'
            media.mkdir()
            entries = []
            for name in FILES:
                payload = name.encode()
                (media / name).write_bytes(payload)
                entries.append({'name': name, 'size': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()})
            (media / 'game-media.json').write_text(json.dumps({'schema': 1, 'files': entries}))
            script = root / 'test.ps1'
            source = '\n'.join(f". '{HERE / name}'" for name in ('guest-start.ps1', 'install-gog.ps1'))
            media_function = 'function Get-GameMedia([string]$RequestedMedia) { return $media }' if mock_media else ''
            script.write_text(f"""
$ErrorActionPreference = 'Stop'
{source}
$testRoot = '{root}'
$media = '{media}'
$env:ProgramData = $testRoot
$env:LOCALAPPDATA = Join-Path $testRoot 'local'
$env:USERNAME = 'Player'
$boot = '2026-11-10T10:00:00.0000000Z'
$script:FlatOutDestination = Join-Path $testRoot 'game'
$script:FlatOutGame = Join-Path $script:FlatOutDestination 'FlatOut2.exe'
function Assert-GuestMachine {{}}
function Assert-ProtectedGuestPath([string]$Path) {{}}
function Protect-GuestFile([string]$Path) {{}}
function Protect-GuestDirectory([string]$Path) {{ New-Item -ItemType Directory -Path $Path -Force | Out-Null }}
function Install-GuestDispatcher([string]$Source) {{ $script:provisioned = $true }}
function Initialize-GameDestination {{ $script:destinationValidated = $true }}
function Assert-GameTree([string]$Path) {{}}
function Assert-GameLaunchPaths {{}}
function Enable-PlayerSavegame {{}}
function Set-GuestShortcuts {{ $script:shortcutsRestored = $true }}
function Get-GuestBootId {{ return $boot }}
{media_function}
function Test-GuestAdministrator {{ return $false }}
function Get-AuthenticodeSignature([string]$LiteralPath) {{
    $cert = [pscustomobject]@{{}}
    $cert | Add-Member -MemberType ScriptMethod -Name GetNameInfo -Value {{ param($type, $issuer) return 'GOG  sp. z o.o.' }}
    return [pscustomobject]@{{ Status = 'Valid'; SignerCertificate = $cert }}
}}
{body}
""")
            process = subprocess.run([str(PWSH), '-NoProfile', '-File', str(script)], text=True,
                                     capture_output=True, timeout=30)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            output = next(line[7:] for line in reversed(process.stdout.splitlines()) if line.startswith('RESULT:'))
            return json.loads(output)

    def test_manifest_identity_is_order_independent_and_binds_both_files(self) -> None:
        result = self.run_ps("""
$manifest = Read-GameManifest $media -VerifyPayload
$reversed = @($manifest.files[1], $manifest.files[0])
$same = (Get-ManifestIdentity $reversed) -ceq $manifest.identity
$reversed[0].sha256 = 'b' * 64
$changed = (Get-ManifestIdentity $reversed) -cne $manifest.identity
$rejected = $false
try { Read-GameManifest $media -VerifyPayload | Out-Null; Set-Content -LiteralPath (Join-Path $media $script:FlatOutFiles[1]) -Value 'corrupt'; Read-GameManifest $media -VerifyPayload | Out-Null }
catch { $rejected = $true }
'RESULT:' + (@{same=$same; changed=$changed; rejected=$rejected} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'same': True, 'changed': True, 'rejected': True})

    def test_attempt_marker_is_durable_before_elevation_and_requires_explicit_retry(self) -> None:
        result = self.run_ps("""
$directory = Join-Path $testRoot 'attempts'
$identity = (Read-GameManifest $media).identity
$first = Register-GuestAttempt $directory $identity
$marker = Get-Content -Raw -LiteralPath (Join-Path $directory ($identity + '.json')) | ConvertFrom-Json
$second = Register-GuestAttempt $directory $identity
$retryResult = Register-GuestAttempt $directory $identity -Retry
$last = Register-GuestAttempt $directory $identity
'RESULT:' + (@{first=$first; second=$second; retry=$retryResult; last=$last; identity=($marker.manifestIdentity -ceq $identity)} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'first': True, 'second': False, 'retry': True, 'last': False, 'identity': True})

    def test_receipt_rejects_crash_tampering_and_defers_3010_until_later_boot(self) -> None:
        result = self.run_ps("""
$manifest = Read-GameManifest $media
$receipt = [pscustomobject]@{schema=2; files=$manifest.files; manifestIdentity=$manifest.identity; destination=$script:FlatOutDestination; game=$script:FlatOutGame; gameSha256=('a'*64); runId=[guid]::NewGuid().ToString(); installerExitCode=3010; rebootRequired=$true; bootId=$boot}
$pending = Get-ReceiptState $receipt $boot
$ready = Get-ReceiptState $receipt '2026-11-10T11:00:00.0000000Z'
$rejected = 0
foreach ($field in @('schema','files','manifestIdentity','destination','game','gameSha256','runId','installerExitCode','rebootRequired','bootId')) {
    $copy = $receipt | ConvertTo-Json -Depth 8 | ConvertFrom-Json
    switch ($field) {
        'files' { $copy.files[1].size++ }
        'schema' { $copy.schema = 1 }
        'installerExitCode' { $copy.installerExitCode = -1073740771 }
        'rebootRequired' { $copy.rebootRequired = $false }
        default { $copy.$field = 'invalid' }
    }
    try { Get-ReceiptState $copy $boot | Out-Null } catch { $rejected++ }
}
'RESULT:' + (@{pending=$pending; ready=$ready; rejected=$rejected} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'pending': 'restart-required', 'ready': 'ready', 'rejected': 10})

    def test_dispatcher_denial_does_not_repeat_and_retry_is_explicit(self) -> None:
        result = self.run_ps("""
$script:elevations = 0
$script:markerBeforeUac = $false
function Start-Process {
    $script:elevations++
    $identity = (Read-GameManifest $media).identity
    $script:markerBeforeUac = Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA ('FlatOut2VM/attempts/' + $identity + '.json'))
    throw 'UAC denied'
}
try { Invoke-GuestStart } catch {}
try { Invoke-GuestStart } catch {}
$automaticCount = $script:elevations
$Retry = $true
try { Invoke-GuestStart } catch {}
'RESULT:' + (@{automatic=$automaticCount; retried=$script:elevations; marker=$script:markerBeforeUac} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'automatic': 1, 'retried': 2, 'marker': True})

    def install_body(self, code: int, suffix: str = '') -> str:
        return f"""
function Test-GuestAdministrator {{ return $true }}
$Elevated = $true
$RunId = [guid]::NewGuid().ToString()
$ManifestIdentity = (Read-GameManifest $media).identity
$script:starts = 0
function Start-Process {{
    $script:starts++
    if (-not $script:destinationValidated) {{ throw 'Installer started before destination validation' }}
    New-Item -ItemType Directory -Path $script:FlatOutDestination -Force | Out-Null
    Set-Content -LiteralPath $script:FlatOutGame -Value 'game'
    return [pscustomobject]@{{ExitCode={code}}}
}}
$failed = $false
try {{ Invoke-GuestInstall }} catch {{ $failed=$true }}
$root = Join-Path $env:ProgramData 'FlatOut2VM'
$receiptExists = Test-Path -LiteralPath (Join-Path $root 'gog-installed.json')
$result = Get-Content -Raw -LiteralPath (Join-Path (Join-Path $root ('install-' + $RunId)) 'result.json') | ConvertFrom-Json
{suffix}
"""

    def test_dispatcher_native_and_wrapped_errors_are_neutral_and_never_reprompt(self) -> None:
        for code, wrapped in ((1223, False), (1223, True), (5, True), (2, False)):
            with self.subTest(code=code, wrapped=wrapped):
                result = self.run_ps(f"""
$Automatic=$true
$script:elevations=0
$script:markerBeforeUac=$false
$script:policy=$false
$script:locked=$false
function Start-Process {{
    param($FilePath, $Verb, [switch]$Wait, [switch]$PassThru, $ArgumentList)
    $script:elevations++
    $identity=(Read-GameManifest $media).identity
    $attempts=Join-Path $env:LOCALAPPDATA 'FlatOut2VM/attempts'
    $script:markerBeforeUac=Test-Path -LiteralPath (Join-Path $attempts ($identity + '.json'))
    try {{ $handle=[IO.File]::Open((Join-Path $attempts 'dispatcher.lock'), 'Open', 'ReadWrite', 'None'); $handle.Dispose() }}
    catch [IO.IOException] {{ $script:locked=$true }}
    $script:policy=($ArgumentList[2] -eq 'RemoteSigned' -and $Verb -eq 'RunAs' -and $Wait -and $PassThru)
    $error=[ComponentModel.Win32Exception]::new({code}, 'SECRET must not enter diagnostics')
    if (${str(wrapped).lower()}) {{ $error=[Exception]::new('SECRET wrapper', $error) }}
    throw $error
}}
$first=''
try {{ Invoke-GuestStart }} catch {{ $first=$_.Exception.Message }}
$log=Join-Path $env:LOCALAPPDATA 'FlatOut2VM/dispatcher-stages.jsonl'
$entries=@(Get-Content -LiteralPath $log | ForEach-Object {{ $_ | ConvertFrom-Json }})
$failure=@($entries | Where-Object stage -eq 'failed')[0]
$firstRun=$entries[0].runId
try {{ Invoke-GuestStart }} catch {{}}
$afterAutomatic=$script:elevations
$Retry=$true
try {{ Invoke-GuestStart }} catch {{}}
$all=@(Get-Content -LiteralPath $log | ForEach-Object {{ $_ | ConvertFrom-Json }})
$raw=Get-Content -Raw -LiteralPath $log
$handle=[IO.File]::Open((Join-Path $env:LOCALAPPDATA 'FlatOut2VM/attempts/dispatcher.lock'), 'Open', 'ReadWrite', 'None')
$handle.Dispose()
'RESULT:' + (@{{automatic=$afterAutomatic; retried=$script:elevations; marker=$script:markerBeforeUac; locked=$script:locked; policy=$script:policy;
    cancelled=$failure.error.cancelled; native=@($failure.error.chain | Where-Object {{ $null -ne $_.nativeErrorCode }})[0].nativeErrorCode;
    chain=@($failure.error.chain).Count; message=$first; secret=$raw.Contains('SECRET');
    stages=@($entries.stage); modes=@($all.mode | Select-Object -Unique);
    metadata=(@($entries | Where-Object {{ -not $_.timestamp -or $_.mode -ne 'automatic' -or $_.runId -ne $firstRun -or $_.pid -ne $PID -or $null -eq $_.session -or $_.elapsedMs -lt 0 }}).Count -eq 0);
    runs=@($all.runId | Select-Object -Unique).Count}} | ConvertTo-Json -Depth 8 -Compress)
""")
                self.assertEqual(result['automatic'], 1)
                self.assertEqual(result['retried'], 2)
                for key in ('marker', 'locked', 'policy', 'metadata'):
                    self.assertTrue(result[key], key)
                self.assertEqual(result['native'], code)
                self.assertEqual(result['cancelled'], code == 1223)
                self.assertGreaterEqual(result['chain'], 3 if wrapped else 2)
                self.assertFalse(result['secret'])
                self.assertNotIn('SECRET', result['message'])
                self.assertNotIn('denied', result['message'])
                self.assertEqual('cancelled or not completed' in result['message'], code == 1223)
                self.assertEqual(result['stages'], [
                    'start', 'validate-player', 'validate-receipt', 'find-media', 'verify-media',
                    'validate-matching-receipt', 'acquire-lock', 'register-attempt',
                    'request-elevation', 'failed', 'finished',
                ])
                self.assertEqual(result['modes'], ['automatic', 'retry'])
                self.assertEqual(result['runs'], 3)

    def test_dispatcher_progress_precedes_hashing_and_log_failure_is_non_authoritative(self) -> None:
        result = self.run_ps("""
$script:progress=[Collections.Generic.List[string]]::new()
$script:checks=0
function Write-Host { param($Object) $script:progress.Add([string]$Object) }
function Read-InstalledGame {
    $script:checks++
    if (-not ($script:progress -match 'hash verification may take a while')) { throw 'No progress before receipt hashing' }
    return $null
}
function Read-GameManifest {
    param($Media, [switch]$VerifyPayload)
    if (-not ($script:progress -match 'Verifying CD payload hashes')) { throw 'No progress before payload hashing' }
    throw 'expected payload rejection'
}
# An unavailable log is not permission to skip hashing, register an attempt or elevate.
function Add-Content { throw 'Diagnostic storage unavailable' }
$script:starts=0
function Start-Process { $script:starts++ }
$message=''
try { Invoke-GuestStart } catch { $message=$_.Exception.Message }
'RESULT:' + (@{checks=$script:checks; starts=$script:starts; message=$message;
    attempted=(Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'FlatOut2VM/attempts'))} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'checks': 1, 'starts': 0, 'message': 'expected payload rejection',
                                  'attempted': False})

    def test_dispatcher_non_native_error_is_not_classified_as_cancellation(self) -> None:
        result = self.run_ps("""
$Automatic=$true
$script:starts=0
function Start-Process { $script:starts++; throw [InvalidOperationException]::new('SECRET internal detail') }
$message=''
try { Invoke-GuestStart } catch { $message=$_.Exception.Message }
try { Invoke-GuestStart } catch {}
$log=Get-Content -LiteralPath (Join-Path $env:LOCALAPPDATA 'FlatOut2VM/dispatcher-stages.jsonl')
$failure=@($log | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object stage -eq 'failed')[0]
'RESULT:' + (@{starts=$script:starts; cancelled=$failure.error.cancelled;
    native=@($failure.error.chain | Where-Object { $null -ne $_.nativeErrorCode }).Count;
    secret=(($log -join '').Contains('SECRET') -or $message.Contains('SECRET'));
    generic=$message.Contains('helper could not be started')} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'starts': 1, 'cancelled': False, 'native': 0,
                                  'secret': False, 'generic': True})

    def test_installer_crash_never_publishes_receipt_even_when_game_exists(self) -> None:
        result = self.run_ps(self.install_body(-1073740771, """
'RESULT:' + (@{failed=$failed; receipt=$receiptExists; status=$result.status; starts=$script:starts} | ConvertTo-Json -Compress)
"""))
        self.assertEqual(result, {'failed': True, 'receipt': False, 'status': 'failed', 'starts': 1})

    def test_success_validates_result_skips_staging_on_retry_and_detects_game_tampering(self) -> None:
        result = self.run_ps(self.install_body(0, """
$installed = Read-InstalledGame $root $boot $ManifestIdentity
$firstState = $installed.state
$secondRun = [guid]::NewGuid().ToString()
$RunId = $secondRun
Invoke-GuestInstall
$staged = Test-Path -LiteralPath (Join-Path $root ('install-' + $secondRun))
Set-Content -LiteralPath $script:FlatOutGame -Value 'tampered'
$tampered = $false
try { Read-InstalledGame $root $boot | Out-Null } catch { $tampered=$true }
'RESULT:' + (@{failed=$failed; receipt=$receiptExists; state=$firstState; starts=$script:starts; staged=$staged; tampered=$tampered} | ConvertTo-Json -Compress)
"""))
        self.assertEqual(result, {'failed': False, 'receipt': True, 'state': 'ready', 'starts': 1,
                                  'staged': False, 'tampered': True})

    def test_3010_receipt_defers_launch_then_resumes_without_cd(self) -> None:
        result = self.run_ps(self.install_body(3010, """
function Test-GuestAdministrator { return $false }
function Get-GameMedia { throw 'CD must not be read' }
$script:launches = 0
function Start-Process { $script:launches++ }
$pending = $false
try { Invoke-GuestStart } catch { $pending=$true }
$before = $script:launches
$boot = '2026-11-10T11:00:00.0000000Z'
Invoke-GuestStart
'RESULT:' + (@{pending=$pending; before=$before; after=$script:launches; receipt=$receiptExists} | ConvertTo-Json -Compress)
"""))
        self.assertEqual(result, {'pending': True, 'before': 0, 'after': 1, 'receipt': True})

    def test_elevated_dispatcher_never_launches_or_requests_another_elevation(self) -> None:
        result = self.run_ps("""
function Test-GuestAdministrator { return $true }
$script:starts = 0
function Start-Process { $script:starts++ }
$failed=$false
try { Invoke-GuestStart } catch { $failed=$true }
'RESULT:' + (@{failed=$failed; starts=$script:starts} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'failed': True, 'starts': 0})

    def test_media_requires_exactly_one_labelled_cd_and_matching_root(self) -> None:
        result = self.run_ps("""
$script:drives = @()
function Get-CimInstance { return $script:drives }
$rejected = 0
try { Get-GameMedia | Out-Null } catch { $rejected++ }
$script:drives = @([pscustomobject]@{DeviceID='D:'; DriveType=3; VolumeName='FLATOUTGAME'})
try { Get-GameMedia | Out-Null } catch { $rejected++ }
$script:drives = @([pscustomobject]@{DeviceID='D:'; DriveType=5; VolumeName='FLATOUTGAME'}, [pscustomobject]@{DeviceID='E:'; DriveType=5; VolumeName='FLATOUTGAME'})
try { Get-GameMedia | Out-Null } catch { $rejected++ }
$script:drives = @([pscustomobject]@{DeviceID='D:'; DriveType=5; VolumeName='FLATOUTGAME'})
$selected = Get-GameMedia
try { Get-GameMedia 'wrong-root' | Out-Null } catch { $rejected++ }
'RESULT:' + (@{rejected=$rejected; selected=$selected} | ConvertTo-Json -Compress)
""", mock_media=False)
        self.assertEqual(result, {'rejected': 4, 'selected': 'D:\\'})

    def test_malformed_manifest_stops_before_attempt_or_uac(self) -> None:
        result = self.run_ps("""
$script:starts=0
function Start-Process { $script:starts++ }
$manifest = Get-Content -Raw -LiteralPath (Join-Path $media 'game-media.json') | ConvertFrom-Json
$manifest.files[1].name = '../arbitrary.ps1'
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $media 'game-media.json')
$failed=$false
try { Invoke-GuestStart } catch { $failed=$true }
$attempted=Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'FlatOut2VM/attempts')
'RESULT:' + (@{failed=$failed; starts=$script:starts; attempted=$attempted} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'failed': True, 'starts': 0, 'attempted': False})

    def test_invalid_or_spoofed_signature_stops_before_payload_staging(self) -> None:
        result = self.run_ps("""
function Test-GuestAdministrator { return $true }
$Elevated=$true
$ManifestIdentity=(Read-GameManifest $media).identity
$script:starts=0
function Start-Process { $script:starts++ }
$failed=0
$staged=0
foreach ($case in @('invalid', 'spoofed')) {
    $RunId=[guid]::NewGuid().ToString()
    function Get-AuthenticodeSignature {
        $cert=[pscustomobject]@{}
        $cert | Add-Member -MemberType ScriptMethod -Name GetNameInfo -Value { param($type, $issuer) return 'GOG Limited Evil' }
        $status=if ($case -eq 'invalid') { 'NotSigned' } else { 'Valid' }
        return [pscustomobject]@{Status=$status; SignerCertificate=$cert}
    }
    try { Invoke-GuestInstall } catch { $failed++ }
    $root=Join-Path $env:ProgramData 'FlatOut2VM'
    if (Test-Path -LiteralPath (Join-Path (Join-Path $root ('install-' + $RunId)) 'payload')) { $staged++ }
}
'RESULT:' + (@{failed=$failed; starts=$script:starts; staged=$staged} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'failed': 2, 'starts': 0, 'staged': 0})

    def test_parent_revalidates_after_elevation_and_launches_only_unelevated(self) -> None:
        result = self.run_ps("""
$script:elevations=0
$script:launches=0
$script:admin=$false
function Test-GuestAdministrator { return $script:admin }
function Start-Process {
    param($FilePath, $Verb, [switch]$Wait, [switch]$PassThru, $ArgumentList, $WorkingDirectory)
    if ($Verb -eq 'RunAs') {
        $script:elevations++
        $script:admin=$true
        try {
            $Elevated=$true
            $RunId=$ArgumentList[7]
            $ManifestIdentity=$ArgumentList[9]
            Invoke-GuestInstall
        } finally { $script:admin=$false }
        return [pscustomobject]@{ExitCode=0}
    }
    if ($FilePath -eq $script:FlatOutGame) {
        if ($script:admin) { throw 'Elevated game launch' }
        $script:launches++
        return
    }
    New-Item -ItemType Directory -Path $script:FlatOutDestination -Force | Out-Null
    Set-Content -LiteralPath $script:FlatOutGame -Value 'game'
    return [pscustomobject]@{ExitCode=0}
}
Invoke-GuestStart
$stages=@(Get-Content -LiteralPath (Join-Path $env:LOCALAPPDATA 'FlatOut2VM/dispatcher-stages.jsonl') |
    ForEach-Object { ($_ | ConvertFrom-Json).stage })
$root=Join-Path $env:ProgramData 'FlatOut2VM'
$receipt=Get-Content -Raw -LiteralPath (Join-Path $root 'gog-installed.json') | ConvertFrom-Json
$resultPath=Join-Path (Join-Path $root ('install-' + $receipt.runId)) 'result.json'
$result=Get-Content -Raw -LiteralPath $resultPath | ConvertFrom-Json
$result.status='failed'
Write-GuestJson $resultPath $result
$rejected=$false
try { Invoke-GuestStart } catch { $rejected=$true }
'RESULT:' + (@{elevations=$script:elevations; launches=$script:launches; rejected=$rejected; stages=$stages} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'elevations': 1, 'launches': 1, 'rejected': True, 'stages': [
            'start', 'validate-player', 'validate-receipt', 'find-media', 'verify-media',
            'validate-matching-receipt', 'acquire-lock', 'register-attempt', 'request-elevation',
            'helper-exited', 'validate-helper-result', 'launch-game', 'game-process-started', 'finished',
        ]})

    def test_all_guest_powershell_files_parse(self) -> None:
        result = self.run_ps(f"""
$errorsFound = @()
foreach ($file in @('{HERE / 'guest-start.ps1'}', '{HERE / 'guest-install.ps1'}', '{HERE / 'install-gog.ps1'}')) {{
    $tokens = $null; $parseErrors = $null
    [Management.Automation.Language.Parser]::ParseFile($file, [ref]$tokens, [ref]$parseErrors) | Out-Null
    $errorsFound += @($parseErrors)
}}
'RESULT:' + (@{{errors=$errorsFound.Count}} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'errors': 0})

    def test_destination_policy_rejects_redirected_untrusted_and_writable_paths(self) -> None:
        result = self.run_ps(f"""
. '{HERE / 'guest-install.ps1'}'
$script:security=[pscustomobject]@{{reparse=$false; nullDacl=$false; owner='S-1-5-32-544'; rules=@()}}
function Get-DestinationSecurity([string]$Path) {{ return $script:security }}
$rejected=0
$script:security.reparse=$true
try {{ Assert-DestinationSecurity 'C:\\Games' }} catch {{ $rejected++ }}
$script:security.reparse=$false
$script:security.nullDacl=$true
try {{ Assert-DestinationSecurity 'C:\\Games' }} catch {{ $rejected++ }}
$script:security.nullDacl=$false
$script:security.owner='S-1-5-21-123-Player'
try {{ Assert-DestinationSecurity 'C:\\Games' }} catch {{ $rejected++ }}
$script:security.owner='S-1-5-32-544'
foreach ($right in @(2,4,16,64,256,65536,262144,524288)) {{
    $script:security.rules=@([pscustomobject]@{{sid='S-1-5-32-545'; allow=$true; inheritOnly=$false; rights=$right}})
    try {{ Assert-DestinationSecurity 'C:\\Games' }} catch {{ $rejected++ }}
}}
$script:security.rules=@([pscustomobject]@{{sid='S-1-5-32-545'; allow=$true; inheritOnly=$false; rights=4}})
Assert-DestinationSecurity 'C:\\' -VolumeRoot
$script:security.rules[0].rights=64
try {{ Assert-DestinationSecurity 'C:\\' -VolumeRoot }} catch {{ $rejected++ }}
'RESULT:' + (@{{rejected=$rejected}} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'rejected': 12})

    def test_real_reparse_traversal_rejects_existing_symlink_without_modifying_target(self) -> None:
        result = self.run_ps(f"""
. '{HERE / 'guest-install.ps1'}'
$target=Join-Path $testRoot 'untouched'
New-Item -ItemType Directory -Path $target | Out-Null
$file=Join-Path $target 'save.txt'
Set-Content -LiteralPath $file -Value 'preserve'
$link=Join-Path $testRoot 'redirected'
New-Item -ItemType SymbolicLink -Path $link -Target $target | Out-Null
$rejected=$false
try {{ Assert-NoReparsePoint (Join-Path $link 'save.txt') }} catch {{ $rejected=$true }}
'RESULT:' + (@{{rejected=$rejected; preserved=((Get-Content -LiteralPath $file) -eq 'preserve')}} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'rejected': True, 'preserved': True})

    def test_destination_ancestors_checked_before_creation_and_untrusted_tree_not_taken_over(self) -> None:
        result = self.run_ps(f"""
. '{HERE / 'guest-install.ps1'}'
$script:FlatOutDestination=Join-Path $testRoot 'Games/FlatOut2'
function Protect-GuestDirectory([string]$Path) {{}}
$script:events=[Collections.Generic.List[string]]::new()
function Assert-DestinationSecurity([string]$Path, [switch]$VolumeRoot) {{ $script:events.Add('check:' + $Path) }}
function New-SecureGameDirectory([string]$Path) {{
    $script:events.Add('create:' + $Path)
    New-Item -ItemType Directory -Path $Path | Out-Null
}}
Initialize-GameDestination
$ordered=($script:events.IndexOf('check:' + $testRoot) -lt $script:events.IndexOf('create:' + (Join-Path $testRoot 'Games')))
$save=Join-Path $script:FlatOutDestination 'save.txt'
Set-Content -LiteralPath $save -Value 'keep'
$script:events.Clear()
function Assert-DestinationSecurity([string]$Path, [switch]$VolumeRoot) {{
    if ($Path -eq $script:FlatOutDestination) {{ throw 'Untrusted destination owner' }}
}}
$rejected=$false
try {{ Initialize-GameDestination }} catch {{ $rejected=$true }}
'RESULT:' + (@{{ordered=$ordered; rejected=$rejected; creations=$script:events.Count; preserved=((Get-Content -LiteralPath $save) -eq 'keep')}} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'ordered': True, 'rejected': True, 'creations': 0, 'preserved': True})

    def test_install_validation_precedes_process_and_shortcuts_follow_result(self) -> None:
        body = self.install_body(0, """
$ordered=$script:destinationValidated -and $script:shortcutsRestored
$script:starts=0
$script:destinationValidated=$false
$RunId=[guid]::NewGuid().ToString()
Remove-Item -LiteralPath (Join-Path $root 'gog-installed.json')
function Initialize-GameDestination { throw 'Untrusted destination; preserve data' }
$rejected=$false
try { Invoke-GuestInstall } catch { $rejected=$true }
'RESULT:' + (@{ordered=$ordered; rejected=$rejected; starts=$script:starts} | ConvertTo-Json -Compress)
""")
        body = """
function Set-GuestShortcuts {
    $path=Join-Path (Join-Path $env:ProgramData 'FlatOut2VM') 'gog-installed.json'
    if (-not (Test-Path -LiteralPath $path)) { throw 'Shortcuts restored before successful receipt' }
    $installed=Read-InstalledGame (Join-Path $env:ProgramData 'FlatOut2VM') $boot
    if (-not $installed) { throw 'Shortcuts restored before successful result' }
    $script:shortcutsRestored=$true
}
""" + body
        result = self.run_ps(body)
        self.assertEqual(result, {'ordered': True, 'rejected': True, 'starts': 0})

    def test_automatic_failure_report_is_actionable_and_viewer_does_not_wait(self) -> None:
        result = self.run_ps("""
$script:waited=$false
$script:viewer=''
function Start-Process { param($FilePath, $ArgumentList, [switch]$Wait)
    $script:waited=[bool]$Wait; $script:viewer=$FilePath
}
Write-GuestStartupFailure 'UAC denied; use Retry'
$report=Get-Content -Raw -LiteralPath (Join-Path $env:LOCALAPPDATA 'FlatOut2VM/startup-failure.txt')
'RESULT:' + (@{waited=$script:waited; viewer=$script:viewer; actionable=($report.Contains('Retry FlatOut 2 installation') -and $report.Contains('UAC denied'))} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'waited': False, 'viewer': 'notepad.exe', 'actionable': True})

    def test_automatic_wrapper_only_pauses_interactive_calls(self) -> None:
        wrapper = (HERE / 'guest-start.cmd').read_text()
        self.assertIn('if /i "%~1"=="-Automatic" set "AUTOMATIC=1"', wrapper)
        self.assertEqual([line.strip() for line in wrapper.splitlines() if 'pause' in line.lower()],
                         ['if not defined AUTOMATIC pause'])
        self.assertIn('guest-start.cmd" -Automatic', (HERE / 'prepare-guest.cmd').read_text())
        self.assertIn("'" + '" -Automatic' + "'", (HERE / 'guest-install.ps1').read_text())
        self.assertIn('exit /b 1', wrapper)

    def test_save_root_accepts_only_narrow_player_acl_not_replace_or_takeover(self) -> None:
        result = self.run_ps("""
function Get-PlayerSid { return 'PlayerSid' }
$script:security=[pscustomobject]@{reparse=$false; directory=$true; nullDacl=$false; owner='S-1-5-32-544'; rules=@(
    [pscustomobject]@{sid='PlayerSid'; allow=$true; inheritOnly=$false; rights=0x1201ff},
    [pscustomobject]@{sid='PlayerSid'; allow=$true; inheritOnly=$true; rights=0x1301bf})}
function Get-DestinationSecurity { return $script:security }
Assert-RepairSaveRoot 'Savegame'
$rejected=0
foreach ($right in @(65536,262144,524288)) {
    $script:security.rules[0].rights=0x1201ff -bor $right
    try { Assert-RepairSaveRoot 'Savegame' } catch { $rejected++ }
}
$script:security.rules=@()
$script:security.owner='PlayerSid'
try { Assert-RepairSaveRoot 'Savegame' } catch { $rejected++ }
$script:security.owner='S-1-5-32-544'
$script:security.reparse=$true
try { Assert-RepairSaveRoot 'Savegame' } catch { $rejected++ }
'RESULT:' + (@{rejected=$rejected} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'rejected': 5})

    def test_save_preserving_repair_after_success_and_hash_or_result_failure(self) -> None:
        result = self.run_ps(self.install_body(0, """
function Get-PlayerSid { return 'PlayerSid' }
function Get-DestinationSecurity([string]$Path) {
    return [pscustomobject]@{reparse=$false; directory=$true; nullDacl=$false; owner='S-1-5-32-544'; rules=@(
        [pscustomobject]@{sid='PlayerSid'; allow=$true; inheritOnly=$false; rights=0x1201ff})}
}
function Assert-DestinationSecurity([string]$Path, [switch]$VolumeRoot) {}
function New-SecureGameDirectory([string]$Path) { New-Item -ItemType Directory -Path $Path | Out-Null }
function Open-SaveInspectionHandle([string]$Path) {
    if ((Get-Item -LiteralPath $Path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'redirect' }
    return [IO.MemoryStream]::new()
}
function Move-PinnedSaveRoot($Handle, [string]$Source, [string]$Destination) { [IO.Directory]::Move($Source, $Destination) }
function Initialize-GameDestination {
    Preserve-RepairSavegame
    $script:destinationValidated=$true
}
$preserved=0
$rejected=0
foreach ($failure in @('hash','result','partial-save-enable')) {
    $save=Join-Path $script:FlatOutDestination 'Savegame'
    New-Item -ItemType Directory -Path $save -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $save 'player.sav') -Value ('saved-' + $failure)
    if ($failure -eq 'hash') { Set-Content -LiteralPath $script:FlatOutGame -Value 'invalid' }
    elseif ($failure -eq 'result') {
        $receipt=Get-Content -Raw -LiteralPath (Join-Path $root 'gog-installed.json') | ConvertFrom-Json
        $path=Join-Path (Join-Path $root ('install-' + $receipt.runId)) 'result.json'
        Write-GuestJson $path @{schema=2; status='failed'}
    } else { Remove-Item -LiteralPath (Join-Path $root 'gog-installed.json') }
    try { $current=Read-InstalledGame $root $boot; if (-not $current) { $rejected++ } } catch { $rejected++ }
    $RunId=[guid]::NewGuid().ToString()
    Invoke-GuestInstall
    $installed=Read-InstalledGame $root $boot $ManifestIdentity
    if ($installed.state -ne 'ready') { throw 'repair failed' }
    $runResult=Get-Content -Raw -LiteralPath (Join-Path (Join-Path $root ('install-' + $RunId)) 'result.json') | ConvertFrom-Json
    $archived=Join-Path $runResult.preservedSavegame 'player.sav'
    if ((Get-Content -LiteralPath $archived) -eq ('saved-' + $failure)) { $preserved++ }
    if (Test-Path -LiteralPath $save) { throw 'Old writable save tree was left in installer destination' }
}
'RESULT:' + (@{preserved=$preserved; rejected=$rejected; starts=$script:starts} | ConvertTo-Json -Compress)
"""))
        self.assertEqual(result, {'preserved': 3, 'rejected': 3, 'starts': 4})

    def test_save_redirect_and_depth_limit_preserve_original_without_move(self) -> None:
        result = self.run_ps("""
function Assert-DestinationSecurity([string]$Path) {}
function Assert-RepairSaveRoot([string]$Path) { Assert-NoReparsePoint $Path }
function New-SecureGameDirectory([string]$Path) { throw 'Must not create archive after rejection' }
function Open-SaveInspectionHandle([string]$Path) {
    if ((Get-Item -LiteralPath $Path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'redirect' }
    return [IO.MemoryStream]::new()
}
$save=Join-Path $script:FlatOutDestination 'Savegame'
New-Item -ItemType Directory -Path $save -Force | Out-Null
$outside=Join-Path $testRoot 'outside'
New-Item -ItemType Directory -Path $outside | Out-Null
Set-Content -LiteralPath (Join-Path $outside 'keep.sav') -Value 'keep'
$link=Join-Path $save 'redirect'
New-Item -ItemType SymbolicLink -Path $link -Target $outside | Out-Null
$rejected=0
try { Preserve-RepairSavegame } catch { $rejected++ }
Remove-Item -LiteralPath $link
$deep=$save
foreach ($level in 1..17) { $deep=Join-Path $deep 'd'; New-Item -ItemType Directory -Path $deep | Out-Null }
try { Preserve-RepairSavegame } catch { $rejected++ }
$rootLink=Join-Path $testRoot 'linked-save'
New-Item -ItemType SymbolicLink -Path $rootLink -Target $outside | Out-Null
try { Assert-RepairSaveRoot $rootLink } catch { $rejected++ }
'RESULT:' + (@{rejected=$rejected; saveStillPresent=(Test-Path -LiteralPath $save); outside=((Get-Content -LiteralPath (Join-Path $outside 'keep.sav')) -eq 'keep')} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'rejected': 3, 'saveStillPresent': True, 'outside': True})

    def test_save_scan_entry_limit_and_native_handle_contract(self) -> None:
        result = self.run_ps(f"""
function Open-SaveInspectionHandle([string]$Path) {{ return [IO.MemoryStream]::new() }}
function Get-Item {{ return [pscustomobject]@{{PSIsContainer=$true}} }}
function Get-ChildItem {{ foreach ($n in 1..4097) {{ [pscustomobject]@{{FullName=('entry-' + $n)}} }} }}
$rejected=$false
try {{ Assert-BoundedSaveTree 'Savegame' }} catch {{ $rejected=$_.Exception.Message.Contains('4096') }}
$source=Get-Content -Raw -LiteralPath '{HERE / 'guest-install.ps1'}'
$native=([regex]::Matches($source, "(?s)Add-Type -TypeDefinition @'\r?\n(.*?)\r?\n'@") | Where-Object {{ $_.Groups[1].Value.Contains('public static class FlatOut2SaveInspection') }}).Groups[1].Value
# Compile the actual interop declarations without invoking Windows kernel APIs on macOS.
Add-Type -TypeDefinition $native
'RESULT:' + (@{{rejected=$rejected; compiled=($null -ne ('FlatOut2SaveInspection' -as [type]))}} | ConvertTo-Json -Compress)
""")
        self.assertEqual(result, {'rejected': True, 'compiled': True})
        source = (HERE / 'guest-install.ps1').read_text()
        self.assertIn('CreateFile($Path, $access, 1,', source)
        self.assertIn('Open-SaveInspectionHandle $save -RenameRoot', source)
        self.assertIn('Move-PinnedSaveRoot $handle $save', source)


if __name__ == '__main__':
    unittest.main()
