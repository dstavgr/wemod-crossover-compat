// CrossOver startup compatibility only. No authentication or trainer modifications.
;(() => {
  const { app } = require('electron');
  const fs = require('fs');
  const path = require('path');
  const diagnostics = app.commandLine.hasSwitch('compat-diagnostics');
  const directory = path.join(path.dirname(process.execPath), 'crossover-compat');
  const log = (event, data) => {
    if (!diagnostics) return;
    try {
      fs.mkdirSync(directory, { recursive: true });
      fs.appendFileSync(path.join(directory, 'startup.log'),
        JSON.stringify({ time: new Date().toISOString(), event, data }) + '\n');
    } catch (_) { /* Logging must never prevent startup. */ }
  };

  // Wine can expose invalid inherited stdio handles to Electron's Node runtime.
  // Avoid lazy initialization of process.stdout / process.stderr by console.
  for (const method of ['log', 'info', 'warn', 'error', 'debug', 'trace']) {
    console[method] = (...args) => {
      if (diagnostics) log('console-' + method, require('util').format(...args));
    };
  }
  // The default compatibility path uses Chromium's software compositor. A
  // caller can retain GPU compositing while selecting Electron's bundled
  // SwiftShader through command-line switches.
  if (!app.commandLine.hasSwitch('compat-enable-gpu')) {
    app.disableHardwareAcceleration();
  }
  app.commandLine.appendSwitch('disable-direct-composition');
  log('bootstrap', { versions: process.versions });
  process.on('uncaughtExceptionMonitor', error => log('uncaughtException', error.stack));
  // Monitor crashes without swallowing the app's exception/rejection behavior.
  app.on('child-process-gone', (_, details) => log('child-process-gone', details));
  app.on('browser-window-created', (_, win) => {
    const contents = win.webContents;
    const forceWindow = app.commandLine.hasSwitch('compat-force-window');
    const windowState = () => ({id: win.id, visible: win.isVisible(), minimized: win.isMinimized(), bounds: win.getBounds(), opacity: win.getOpacity(), display: require('electron').screen.getPrimaryDisplay().workArea});
    for (const event of ['show', 'hide', 'focus', 'blur', 'minimize', 'restore']) {
      win.on(event, () => log('window-' + event, windowState()));
    }
    contents.on('render-process-gone', (_, details) => log('render-process-gone', details));
    contents.on('did-fail-load', (_, code, description) => log('did-fail-load', { code, description }));
    contents.once('did-finish-load', () => {
      log('did-finish-load', { id: win.id });
      // WeMod creates the primary window hidden until a renderer IPC handshake.
      if (win.id === 1 && !app.commandLine.hasSwitch('start-in-tray')) {
        if (forceWindow) {
          const workArea = require('electron').screen.getPrimaryDisplay().workArea;
          win.setBounds({
            x: workArea.x + 48,
            y: workArea.y + 48,
            width: Math.min(1200, workArea.width - 96),
            height: Math.min(800, workArea.height - 96),
          });
          win.setAlwaysOnTop(true);
          // Raising the Wine window once makes it reachable from macOS. Do not
          // keep it above the game after startup.
          setTimeout(() => {
            if (!win.isDestroyed()) {
              win.setAlwaysOnTop(false);
              log('window-normal-level', windowState());
            }
          }, 1500);
        }
        win.show();
        win.restore();
        win.focus();
        if (forceWindow) win.moveTop();
      }
      log('window-loaded', windowState());
    });
  });
  app.whenReady().then(() => log('ready', app.getGPUFeatureStatus()));
})();
