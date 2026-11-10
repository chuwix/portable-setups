# FlatOut 2 VM verification state

## Current scope

Current unit: finalize the flash-drive installation UX for testing on a separate Mac.
User narrowed requirements to flash-drive installation only; authenticated GOG/Steam, audio,
LAN, and further local VM experiments are deferred. Folder selection remains the USB fallback.
The source menu now offers only these two implemented offline routes. Existing
`feat/flatout2-vm` worktree, no ticket; canonical requirements are in implementation.md.
User explicitly authorized commit, push, and merge of the experimental test candidate.
Publication is in progress; runtime acceptance is not implied by merging.

Handoff: [second-machine checklist](testing.md), [user flow](../README.md), and
[cleanup](cleanup.md). This is a runtime test candidate, not accepted E2E: known GOG crash,
unautomated graphics provisioning, and native Windows UX/repair checks remain open. All VMs
are off and UTM exited; host window dragging/resizing stayed laggy after exit, while pointer
and scrolling were smooth. No further host settings or VM operations are part of this unit.

Latest focused verification: **99 offline tests passed**, including the two-choice source-menu
regressions; `git diff --check`, launcher `bash -n`, and local documentation file-link checks
passed. README now removes the contradictory full guest-tools/
store setup recipe. New `docs/testing.md` records second-machine install/UAC/retry/Play/save/
cleanup checks and blocked graphics/gameplay. Focused read-only handoff review passed with no
findings; Windows runtime acceptance and the documented blockers remain open. Implementation
committed as `31c19a7038fd7076736331b1780ffd88ea5bf0e8`; documentation/publication in progress.
No VM operations or deletion in this scope-finalization pass.
Startup/privacy implementation committed locally as
`613637d72c7c464dc3b84661a9d0ec513eac2225`; 37 offline tests passed before commit.

## Evidence and acceptance criteria

- AC-1: Local runtime pass. Fresh autologon candidate reached Player desktop with its report
  open. A diagnostic-triggered normal reboot returned to Player desktop without password entry
  or setup clicks. User reported Windows running before inspection; no agent login input was
  sent for this candidate. Public-repository E2E still pending.
- AC-2: Local runtime partial pass. Startup generated status.txt and dxdiag.txt in Player local
  application data and opened the report. PnP display enumeration returned no devices, so that
  section is inconclusive. Notepad's first-use tooltip obscures part of the report but does not
  block startup. Improve display reporting before declaring diagnostics complete.
- AC-3: Historical baseline passed: Player was created in Users and VMAdmin in Administrators.
  Revised requirement now makes Player an administrator with UAC retained, avoiding end-user
  password entry. Source/tests updated. Existing test VM migration and Yes/No consent verified;
  fresh-install account change still not runtime verified.
  Preparation
  runs during specialize. Recheck regression coverage after changes.
- AC-4: Partial. Existing guest dxdiag reports Microsoft Basic Display Driver, WDDM 1.3.
  Experimental graphics-only package was accepted by Windows with pnputil exit 0 and bound
  to DEV_1050; desktop recovered at higher resolution. Subsequent reboot remained on the
  boot-logo image for more than two minutes. Forced stop followed by cold start recovered
  Player desktop and regenerated the startup report. Could be warm-restart stall or stale
  display. Subsequent inspection identifies Red Hat VirtIO GPU 3D controller,
  100.6.101.58000, WDDM 2.2. A 32-bit D3D9 HAL probe rendered 300 frames with hardware
  vertex processing using neptune_umd_x86.dll (vendor 1af4, device 1050). Readback at frames
  0 and 299 matched center ff00ff and background 002040; visible magenta triangle observed.
   Basic rendering passes; user subsequently confirmed racing/saves with NoSound (details
   below). Sound, LAN, fresh-install repeatability, and restart reliability remain open.
- AC-5: 37 offline tests passed after login/startup changes. Local login/reboot observation
  completed; graphics runtime checks and diagnostics improvements remain pending.

## Verified baseline

The privacy-wrapper local test reached Windows lock screen and Player desktop. NetKVM
installation logged exit 0, driver version 100.100.104.27100, Microsoft signature. VirtIO NIC
obtained a DHCP address; outbound TCP 443 succeeded. All seven intended privacy values were
checked, including Player's tailored-experiences policy. Normal reboot and subsequent DNS/ping
succeeded. These observations do not establish LAN multiplayer or graphics compatibility.

