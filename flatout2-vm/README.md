# FlatOut 2 in an isolated UTM VM

**Experimental setup scripts for Apple Silicon Macs. Not yet a tested one-click installer.**
No Nix installation is required. This directory is self-contained. Never share a populated VM,
credentials, Windows media, or game installers.

## Current status

Implemented: generation of a dedicated Windows 11 ARM UTM bundle, sparse 80 GiB guest disk,
read-only installation media, unattended Windows answer file, separate administrator and
player accounts, configuration audit, and guest-side GOG offline installation helper.

**Current delivery scope: installation from a flash drive containing the supported GOG
offline installer.** Selecting its folder explicitly is also supported. Authenticated GOG,
Steam, LAN, and reliable audio are deferred. For testing on another Mac, follow the
[second-machine acceptance checklist](docs/testing.md).

Observed locally on UTM 5.0.8: unattended installation to the Windows sign-in screen,
automatic NetKVM installation, outbound networking, intended privacy registry values,
Player desktop after sign-in, and a normal reboot with networking preserved.
The separate experimental graphics VM passed a 32-bit Direct3D 9 rendering probe. With
FlatOut 2 configured to **NoSound**, the user confirmed racing and saves work. Sound, LAN,
cross-reboot save persistence, and a repeatable fresh installation remain unverified.

The new first-login dispatcher, administrator Player account, receipt-gated launch, and repair
flow pass offline tests but still need fresh Windows runtime acceptance. Experimental graphics
remains excluded from automated defaults. In the earlier USB test the GOG installer exited
with `0xC000041D` after writing game files; the helper correctly reports failure. Do not treat
those files as a successful installation. An audio experiment also produced severe lag;
audio remains disabled in the supported launcher. Local validation is not a
published-repository E2E pass or proof of isolation.

## Security boundary

Use legitimate GOG/Steam copies, not suspected malware. A VM reduces exposure; it cannot
guarantee safety against hypervisor, graphics-driver, or network vulnerabilities.

- No shared folders, clipboard sharing, USB forwarding, serial ports, or custom QEMU arguments.
- ISO files are copied into the VM bundle and attached read-only. No host directory is mounted.
- UEFI, Secure Boot variable template, and TPM enabled; no Windows hardware-check bypasses.
- Shared networking initially requests host isolation. This is not a guarantee against access
  to other LAN devices or every host address.
- Bridged LAN mode exposes the VM to the normal network and can expose the host over IP.
  It is not a containment boundary against malicious network traffic.
- Audio is disabled until output-only operation is verified, rather than risk enabling microphone capture.
- Generated passwords and the unattended answer file are stored locally with private permissions.
  They also exist on the seed ISO and may be cached by Windows Setup. Do not reuse them elsewhere.
- Player automatic login stores its guest password in Windows and removes the guest login barrier.
  Anyone who can start or read the VM can access Player's data. VMAdmin never logs in automatically.
- New VMs make Player a guest administrator so installation requires a Yes/No UAC approval,
  not the generated VMAdmin password. UAC remains enabled. This weakens separation inside
  Windows: Player applications can request administrative access. Host sharing stays disabled.
  Existing standard-Player VMs are not silently migrated by changing these scripts.
- The launch audit checks configuration, not the running guest, hypervisor integrity, or malware.

Keep UTM and Windows updated, leave Defender enabled, and play as **Player**, not **VMAdmin**.

## Prerequisites

- Apple Silicon Mac with macOS 13+, preferably at least 16 GiB RAM and 100 GiB free disk space.
- Terminal and Homebrew. Setup installs missing Python **3.11+** and UTM **5.0.8+** through brew.
- A valid Windows 11 Pro license.
- Internet access for the pinned Microsoft Windows ISO, or a local ARM64 ISO override.
- Your own GOG FlatOut 2 offline installer, build **1.0 (26697)**, on a mounted flash drive.
  Keep `setup_flatout_2_1.0_(26697).exe` and `setup_flatout_2_1.0_(26697)-1.bin` together.
  Other builds and Steam installations are not supported by this flow.

The setup launcher checks prerequisites and installs missing tools through Homebrew. It upgrades
an outdated UTM if Homebrew manages it; an outdated unmanaged UTM may require manual resolution
if Homebrew refuses to adopt it. Homebrew may request macOS authorization. Never run setup as sudo.
The Play launcher does not install anything.

