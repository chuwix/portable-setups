# FlatOut 2 VM requirements and acceptance

## Scope and document ownership

Deliver an experimental Apple Silicon/macOS UTM flow using a legitimate GOG offline installer
from USB or an explicitly selected folder. Authenticated GOG/Steam routes, LAN, reliable audio,
disposable guests, Tiny11, and other host platforms are deferred. Graphics automation is a
delivery gap, not an implicit manual prerequisite that counts as complete.

- [README](../README.md): user guide, prerequisites, supported media, download pins, security limits.
- [state.md](state.md): verified findings, current publication/cleanup status, resume actions.
- [testing.md](testing.md): runtime acceptance procedure and reporting.
- [cleanup.md](cleanup.md): shutdown, temporary media removal, permanent removal and data loss.

## Acceptance criteria

Stable identifiers retain the original requirement mapping. Deferred criteria are not completed.

| ID | Required observable outcome |
| --- | --- |
| AC-1 | Fresh Windows setup reaches Player desktop without guest input and repeats after a normal reboot. |
| AC-2 | Unelevated guest diagnostics produce an accessible account/network/display report without host UI automation or sharing. Successful gameplay is not obscured by diagnostics; failures remain visible. |
| AC-3 | Privileged preparation finishes before Player login. Player is an administrator with UAC enabled, so installation asks Yes/No rather than for a generated password. |
| AC-4 | Diagnostics identify the installed graphics driver. A basic display driver or DirectX feature-level list is never proof of game compatibility. |
| AC-5 | Offline regression tests pass and are reported separately from runtime results. |
| AC-6 | Source menu offers USB detection and explicit folder selection. The originally planned authenticated GOG/Steam options are deferred and not advertised as working. |
| AC-7 | Identify the supported FlatOut 2 EXE and complete matching BIN pair; ignore FlatOut 1, AppleDouble, hidden directories, and symlinks. Resolve ambiguity with user selection. Missing parts, bad signatures, or failed transfers stop with actionable errors. Never execute the installer on macOS. |
| AC-8 | Confirm source/terms, preserve source files, verify transfer integrity, and use temporary read-only media. No host accessibility/screen-recording permission, folder/clipboard sharing, or USB passthrough. Explicit guest helper launch and normal UAC consent are allowed; installer wizard steps remain automatic. Local hashes do not establish vendor authenticity. |
| AC-9 | Deferred store routes keep authentication, MFA, purchases/redemption, ownership, and consent user-controlled inside Windows. Never collect account credentials. GOG Galaxy is optional; authenticated browser download could satisfy that route. |
| AC-10 | Install onto the guest disk with logs, retry-safe state, explicit success/failure, and unelevated Player launch. No VMAdmin password entry, disabled Defender/signature checks, or weakened host isolation. |
| AC-11 | Regressions cover discovery, ambiguity, completeness, transfer integrity, retry state, and failures. Runtime tests use the public launcher and distinguish local from published-repository runs. Gameplay, saves, sound, and LAN each require their own evidence. |
| AC-12 | Fresh setup confirms source and verifies game ISO before first boot. Existing-VM attachment requires an installed GPT disk. Announce source release after ISO readback; external-volume eject remains manual in Finder. |
| AC-13 | Bounded unelevated Player-login dispatcher attempts once per media identity, requests Yes/No UAC, then exits. Denial/failure requires explicit Retry. No service, polling listener, host command channel, persistent execution-policy change, or elevated game launch. |
| AC-14 | Later Player logins attempt one receipt-validated launch. Already-running host Play focuses UTM and directs to the guest shortcut without claiming remote game launch. Missing, paused, or transitional states get guidance without media writes. |
| AC-15 | Protected receipts bind schema, both payload names/sizes/hashes, executable path/hash, run ID, and installer exit. A crash cannot publish success. Restart-required results defer launch. Receipt-matching retry skips payload staging. Logs/results stay guest-local. |
| AC-16 | README/setup completion link cleanup guidance distinguishing shutdown, media removal, and permanent VM removal. Warn of save/Windows loss; describe backup-before-removal, default/custom paths, registration, cache, and host-wide preferences. Guidance alone authorizes no deletion. Preserve unrelated files, source installers, other VMs, and shared prerequisites. |

## Implementation contracts

These describe existing safeguards that future changes must retain, not completed runtime acceptance.

### Host setup and media

- `flatout2_vm.py` owns unattended generation, detection/selection, game ISO creation,
  configuration auditing, registration/start, `install-game`, and `detach-game`.
  `.command` launchers own user-facing bootstrap and invocation. Distribution is a clone/source
  ZIP; there is no separate standalone-download manifest.