## Outstanding

- Improve display diagnostics and verify the report is refreshed after reboot, rather than
  relying on Notepad's restored tab. Report Generated timestamp advanced after another cold
  startup, proving it was regenerated. Local source now appends dxdiag adapter details,
  refuses stale dxdiag output, and adds a run ID; these additions are not in the installed VM.
  Current test home: FlatOut2VM-autologon; VM UUID
  C614ABE6-A11A-4E94-B5D9-9DC4128CAFAF. Prior privacy-wrapper VM is stopped.
- Review and test the identified experimental ARM64 graphics package. Existing driver ISO is from
  July 2025, before UTM 5 graphics support; the inspected driver directory contains viogpudo
  display-only drivers, not a validated accelerated package.
- UTM v5.0.8 source uses `utm-guest-tools-3d-latest.iso`, which currently redirects to
  `osy/kvm-guest-drivers-windows` v0.5. Inspected graphics-only asset:
  `https://github.com/osy/kvm-guest-drivers-windows/releases/download/v0.5/viogpu3d-arm64x-signed.zip`,
  SHA256 `155695ab7820f71e75c369aeae7b8c060691ba43646ac37edef72aa2428506d5`,
  2,133,662 bytes (GitHub release metadata; local SHA256 matches).
  INF version 100.6.101.58000 targets ARM64 VirtIO GPU DEV_1050. Includes x86 user-mode DLLs;
  D3D9 is routed through D3D9On12. Adds a LocalSystem resolution service, not a sharing agent.
  INF also changes GPU scheduler/preemption and TDR debugging values: review impact before
  installation. Manual isolated test installed this package with pnputil (exit 0), then a
  reboot stopped producing visible progress. Launcher download pins unchanged; graphics is
  NOT enabled in unattended setup. A graphics-only ISO replaced this test VM's seed.iso
  while stopped; original seed preserved as Data/seed-before-graphics.iso. No answer file or
  sharing agents on the diagnostic ISO. Test VM recovered after forced stop and cold start;
  currently running at Player desktop. Warm reboot reliability remains unresolved;
  previous privacy-wrapper baseline remains stopped and unchanged.
- Basic DirectX 9 rendering passed in a development-only probe, not a game or performance
  test. Probe binary SHA256:
  `c9597f786dabf0a22aa5ec71abebaf7a0296bd585bccfa339c79d33df29fdd1e`.
  Built with Go 1.27.3, GOOS=windows GOARCH=386 CGO_ENABLED=0, pinned d3d9 v1.2.4 and
  w32/v2 v2.11.1 dependencies with Go checksum verification. Source, go.mod/go.sum, executable,
  and screenshots remain under this session's approved temporary directory in `d3d9-probe/`.
  Guest result: `%LOCALAPPDATA%\FlatOut2VM\d3d9-probe.txt`. Read-only diagnostic ISO contains
  the probe; original setup seed remains backed up. Normal shutdown and cold start succeeded
  again to attach this ISO. No new driver changes or host-sharing services added.
- Three consecutive normal restarts after the rendering probe returned to Player desktop
  within 60 seconds without password entry. The second check confirmed Windows boot time
  14:35:14; the third generated a fresh startup report at 14:37:37 on 2026-11-10.
  Earlier hang was not reproduced, but its cause is unknown and no corrective driver change
  was made. Repeated restart smoke checks pass; the original failure is not proven fixed.
- User confirmed FlatOut 2 racing and saves with NoSound. Repeat through a successful automatic
  installation and verify sound/LAN. Supplied GOG EXE/BIN details are recorded below.
- Public launcher E2E remains pending separate-machine testing. Publication now approved;
  the candidate is not a validated release.
- Clean obsolete task-created VM state after preserving evidence and validating replacement.

See [implementation.md](implementation.md) for delivery and verification steps.

## Resume checkpoint: automatic installer unit

### Current status and next action

- AC-6: USB/folder routes implemented; local USB launcher test passed. Authenticated GOG/Steam
  routes are explicit not-implemented menu options, not working capabilities.
- AC-7: Initial implementation accepts only exact GOG build 26697, requiring its known EXE/BIN
  pair. Detection excludes FlatOut 1, AppleDouble, hidden directories, and symlinks; asks for
  ambiguity/confirmation. Other builds fail explicitly. Windows signature validation passed
  after correcting exact GOG publisher-name handling and whitespace normalization.
