# Automatic Player startup, graphics validation, and game installation

## Scope

### Registration-race follow-up

User approved the focused fix and a clean-clone run under `~/dev/tink/` in the Herdr split.
Reuse the existing `feat/flatout2-vm` worktree, no ticket. In `flatout2_vm.py`, share a bounded
registration wait between fresh setup and blank-home recovery: open once, poll the exact UUID
for up to 60 half-second intervals, retry only missing registration, and require stopped state.
Other errors propagate immediately. Timeout preserves the home and gives recovery guidance.
Tests cover delayed fresh/recovery registration, timeout, unrelated errors, and nonstopped state.
Run offline tests and syntax checks, then a clean local clone of the committed fix with a fresh
distinct VM home; do not publish or merge this follow-up without approval.

### Current delivery override: flash drive only

User narrowed scope to finalizing the flash-drive flow for separate-machine testing.
Continue in the existing approved worktree, no ticket. Preserve existing implementation and
VM data; no further local VM/audio experiments. User subsequently explicitly approved commit,
push, and merge as an experimental candidate, with runtime blockers retained.

- AC-6 now offers USB detection and explicit folder selection only. Authenticated GOG/Steam
  delivery in AC-9 and the earlier four-option roadmap are deferred, not completed.
- README owns setup, first-login UAC, failure/retry, stopped/running Play, and cleanup guidance.
- `docs/testing.md` owns the independent-machine runtime checklist and known blockers.
- Keep strict installer exit/receipt gates and isolation. The known GOG crash is not success.
- Graphics automation remains an explicit delivery gap; do not recommend full guest tools.
- Verify offline regressions and source review, then hand off runtime acceptance. No claim of
  end-to-end completion until the separate machine passes the required checks.

Continue the experimental Apple Silicon setup on `feat/flatout2-vm` in the existing worktree.
No reference ticket. Keep changes local until publishing is explicitly approved.
Users must not need host accessibility or screen-recording permissions. Store authentication
and game ownership remain interactive. Do not weaken driver signature checks or host isolation.

## Acceptance criteria

- AC-1: A fresh install reaches the Player desktop without guest input and repeats
  that behavior after a reboot.
- AC-2: Guest startup produces a visible diagnostic report without elevation, host automation,
  shared folders, clipboard sharing, or USB forwarding.
- AC-3: Privileged preparation occurs before Player login. Revised by user approval: Player is
  a guest administrator, with UAC retained, so end users never need generated guest passwords.
- AC-4: Graphics validation identifies the actual installed driver. A basic display driver or
  a list of DirectX feature levels must not be reported as proof of game compatibility.
- AC-5: Offline regression tests pass; runtime results remain distinct from static checks.

## Implementation

1. Extend `flatout2_vm.py:unattended` with native Player AutoLogon and the generated Player
   password. Use a bounded logon count and document the stored-credential tradeoff.
2. Extend `prepare-guest.cmd` before its final network-driver call to copy a startup diagnostic
   into Program Files and register it in the common Startup folder. Setup owns the files;
   diagnostics run as Player and write only under Player's local application data.
3. Add a guest-only CMD diagnostic: report account, network configuration, installed display
   devices, and dxdiag output. Open its report automatically, with game compatibility explicitly
   unverified. Do not install a whole guest-tools suite or sharing agents.
4. Update `test_flatout2_vm.py` for AutoLogon identity/password, permissions, seed completeness,
   and startup diagnostics. Update README with verified baseline and pending new runtime checks.
5. Investigate a versioned official experimental graphics package independently of the existing
   NetKVM pin. Review contents/signatures before attempting installation. Do not substitute a
   moving latest download into the launcher.

