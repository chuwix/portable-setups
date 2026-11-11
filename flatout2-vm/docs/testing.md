# Flash-drive flow: second-machine acceptance

Test candidate only, not a verified one-click release. Use a separate Apple Silicon Mac,
the exact candidate revision, a fresh VM home, and the normal `.command` launchers. Do not
copy an existing Windows VM, credentials, or experimental audio configuration.

## Scope and known blockers

Required now: the supported GOG offline installer on a flash drive, automatic Windows/Player
setup, explicit UAC consent, honest install/failure/retry behavior, Play, and safe cleanup.
Folder selection is a fallback for USB detection. Authenticated stores, LAN, and audio are
deferred. Audio stays disabled; use NoSound for gameplay.

- The previous GOG installer exited **0xC000041D** despite creating game files. That is a
  failed install. Do not bypass the exit gate or manufacture a success receipt.
- Accelerated graphics provisioning is not automated. Installation/UX can be assessed without
  it, but gameplay stays blocked until a reviewed graphics-only path is supplied.
- Offline tests mock Windows ACLs, tokens, COM, and native save archival. They do not establish
  Windows PowerShell 5.1 runtime correctness.
- A previous host developed window-move/resize lag that persisted after UTM exited. Cause
  remains unknown. Stop and report host responsiveness problems; do not restart WindowServer.

## Prepare

1. Obtain the candidate checkout with all source files. Record `git rev-parse HEAD` and
   `git status --short`. Published-repository E2E requires an explicitly published revision;
   an unpublished checkout is a candidate test only.
2. Follow the [prerequisites](../README.md#prerequisites). Record Mac model, macOS version,
   UTM version, RAM, free disk space, and connected displays.
3. Keep both purchased files together on the flash drive:
   `setup_flatout_2_1.0_(26697).exe` and `setup_flatout_2_1.0_(26697)-1.bin`.
   Check that source files and unrelated drive content remain unchanged after testing.
4. In Terminal, enter the checkout's `flatout2-vm` directory. Use this distinct home on every
   command. If it already exists, choose another path; do not delete prior attempts.

```sh
./setup-flatout2.command --home "$HOME/Library/Application Support/FlatOut2VM-usb-test"
```

## Acceptance checklist

Record passed, failed, or blocked with observable evidence for each check. A successful host
command does not prove successful guest installation.

1. **Source selection:** Accept terms only if agreed. Choose USB detection and confirm the
   exact pair. Multiple matches require selection; missing BIN/unsupported build fails clearly.
   Folder selection or `--source-dir '/Volumes/DRIVE/folder'` recovers detection failures.
2. **Transfer:** Wait for read-only ISO verification and source-release message. Eject the
   flash drive in Finder, then continue. No USB passthrough, host folder, or clipboard sharing.
3. **First login:** Windows reaches Player automatically. No routine diagnostics window or
   generated-password entry. Defender, updates, driver signatures, and UAC stay enabled.
4. **Installation:** One expected Yes/No UAC prompt; no manual installer wizard. Success
    requires the protected receipt and matching result. Preserve failure logs. Exit 3010 must
    defer launch until a later boot if encountered. The known crash must remain failure.
    Observe the first automatic attempt continuously from before Player login and record whether
    UAC appeared and how it was answered. Manual Retry reaching installation does not pass this
    check. A cancellation message alone does not establish that the user clicked No.
5. **Denial/retry:** In a separate disposable attempt, deny UAC. A later login must not
   automatically prompt again for the same media. Use **Retry FlatOut 2 installation** to
   request consent deliberately. Failure must remain actionable, without automatic loops.
6. **Stopped Play:** After genuine installation success, shut Windows down and run:

   ```sh
   ./play-flatout2.command --home "$HOME/Library/Application Support/FlatOut2VM-usb-test"
   ```

   Windows starts and Player login attempts receipt-validated, unelevated game launch.
7. **Running Play:** Repeat with Windows already running. It selects UTM and directs you to
   the guest shortcut, without claiming remote launch or starting another VM/game instance.
8. **Graphics/gameplay:** Blocked until reviewed graphics-only provisioning is available.
   Then verify responsive host/guest, a complete race with NoSound, saving, normal Windows
   restart, and save persistence. Never install sharing-capable guest-tools suites.
9. **Repair:** Disposable successful installation only: create a Player save, invalidate the
   executable hash, then Retry. Verify original save bytes survive in the reported archive and
   are readable as Player. Also test failure after archival. Restore unelevated with the game
   closed; do not use personal saves. Native handle/ACL behavior needs real Windows evidence.
10. **Media cleanup:** After success and normal shutdown, run:

    ```sh
    python3 flatout2_vm.py detach-game --home "$HOME/Library/Application Support/FlatOut2VM-usb-test"
    ```

    Only game media detaches. Guest disk, saves, setup media, and source drive remain intact.
    Restart without the game CD and recheck launch.
11. **Removal:** Follow the [cleanup guide](cleanup.md). Verify a stopped backup before
    deletion if saves/state are wanted. Removal must be deliberate; preserve shared tools and
    unrelated files. Archives inside Windows are lost with the VM too.

## Report back

Provide revision, environment, checklist results, exact error/exit code, and host responsiveness.
Installer evidence is under `C:\ProgramData\FlatOut2VM\install-<run-id>`; on-demand diagnostics
are under `%LOCALAPPDATA%\FlatOut2VM`. Do not publish credentials, unattended answer files,
purchased installers, full VM bundles, or unreviewed private logs.
Keep Windows crash dumps private: they can contain purchased installer data and process memory.
Share only reviewed, sanitized fault-module and stack findings, not the dumps themselves.

Offline tests alone do not accept the flash-drive flow. Failed installation or blocked gameplay
must remain explicit. Publication and deletion of existing VMs require separate approval.