- AC-8: Local launcher runtime pass for USB detection, confirmed source, verified file copies,
  verified ISO readback, stopped-VM attachment/reload, and Windows start. No sharing/passthrough
  enabled. User relaxed the original no-guest-click constraint: explicit helper/elevation is
  allowed and Player can be admin if necessary. Latest user steering rejects password prompts:
  new Player accounts now use Administrators, with UAC retained for Yes/No consent. Existing
  test VM migrated successfully using its existing VMAdmin credential (never printed), then
  restarted and automatically logged in. Retried CD helper now shows Yes/No UAC, no password.
- AC-9: Store routes deferred, not verified. No account credentials collected.
- AC-10: Helper exercised locally; successful installer completion NOT verified. It validates hashes/GOG signature, copies
  into guest-local storage, silently installs with no auto-reboot, writes logs/result/receipt,
  and creates a public desktop game shortcut. Retry receipt checks game hash. Host Play still
  boots the VM only. No assertion that game installation or launch works yet.
- AC-11: 51 offline tests pass, shell syntax and PowerShell parser pass; `git diff --check`
  passes. Guest helper execution, publisher/hash acceptance, and Player game-menu launch with
  NoSound passed locally. Successful installer exit/retry receipt, game-media detachment,
  sound and LAN remain unverified. User confirmed racing and saves work nicely with NoSound;
  cross-reboot save persistence has not been independently checked.
- Latest failure diagnosed from guest result.json: Authenticode status Valid, but our subject
  regex rejected actual signer GOG's certificate legal name. A first exact-name retry exposed
  repeated spaces in `GOG  sp. z o.o.`. Source now normalizes whitespace and compares
  certificate SimpleName to exact allowed GOG
  legal names while still requiring Valid. Elevated window stays open and failure handler
  prints/preserves error/result location. 51 tests and PowerShell parse pass.
- Rebuilt/readback-verified game CD twice while stopped; previous versions preserved as
  `game-before-publisher-fix.iso` and `game-before-publisher-whitespace-fix.iso`. Latest helper
  launched and Yes/No UAC approved in local development testing; no password needed. The
  resulting installer failure is recorded below. Known/unknown publisher cases tested
  with PowerShell, including double-space spelling and rejection of name suffix/prefix spoofing.
- Latest runtime result: publisher/hash checks PASSED, guest payload copy completed, installer
  ran but exited -1073740771 (`0xC000041D`). Helper correctly reports failure and retains logs.
  Guest latest run: `C:\ProgramData\FlatOut2VM\install-a4e2debe-5e79-4e1f-8ebb-ce5de53e7761`.
  Inno log reports 'Installation process succeeded' at 15:32:00, then runs bundled
  `C:\Games\FlatOut2/_redist/DirectX/DXSETUP.exe /silent`. At 15:32:34 it records an access
  violation in the installer temporary module (write to 0000024C), after 'Need to restart
  Windows? No'. Files/registry may already be installed, but no successful helper receipt or
  shortcut/result can be claimed. Do not convert this exit code into success.
- Next: investigate bundled DirectX post-install step/installer crash and verify game files,
  safe retry options, and output-only guest audio. Preserve failed run and original installer.
  Installation not yet verified. Fresh-VM account change also needs runtime verification.
  Initial helper launch FAILED: Windows default Restricted policy produced SecurityError /
  UnauthorizedAccess before script execution. User approved process-only RemoteSigned for
  both initial/elevated sessions. Source fix, regression tests, PowerShell parse, and read-only
  ISO rebuild/readback passed. VM shut down normally, old game ISO preserved as
  `Data/game-before-remotesigned.iso`, rebuilt `Data/game.iso` attached unchanged and VM started.
  Guest retry passed script execution/elevation; later installer crash remains unresolved.
  No Bypass, saved policy change, Defender change, or relaxed GOG signature check authorized.
- Existing `guest-setup.ps1` is only a manual elevated helper: validates GOG signature, starts
  an interactive installer, and asks for C:\Games\FlatOut2. Steam download is not checksum
  pinned. It does NOT meet the newly approved automatic flow.
- Public Play currently boots Windows only; experimental graphics is still manual/test-only.
  These remain implementation gaps, not validated capabilities.

### Installer and game crash investigation

