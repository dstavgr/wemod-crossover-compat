# Complete setup guide

This guide starts with an existing CrossOver bottle in which the Windows game already runs. It does not require another CrossOver installation.

## 1. Choose the target bottle

WeMod and the game must be in the **same bottle**. CrossOver gives each bottle its own Wine prefix and process namespace. A WeMod process in one bottle cannot attach to a game in another bottle, even when both windows are open on the same Mac.

For the verified Epic setup, the bottle is named:

```text
Epic Games Store
```

Its default host path is:

```text
~/Library/Application Support/CrossOver/Bottles/Epic Games Store
```

Before changing the bottle, stop WeMod and make a CrossOver bottle archive or an APFS copy. The patcher also makes file-level backups, but a bottle backup protects installed runtimes and account data.

The tested bottle settings were:

- Bottle type: Windows 10, 64-bit
- Graphics: Auto
- MSync: on
- High Resolution Mode: off

The patch does not change the bottle's graphics settings. Its SwiftShader flags apply only to WeMod; the game continues to use the bottle's normal graphics path.

## 2. Install .NET Framework 4.8 in that bottle

WeMod 11.6 checks for native .NET Framework 4.8 when it starts its support service.

1. Open CrossOver.
2. Select the game bottle.
3. Click **Install Application into Bottle**.
4. Search for **Microsoft .NET Framework 4.8**.
5. Confirm the selected destination is the existing game bottle.
6. Complete CrossOver's component installation.

Do not create a separate .NET or WeMod bottle. The .NET SDK and Wine Mono do not satisfy this application's native Framework check.

## 3. Place the supported WeMod application in the bottle

Obtain WeMod 11.6.0 through a source you are authorized to use. This repository cannot redistribute it.

The tested package exposed the application under `lib/net45`. Copy the contents of that directory into `drive_c/WeMod116` in the target bottle. For example:

```sh
BOTTLE_NAME='Epic Games Store'
BOTTLE_ROOT="$HOME/Library/Application Support/CrossOver/Bottles/$BOTTLE_NAME"
SOURCE_DIR="$HOME/Downloads/wemod116/lib/net45"
APP_ROOT="$BOTTLE_ROOT/drive_c/WeMod116"

mkdir -p "$APP_ROOT"
ditto "$SOURCE_DIR" "$APP_ROOT"
```

The resulting layout must contain at least:

```text
drive_c/WeMod116/WeMod.exe
drive_c/WeMod116/resources/app.asar
drive_c/WeMod116/resources/app.asar.unpacked/
```

Verify the two supported files before patching:

```sh
shasum -a 256 "$APP_ROOT/WeMod.exe" "$APP_ROOT/resources/app.asar"
```

Expected output:

```text
2598ca2fba0f24b9f2e955d8dd1a2644be04b648f350adc92e7c266182412bfd  .../WeMod.exe
e3dd93c7ebc3cdf092a22564480468bd4748670d4888bd5942cde1b297606b40  .../resources/app.asar
```

Stop if either hash differs. This patch is tied to the exact Electron bundle structure of WeMod 11.6.0.

## 4. Locate CrossOver

CrossOver is commonly installed in either:

```text
/Applications/CrossOver.app
~/Applications/CrossOver.app
```

Set the actual path on your Mac:

```sh
CROSSOVER_APP="$HOME/Applications/CrossOver.app"
test -x "$CROSSOVER_APP/Contents/SharedSupport/CrossOver/bin/wine"
```

If that command fails and CrossOver is in the system Applications directory, use:

```sh
CROSSOVER_APP='/Applications/CrossOver.app'
```

## 5. Apply the patch

Clone this repository, then apply the patch to the unmodified application:

```sh
git clone https://github.com/dstavgr/wemod-crossover-compat.git
cd wemod-crossover-compat

python3 patch.py apply \
  --app "$APP_ROOT" \
  --bottle "$BOTTLE_NAME" \
  --crossover "$CROSSOVER_APP"
```

Success prints two lines: one confirming the patch and one naming the generated launcher. The following files are created inside `WeMod116/crossover-compat`:

```text
WeMod.exe.original
app.asar.original
manifest.json
Launch WeMod.command
```

The original files are checksum-verified. Re-running the same command is safe and produces the same patched files. The patcher refuses to replace an unknown vendor update or a file changed by another patch.

## 6. Launch WeMod correctly

The generated `.command` launcher contains the complete tested Chromium configuration. Double-click it in Finder or run:

```sh
open "$APP_ROOT/crossover-compat/Launch WeMod.command"
```

The essential Windows command is:

```text
"C:\WeMod116\WeMod.exe" --no-sandbox --compat-force-window --compat-enable-gpu --use-angle=swiftshader --enable-unsafe-swiftshader --enable-features=Vulkan,UseSkiaRenderer --use-vulkan=swiftshader --ignore-gpu-blocklist --enable-gpu-compositing --disable-direct-composition
```

Launching only `C:\WeMod116\WeMod.exe` omits the renderer selection and can recreate the blank window.

### Optional: create a normal CrossOver icon

1. Open CrossOver and select the target bottle.
2. Click **Run Command**.
3. Paste the complete Windows command shown above into **Command**.
4. Click **Save Command as a Launcher**.
5. Use the new **WeMod** launcher inside CrossOver or the generated macOS app under `~/Applications/CrossOver`.

If `WeMod116` was installed somewhere else inside `drive_c`, change only the executable path. Preserve every flag.

## 7. First login and expected behavior

On the first launch in a new bottle:

1. Wait for the framed WeMod window to appear.
2. Choose **Log in now** and complete the normal WeMod login.
3. Wait for **Library** and **My Games** to appear.

The window is briefly raised above other windows so Wine presents it correctly. The patch returns it to the normal window level after 1.5 seconds.

The following messages are harmless when other startup milestones succeed:

```text
WSALookupServiceBegin failed with: 8
Failed parsing 'srcset' attribute value
Unsupported pixel format: -1
```

## 8. Epic Games and Total War: WARHAMMER III

Use this order for the verified setup:

1. Launch the patched WeMod in the `Epic Games Store` bottle.
2. Wait for its Library to finish loading.
3. Launch Epic Games Launcher in the same bottle.
4. Start Total War: WARHAMMER III from Epic.
5. In WeMod, open **Total War: Warhammer III** under **My Games**.
6. Click **Play** on the trainer page. If the game is already running, WeMod attaches to that process.
7. Confirm the top-right state changes to **Playing**.
8. Confirm WeMod reports **Mods are running in the background** and the trainer switches become available.

The tested game process is:

```text
C:\Program Files\Epic Games\TotalWarWARHAMMERIII\warhammer3.exe
```

Use trainer options in a single-player campaign or battle. Test a reversible option first, turn it back off, and exit without saving until you are satisfied that the game and trainer revisions match.

## 9. Install into another bottle

Repeat the setup separately for every bottle. Do not point a launcher in one bottle at an application in another prefix.

For a bottle named `Steam`, the commands are:

```sh
BOTTLE_NAME='Steam'
BOTTLE_ROOT="$HOME/Library/Application Support/CrossOver/Bottles/$BOTTLE_NAME"
APP_ROOT="$BOTTLE_ROOT/drive_c/WeMod116"
CROSSOVER_APP="$HOME/Applications/CrossOver.app"

mkdir -p "$APP_ROOT"
ditto "$HOME/Downloads/wemod116/lib/net45" "$APP_ROOT"

python3 patch.py apply \
  --app "$APP_ROOT" \
  --bottle "$BOTTLE_NAME" \
  --crossover "$CROSSOVER_APP"
```

Then install .NET Framework 4.8 into `Steam`, create that bottle's own launcher, sign in to WeMod in that bottle, and start the Steam game from the same bottle.

Use an **unmodified** WeMod 11.6.0 source for each new bottle. Do not copy a previously patched `WeMod.exe` or `app.asar`; the patcher intentionally expects the original hashes. Copying the original application directory is fine. Account/profile data remains separate because it lives under each bottle's `drive_c/users/crossover/AppData` tree.

The same pattern applies to Battle.net, Ubisoft Connect, GOG, or a direct game executable:

- game, launcher, .NET, and WeMod all belong in one bottle;
- apply the patch to that bottle's own WeMod copy;
- launch WeMod with that bottle's generated `.command`;
- launch the game normally inside that bottle;
- select the detected game in WeMod and click **Play**.

## 10. Restore or update

Close WeMod before restoring:

```sh
python3 patch.py restore --app "$APP_ROOT"
```

Restore does not remove .NET, delete the WeMod profile, or alter the game.

If WeMod updates, the updater can replace the patched files. Do not force this patch onto a different version. Restore when possible, retain the new vendor files, and wait for a patch version that explicitly lists their hashes.