- [Supported build and filenames](../README.md#prerequisites) are exact until another layout has
  a safe completeness check. USB discovery uses external physical/USB checks and bounded scanning
  (three subfolders, at most 5000 directories). `--source-dir` skips the menu, not confirmation.
- Stage only the two selected payload files, manifest, and allowlisted helpers. Read-only ISO
  readback verifies hashes and exact manifest/helper bytes. Never expose the whole USB drive.
  Seed/game helper allowlists must stay synchronized with guest validation.
- Reject bundle-root symlinks, unsafe media types, and unrecognized drive configurations.
  Never overwrite an existing game ISO or modify media while Windows runs. Recheck stopped
  state and unchanged configuration before updates; restore configuration on reload failure.
- An orphan `Data/game.iso` requires explicit `detach-game` quarantine confirmation. Preserve it
  under a collision-safe `game-orphan-<UUID>.iso` name; recheck state/config after confirmation.
  Preserve guest disk, other media, and source files.
- Never recreate an existing guest disk or rerun unattended setup on a partitioned disk.
  Blank-home retry requires stopped state and a zero-filled first MiB. This is a prototype
  recovery check, not a general disk classifier. Installed GPT setup routes to game attachment.
- No-prompt boot modification checks both bundled EFI image hashes and the default EFI catalog
  entry before writing, then reads back the replacement. Keep the cached ISO unchanged and
  the system disk before CDs in boot priority.
- After opening a bundle once, fresh setup and blank recovery poll its exact UUID for up to
  60 half-second intervals. Retry only missing registration, require stopped state, propagate
  unrelated errors, and preserve the home with guidance on timeout.
- `setup --stage-only` returns before registration/boot, including eligible blank retries.
  Reject installed GPT homes and non-setup actions. It does not authorize experimental devices
  or relax the production audit.

### Guest startup, installation, and repair

- `prepare-guest.cmd` performs privileged preparation during Windows Setup. It installs protected
  helpers in Program Files and registers the brief Player-only dispatcher. Native AutoLogon is
  bounded and stores the generated Player credential; see the [security tradeoff](../README.md#security-boundary).
  Source changes do not migrate existing guests.
- The synchronous `specialize` command locates seed media by `flatout2-seed.tag`, not a drive
  letter, and runs NetKVM `pnputil /add-driver /install` before OOBE. Missing media/failed install
  fails the command; Windows Setup handles requested reboot. No full guest-tools installer runs.
- Apply privacy policies before networking. Seed tailored-experiences policy into the default
  user profile; set `DisablePrivacyExperience` only after policy writes succeed and use
  `ProtectYourPC=3` to disable Express settings. Failures remain logged and fail setup.
- `guest-start.cmd`/`guest-start.ps1` run unelevated. Record the media attempt before UAC;
  failure/denial must not produce another automatic prompt or an indefinite CMD pause.
  Play, Retry, and diagnostics remain explicit guest actions. Successful startup must not open
  diagnostics over the game.
- `install-gog.cmd`/`install-gog.ps1` and shared `guest-install.ps1` verify QEMU/read-only CD,
  exact payload names/hashes, and Valid Authenticode from an exact allowed GOG legal name after
  whitespace normalization. Prefix/suffix lookalikes remain rejected. Use process-only
  `RemoteSigned` in initial/elevated sessions, never Bypass or saved-policy/Group Policy changes.
- Copy to guest-local storage, invoke silent installation without automatic reboot, and retain
  per-run logs/results. Nonzero failure exits stay failed, including `0xC000041D`. Host success
  means staging/start only. The unelevated parent requires a protected schema-2 receipt and
  matching success result before launch; restart-required results defer it to a later boot.
- Before elevated installation, validate destination ancestors, ownership, ACLs, and reparse
  points. Reject writable/untrusted roots rather than taking ownership or broadening permissions.
  Recreate guarded public shortcuts after installation because the vendor may replace them.
- Repair may preserve an intentionally Player-writable Savegame tree outside the destination,
  under `C:\Games\FlatOut2-saves-<GUID>\Savegame`. Do not exempt unchecked writable trees from
  elevated safety checks. Report archive location; restoration is manual and unelevated with the
  game closed. Never perform an elevated recursive copy from writable saves.
- `guest-status.cmd` reports account/network/display and fresh dxdiag output with a run identity.
  Diagnostics remain under Player local application data. Informational dispatcher stage records
  contain bounded exception/native codes and timing, not messages, payloads, or command lines.
  Logs cannot establish success, authorize retry, or bypass launch validation.

### Isolation and experiments

Keep the [README security boundary](../README.md#security-boundary): no sharing agents, host
integration channel, custom QEMU arguments, bypassed signatures, or disabled Defender/updates/UAC.
Production networking remains Shared with requested host isolation; audio remains disabled.
Bridging, accelerated graphics, and output-only audio experiments are not accepted defaults.
Use versioned, reviewed graphics-only packages, not moving latest downloads or a full guest-tools
suite. Download pins belong in the [README](../README.md#pinned-windows-media).

An HDA test requires local launch, verified CoreAudio output-only QEMU arguments and no guest
recording endpoint. App-wide preference alone is insufficient: remote SPICE may select duplex.
Do not grant microphone permission. Remove an experimental HDA card while stopped before
reverting to a potentially duplex backend. Saved-state suspension is not a reliable experiment
rollback with the accelerated display device.

## Remaining acceptance

1. Resolve the GOG crash without relabeling it success or weakening receipt/signature gates.
   Initial automatic elevation cancellation is a separate unresolved issue; observe its actual
   prompt/response before choosing a startup change. Manual Retry does not pass AC-13.
2. Deliver reviewed graphics-only automation, then verify a complete NoSound race and saves
   through normal reboot on a fresh successful installation. The manual shortcut experiment
   satisfies neither installation nor launch acceptance.
3. Run the [runtime checklist](testing.md): fresh administrator Player/Yes-No consent, Windows
   PowerShell 5.1 diagnostics, native ACLs/tokens/COM/handle/archive behavior, failure/denial retry,
   receipt-gated stopped/running Play, media detachment, and repair preserving save bytes.
4. Repeat from an explicitly published revision on a separate Mac and record each pass, failure,
   or blocker. Offline/static checks are necessary but insufficient.

Current findings and authorized publication/permanent-cleanup work are tracked only in
[state.md](state.md). Detailed superseded plans and investigation history remain at git `57e009c`.
