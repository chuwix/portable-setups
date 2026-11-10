# Automatic Player startup and graphics validation

## Scope

Continue the experimental Apple Silicon setup on `feat/flatout2-vm` in the existing worktree.
No reference ticket. Keep changes local until publishing is explicitly approved.
Users must not need host accessibility or screen-recording permissions. Store authentication
and game ownership remain interactive. Do not weaken driver signature checks or host isolation.

## Acceptance criteria

- AC-1: A fresh install reaches the standard Player desktop without guest input and repeats
  that behavior after a reboot.
- AC-2: Guest startup produces a visible diagnostic report without elevation, host automation,
  shared folders, clipboard sharing, or USB forwarding.
- AC-3: Privileged preparation occurs before Player login; Player remains in Users only.
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
unattended installation media. No commit, push, merge, or deletion of unrelated state.