- DirectX log in `%WINDIR%\Logs\DirectX.log` reports installation ended with value 0 at
  15:32:23. Windows Application event 1000 faults in the GOG setup temporary module, not
  DXSETUP. Installer cleanup/custom code crash remains a hypothesis, not a proven cause.
- Development-only retry of the retained guest-local installer with `/NOGUI` still exited
  -1073740771. Log `C:\ProgramData\FlatOut2VM\nogui-test.log` says installation succeeded,
  dependency already installed, no reboot needed; exit still failed. This direct diagnostic
  retry is NOT automation acceptance evidence. `/NOGUI` has not been added to the helper.
- `C:\Games\FlatOut2\FlatOut2.exe` exists, 2,990,080 bytes. First configuration dialog
  detected VirtIO GPU; game then exited. Windows event 1000 at 15:46:33 reports FlatOut2.exe
  access violation `0xC0000005`, fault offset `0x00216EB1`; no remaining process.
- VM has no audio device, while config selected DirectSound/Primary Sound Driver. Preserved
  binary configuration as `C:\Games\FlatOut2\Savegame\device-before-crash-investigation.cfg`
  by moving device.cfg, then opened the normal first-run configuration dialog again. `-setup`
  alone did not reopen it in this build. Changed Sound Output from DirectSound to NoSound,
  leaving graphics settings unchanged. Game then reached full-screen rendered SELECT PROFILE
  menu, CREATE NEW PROFILE selected. No sound hardware, DLL packs, or security settings changed.
- User subsequently confirmed racing and saves work nicely with NoSound. This is user-reported
  gameplay/save evidence on the current experimental GPU VM, not sound, LAN, cross-reboot save
  persistence, or a clean installer pass. Preserve the working VM and its saves.
  Screenshot evidence: session temporary directory `flatout2-nosound-launch.png`.
- Source helper now prints hash/copy/install progress, but that display-only improvement is
  not on the currently attached game ISO yet. Need regression checks after next code batch.
- User requested local commit and continuation. Next work: investigate output-only audio without
  enabling microphone capture; preserve working NoSound as rollback. Installer exit crash remains
  separate and must not be relabeled success. No push authorized.

### Current implementation and local runtime evidence

- New `install-flatout2.command` bootstraps existing prerequisites, then calls `install-game`.
  `setup-flatout2.command` also enters that route for an installed GPT guest disk instead of
  refreshing unattended media. Explicit `--source-dir` bypasses the source-menu selection but
  still requires confirmation. USB detection uses diskutil external physical disks plus USB
  protocol/internal checks. Scan is bounded to three subfolders and 5000 directories.
- `flatout2_vm.py` builds `Data/game.iso` from only two payload files, manifest, and guest helper
  pair. Readback checks payload hashes and exact manifest/helper bytes. Existing game ISO is
  never overwritten. VM must be stopped, with a GPT disk; status/config are rechecked before
  configuration update. Original setup/probe CDs remain attached unchanged. UTM configuration
  reload failure restores the previous config and retains media for diagnosis.
- `install-gog.cmd` launches `install-gog.ps1` with process-only RemoteSigned, repeated on
  elevation; saved policy and Group Policy remain unchanged. Guest helper
  verifies QEMU and read-only CD volume, asks for RunAs elevation, validates supported file
  names/hash and Valid GOG signer, copies to guest disk, then invokes Inno silent flags.
  Result/logs: `C:\ProgramData\FlatOut2VM\install-<run-id>`. This path is guest-only; host
  launcher cannot observe success. No elevation service or privileged watcher installed.
- Local development E2E used the actual `install-flatout2.command` in Herdr pane w1:p1T with
  `--home /Users/martin.milota/Library/Application Support/FlatOut2VM-autologon`, chose USB
  option 1 and confirmed the identified installer. Completed in about 45 seconds. Both file
  hashes and ISO readback passed, UTM reload/start succeeded. Guest installation not yet run.
- Exact supported-build restriction is deliberate until a safe completeness check for other
  GOG installer layouts exists. Do not advertise arbitrary GOG versions as supported.

### Supplied media

- Host volume `/Volumes/SAMSUNT256`, ExFAT per `diskutil info` (partition type Windows_NTFS),
  256.6 GB external physical disk. At discovery it was
  `/dev/disk4`, partition `disk4s1`; re-identify before use because disk identifiers can change.
