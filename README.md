# Portable setups

Self-contained setups, isolated environments, and launchers you can share without sharing
your personal machine configuration. Projects do not require Nix.

| Project | Platform | Status |
| --- | --- | --- |
| [FlatOut 2 VM](flatout2-vm/) | Apple Silicon macOS, UTM | Experimental flash-drive installer; E2E blocked |

## Use a project

Open its README before running anything. Each project owns its prerequisites, security
limitations, installation steps, and removal instructions.

There are **no validated installer releases yet**. The source ZIP is available through
GitHub's **Code > Download ZIP**, but downloading source is not a promise of a working
one-click setup. Check the project's status before using it.

### Test the FlatOut 2 prototype

Experimental source is available on `main`; check the project's
[current verification state](flatout2-vm/docs/state.md) for pending follow-up publication.
On an Apple Silicon Mac with Terminal, Homebrew, and Git available:

```sh
git clone https://github.com/chuwix/portable-setups.git
cd portable-setups/flatout2-vm
./setup-flatout2.command --home "$HOME/Library/Application Support/FlatOut2VM-usb-test"
```

Alternatively, download the main branch source ZIP on GitHub, extract it, and open
`flatout2-vm/setup-flatout2.command`. macOS may require permission to open downloaded scripts.
Read [the project's prerequisites and limitations](flatout2-vm/) first. The launcher asks for
Windows license acceptance and a supported GOG offline installer on your flash drive, then
downloads its pinned ISO. Before that it installs missing UTM
and Python through Homebrew, or upgrades an outdated Homebrew-managed UTM. Nix-managed Homebrew
is left unchanged. No ISO path or checksum entry is needed.

Use the [second-machine checklist](flatout2-vm/docs/testing.md) and record the exact revision
tested. Authenticated GOG/Steam, LAN, and audio are outside the current test scope.

Do not upload Windows images, purchased game files, populated virtual machines, credentials,
license keys, or personal configuration. Scripts must not execute a game installer on the host
when the project promises guest isolation.

## Development

For the FlatOut 2 prototype, Python 3.11 or later:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s flatout2-vm -v
bash -n flatout2-vm/setup-flatout2.command flatout2-vm/play-flatout2.command
```

Offline tests validate generated configuration and safeguards, not actual guest isolation or
game compatibility. Runtime acceptance requires a clean installation, complete gameplay,
save persistence, and any networking promised by the project.
