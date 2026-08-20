# Nine Parchments — No Friendly Fire

This version-locked Windows Steam mod prevents health damage between two
different player characters. It also suppresses the player-to-player hit
reaction and floating damage numbers. This makes playing with inexperienced
gamers, such as my kids way more fun. 

This is an unofficial fan-made mod. It is not affiliated with or endorsed by
Frozenbyte. Nine Parchments and its game files are the property of their
respective owners. This repository does not distribute game executables or
other game assets.

Two hooks use the same selective check. The health hook runs at the confirmed
health-subtraction handler. The presentation hook runs earlier, where the game
has prepared the true source entity ID but has not yet dispatched the hit
reaction, floating number, or health event. Each hook resolves the source and
checks `PlayerComponent` on both source and target. It returns early only when
both are different player entities. Enemy damage, player damage to enemies,
and self-damage continue through the original paths.

## Compatibility

Supported original executable SHA-256:

`69b1c5e94533858e7403049f95070c3b2494d5d871e910fcb92ec5c3a217ca27`

Permanent patched executable SHA-256:

`a79659f53ae19cb3939492755f538203b082aba38c1894d337ece3bc0b9e7def`

The manager can upgrade the earlier health-only build, refuses unknown builds,
and verifies the original backup before every install or removal. A Steam
update or **Verify integrity of game files** may restore the executable, after
which the mod must be installed again.

## Use

Close the game before installing or removing the mod.

### Standalone release

Download `NineParchmentsNoFriendlyFire.exe` from the GitHub Releases page and
place it either directly in the Nine Parchments installation folder or in a
direct subfolder. Run it once to show status, or use PowerShell for explicit
actions:

```powershell
.\NineParchmentsNoFriendlyFire.exe --install
.\NineParchmentsNoFriendlyFire.exe
.\NineParchmentsNoFriendlyFire.exe --uninstall
```

The release program contains only the mod manager and patching logic. It does
not contain the Nine Parchments executable or any other game asset.

### Python source

Install the dependency and run the manager from this folder:

```powershell
python -m pip install -r .\requirements.txt
python .\permanent_manager.py --install
python .\permanent_manager.py
python .\permanent_manager.py --uninstall
```

The verified original backup is stored beside the executable as:

`nineparchments_64bit.exe.np-no-ff.original`

Keep that backup while the mod is installed. Temporarily uninstall the mod for
any quest or mechanic that intentionally requires one player to damage another.

## Building the standalone manager

With Python, the requirements installed, and PyInstaller available:

```powershell
python -m pip install pyinstaller
python -m PyInstaller --onefile --name NineParchmentsNoFriendlyFire .\permanent_manager.py
```

Publish only the resulting manager from `dist`. Do not publish a patched or
original copy of `nineparchments_64bit.exe`.

## Tested scope

Local two-player testing confirmed that player-to-player health damage,
reaction, and floating numbers are suppressed. Player-to-enemy and
enemy-to-player damage and presentation remained normal in the same test. The
universal health handler was also confirmed for the tested direct and
ground/area attacks. Online co-op has not been tested; using the same patched
build for every PC participant is recommended to avoid differing simulation.