- Selected FlatOut 2 files at volume root:
  - `setup_flatout_2_1.0_(26697).exe`
  - `setup_flatout_2_1.0_(26697)-1.bin`
- Also present: FlatOut 1 installer `setup_flatout_1.1_(17772).exe`, `._` sidecars, and system
  directories. Leave them untouched and exclude them from automatic detection/transfer.
- An ad-hoc copy/checksum operation was interrupted by the user. Temporary directory
  `/private/var/folders/c5/cj3448h50vs0t5jst23wrww80000gp/T/opencode/flatout2-gog-media`
  may contain a partial copy; no hashes or completed-copy evidence was returned. Inspect
  before reuse; do not trust its contents as verified. No game installation was attempted.
- USB passthrough was NOT enabled. Approved transfer design is selected files on a temporary
  read-only virtual CD, avoiding exposure of the entire USB drive to the guest.

### Environment and preservation constraints

- Worktree: `/Users/martin.milota/dev/portable-setups/worktrees/feat-flatout2-vm`.
- Current VM home: `~/Library/Application Support/FlatOut2VM-autologon`; UUID
  `C614ABE6-A11A-4E94-B5D9-9DC4128CAFAF`, last observed running as Player with report open.
  UTM UUID matching is case-sensitive. Last VM window ID 206949; refresh if capture fails.
- Previous working privacy-wrapper VM UUID `CEC6D965-1C0D-4C7E-AF68-CFB2C5BEF2BA` is stopped;
  preserve it. Other task test VMs are stopped. Do not start the old VM alongside the current
  one without need, and stop an old active test before starting a replacement.
- Current seed.iso is a diagnostic graphics/probe ISO, NOT the original unattended seed.
  Original is backed up as `Data/seed-before-graphics.iso`. Separate `Data/game.iso` is now
  attached as the fourth drive. Do not overwrite these casually. Remove game media through
  `detach-game` while stopped after verifying installation; detach runtime test still pending.
- Guest credentials are in the current VM home's `credentials.json` (Player/VMAdmin). Never
  print, commit, or put passwords in notes. UI automation is available for diagnosis only,
  not acceptable implementation of user-facing automation.
- Interactive host commands must use existing Herdr split `w1:p1T`, not a new Terminal window.
  Consult `herdr --skill` and verify `HERDR_ENV=1` before control operations.
- Historical pre-publication state: four local unpublished commits: `dd75cb409110f400508769a497595b8e5a18b547`
  (network specialize fix), `613637d72c7c464dc3b84661a9d0ec513eac2225` (privacy/login),
  `36b1e7be493caca2ae4a34f16750d886ce2346c2` (GOG media/helper and admin Player), and
  `befda3412ba5c4c33a193a510a58f5fbdeb9f8df` (requirements and runtime evidence).
  51 tests passed before the latest commits; working tree was clean after both commits.
  Subsequent audio investigation notes are uncommitted. Do not push without explicit approval.
- Public repository is https://github.com/chuwix/portable-setups; earlier published revision
  `b65878336514f623d2a753da1d94a5c8dbd3114a` lacks these local improvements. A local launcher
  test is not a published-repository E2E pass.

## Output-only audio investigation

- UTM 5.0.8 source `Configuration/UTMQemuConfiguration+Arguments.swift:soundArguments`
  generates `hda-output,audiodev=audio1` only when app-wide QEMUSoundBackend is explicitly
  CoreAudio and a local HDA card is configured. Otherwise HDA uses `hda-duplex,audiodev=audio0`.
  `UTMQemuConfigurationSound.swift` stores only Hardware; no per-VM output-only switch.
- UTM docs https://docs.getutm.app/preferences/macos/ identify CoreAudio as output-only.
  The input/output toggles in Apple-backend docs do not apply to this QEMU Windows guest.
- Current QEMUSoundBackend preference is absent (default), checked read-only. No sound card,
  global preference, or microphone permission changed; working NoSound VM preserved.
- App-wide CoreAudio/HDA test approved and in progress below, retaining NoSound/config rollback.
  Verify no guest recording endpoint. Never permit arbitrary custom QEMU arguments or silently
  restore the default backend with HDA still installed. Gameplay must be saved/exited before
  stopping the working VM.

### Parallel continuation and approved audio experiment

- User explicitly requested focused/long-running subagents and parallel work. Three read-only
  investigations completed: installer crash, output-only audio, and media/launch review.
