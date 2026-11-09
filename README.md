# Portable setups

Self-contained setups, isolated environments, and launchers you can share without sharing
your personal machine configuration. Projects do not require Nix.

| Project | Platform | Status |
| --- | --- | --- |
| [FlatOut 2 VM](flatout2-vm/) | Apple Silicon macOS, UTM | Experimental prototype; gameplay and LAN unverified |

## Use a project

Open its README before running anything. Each project owns its prerequisites, security
limitations, installation steps, and removal instructions.

There are **no validated installer releases yet**. The source ZIP is available through
GitHub's **Code > Download ZIP**, but downloading source is not a promise of a working
one-click setup. Check the project's status before using it.

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
