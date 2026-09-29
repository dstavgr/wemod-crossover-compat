# Complete setup guide

This guide starts with an existing CrossOver bottle where a Windows game already runs. It uses your current CrossOver installation and does not create or download another version.

## 1. Keep WeMod and the game in one bottle

CrossOver gives every bottle a separate Wine prefix and process namespace. WeMod can attach only to a game process in the same bottle.

Choose the bottle that already runs the game, then set its name:

```sh
BOTTLE_NAME='Your Game Bottle'
BOTTLES_ROOT="$HOME/Library/Application Support/CrossOver/Bottles"
BOTTLE_ROOT="$BOTTLES_ROOT/$BOTTLE_NAME"
```

Confirm it exists:

```sh
test -d "$BOTTLE_ROOT/drive_c" && echo 'Bottle found'
```

Make a CrossOver bottle archive or an APFS copy before changing an important bottle. The patcher makes file-level backups of the two files it edits, while a bottle backup also preserves runtimes and profile data.

The verified bottle used Windows 10 64-bit, Auto graphics, MSync on, and High Resolution Mode off. The patch does not change these settings. Its renderer flags apply to WeMod; the game continues to use the bottle's configured graphics path.

## 2. Install WeMod prerequisites in that bottle

Install the prerequisites required by your WeMod build into the game bottle. The verified WeMod 11.6.0 build requires native **Microsoft .NET Framework 4.8**:

1. Open CrossOver.
2. Select the game bottle.
3. Choose **Install Application into Bottle**.
4. Search for **Microsoft .NET Framework 4.8**.
5. Confirm the existing game bottle as the destination.
6. Complete the component installation.

Wine Mono and the modern .NET SDK do not replace native .NET Framework 4.8 for this build. A newer WeMod release may have different prerequisites; follow that release's requirements.

## 3. Place an unmodified WeMod application in the bottle

Obtain WeMod from a source you are authorized to use. This repository does not redistribute vendor binaries.

Place the application under the bottle's `drive_c`. You can choose any directory name. This guide uses `C:\WeMod`:

```sh
APP_ROOT="$BOTTLE_ROOT/drive_c/WeMod"
mkdir -p "$APP_ROOT"
ditto "/path/to/unmodified/WeMod/application" "$APP_ROOT"
```

The selected directory must directly contain:

```text
WeMod.exe
resources/app.asar
resources/app.asar.unpacked/   # when supplied by that build
```

For the verified 11.6.0 package, the application files were inside the package's `lib/net45` directory. In that case, copy the **contents** of `lib/net45`, not the parent directory.

Do not copy a previously patched `WeMod.exe` or `app.asar` into a new bottle. Reuse an unmodified source so each bottle gets its own verified backups and manifest.

## 4. Clone the patch and run a read-only check

```sh
git clone https://github.com/dstavgr/wemod-crossover-compat.git
cd wemod-crossover-compat

python3 patch.py check --app "$APP_ROOT"
```

The command changes nothing. It prints the WeMod version and detected Electron main entry. There are two successful compatibility states:

```text
tested: ...
structurally compatible, not yet listed as a tested build
```

The first means that exact pair of vendor files passed an end-to-end test. The second means the application passed every deterministic package check but that exact version has not been through the published integration test.

If `check` fails, stop and use the corresponding section in [TROUBLESHOOTING.md](TROUBLESHOOTING.md). Do not weaken the checks or edit the application manually.

## 5. Apply the patch and create the bottle launcher

```sh
python3 patch.py apply \
  --app "$APP_ROOT" \
  --bottle "$BOTTLE_NAME"
```

CrossOver is auto-detected in these locations:

```text
~/Applications/CrossOver.app
/Applications/CrossOver.app
```

For a different location, supply it explicitly:

```sh
python3 patch.py apply \
  --app "$APP_ROOT" \
  --bottle "$BOTTLE_NAME" \
  --crossover "/path/to/CrossOver.app"
```

If your CrossOver bottle directory is also nonstandard, add:

```text
--bottles-root "/path/to/Bottles"
```

The patch creates this directory:

```text
crossover-compat/
├── WeMod.exe.original
├── app.asar.original
├── manifest.json
└── Launch WeMod.command
```

The manifest records the detected product, version, original hashes, and patched hashes. Running `apply` again is safe. It rebuilds from the saved originals and refuses to replace a vendor update or a file changed by another tool.