- User approved the app-wide CoreAudio output-only change and HDA test. Other VMs remain
  stopped. Never grant microphone permission. CoreAudio is not a universal capture-disable
  policy: remote SPICE selects duplex even with that preference. Require a local launch and
  verify the generated codec/backend and guest recording endpoints before gameplay testing.
- Pre-audio guest backup completed at
  `C:\Users\Player\AppData\Local\FlatOut2VM\before-audio-20261110-160732\Savegame`.
  No FlatOut process remained. Normal shutdown requested; hardware not changed yet.
- A focused implementation agent owns only `flatout2_vm.py` and `test_game_media.py` to fix
  missing bundle-root symlink rejection and evidence-preserving orphan ISO recovery. Main
  coordinator owns this tracker and live VM operations. No concurrent VM mutations.
- Installer research found no verified build-specific fix or dependency-skip flag. Keep
  nonzero exits as failures; next diagnostic is a crash-stack capture in a stopped-cloned,
  disposable VM, not repeated reinstallations over the user's working game/saves.
- Host Play integration remains deferred; needs explicit already-running-VM semantics and
  an unelevated guest-local launch mechanism, not sharing or a privileged watcher.
- Audio experiment configured while all VMs were stopped: one `intel-hda`, app preference
  `QEMUSoundBackend=2` after quitting/reopening UTM, diagnostic DebugLog enabled locally.
  Original config and exact absent preference state preserved under VM home
  `audio-experiment-20261110/`. No custom arguments or sharing settings changed.
- Actual launch in `Data/debug.log` contains `-audiodev coreaudio,id=audio1` and
  `-device hda-output,audiodev=audio1`, no `hda-duplex`. SPICE uses a local UNIX socket.
  Windows completed its update/restart sequence and returned to Player desktop automatically.
  Get-PnpDevice shows one present Speakers (High Definition Audio Device), Status OK;
  Win32_SoundDevice Status OK. MMDevices Audio Capture enumeration returned count 0.
  Windows SoundPlayer PlaySync returned without error (audibility needs user confirmation).
  Preserved NoSound device.cfg as Savegame/device-nosound-before-hda.cfg and reopened game
  configuration. DirectSound/Primary Sound Driver selected; launch passed the former immediate
  crash, showing publisher intro, loading screen, then SELECT RACE (Timberlands 1). Audible output and racing with audio
  user subsequently reports audible but very choppy game/sound and laggy whole Windows.
  Audio runtime test FAILED performance acceptance; successful initialization is not a pass.
  Window ID after reopening UTM: 207442.
- Media-recovery agent completed bundle-root symlink guard and confirmed orphan quarantine
  via `detach-game`. Main review and independent full suite passed: 56 tests. Changes remain
  uncommitted; no runtime detachment or cleanup performed on the audio test VM. Independent
  scoped reviewer reported no findings. A separate read-only agent is designing the first-run
  journey and isolation-compatible install/launch/media-lifecycle contracts for user approval.
- First-run design returned; proposal awaiting approval: stage confirmed source before fresh
  VM's first boot, bounded unelevated Player-login dispatcher requests UAC once per media,
  explicit retry after denial/failure, launch only from unelevated parent after valid receipt,
  boot-to-game on later logins. No resident service/watcher or host-to-guest command channel.
  Already-running host Play focuses VM and guides to guest shortcut, not remote relaunch.
  Announce source release after ISO readback; Finder eject stays manual. Virtual CD stays until
  guest success plus normal shutdown and explicit detach. Suppress foreground diagnostics on
  successful game startup, retaining an accessible diagnostic shortcut/failure reports.
  Files likely affected: flatout2_vm.py, prepare-guest.cmd, new guest-start.cmd/ps1,
  install-gog.cmd/ps1, guest-status.cmd, tests/docs. Not implemented or approved yet; keep
  installer-crash gate intact. User has now approved this slice with an additional requirement:
  explain end-of-use VM cleanup and save-loss warnings. AC-12–AC-16 and parallel ownership
  are recorded in implementation.md. No deletion of current state is authorized.
