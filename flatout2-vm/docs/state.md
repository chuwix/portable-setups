# FlatOut 2 VM verification state

## Current scope

Local automatic Player startup and graphics investigation. Plan and tracker location approved
on 2026-11-10; use existing `feat/flatout2-vm` worktree, no ticket. No push authorized.

## Evidence and acceptance criteria

- AC-1: Local runtime pass. Fresh autologon candidate reached Player desktop with its report
  open. A diagnostic-triggered normal reboot returned to Player desktop without password entry
  or setup clicks. User reported Windows running before inspection; no agent login input was
  sent for this candidate. Public-repository E2E still pending.
- AC-2: Local runtime partial pass. Startup generated status.txt and dxdiag.txt in Player local
  application data and opened the report. PnP display enumeration returned no devices, so that
  section is inconclusive. Notepad's first-use tooltip obscures part of the report but does not
  block startup. Improve display reporting before declaring diagnostics complete.
- AC-3: Baseline passed: Player is created in Users and VMAdmin in Administrators. Preparation
  runs during specialize. Recheck regression coverage after changes.
- AC-4: Partial. Existing guest dxdiag reports Microsoft Basic Display Driver, WDDM 1.3.
  Experimental graphics-only package was accepted by Windows with pnputil exit 0 and bound
  to DEV_1050; desktop recovered at higher resolution. Subsequent reboot remained on the
  boot-logo image for more than two minutes. Forced stop followed by cold start recovered
  Player desktop and regenerated the startup report. Could be warm-restart stall or stale
  display; no fresh accelerated dxdiag inspection or DirectX 9 rendering proof obtained.
  Graphics gate remains blocked on reliability and rendering verification.
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
- Validate DirectX 9 rendering and the actual game; no game installer/account supplied.
- Public launcher E2E remains pending publication approval. Local candidate is not a release.
- Clean obsolete task-created VM state after preserving evidence and validating replacement.

See [implementation.md](implementation.md) for delivery and verification steps.