## 6. Launch WeMod correctly

Double-click `Launch WeMod.command` in Finder or run:

```sh
open "$APP_ROOT/crossover-compat/Launch WeMod.command"
```

The launcher selects the chosen bottle and passes the complete rendering configuration:

```text
--no-sandbox
--compat-force-window
--compat-enable-gpu
--use-angle=swiftshader
--enable-unsafe-swiftshader
--enable-features=Vulkan,UseSkiaRenderer
--use-vulkan=swiftshader
--ignore-gpu-blocklist
--enable-gpu-compositing
--disable-direct-composition
```

Launching `WeMod.exe` directly omits these switches and can recreate the blank window.

### Optional CrossOver icon

1. Open CrossOver and select the game bottle.
2. Choose **Run Command**.
3. Select the patched `WeMod.exe`.
4. append all flags shown above to the command.
5. Choose **Save Command as a Launcher**.

The generated `.command` file remains the reference launcher because it already quotes bottle names and paths safely.

## 7. Sign in and attach to a game

1. Start WeMod through the generated launcher.
2. Wait for the framed window.
3. Sign in normally if this bottle has no WeMod session.
4. Wait until **Library** and **My Games** load.
5. Start the store launcher and game in the same bottle.
6. Open the game's trainer page in WeMod.
7. Click **Play**.
8. Confirm WeMod changes to **Playing** and enables the available options.

For a directly launched game, start its Windows executable in this same bottle instead of a store launcher. If WeMod offers an installation selector, choose the real game executable rather than an intermediate launcher.

Test a reversible trainer option in a single-player session first, turn it back off, and exit without saving until the trainer and game revisions are confirmed compatible.

## 8. Worked example: Epic Games Store and TWW3

This is the verified example, not a requirement of the patch:

```sh
BOTTLE_NAME='Epic Games Store'
BOTTLES_ROOT="$HOME/Library/Application Support/CrossOver/Bottles"
BOTTLE_ROOT="$BOTTLES_ROOT/$BOTTLE_NAME"
APP_ROOT="$BOTTLE_ROOT/drive_c/WeMod116"

python3 patch.py check --app "$APP_ROOT"
python3 patch.py apply --app "$APP_ROOT" --bottle "$BOTTLE_NAME"
open "$APP_ROOT/crossover-compat/Launch WeMod.command"
```

Then:

1. Wait for WeMod's Library.
2. Start Epic Games Launcher in `Epic Games Store`.
3. Launch Total War: WARHAMMER III from Epic.
4. In WeMod, open **Total War: Warhammer III** under **My Games**.
5. Click **Play**.
6. Confirm **Playing** and **Mods are running in the background**.

The verified game executable was:

```text
C:\Program Files\Epic Games\TotalWarWARHAMMERIII\warhammer3.exe
```

## 9. Repeat the setup for another bottle

Each bottle needs its own unmodified WeMod copy, patch manifest, launcher, prerequisites, and login profile. Example for a Steam bottle:

```sh
BOTTLE_NAME='Steam'
BOTTLE_ROOT="$HOME/Library/Application Support/CrossOver/Bottles/$BOTTLE_NAME"
APP_ROOT="$BOTTLE_ROOT/drive_c/WeMod"

mkdir -p "$APP_ROOT"
ditto "/path/to/unmodified/WeMod/application" "$APP_ROOT"

python3 patch.py check --app "$APP_ROOT"
python3 patch.py apply --app "$APP_ROOT" --bottle "$BOTTLE_NAME"
open "$APP_ROOT/crossover-compat/Launch WeMod.command"
```

Use the same pattern for GOG, Ubisoft Connect, Battle.net, Epic, another Steam bottle, or direct executables. Only these variables change:

- `BOTTLE_NAME` selects the Wine prefix;
- `APP_ROOT` identifies that bottle's WeMod directory;
- store and game launch steps follow the software already installed in that bottle.

## 10. Restore or handle an update

Close WeMod before restoring:

```sh
python3 patch.py restore --app "$APP_ROOT"
```

Restore does not delete WeMod's profile, remove runtimes, or alter a game.

When WeMod updates, its updater may replace the patched files. Preserve the new vendor files and run `check` against the new application. If it passes, apply again. If it fails, open an issue with the version and exact error; do not upload the binaries or remove the structural check.