- Parallel implementation started with disjoint ownership: host orchestration/media tests and
  guest startup/receipt/helpers/tests. Coordinator added `docs/cleanup.md` and README link,
  with normal shutdown, temporary media removal, backup-first permanent removal, exact default
  vs custom home/cache, source/unrelated/shared-tool preservation, and app-wide audio caveat.
  Independent cleanup review found an older README removal shortcut that could put backup after
  destructive UTM removal. Replaced it with the canonical guide and explicit backup-before-UTM
  warning. New guide otherwise passed review; host agent will link it from setup completion.
  No VM, cache, source, or prerequisite deletion performed. Integration and runtime UX remain
  unverified; do not treat the proposed first-login flow as implemented yet.
- Host implementation agent finished source-before-download/pre-first-boot media staging,
  strict helper ISO readback, blank retry recovery, source-release and cleanup messages, and
  explicit Play state branching. Reports 61 focused host tests, 76 total tests passing.
  Independent host review found partial-home registration recovery issue; fixed by host agent
  and re-reviewed with no findings. Guest implementation completed; independent guest review
  in progress. Main coordinator independently reran integrated suite: 83 tests passed, including
  PowerShell behavioral/parser tests. Runtime fresh setup remains unverified.
- Guest review returned two findings; fixes delegated back to guest agent before runtime use:
  elevated install must validate/protect destination ancestors and reject junctions/untrusted
  ownership before installer invocation; automatic CMD startup must not pause indefinitely on
  failure/denial. Recreate guarded Play shortcuts after accepted installation in case GOG writes
  its own public shortcut. ACL/reparse, true token behavior, COM and Windows PowerShell 5.1 still
  need Windows runtime coverage. The 83-test result predates these review fixes.
- Guest agent reports both review issues fixed plus post-install guarded shortcut restoration;
  89 tests reported passing. Independent re-review in progress; coordinator's attempt to rerun
  suite was declined, so latest independently completed suite remains 83 tests before fixes.
- Lag investigation: host CPU ~71% idle and memory pressure healthy; active GPU version still
  100.6.101.58000. No FlatOut process remained during inspection. Many render workers alone
  are not failure evidence. Private debug log preserved as
  `audio-experiment-20261110/debug-audio-lag.log`. NoSound rollback typing was interrupted,
  leaving completion UNCONFIRMED; do not assume device.cfg restored or remove its backups.
- User now explicitly requests FRESH VM WITH SOUND, not a no-audio fresh baseline. Create a
  separate candidate home, HDA + approved app-wide CoreAudio output-only from first boot,
  DebugLog false, guest diagnostics on-demand only. Preserve current VM/saves; normal shutdown
  before starting replacement, no concurrent 8 GiB guests. Do not relax production audit to
  advertise audio as validated; candidate-specific experiment needs strict output-only checks.
  Verify clean Windows responsiveness before game, then actual sound/racing/save behavior.
  Keep updates/Defender/UAC/signature checks enabled. Fresh game automation still depends on
  unresolved GOG installer crash and Windows validation of new helpers.
- Requested normal shutdown of the laggy current VM for preservation before fresh-audio setup.
  A focused agent is preparing the fresh-audio staging sequence without weakening production
  audits; no fresh candidate has been created or booted yet.
- Guest re-review verified prior fixes but found save-permission repair regression: recursive
  destination checks reject intentional Player-writable Savegame contents during repair. Guest
  agent is implementing a narrow safe policy and regression test; never exempt unchecked
  writable directories from elevated installer safety checks. Fresh UX not runtime-ready yet.
- All existing VMs now stopped. Fresh candidate home absent at preflight; ~1676 GiB free.
  Existing graphics ZIP checksum matches pin. Prepare-only implemented, agent reports 96 tests;
  independent stage-only review in progress. Invoked actual setup wrapper in existing Herdr
  pane w1:p1T for `FlatOut2VM-fresh-audio --stage-only --source-dir /Volumes/SAMSUNT256`.
  Confirmed ordinary Windows/source terms using user's earlier verification consent; staging
  in progress, no boot. Candidate must receive sound before first boot; game CD deferred until
  clean Windows/graphics checks. Preserve old VM/config and interrupted rollback evidence.
- Fresh staging completed through actual wrapper in 41s; prepare-only returned without opening
  or registering VM. Candidate UUID `FBB49FDA-D707-4005-BAA5-D9B1361C1D6C`. Verified blank disk,
  global CoreAudio 2, DebugLog false, no sharing/custom args. Preserved staged config and game
  drive record under candidate `experiment/`; configured exactly one intel-hda and deferred
  already-verified game.iso by removing only its drive record. Candidate not booted; guest
  review fix and stage-only review pending. This is development-only audio configuration,
  still refused by ordinary production audit, not public audio-support evidence.
