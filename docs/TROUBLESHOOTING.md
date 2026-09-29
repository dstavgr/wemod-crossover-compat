# Troubleshooting

Match the visible symptom or exact patcher error before changing the bottle. Reinstalling unrelated components can hide the original failure.

## `app.asar is not a WeMod Electron package`

`--app` points at the wrong directory or the package does not identify itself as WeMod.

Confirm that the same directory directly contains both files:

```text
WeMod.exe
resources/app.asar
```

Use the application directory, not `resources`, the installer directory, or the bottle root.

## `Missing packed ASAR entry`

The package declares a main entry that is absent or stored in a layout this patcher cannot safely modify. Confirm the application was copied completely. If it was, this WeMod release needs a reviewed compatibility update.

## `Expected exactly one compatible primary frameless window configuration`

This WeMod release changed its Electron window construction, or the ASAR was already edited. Start from an unmodified application and run `check` again. If the same error remains, open an issue with:

- WeMod version;
- CrossOver version;
- the complete error line;
- SHA-256 values for `WeMod.exe` and `resources/app.asar`.

Do not upload either vendor file and do not loosen the match count. Requiring one unambiguous target prevents accidental edits to unrelated windows.

## `Expected exactly one embedded ASAR integrity digest`

`WeMod.exe` and `resources/app.asar` do not belong to the same vendor package, the application was already modified, or the executable layout changed. Restore a matching unmodified pair. The patcher cannot safely guess which embedded digest to replace.

## `changed outside this patcher; refusing to overwrite it`

The live file matches neither the original backup nor the last patched hash in `manifest.json`. This commonly means an updater replaced one file, another patch modified it, or only part of the application was copied.

Preserve the current files. If the change is a vendor update, place the complete updated application in a clean directory and run `check`. If you want the old version back, restore both matching originals from `crossover-compat` or from the full bottle backup.

## `Original backup checksum mismatch`

A file in `crossover-compat` no longer matches the manifest. Do not overwrite it or the live application. Recover the bottle backup or a known matching unmodified vendor package.

## `CrossOver was not found`

Pass the actual application path:

```sh
python3 patch.py apply \
  --app "$APP_ROOT" \
  --bottle "$BOTTLE_NAME" \
  --crossover "/path/to/CrossOver.app"
```

If bottles are stored outside the default location, also pass `--bottles-root "/path/to/Bottles"`.

## `--app is not inside bottle`

The application path and bottle name do not refer to the same Wine prefix. Recheck `BOTTLE_NAME`, `APP_ROOT`, and `--bottles-root`. WeMod must live below that bottle's `drive_c` for the generated launcher to reach it.

## No window, a transparent window, or a blank window

The most common cause is starting the executable without the generated flags.

- Launch `crossover-compat/Launch WeMod.command`.
- Re-run `apply` to regenerate the launcher after moving CrossOver or the bottle.
- If you made a CrossOver icon, compare every switch with the setup guide.
- Confirm `manifest.json` is beside the launcher.

These messages indicate the unsupported renderer path was used:

```text
DCompositionCreateDevice3 failed: Not implemented. (0x80004001)
GPU process exited unexpectedly: exit_code=-1073741819
Failed to create D3D renderer
No available renderers
```

## Login succeeds but the dashboard loads forever

Wine may expose an invalid renderer stderr handle. Unpatched Electron code can then throw:

```text
Error: open EBADF
```

The runtime renderer bootstrap fixes this without depending on a versioned Webpack filename. If the loop returns:

1. Close WeMod.
2. Run `python3 patch.py check --app "$APP_ROOT"`.
3. Run the same `apply` command again.
4. Launch only through the generated command.
5. Check whether an updater changed either vendor file.

## The window stays above the game

The current bootstrap removes always-on-top after 1.5 seconds. Reapply the current repository version. An older experimental bootstrap did not lower the window automatically.

## The dashboard works but a game is missing

- Confirm WeMod and the game run in the same bottle.
- Launch the game once so its installation is discoverable.
- Refresh or reopen WeMod's Library.
- Use the control beside **Play** to select the real game executable when offered.

For the Epic/TWW3 example, select:

```text
C:\Program Files\Epic Games\TotalWarWARHAMMERIII\warhammer3.exe
```

## WeMod finds the game but never says `Playing`

1. Start WeMod and wait for Library.
2. Start the store launcher and game in the same bottle.
3. Wait for the real game process, not only an intermediate launcher.
4. Open the trainer page and click **Play**.

In the TWW3 example, the process is `warhammer3.exe`; Creative Assembly's `launcher.exe` is only an intermediate launcher.

The verified 11.6.0 build uses `WeModAuxiliaryService.exe`. It does not need to show a permanent process literally named `trainer.exe` for attachment to succeed.

## `Playing` appears but an individual option has no effect

That is outside the Electron compatibility layer. Check:

- the trainer revision supports the installed game revision;
- the option is valid in the current context, such as campaign map or battle;
- the session is single-player;
- the option's notes do not require a particular activation order;
- another mod is not changing the same value.

Test a reversible option first, turn it off, and exit without saving.

## .NET or support service fails

The verified WeMod 11.6.0 build needs native **Microsoft .NET Framework 4.8** in the same bottle. Wine Mono and the modern .NET SDK are different runtimes.

For that build, confirm the auxiliary service exists below:

```text
resources\app.asar.unpacked\static\unpacked\auxiliary\
```

Other WeMod versions may use different prerequisites or helper layouts.

## Harmless messages from the verified run

These did not prevent the dashboard or attachment:

```text
WSALookupServiceBegin failed with: 8
Failed parsing 'srcset' attribute value
Dropped srcset candidate
Unsupported pixel format: -1
```

Treat them as secondary unless a renderer, window, helper service, or trainer state also fails.

## Collect diagnostics

Run:

```sh
"$APP_ROOT/crossover-compat/Launch WeMod.command" --compat-diagnostics
```

Then inspect:

```text
crossover-compat/startup.log
```

Useful success events include `renderer-bootstrap-installed`, `did-finish-load`, `window-loaded`, and `window-normal-level`. `renderer-bootstrap-failed`, `render-process-gone`, `child-process-gone`, or `uncaughtException` identify the failing stage.

Logs can contain account identifiers or temporary authentication data. Redact them before opening an issue. Do not upload an entire bottle or WeMod profile.

## Return to the original application

Close WeMod and run:

```sh
python3 patch.py restore --app "$APP_ROOT"
```

If restore refuses, preserve the current files. The refusal prevents an update or third-party change from being silently destroyed.