## Verification

Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s flatout2-vm` and
`git diff --check` in this worktree. Test a fresh VM through `setup-flatout2.command`, then
observe first login, report generation, and reboot without guest input. A local worktree run
is not the public-repository E2E check. Preserve the known-working VM during testing.

Rollback: use a separate test home; do not retrofit the partitioned diagnostic VM with
unattended installation media. Local commits are authorized; no push, merge, or deletion
of unrelated state.

## Approved next unit: installer sources and automatic game installation

User approved this scope on 2026-11-10. Continue in the existing worktree, no ticket.
Local commits are authorized; publishing still requires explicit approval.

### Requirements and acceptance criteria

- AC-6: The user-facing launcher offers four source options:
  1. Automatically detect a FlatOut 2 GOG offline installer on mounted USB media.
  2. Select an installer source directory explicitly.
  3. Obtain/install the game through GOG inside the VM.
  4. Obtain/install the game through Steam inside the VM.
- AC-7: USB detection and explicit-directory routes identify the FlatOut 2 executable and all
  required matching BIN parts. Ignore macOS AppleDouble files and FlatOut 1 installers. Ask
  when candidates are ambiguous; missing parts, invalid signatures, or failed transfers stop
  installation with an actionable error. Do not execute supplied installers on macOS.
- AC-8: After source selection/confirmation, transfer and installation require no host
  accessibility or screen-recording permission. User subsequently authorized an explicit
  guest-side helper launch and elevation step when needed; installer wizard steps should
   still be automatic. Player is a guest administrator with UAC retained. Use temporary
  read-only media, not host shared folders, shared clipboard, or USB passthrough. Verify copy
  integrity; local hashes do not establish vendor authenticity. Preserve source files.
- AC-9: GOG/Steam authentication, MFA, purchases, and required consent remain user-controlled
  inside Windows. Do not infer ownership or collect account credentials. Users may purchase
  or redeem the game if not owned. GOG Galaxy is optional: authenticated offline download in
  the guest browser may satisfy the GOG route. Clearly distinguish interactive store steps
  from automatic installation steps.
- AC-10: All routes install onto the guest disk and converge on logged, retry-safe setup,
  an explicit success/failure result, and a Play action that launches FlatOut 2 as Player.
   User rejects generated-password prompts: use administrator Player and Yes/No UAC consent,
   not VMAdmin credential entry. Never require host UI automation. Keep
   Defender, signature checks, and isolation intact.
- AC-11: Regression tests cover source detection, selection/ambiguity, missing BIN parts,
  transfer integrity, installation state/retries, and failure handling. Runtime verification
  uses the user-facing launcher with the supplied USB media; distinguish local development
  E2E from a later published-repository E2E. Gameplay, saves, sound, and LAN require separate
  runtime evidence; installation success alone does not establish them.

### Delivery sequence and investigation

1. Implement AC-6 options 1–2 first. Inspect `flatout2_vm.py`, `setup-flatout2.command`,
   `bootstrap.sh`, and `guest-setup.ps1` before choosing integration points; preserve standalone
   bootstrap downloads and add any new required files to its verified manifest/tests.
2. Add source detection/selection and matching installer-part validation. Test with the supplied
   SAMSUNT256 files recorded in state.md; do not mistake FlatOut 1 or `._` sidecars for candidates.
3. Use the newly authorized explicit guest-side helper launch/elevation for existing VMs.
   No privileged media watcher or automatic elevation service is needed. New VMs create Player
   in Administrators. Existing test VM requires a one-time development migration with its
   existing administrator credentials; that is not part of the end-user installation flow.
   No guest agent, persistent sharing, or relaxed driver/persistent script policy is approved.
   User approved process-only RemoteSigned for the initial and elevated helper after the
   guest's default Restricted policy blocked its first launch. No Bypass or saved policy change.
   Review GOG
   silent-install switches, signatures, exit codes, dependencies, and licensing behavior using
   current documentation before execution.
4. Stage only the selected installer and companion files onto a read-only ISO. Do not overwrite
   active VM media or modify a running bundle behind UTM. Preserve setup media and evidence;
   use supported media changes or a confirmed stopped VM. Never rerun Windows unattended setup
   on an installed disk. Detach temporary game media after success when safe.
5. Implement guest installation/result handling and actual Player game launch, then regression
   tests and a local launcher-based install using the supplied USB. No manual installer run
   should be reported as automation proof.
6. Add authenticated GOG and Steam guest routes, reusing the installed-game state and Play path.
   Pin public prerequisite downloads/checksums; authenticated game links are not public pins.
   Keep game installers, media, tokens, and credentials out of Git and the public repository.
7. Update README and state.md with implemented behavior versus verified results. Validate
    FlatOut 2 gameplay before enabling experimental graphics by default.

### First-slice integration

- `flatout2_vm.py`: `installer_files`, `find_installers`, `usb_roots`, `choose_installer`,
  `build_game_media`, `reload_vm`, and `game_media`; CLI actions `install-game`/`detach-game`
  with `--source-dir`. Setup routes installed GPT disks to game installation. Existing
  partitioned-disk refresh rejection stays intact for non-GPT/unknown disks.
- `install-flatout2.command`: source-menu launcher using existing bootstrap prerequisite checks.
  Repository is distributed as clone/source ZIP; no separate download manifest exists here.
- `install-gog.cmd`/`install-gog.ps1`: user-launched CD helper, explicit UAC elevation,
  process-only RemoteSigned (initial and elevated sessions), hash/signature verification,
  guest-local copy, Inno silent install, receipt/result,
  public Player shortcut. Host Play integration remains deferred, not implemented.
- `test_game_media.py`: discovery/completeness/ambiguity, copy verification, allowlisted media,
  running/uninstalled VM refusal, config rollback, attach/detach preservation, and helper guards.
- Media recovery hardening: reject a symlink at the bundle root before reading state. When
  `Data/game.iso` exists without an attached drive, `detach-game` asks for explicit confirmation
  and quarantines it as `Data/game-orphan-<UUID>.iso`, preserving evidence. Recheck stopped state
  and unchanged configuration after confirmation. Reject non-file media and unrecognized drive
  configurations. Tests cover cancellation, name collisions, failed reload recovery, changing
  status/configuration during copy, missing backing files, and preservation of other state.
- Source docs: current Inno flags/exit-code references via Context7 `/jrsoftware/issrc`, and UTM
  stopped configuration reload via `/websites/getutm_app`; runtime compatibility still required.

### Verification and rollback

### Approved first-run UX continuation

User approved the proposed UX slice, adding end-of-use removal guidance. Continue in the
existing worktree, no ticket, local commits only, no push. Split implementation into parallel
host orchestration and guest dispatcher units with disjoint file ownership; coordinator owns
documentation, integration review, and serial VM experiments.

- AC-12: Fresh setup confirms USB/folder source and verifies game ISO before first boot.
  Installed-GPT attachment restriction remains for existing VMs. Announce after ISO readback
  that the source is no longer needed; user ejects external volumes in Finder.
- AC-13: A bounded, unelevated Player-login dispatcher attempts installation once per media
  identity, requests normal Yes/No UAC, and exits. Denial/failure requires explicit Retry.
  No service, polling listener, host command channel, saved execution-policy change, or
  elevated game launch. Successful installation launches only through the unelevated parent.
- AC-14: Later Player logins launch a receipt-validated game once. Already-running host Play
  focuses Windows and explains guest shortcut use; never claims actual game launch.
  Missing/suspended/transitional VM states receive actionable guidance without media writes.
- AC-15: Receipts bind schema, both payload files/sizes/hashes, game hash/path, run ID and
  installer exit. Crash cannot publish success; restart-required results defer launch.
  Receipt-matching retry skips payload staging. Logs/results remain guest-local.
- AC-16: README and setup-completion guidance link an end-of-use cleanup guide. Distinguish
  normal shutdown, installer-media cleanup, and permanent VM removal. Warn that deleting VM
  loses game saves/Windows state; explain preserving the stopped VM before removal. Identify
  exact state/cache locations, custom-home handling, UTM registration, and any host-wide
  preferences. Preserve source installers, unrelated files, other VMs, and shared prerequisites.
  Adding guidance does not authorize deleting the current VM or implementing automatic deletion.

Host unit owns flatout2_vm.py and Python orchestration/media tests. Guest unit owns
guest-start.cmd/ps1, guest-install.ps1 (shared contract), install-gog.cmd/ps1,
prepare-guest.cmd, guest-status.cmd and a dedicated guest-flow test module. Host stages
all helpers on seed/game CDs; guest source allowlist must match host ISO verification.
Coordinator owns README, docs/cleanup.md, implementation.md/state.md.

Verification: full offline unittest suite, shell syntax, PowerShell parser/behavior checks
where available, independent read-only review; runtime fresh-VM/UAC/Play/media detach checks
remain separate. Existing working VM/saves stay preserved; installer crash remains failed.
Roll back via scoped source changes and separate fresh VM home, not restoring unattended
media over a partitioned disk. Audio experiment remains excluded from launcher defaults.

### Fresh audio candidate (user-directed performance investigation)

User explicitly requests a fresh VM with sound from first boot and no routine diagnostics.
Candidate home: `~/Library/Application Support/FlatOut2VM-fresh-audio`; preserve all older
VMs/saves/evidence. Add `setup --stage-only` so verified setup can return before registration
or boot; reject this option for installed GPT homes and non-setup actions. Eligible blank
retries must not register or boot in stage-only mode. Normal production audio audit remains
unchanged. Tests prove no open/start on stage-only paths and account/disk preservation.

Coordinator then configures only this stopped candidate for exactly one intel-hda controller,
DebugLog false, and deferred verified game CD. Keep CoreAudio preference 2 and local-only UTM
launch, check all other isolation fields against audited configuration. Windows first boots
with sound; check desktop/playback responsiveness and no recording endpoint before graphics
and game. Install only pinned signed graphics package, never sharing-capable guest tools.
Keep source/license prompts in the actual launcher. New helpers remain subject to independent
review and Windows runtime checks; no claim that fresh sound is a proven fix.

Use the existing offline suite and `git diff --check`, then run the local user-facing launcher.
Verify installation and Play without host control permissions. Keep the previous working VM
and installation disk intact. Avoid starting multiple 8 GiB guests simultaneously. Preserve
failure logs; do not delete unrelated or source-drive data. Push remains prohibited until the
user explicitly approves it.