- Independent stage-only review passed with no findings. Checked all seven candidate seed
  helper source files against current worktree bytes; matched at this check. Candidate remains
  unbooted with HDA and DebugLog false. Repeat comparison/refresh if pending guest repair
  agent changes helpers before first boot; no stale seed should be treated as reviewed.
- Guest save-preserving repair fix completed; independent re-review pending. Coordinator
  independently ran full suite: 97 tests passed including PowerShell behavior/parser checks.
  Refreshed fresh candidate seed with latest helper sources while all VMs stopped and disk
  blank; preserved prior ISO as Data/seed-before-save-repair.iso. Exact config comparison
  against production-audited staged config permits only HDA card and deferred game-drive
  record. Game.iso still contains earlier helper bytes and MUST be rebuilt/reverified before
  attaching later; currently unattached, no game install can begin from it. Candidate unbooted.
- Final save-repair source review passed with no findings; Windows native ACL/handle/archive
  behavior remains unverified. Registered candidate via open, confirmed stopped, then started
  UUID FBB49FDA-D707-4005-BAA5-D9B1361C1D6C with HDA from first boot, DebugLog false, game CD
  unattached. Earlier VMs remain stopped. Candidate window ID 207560 exists/visible per UTM and
  CoreGraphics, but screencapture of it repeatedly returned 'could not create image from window';
  Windows setup progress not yet visually verified. No diagnostic logging enabled to work around
  capture failure. Need inspect visible candidate/refresh capture before claiming install progress.
- User visually confirmed fresh Windows installation running, then reported whole macOS sluggish
  (window movement lag). Only fresh candidate running; old VMs stopped. QEMU observed ~182%
  sampled CPU / ~438% ps reading, no render-server workers; host still 46–65% idle, memory
  pressure healthy, no new swap I/O in sample. Reproduces without game, guest experimental
  GPU driver, or DebugLog; audio vs active installation not isolated.
- User approved suspend comparison. Ran `utmctl suspend` on fresh UUID; status is `paused`.
  No force stop, disk discard, settings change, or resume. QEMU CPU then ~4.3%, WindowServer
  ~18.2% (previous ~40%); samples alone do not prove responsiveness recovered. Await user's
  macOS window-movement comparison before choosing next experiment. Installation state retained.
- User reports macOS still sluggish while paused, approved saving state and fully quitting UTM.
  Saving already-paused VM refused ('not running'). Briefly resumed, immediately requested
  suspend --save-state; UTM refused because GPU acceleration does not support suspend snapshots.
  Status now paused. No saved-state guarantee, no quit/kill/force-stop performed. Need normal
  guest shutdown (resume + ACPI request, allow setup progress) or user wait before quitting UTM.
  Do not disable GPU/change paused configuration to force snapshot compatibility.
- User explicitly authorized abandoning fresh candidate installation and recreating later.
  Force-stopped ONLY fresh UUID FBB49FDA-D707-4005-BAA5-D9B1361C1D6C, then quit UTM normally.
  Process inspection shows no remaining /Applications/UTM.app processes. Old working VM/saves
  untouched; fresh bundle retained on disk (interrupted installation must not be trusted).
  Await host responsiveness comparison with UTM fully exited. Do not recreate/start another VM
  until this host-lag check is resolved. WindowServer instantaneous CPU ~60.8% after quit is
  not itself a responsiveness result; no host processes/settings changed.
- User confirms macOS still sluggish after UTM fully exited; approved read-only host checks.
  Sample: CPU ~84% idle, WindowServer ~13% CPU, memory pressure healthy, no new swap I/O,
  pmset reports no thermal/performance warning. Two DELL P2725QE displays: landscape 4K and
  rotated portrait 4K, both reported 100 Hz; no evidence this configuration recently changed.
  Targeted recent kernel/WindowServer log query showed no matching GPU reset/stall evidence
  (returned unrelated installation-policy messages). No confirmed root cause. All VMs remain
  off; no unrelated processes, display settings, or WindowServer changed. Next low-impact
  user check: whether both displays and non-pointer animations lag equally, and whether direct
  trackpad input differs from external mouse. Any refresh-rate test/reconnect/reboot requires
  user choice; don't blame normal dual-display setup from configuration alone.
