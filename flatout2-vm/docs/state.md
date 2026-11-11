# FlatOut 2 VM verification state

**2026-11-11: experimental candidate, not accepted end to end.** The latest completed
verification is **105 offline tests**, launcher syntax checks, and `git diff --check`.
Windows PowerShell 5.1 runtime behavior of the new diagnostics remains unverified.

## Verified findings

| Area | Observation | Limit |
| --- | --- | --- |
| Windows setup | Local UTM 5.0.8 tests reached Player desktop, installed NetKVM, obtained outbound networking, and applied all seven intended privacy values. Automatic login and normal reboot were observed. | Not a fresh published-repository E2E pass. |
| Registration | Bounded registration polling recovered the clean-clone setup race and reached Player desktop. | Does not establish game-install success. |
| Media transfer | User-facing USB detection, confirmed EXE/BIN selection, SHA256 copy checks, read-only ISO readback, stopped-VM attachment, and Windows start worked locally. | Guest outcome is not observable by the host launcher. |
| Automatic installation | The first automatic attempt ended in elevation cancellation roughly 123 seconds after its attempt marker. | Cause, prompt visibility, and user response are unknown. The interval does not prove a Windows timeout. |
| Explicit Retry | Hash and GOG signature checks passed; the installer ran and exited `-1073740771` (`0xC000041D`). | Failed installation, even though game files were written. No successful protected receipt. |
| Repair | A later attempt refused a writable game root. Read-only ACL inspection showed an Everyone allow entry on the root and executable. | Complete ACE details and Savegame ACL were not established. Do not normalize ACLs or bypass the refusal. |
| Graphics | A manual graphics-only test used driver 100.6.101.58000 and rendered 300 frames in a 32-bit D3D9 HAL probe, with expected pixel readback. | Graphics provisioning is not automated; a probe does not establish gameplay or performance. |
| Gameplay | User confirmed racing and saves with NoSound, and later confirmed launch after restart through an explicitly approved manual experimental shortcut. | Not shipped behavior, automatic-install success, or verified cross-reboot save persistence. |
| Audio | A local CoreAudio/HDA experiment used `hda-output` and showed no guest recording endpoints. | User reported very choppy game/audio and Windows lag. Performance acceptance failed; production audio remains disabled. |
| LAN | One test VM was explicitly bridged to Wi-Fi `en0`. | Guest-network membership, discovery, and complete multiplayer races remain unverified. Production networking remains Shared. |

The manual shortcut launched existing `C:\Games\FlatOut2\FlatOut2.exe` unelevated, without
arguments, from its game directory. Its description disclosed the failed installation and
missing validated receipt. This approved experiment did not alter the guarded launcher,
receipts, results, ACLs, or automatic startup and must not become an undocumented bypass.

### Sanitized crash and reliability findings

- GOG's log reported installation complete, ran bundled DirectX, and reported no restart
  needed before an access violation in `setup_flatout_2_1.0_(26697).tmp`. Application event
  1001 identified the same application and fault module, version `51.1052.0.0`.
- DirectX's log ended with value 0. A development-only `/NOGUI` retry still failed with
  `0xC000041D`. Neither observation proves the crash cause; no verified build-specific fix
  or dependency-skip flag was found. Do not convert this exit into success.
- WER events referenced dump attachments/report directories, but file accessibility was not
  established. No dump was obtained or analyzed. Suppressed enumeration errors did not prove
  that files were absent. Do not cite old temporary captures or runtime paths as available evidence.
- A game crash with DirectSound selected on a VM without audio hardware stopped after selecting
  NoSound. User-reported racing followed. This does not validate sound support.
- One graphics restart appeared stuck; cold start recovered. Three later normal restarts
  returned to Player desktop within 60 seconds. Cause of the earlier stall remains unknown.
  UTM refused saved-state suspension with the accelerated display device.
- A fresh audio candidate was abandoned after host responsiveness complaints. Lag persisted
  while paused and after UTM exited; read-only CPU, memory, thermal, and targeted log checks
  did not identify a cause. Do not attribute it to the display configuration or claim an audio fix.

## Publication and permanent cleanup

The user has authorized **pushing all changes to `main`** and **permanent removal of all local
FlatOut runtime state, without backups**, accepting loss of saves, Windows state, and runtime
evidence. **Publication and cleanup are pending primary-session execution and verification.**
This authoring pass performs neither operation. The authorization supersedes earlier
preservation-only and no-push instructions; it is not a claim that deletion or publication occurred.

Retain only sanitized findings in repository documentation. Do not rely on historical VM homes,
screenshots, logs, dumps, probe artifacts, or rollback copies surviving cleanup. The detailed
investigation history remains in git at `57e009c`.

## Resume

1. **Primary session:** verify the final source/docs revision, publish the approved changes,
   inventory and permanently remove the authorized local FlatOut runtime state without backups,
   then record verified publication/cleanup outcomes. Do not remove unrelated VMs, source media,
   or shared tools under an ambiguous name match.
2. **Runtime tester:** use a fresh home and the [second-machine checklist](testing.md), not the
   old experimental shortcut or an assumed retained VM. Observe the initial UAC attempt directly.
3. **Implementer:** resolve the installer failure without weakening success/receipt gates and
   deliver reviewed graphics-only provisioning. Native diagnostics, ACL/token/COM behavior,
   repair/archive safety, Play, media detachment, and cross-reboot saves still need acceptance.

Requirements and remaining criteria: [implementation.md](implementation.md).
User operation: [README](../README.md). Removal procedure: [cleanup.md](cleanup.md).