Nix-managed Homebrew is detected and never modified. On such machines, satisfy prerequisites
through your manager, then run the same launcher. With supported tools already installed,
setup performs no brew installation or upgrade. Direct Python invocation skips this bootstrap.

### Pinned Windows media

The default download is **Windows 11 25H2, build 26200.6584, ARM64, English (en-US)**,
from [Microsoft's static CDN](https://software-static.download.prss.microsoft.com/dbazure/888969d5-f34g-4e03-ac9d-1f9786c66749/26200.6584.250915-1905.25h2_ge_release_svc_refresh_CLIENT_CONSUMER_a64fre_en-us.iso).
The version-specific URL has no expiring query token. Its availability is not guaranteed forever.

- Size observed: **7,299,147,776 bytes**.
- SHA256: `32cde0071ed8086b29bb6c8c3bf17ba9e3cdf43200537434a811a9b6cc2711a1`.
- Provenance: downloaded directly over HTTPS from the Microsoft CDN on 2026-11-09;
  SHA256 computed from those bytes. This is a maintainer-observed pin, not an independently
  verified Microsoft-published checksum for this historical image.

The script caches by SHA256 under `~/Library/Caches/portable-setups/flatout2-vm/`, verifies
every cached image before use, rejects mismatches, and never falls back to a mirror or a newer
Windows release. Redirects must remain HTTPS. The initial source is Microsoft; a checksum pin
establishes subsequent byte identity, not independent certification of the source image.

## Prepare the VM

Finished playing for good? See [shutdown, media cleanup, and permanent VM removal](docs/cleanup.md).
Removing the VM also removes its saves and Windows state; the guide explains backup first.

Run from this directory:

```sh
./setup-flatout2.command
```

1. Connect the flash drive. Accept the Windows terms only if you agree to them.
2. Choose **1. Detect GOG offline installer on USB** and confirm the displayed installer.
   If detection fails, choose its folder instead, or rerun with `--source-dir '/Volumes/DRIVE/folder'`.
3. Wait for copying and read-only ISO verification. When the launcher says the source is no
   longer needed, you may eject the flash drive in Finder. It is never passed through to Windows.
4. Let Windows finish setup and sign in automatically as **Player**. The bounded startup
   helper requests **Yes/No UAC consent** for installation. Approve only the expected helper.
   A generated administrator password should not be needed on a fresh VM.
5. A valid successful result allows the unelevated helper to launch the game. If a restart is
   required, restart Windows normally. On failure, preserve the report and logs; use
   **Retry FlatOut 2 installation** deliberately rather than reinstalling over saves manually.

Graphics is still a separate test prerequisite, not an automated step. See
[graphics test constraints](#graphics-test-prerequisite-not-automated) before assessing gameplay.
The known installer crash must remain a failed test even if the game files are present.

For later sessions, run `./play-flatout2.command`. If Windows is stopped, it starts Windows
and the login helper attempts receipt-validated game launch. If Windows is already running,
Play selects UTM and asks you to use the guest **FlatOut 2** shortcut; it does not remotely
launch a second game process. Guest launches run unelevated as Player.

The launcher prompts for Windows license acceptance before downloading or creating a VM.
Fresh setup also asks you to select and confirm your supported GOG USB/folder installer before
downloads. It stages a verified game CD before the first Windows boot. The new first-login
install/launch path passes offline tests but still needs a fresh-VM runtime test; the known GOG
installer crash remains unresolved. Keep its failure logs rather than assuming installed files
mean a successful setup.
Declining cancels setup. For unattended use, pass `--accept-windows-license` only after reading
and accepting Microsoft's Windows license terms.
The generic installation key selects Pro; it does not activate Windows or provide a license.

Explicit overrides (no automatic source or version selection):

```sh
# Local copy of the exact pinned ISO uses the default checksum.
python3 flatout2_vm.py setup --windows-iso '/path/to/windows-arm64.iso' --accept-windows-license

# Another image requires its matching trusted checksum.
python3 flatout2_vm.py setup \
  --windows-url 'https://example.org/your-windows-arm64.iso' \
  --windows-sha256 'YOUR_TRUSTED_64_CHARACTER_SHA256' \
  --accept-windows-license
```

`--windows-iso` and `--windows-url` are mutually exclusive. A URL override always requires
`--windows-sha256`; local media defaults to the pinned hash unless explicitly overridden.
The boot preparation currently recognizes only the EFI images bundled with the pinned ISO;
different boot image hashes are rejected, even with an explicit ISO checksum override.
Overrides must still supply an English ARM64 image containing the Windows 11 Pro edition,
or the generated installation answer file must be adapted. A custom URL is an explicit trust
decision, not an endorsement of that source.

Default state directory: `~/Library/Application Support/FlatOut2VM/`.
Setup also downloads and SHA256-verifies the [UTM guest tools 0.1.271 ISO](https://github.com/utmapp/qemu/releases/download/v10.0.2-utm/utm-guest-tools-0.1.271.iso)
(about 121 MiB, SHA256 `65b6a69b392ee01dd314c10f3dad9ebbf9c4160be43f5f0dd6bb715944d9095b`).
This hash was computed from the official download, not independently published by its vendor.
Only the Windows 11 ARM64 NetKVM package and its license are copied into our seed ISO.
The tools ISO's answer file and installer are not attached or run. A synchronous command in
the `specialize` pass locates our seed by `flatout2-seed.tag` and runs `pnputil /add-driver /install`
before OOBE. No CD drive letter is assumed. Windows signature enforcement stays enabled.
Results are written to `C:\Windows\Panther\flatout2-network.log`; missing media or a failed
installation fails the command rather than silently continuing. A requested reboot is handed
to Windows Setup. This path replaces WinPE configuration-set staging, which copied no drivers
in the observed Windows 11 25H2 installation. The specialize path subsequently installed NetKVM
successfully in the local Windows test, with exit code 0 and working outbound networking.

Before network installation, the same guest-only `specialize` step applies privacy policies:
location, Find my device, advertising ID, online speech personalization, and tailored
experiences are disabled; diagnostics are limited to required data on Windows 11 Pro.
The tailored-experiences policy is seeded into the default user profile for new accounts.
Only after those writes succeed is the privacy-choice screen suppressed with
`DisablePrivacyExperience`. The answer file also sets `ProtectYourPC=3` to disable Express
settings. Failures are logged to `C:\Windows\Panther\flatout2-privacy.log` and fail the setup
command. This is not a zero-telemetry guarantee and does not disable Defender or updates.
The privacy screen was skipped in the local test, and all seven policy values were checked
after Player sign-in. These settings do not change existing VMs.

The setup never recreates an existing guest disk. A retry refreshes seed media only when UTM
reports the VM stopped and the first MiB of its raw guest disk is still zero-filled. Any
partitioned disk is refused because the unattended installer wipes guest disk 0. This is a
recovery check for this prototype, not a general disk-content classifier.
For a separate attempt use `--home '/another/path'`
on every command. Paths can contain spaces; no repository or username is hardcoded.

UTM opens and starts the generated VM. macOS may ask for permission. Setup replaces the
keypress-required EFI boot image in the VM-local ISO copy with Microsoft's bundled
`efisys_noprompt.bin`. It checks both boot image SHA256 hashes and the default EFI catalog
entry before writing, then reads back the replacement. The cached download stays unchanged.
The system disk precedes both CDs in UTM's drive list, which determines QEMU boot priority.
An empty disk should fall through to the no-prompt installer; subsequent restarts should boot
the installed system. This boot/restart path reached sign-in in the local test. US English locale
and a single US keyboard are configured for both Windows Setup and OOBE. Image selection,
disk partitioning, and account creation are preconfigured. Current Windows builds may still
show OOBE/license/account screens. Do not bypass security checks to suppress them.

No UEFI shell script is required. If the VM remains at
`Shell>`, that is a failed boot test, not a Windows or PowerShell script failure. Do not format
anything or recreate the VM to troubleshoot it; preserve the state for diagnosis.

### Automatic Player startup (runtime test pending)

New VMs configure Windows-native automatic login as the administrator **Player** account. No host
accessibility or screen-recording permission is required. Privileged preparation runs during
Windows Setup, not through an elevated Player session. Automatic login is bounded: the answer
file requests 999 logons; Windows documents an off-by-one issue in this setting. After that,
use the generated `credentials.json` to sign in. This does not modify existing installations.

New Windows preparation installs a brief, unelevated Player-login dispatcher under
`C:\Program Files\FlatOut2VM`. It validates a protected installation receipt and launches the
game, or attempts installation from exactly one confirmed game CD. It records the attempt
before requesting UAC; denial or failure requires an explicit **Retry FlatOut 2 installation**
action rather than prompting again every login. It exits after handling startup, with no
resident listener or service. Existing VMs are not updated merely by changing repository files.

The **FlatOut 2 diagnostics** shortcut retains the account, network, and display report under
`%LOCALAPPDATA%\FlatOut2VM`; successful game startup does not open it over the game. The Startup
entry ignores other accounts. Failed setup attempts are preserved for diagnosis. Store sign-in
remains user-controlled inside Windows. All new dispatcher behavior still needs Windows runtime
verification, including UAC, ACLs, shortcuts, and unelevated game launch.

## Attach or retry the flash-drive installer (experimental)

Fresh setup already stages the game CD; do not run a second attachment while Windows is
installing. Use this separate command for an existing VM without game media, or to recover an
attachment failure. Shut Windows down normally, connect the flash drive, then run:

```sh
./install-flatout2.command
# Or select a folder directly:
./install-flatout2.command --source-dir '/path/to/installer-folder'
```

Use `--home '/your/test/home'` if the VM uses a nondefault state directory. Rerunning the
setup launcher on an installed GPT guest disk also enters this flow instead of refreshing
unattended media. The launcher refuses media changes while Windows is running.

1. Choose USB detection or a source folder, then confirm the installer and applicable license
   terms. If multiple candidates exist, select one. The initial version supports only GOG build
   **1.0 (26697)**: `setup_flatout_2_1.0_(26697).exe` and its matching `-1.bin`, together.
   Other builds fail explicitly rather than guessing whether all parts are present.
2. The launcher copies only those two files, verifies SHA256 integrity, builds a read-only
   `FLATOUTGAME` CD, and verifies its contents by mounting it read-only. These local checksums
   establish transfer integrity, not vendor authenticity. The source drive is unchanged.
3. Windows starts. Updated guests attempt installation at Player login. On an older guest, or
   for explicit retry, open the `FLATOUTGAME` CD in File Explorer and run **install-gog.cmd**.
   Approve the Windows Yes/No elevation request. New VMs use an administrator Player account;
   no generated guest password should be required. Older standard-Player VMs require migration
   or a fresh VM before this flow works without a password. Do not disable UAC to work around it.
   No host accessibility permission, shared folder, clipboard, or USB passthrough is used.
4. The helper validates the file hashes and GOG Authenticode signature, copies the payload
   onto the guest disk, and runs the installer silently into `C:\Games\FlatOut2` without an
   automatic reboot. Do not disable signature checking, Defender, or execution policy if a
   check fails. Report the error and preserve logs instead. The helper uses process-only
   `RemoteSigned` for its initial and elevated PowerShell sessions. This permits local
   scripts without changing saved execution policy or overriding Group Policy; downloaded
   scripts still require signatures. The separate GOG installer signature check remains.
5. Check the helper's result and logs under `C:\ProgramData\FlatOut2VM\install-<run-id>`.
   Failed runs retain their payload for diagnosis. Successful runs remove that payload and
    create public Play, Retry, and diagnostic shortcuts. The unelevated parent launches the game
    only after validating the successful result and receipt. A required restart defers launch
    until a later Windows boot; no automatic reboot is requested. Launch as Player, not VMAdmin.

The host command cannot observe the guest result and does not claim installation success.
Rerunning the helper skips payload staging/reinstallation only when the schema-2 receipt binds
both payload files and the game executable hash, with a matching protected success result.
Installation success does not prove gameplay, sound, saves, or LAN operation.
Authenticated GOG and Steam routes are outside the current delivery scope and are not offered
in the source menu.

If repair finds an intentionally Player-writable Savegame tree, it preserves that tree outside
the installer destination under `C:\Games\FlatOut2-saves-<GUID>\Savegame`. Its location appears
in the result/report. Restoration is manual, as unelevated Player with the game closed; never
run an elevated recursive copy from writable saves. Keep the archive and stopped VM until
restoration is verified. Native Windows repair/archive behavior still requires runtime testing.

After success, shut down Windows and remove only the temporary game CD:

```sh
python3 flatout2_vm.py detach-game
```

This preserves setup CDs, the guest disk, saves, and USB source files. If attachment failed
after creating `Data/game.iso`, preserve it for diagnosis; it is not silently overwritten.
`detach-game` offers explicit quarantine of an orphan ISO so that setup can be retried without
deleting that evidence. After verified ISO creation, the original source folder is no longer
needed; eject an external source drive in Finder when convenient. This does not detach the
virtual CD. See the [cleanup guide](docs/cleanup.md) for permanent VM removal and save backup.

## Graphics test prerequisite (not automated)

The launcher does not install the accelerated graphics driver. Microsoft Basic Display Driver
is not a gameplay-ready result. A separate local test used the graphics-only signed
[v0.5 ARM64X package](https://github.com/osy/kvm-guest-drivers-windows/releases/tag/v0.5),
driver **100.6.101.58000**, and passed a 32-bit D3D9 probe plus racing with NoSound.
Pinned package and runtime evidence are recorded in [verification state](docs/state.md).

Do not install the complete guest-tools suite: sharing agents are outside this flow's isolation
contract. Until graphics-only provisioning has a reviewed delivery path, the second-machine
tester should report installation/UX separately from blocked gameplay validation. Do not
substitute arbitrary drivers or DLL packs, disable signature enforcement, or claim that a
DirectX feature list proves the game works. Keep Windows Update and Defender enabled.

Preserve a stopped VM copy before graphics experiments. Do not rely on suspend snapshots:
UTM refused saved-state suspension with the accelerated display device in the local test.

## LAN on normal Wi-Fi (deferred, not part of flash-drive acceptance)

1. Shut down the VM. In its UTM network settings choose **Bridged**, selecting the physical
   Wi-Fi/Ethernet interface, not a VPN. Keep folder, clipboard, and USB sharing disabled.
2. Start Windows. Mark only your trusted home LAN as **Private**.
3. After installing the game, add an inbound firewall allowance restricted to its executable,
   Private profile, and local subnet. In elevated guest PowerShell:

   ```powershell
   New-NetFirewallRule -Name FlatOut2-LAN -DisplayName 'FlatOut 2 LAN' `
     -Direction Inbound -Action Allow -Program 'C:\Games\FlatOut2\flatout2.exe' `
     -Profile Private -RemoteAddress LocalSubnet
   ```

4. Verify the VM has an address on the players' LAN, then test hosting and joining a complete race.

Wi-Fi bridging, broadcast filtering, guest-network client isolation, or firewall rules can prevent
discovery. Do not disable either the Mac or Windows firewall as a workaround. GOG/Steam cross-edition
LAN compatibility is unverified.

## Launch, audit, and removal

```sh
python3 flatout2_vm.py audit
python3 flatout2_vm.py start
```

The `.command` launchers wrap these commands. Setup prompts for explicit Windows license acceptance;
it does not silently accept it. The Play launcher starts the registered VM.
If it is already running, use its existing window rather than starting another instance.

For removal, follow [Finished playing?](docs/cleanup.md). Make and verify any wanted backup
**before removing the VM from UTM**: that action may delete its data as well as its list entry.
The guide covers saves, remaining setup files, optional download-cache cleanup, and custom paths.

## Disposable guests and Tiny11

A one-shot guest does not require Defender or update support as a project policy. These protect
the guest, not the hypervisor boundary. Host integration restrictions, deliberate network access,
trusted source media, and current host/UTM security patches remain important. A disposable guest
can still expose storefront credentials or attack LAN services during a session.

The current prototype creates a persistent stock Windows guest. An immutable base plus disposable
runs is planned, not implemented. Saves and login sessions would otherwise disappear with the run.

Tiny11 ARM64/Core may be evaluated as a separate profile built from official source media with a
pinned [Tiny11 Builder](https://github.com/ntdevlabs/tiny11builder) revision and reviewed recipe.
No prebuilt third-party Tiny11 ISO is selected by default. Core removes servicing and disables
Defender. Preserve x86 application support, graphics/network drivers, DirectX runtimes, and any
storefront dependencies. A stripped image does not improve UTM's virtual GPU compatibility.

## Other platforms

UTM automation here is macOS-only. Native Windows and Linux Proton instructions would not meet
the full-VM requirement. Windows/Linux guest acceleration, suitable free hypervisors, and LAN
compatibility need separate testing; no support is claimed for them yet.

## Sources

- [UTM 5 graphics and scripting changes](https://docs.getutm.app/updates/v5.0/)
- [Windows graphics limitations and guest tools](https://docs.getutm.app/guest-support/windows/)
- [Windows installation guide](https://docs.getutm.app/guides/windows/)
- [UTM scripting reference](https://docs.getutm.app/scripting/reference/)
- [UTM v5.0.8 configuration schema](https://github.com/utmapp/UTM/tree/v5.0.8/Configuration)
- [Microsoft unattended setup](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/automate-windows-setup)
