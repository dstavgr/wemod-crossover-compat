# WeMod compatibility patch for CrossOver

[![Test](https://github.com/dstavgr/wemod-crossover-compat/actions/workflows/test.yml/badge.svg)](https://github.com/dstavgr/wemod-crossover-compat/actions/workflows/test.yml)

This project makes compatible Windows builds of WeMod usable inside an existing CrossOver bottle on macOS. It patches the local Electron package, keeps checksum-verified originals, and generates a launcher with the renderer flags CrossOver needs.

The patch is **bottle and store independent**. Steam, Epic Games Store, GOG, Ubisoft Connect, Battle.net, and directly launched games use the same workflow: install WeMod in the bottle that runs the game, apply the patch to that copy, then launch both programs in that bottle.

## What is universal

The patcher does not depend on a bottle name, game, store, WeMod installation directory, hashed Webpack bundle filename, or fixed Electron main filename. It reads `package.json` from `app.asar`, discovers the main process entry, injects the renderer fix at runtime, finds CrossOver in its common macOS locations, and creates a launcher for the selected bottle.

Future WeMod builds can change their Electron layout. The patcher therefore checks structure before writing:

- `app.asar` must identify itself as WeMod;
- its declared main entry must be a safe packed path;
- there must be exactly one compatible primary window configuration;
- `WeMod.exe` must contain exactly one matching ASAR header digest;
- an existing installation may match only its saved original or last patched checksums.

`check` performs these tests without modifying files. A structurally compatible but previously unlisted version is reported as such. An incompatible version is rejected rather than patched by guesswork.

## Verified example

The implementation has been verified end to end with:

| Component | Verified configuration |
| --- | --- |
| macOS | 27 “Golden Gate” |
| CrossOver | 26.3 |
| WeMod | 11.6.0, Electron 34.0.0 / Chromium 132.0.6834.83 |
| Bottle | 64-bit Windows 10 |
| Store | Epic Games Store |
| Game | Total War: WARHAMMER III |

The test reached each relevant state: WeMod opened as a visible interactive window, login completed, the dashboard loaded, TWW3 appeared in **My Games**, Epic launched `warhammer3.exe`, and WeMod changed to **Playing** with **Mods are running in the background**.

The compatibility layer fixes WeMod startup and process attachment. Individual trainer options still depend on the trainer revision, game revision, and the game state where an option is activated.

## Why this is needed

Unmodified Electron builds can reach Windows graphics APIs that Wine does not implement:

```text
DCompositionCreateDevice3 -> E_NOTIMPL
GPU process exits
shared renderer context fails
window is blank or never becomes usable
```

Disabling the GPU alone avoids that crash but does not produce a reliable window. Wine can also expose invalid inherited standard output or error handles to Node. That produces `open EBADF` while the authenticated dashboard loads and looks like an infinite login loop.

The patch:

- selects Electron's bundled SwiftShader Vulkan renderer;
- disables DirectComposition for WeMod;
- replaces invalid main and renderer process output streams;
- gives the main window a native frame;
- shows and raises the window once, then returns it to normal window level;
- recalculates ASAR entry integrity and the ASAR header digest embedded in `WeMod.exe`;
- stores original and patched checksums for repeat application and safe restoration.

The launcher uses `--no-sandbox`, which disables Chromium's process sandbox for WeMod. Modifying the executable also invalidates its original Authenticode signature.

## Easy installer

Clone the repository and run the interactive installer:

```sh
git clone https://github.com/dstavgr/wemod-crossover-compat.git
cd wemod-crossover-compat
python3 patch.py install
```

It displays every detected CrossOver bottle and marks the bottles where WeMod was found:

```text
Choose the bottle that runs your game:
  [1] Epic Games Store — WeMod found (2)
  [2] Steam — WeMod not found
Bottle [1-2] (q to quit):
```

After the user chooses a bottle, the installer:

1. uses the existing WeMod application in that bottle, or asks for a clean extracted WeMod directory;
2. verifies the Electron package before copying or editing anything;
3. installs clean source files under that bottle's `drive_c` when needed;
4. applies the compatibility patch and checksum manifest;
5. creates `crossover-compat/Launch WeMod.command` and prints the launch command.

To supply the clean source in advance while retaining the bottle menu:

```sh
python3 patch.py install \
  --source "$HOME/Downloads/wemod116/lib/net45"
```

To select both values without menus:

```sh
python3 patch.py install \
  --bottle 'Steam' \
  --source "$HOME/Downloads/wemod116/lib/net45"
```

The installer does not download WeMod or install Windows prerequisites. The verified WeMod 11.6.0 build needs Microsoft .NET Framework 4.8 in the selected bottle.

## Manual installation

Set the bottle name and the directory containing `WeMod.exe`:

```sh
git clone https://github.com/dstavgr/wemod-crossover-compat.git
cd wemod-crossover-compat

BOTTLE_NAME='Your Game Bottle'
APP_ROOT="$HOME/Library/Application Support/CrossOver/Bottles/$BOTTLE_NAME/drive_c/WeMod"

python3 patch.py check --app "$APP_ROOT"
python3 patch.py apply --app "$APP_ROOT" --bottle "$BOTTLE_NAME"
open "$APP_ROOT/crossover-compat/Launch WeMod.command"
```

CrossOver is auto-detected in `~/Applications/CrossOver.app` and `/Applications/CrossOver.app`. If it is elsewhere, add `--crossover "/path/to/CrossOver.app"` to `apply`.

Do not launch the patched `WeMod.exe` without the generated flags. A plain shortcut can return to the blank-window or DirectComposition failure.

The [complete setup guide](docs/SETUP.md) explains how to identify paths, prepare any bottle, repeat the setup for other bottles, and use the Epic/TWW3 configuration as an example. The [troubleshooting guide](docs/TROUBLESHOOTING.md) is organized by visible symptom.

## Tested build record

The following original files are the fully verified reference build:

```text
WeMod 11.6.0

WeMod.exe
2598ca2fba0f24b9f2e955d8dd1a2644be04b648f350adc92e7c266182412bfd

resources/app.asar
e3dd93c7ebc3cdf092a22564480468bd4748670d4888bd5942cde1b297606b40
```

Other versions are accepted only when every structural safety check succeeds. Their acceptance means the package can be patched deterministically; it is not a claim that every application feature has been tested on that version.

## Restore

Close WeMod, then run:

```sh
python3 patch.py restore --app "$APP_ROOT"
```

Only `WeMod.exe` and `resources/app.asar` are restored. Account data, bottle runtimes, games, and saves are untouched.

## Diagnostics and privacy

Diagnostics are off by default. Add `--compat-diagnostics` after the generated launcher path:

```sh
"$APP_ROOT/crossover-compat/Launch WeMod.command" --compat-diagnostics
```

This creates `crossover-compat/startup.log`. Application logs can contain account identifiers or short-lived authentication material. Redact logs before sharing them. Never commit bottle profiles, cookies, tokens, game saves, vendor executables, ASAR archives, or diagnostics.

## Development checks

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile patch.py tests/test_patch.py
node --check renderer-bootstrap.js
```

The tests create synthetic ASAR packages. They cover the interactive installer, bottle and application discovery, clean source copying, dynamic entry discovery, arbitrary compatible versions, nested paths, entry integrity, embedded executable digests, unrelated asset preservation, v1 manifest migration, repeat application, restoration, update protection, CrossOver discovery, and launcher generation.

## Scope

This is an independent compatibility project. It does not modify authentication, subscriptions, trainer definitions, anti-cheat systems, or game files. Use trainers only where the game and service rules permit them, such as your own single-player sessions.

WeMod, Wand, CrossOver, Total War, WARHAMMER, Epic Games, and macOS are names belonging to their respective owners. No affiliation is implied.
