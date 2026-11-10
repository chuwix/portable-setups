# FlatOut 2 in an isolated UTM VM

**Experimental setup scripts for Apple Silicon Macs. Not yet a tested one-click installer.**
No Nix installation is required. This directory is self-contained. Never share a populated VM,
credentials, Windows media, or game installers.

## Current status

Implemented: generation of a dedicated Windows 11 ARM UTM bundle, sparse 80 GiB guest disk,
read-only installation media, unattended Windows answer file, separate administrator and
standard player accounts, configuration audit, and guest-side GOG/Steam installation helper.

Observed locally on UTM 5.0.8: unattended installation to the Windows sign-in screen,
automatic NetKVM installation, outbound networking, intended privacy registry values,
Player desktop after sign-in, and a normal reboot with networking preserved.
The installed display driver is Microsoft Basic Display Driver, not validated acceleration.

New native Player auto-login and startup diagnostics still need a fresh-install test.
Experimental graphics, DirectX 9 gameplay, sound, saves, and LAN discovery remain release
blockers. Game installation and launch are not automated. The Play shortcut starts the VM,
not the game. Local validation is not a published-repository E2E pass or proof of isolation.

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
- The launch audit checks configuration, not the running guest, hypervisor integrity, or malware.

Keep UTM and Windows updated, leave Defender enabled, and play as **Player**, not **VMAdmin**.

## Prerequisites

- Apple Silicon Mac with macOS 13+, preferably at least 16 GiB RAM and 100 GiB free disk space.
- Terminal and Homebrew. Setup installs missing Python **3.11+** and UTM **5.0.8+** through brew.
- A valid Windows 11 Pro license.
- Internet access for the pinned Microsoft Windows ISO, or a local ARM64 ISO override.
- Your own FlatOut 2 purchase on GOG or Steam. Use the same edition/version for all LAN players.

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

Run from this directory:

```sh
./setup-flatout2.command
```

The launcher prompts for Windows license acceptance before downloading or creating a VM.
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

New VMs configure Windows-native automatic login as the standard **Player** account. No host
accessibility or screen-recording permission is required. Privileged preparation runs during
Windows Setup, not through an elevated Player session. Automatic login is bounded: the answer
file requests 999 logons; Windows documents an off-by-one issue in this setting. After that,
use the generated `credentials.json` to sign in. This does not modify existing installations.

At each Player login, a guest-only diagnostic runs from `C:\Program Files\FlatOut2VM` and opens
`%LOCALAPPDATA%\FlatOut2VM\status.txt`. A `dxdiag.txt` report is written beside it. The report
includes account, network configuration, and display-driver information, but never declares
the game ready merely because Windows booted. It uses no network downloads, sharing agents,
host scripting, or elevation. Store sign-in and game installation remain separate.

Windows Setup installs the diagnostic and its common Startup entry before Player login.
The entry ignores other accounts. Failed setup attempts are preserved for diagnosis, not
silently deleted or overwritten. Use **VMAdmin** credentials only when administration is needed.

## Finish guest setup (currently manual)

1. Install the [official UTM Windows guest tools](https://docs.getutm.app/guest-support/windows/)
   inside the VM. Enable the experimental 3D driver. UTM recommends a fresh Windows installation.
   Do not attach an unverified guest-tools ISO before Windows setup; UTM documents possible
   Windows setup black screens with some driver/image combinations.
2. Keep UTM's renderer at Default or ANGLE (Metal). DirectX driver must not be Disabled.
   Without Rosetta, UTM 5.0.8 can fall back to DXMT. No host Rosetta installation is performed here.
3. Run Windows Update and verify Defender is enabled.
4. Download your GOG offline installer inside the guest, or use the Steam helper below.
5. In an elevated Windows PowerShell window, run the helper from the `FLATOUTSETUP` CD:

   ```powershell
   # Substitute the CD drive letter; no execution-policy change is required by this guide.
   & 'E:\guest-setup.ps1' -Store Steam
   # Or:
   & 'E:\guest-setup.ps1' -Store GOG -GogInstaller 'C:\Users\VMAdmin\Downloads\setup_flatout_2.exe'
   ```

   Installer signatures must validate against Valve or GOG. Installation wizards and Steam
   authentication remain interactive. If script execution is blocked, inspect the script and
   follow your Windows execution-policy rules; do not globally disable protection.
6. Sign out of VMAdmin and play as Player. In Steam, sign in as Player and install app **2990**.
   For GOG, install to `C:\Games\FlatOut2`, outside the administrator's profile.
7. Shut down Windows, detach installation CDs in UTM, and take a clean snapshot using UTM.
   Delete seed files and rotate initial passwords after setup if required by your threat model.

FlatOut 2 needs DirectX 9. UTM advertises experimental DirectX 11/12 support, which does **not**
prove this game works. Do not install arbitrary DLL packs or disable Defender to make it run.
Any required guest-only translation layer must be selected and tested before declaring support.

## LAN on normal Wi-Fi

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

To remove: shut down the guest, remove its registration in UTM, then remove only the dedicated
state directory after backing up needed saves. This also removes local credentials and media.
The separately cached Windows ISO remains; remove its exact hash-named file to reclaim that space.
Never point cleanup commands at a parent directory or use UTM deletion on unrelated VMs.

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
