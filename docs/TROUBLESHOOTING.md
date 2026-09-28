# Troubleshooting

Match the visible symptom before changing anything. Reinstalling random components can hide the original failure and make the bottle harder to recover.

## `Unsupported original WeMod.exe` or `Unsupported original app.asar`

The files do not match the exact supported 11.6.0 build.

1. Check the hashes in the main README.
2. Confirm you copied the contents of the package's `lib/net45` directory.
3. Confirm an updater did not replace the application.
4. Start again from an unmodified authorized copy.

Do not edit the `SUPPORTED` hashes. ASAR entry names, offsets, window configuration, and integrity records can change between releases.

## `changed outside this patcher; refusing to overwrite it`

The live file matches neither the original nor the last manifest written by this patcher. Preserve it and inspect what changed. To return to the supported state, close WeMod and restore the verified originals from `crossover-compat` or from the full bottle backup.

## No window, a transparent window, or a blank window

The most common cause is launching the executable without the tested flags.

- Use `crossover-compat/Launch WeMod.command`.
- If you created a CrossOver icon, edit it through **Run Command** and compare every flag with the setup guide.
- Confirm `--compat-enable-gpu`, both SwiftShader flags, `Vulkan,UseSkiaRenderer`, and `--disable-direct-composition` are present.
- Confirm the patcher reported success; flags alone do not add the native frame and stream fixes.

Errors such as these confirm that the wrong renderer path was used:

```text
DCompositionCreateDevice3 failed: Not implemented. (0x80004001)
GPU process exited unexpectedly: exit_code=-1073741819
Failed to create D3D renderer
No available renderers
```

## Login succeeds but the dashboard loads forever

In the unpatched renderer, entering `/app/dashboard` can access Wine's invalid inherited stderr handle and throw:

```text
Error: open EBADF
```

The renderer bootstrap fixes this. If the loop returns:

1. Close WeMod.
2. Verify `manifest.json` exists beside the generated launcher.
3. Run the same `patch.py apply` command again.
4. Launch only through the generated command.
5. Check whether a WeMod updater replaced `resources/app.asar`.

## The window stays above the game

The current bootstrap removes always-on-top after 1.5 seconds. Reapply the current repository version. An older experimental bootstrap did not lower the window automatically.

## The dashboard works but the game is missing

- Verify WeMod and the game are running in the same bottle.
- Launch the game once so its installation and executable are discoverable.
- Open WeMod's Library again.
- Use the arrow beside **Play** or the game's installation control to select the executable when the UI offers that option.

For the verified Epic edition of TWW3, select:

```text
C:\Program Files\Epic Games\TotalWarWARHAMMERIII\warhammer3.exe
```

## WeMod finds the game but never says `Playing`

Use the verified order:

1. Start WeMod and wait for Library.
2. Start the store launcher and game in the same bottle.
3. Wait until the real game executable is running, not only its launcher.
4. Open the game's trainer page in WeMod.
5. Click **Play**.

For TWW3, the process must be `warhammer3.exe`. `launcher.exe` is only Creative Assembly's intermediate launcher.

The expected helper is `WeModAuxiliaryService.exe`. WeMod 11.6 does not need to show a permanently separate process literally named `trainer.exe` for the UI to report a successful attachment.

## `Playing` appears but an individual option has no effect

That is beyond the Electron compatibility layer. Check:

- the option is valid in the current state, such as campaign map versus battle;
- the trainer revision supports the installed game revision;
- the session is single-player;
- the option's notes or information icon do not require a specific order;
- another mod is not changing the same values.

Test a reversible switch first and turn it off before saving.

## .NET check or support service fails

Install **Microsoft .NET Framework 4.8** through CrossOver into the same bottle. Wine Mono and the modern .NET SDK are different products and do not satisfy this version check.

Confirm `WeModAuxiliaryService.exe` can start from:

```text
C:\WeMod116\resources\app.asar.unpacked\static\unpacked\auxiliary\
```

## Harmless log messages

These appeared in the successful tested run:

```text
WSALookupServiceBegin failed with: 8
Failed parsing 'srcset' attribute value
Dropped srcset candidate
Unsupported pixel format: -1
```

Treat them as secondary unless the dashboard, helper service, or trainer state also fails.

## Collect diagnostics

Run:

```sh
"/path/to/WeMod116/crossover-compat/Launch WeMod.command" --compat-diagnostics
```

Then inspect:

```text
WeMod116/crossover-compat/startup.log
```

Useful success events include `did-finish-load`, `window-loaded`, and `window-normal-level`. `render-process-gone`, `child-process-gone`, or `uncaughtException` identify the failing stage.

Logs can contain account identifiers or temporary authentication data. Redact them before opening an issue. Do not upload an entire bottle or WeMod's profile.

## Return to the original application

Close WeMod and run:

```sh
python3 patch.py restore --app "/absolute/path/to/the/bottle/drive_c/WeMod116"
```

If restore refuses, preserve the current files. Its refusal prevents an unknown update from being silently overwritten.
