# FlatOut 2 in an isolated UTM VM

**Experimental setup scripts for Apple Silicon Macs. Not yet a tested one-click installer.**
No Nix installation is required. This directory is self-contained. Never share a populated VM,
credentials, Windows media, or game installers.

## Current status

Implemented: generation of a dedicated Windows 11 ARM UTM bundle, sparse 80 GiB guest disk,
read-only installation media, unattended Windows answer file, separate administrator and
standard player accounts, configuration audit, and guest-side GOG/Steam installation helper.

Not verified: UTM importing and booting this generated bundle, unattended Windows setup,
guest drivers, DirectX 9 gameplay, sound, save persistence, or LAN discovery. These are release
blockers. Automated guest-tools installation, game installation, and game launch are not yet
implemented. The Play shortcut currently starts the VM, not the game.

Runtime validation with UTM 5.0.8 or later is outstanding. Offline tests do not establish game
compatibility or security isolation at runtime.

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
- The launch audit checks configuration, not the running guest, hypervisor integrity, or malware.

Keep UTM and Windows updated, leave Defender enabled, and play as **Player**, not **VMAdmin**.

## Prerequisites

- Apple Silicon Mac with macOS 13+, preferably at least 16 GiB RAM and 100 GiB free disk space.
- UTM **5.0.8+**, Python **3.11+**, and a valid Windows 11 Pro license.
- Official English (en-US) Windows 11 ARM64 multi-edition ISO and its published SHA256.
- Your own FlatOut 2 purchase on GOG or Steam. Use the same edition/version for all LAN players.

For an **unmanaged** Mac with Homebrew:

```sh
brew install --cask utm
brew install python
```

If UTM is already installed, use `brew upgrade --cask utm`. On a declaratively managed Mac,
update through its manager instead. These scripts never install or upgrade host software.

Obtain Windows from [Microsoft](https://www.microsoft.com/en-us/software-download/windows11arm64).
Select English, download the ARM64 ISO, and copy the SHA256 from **Verify your download**.
The script checks the hash before preparing the VM. It does not circumvent Microsoft's download flow.

## Prepare the VM

Run from this directory, substituting your ISO path and Microsoft's hash:

```sh
python3 flatout2_vm.py setup \
  --windows-iso '/path/to/Windows11_English_Arm64.iso' \
  --windows-sha256 'PASTE_MICROSOFT_SHA256_HERE' \
  --accept-windows-license
```

Only pass `--accept-windows-license` after reading and accepting Microsoft's Windows license terms.
The generic installation key selects Pro; it does not activate Windows or provide a license.

Default state directory: `~/Library/Application Support/FlatOut2VM/`.
The setup refuses to overwrite existing state. For a separate attempt use `--home '/another/path'`
on every command. Paths can contain spaces; no repository or username is hardcoded.

UTM opens the generated VM. macOS may ask for permission. Start the VM, press a key at the
Windows boot prompt, and allow Windows Setup to use the answer file. Locale, image selection,
disk partitioning, and account creation are preconfigured. Current Windows builds may still
show OOBE/license/account screens. Do not bypass security checks to suppress them.

Use the generated `credentials.json` to sign into VMAdmin for initial setup. An interrupted
attempt is retained for diagnosis; it is not silently deleted or overwritten.

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

The `.command` launchers wrap these commands. Setup still needs its ISO/hash arguments; a
double-click without them reports missing inputs. The Play launcher starts the registered VM.
If it is already running, use its existing window rather than starting another instance.

To remove: shut down the guest, remove its registration in UTM, then remove only the dedicated
state directory after backing up needed saves. This also removes local credentials and media.
Never point cleanup commands at a parent directory or use UTM deletion on unrelated VMs.

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
