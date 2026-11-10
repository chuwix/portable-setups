# FlatOut 2 VM verification state

## Current scope

Next unit: automatic game installation from USB/folder, then guest-side GOG/Steam routes.
Four-option requirements and delivery order approved on 2026-11-10; canonical requirements
and AC-6–AC-11 are in implementation.md. Existing `feat/flatout2-vm` worktree, no ticket.
Local commits authorized. No push authorized.
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
  Basic rendering passes; game compatibility and restart reliability remain unverified.
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
- Validate actual FlatOut 2 gameplay after implementing the automatic installer. User chose
  GOG and supplied a USB containing an offline installer and companion BIN (details below).
- Public launcher E2E remains pending publication approval. Local candidate is not a release.
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
- Branch has two local unpublished commits: `dd75cb409110f400508769a497595b8e5a18b547`
  (network specialize fix), then `613637d72c7c464dc3b84661a9d0ec513eac2225` (privacy/login).
  Current requirement/evidence updates are uncommitted. Do not push without explicit approval.
- Public repository is https://github.com/chuwix/portable-setups; earlier published revision
  `b65878336514f623d2a753da1d94a5c8dbd3114a` lacks these local improvements. A local launcher
  test is not a published-repository E2E pass.
