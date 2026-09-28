# WeMod 11.6 compatibility patch for CrossOver 26.3

This project makes the exact **WeMod 11.6.0** Windows build listed below usable in a 64-bit CrossOver 26.3 bottle on macOS. It patches the local Electron application, preserves a verified backup, and generates a launcher with the rendering flags CrossOver needs.

No WeMod, CrossOver, Microsoft, or game binaries are included.

## Verified result

The tested configuration is:

| Component | Tested configuration |
| --- | --- |
| Host | macOS 27 “Golden Gate” |
| CrossOver | 26.3.0 |
| Bottle | 64-bit Windows 10 bottle |
| WeMod | 11.6.0, Electron 34.0.0 / Chromium 132.0.6834.83 |
| Game | Total War: WARHAMMER III, Epic Games edition |
| Game launcher | Epic Games Launcher in the same bottle |

Fresh verification reached all of these states:

- WeMod opened as a visible, interactive macOS window from a saved CrossOver launcher.
- Existing WeMod authentication was refreshed and the dashboard loaded without the former infinite login loop.
- Total War: WARHAMMER III appeared under **My Games**.
- Epic launched `warhammer3.exe` and began tracking playtime.
- WeMod attached to the running process, changed its state to **Playing**, and displayed **Mods are running in the background**.

The compatibility patch fixes application startup and trainer attachment. Individual trainer options still depend on the trainer revision, the game revision, and the point in the game where the option is used.

## Why the patch is needed

The unmodified application reaches unsupported Windows graphics APIs under Wine:

```text
DCompositionCreateDevice3 -> E_NOTIMPL
GPU process exits
shared renderer context fails
window is blank or never becomes usable
```

Disabling the GPU alone avoids that crash but does not produce a reliable window. After login, Wine also exposes invalid inherited standard-error handles to Node. Electron then throws `open EBADF` while entering the authenticated dashboard and appears to loop forever.

This patch:

- selects Electron's bundled SwiftShader Vulkan renderer;
- disables the unsupported DirectComposition path;
- replaces invalid stdout/stderr handles in Electron's main and renderer processes;
- changes the main window to a native framed window;
- shows and raises that window once, then restores its normal window level after 1.5 seconds;
- recalculates both ASAR entry integrity records and the ASAR header digest embedded in `WeMod.exe`;
- rejects every unknown WeMod build instead of guessing.

The launcher uses `--no-sandbox`, so Chromium's process sandbox is disabled for this application. Updating the executable also invalidates its original Authenticode signature.

## Installation

Follow the [complete setup guide](docs/SETUP.md). It covers:

- preparing an existing game bottle;
- verifying the exact supported WeMod files;
- applying and restoring the patch;
- creating a normal CrossOver launcher;
- the required launch order for Epic/TWW3;
- installing the same setup into other bottles.

If something fails, use the symptom-based [troubleshooting guide](docs/TROUBLESHOOTING.md).

## Quick start

The following example assumes CrossOver is installed in `~/Applications`, the target bottle is named `Epic Games Store`, and an unmodified WeMod 11.6.0 application is already in `C:\WeMod116` inside that bottle.

```sh
git clone https://github.com/dstavgr/wemod-crossover-compat.git
cd wemod-crossover-compat

python3 patch.py apply \
  --app "$HOME/Library/Application Support/CrossOver/Bottles/Epic Games Store/drive_c/WeMod116" \
  --bottle 'Epic Games Store' \
  --crossover "$HOME/Applications/CrossOver.app"
```

Start the generated launcher:

```sh
open "$HOME/Library/Application Support/CrossOver/Bottles/Epic Games Store/drive_c/WeMod116/crossover-compat/Launch WeMod.command"
```

Do not launch `WeMod.exe` without the generated flags. A plain shortcut returns to the blank-window or DirectComposition failure.

## Supported files

Only this exact build is accepted:

```text
WeMod.exe
2598ca2fba0f24b9f2e955d8dd1a2644be04b648f350adc92e7c266182412bfd

resources/app.asar
e3dd93c7ebc3cdf092a22564480468bd4748670d4888bd5942cde1b297606b40
```

The patcher checks both hashes before writing anything. A refusal is a safety feature; do not remove the check for another release.

## Restore

Close WeMod, then run:

```sh
python3 patch.py restore \
  --app "$HOME/Library/Application Support/CrossOver/Bottles/Epic Games Store/drive_c/WeMod116"
```

The patcher restores only `WeMod.exe` and `resources/app.asar`. Account data, .NET, the bottle, games, and save files are untouched.

## Diagnostics and privacy

Diagnostics are disabled by default. Add `--compat-diagnostics` after the generated `.command` path to write `crossover-compat/startup.log`:

```sh
"$HOME/Library/Application Support/CrossOver/Bottles/Epic Games Store/drive_c/WeMod116/crossover-compat/Launch WeMod.command" --compat-diagnostics
```

Application logs can contain account identifiers or short-lived authentication material. Inspect and redact logs before sharing them. Never commit bottle profiles, cookies, tokens, game saves, vendor binaries, ASAR archives, or diagnostic logs.

## Development checks

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile patch.py tests/test_patch.py
node --check bootstrap.js
node --check renderer-bootstrap.js
```

The tests build synthetic ASAR archives. They verify both modified entries, per-block integrity, the executable's embedded header digest, unchanged unrelated assets, repeat application, restoration, and refusal to overwrite unknown files.

## Scope

This is an independent compatibility project. It does not modify authentication, subscriptions, trainer definitions, anti-cheat systems, or game files. Use trainers only where the game and service rules permit them, such as your own single-player sessions.

WeMod, Wand, CrossOver, Total War, WARHAMMER, Epic Games, and macOS are names belonging to their respective owners. No affiliation is implied.
