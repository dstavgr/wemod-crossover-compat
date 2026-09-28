// Wine can expose invalid inherited stdio handles to Electron's renderer.
// Some Node internals lazily access stderr while constructing an error; under
// CrossOver that secondary EBADF aborts WeMod's authenticated dashboard route.
;(() => {
  const makeSink = fd => ({
    fd,
    isTTY: false,
    writable: true,
    destroyed: false,
    columns: 80,
    rows: 24,
    write: () => true,
    end: () => {},
    destroy: () => {},
    on() { return this; },
    once() { return this; },
    emit: () => false,
    removeListener() { return this; },
    getColorDepth: () => 1,
    hasColors: () => false,
  });

  for (const [name, fd] of [['stdout', 1], ['stderr', 2]]) {
    try {
      Object.defineProperty(process, name, {
        value: makeSink(fd),
        configurable: true,
        enumerable: true,
      });
    } catch (_) { /* A valid stream needs no replacement. */ }
  }
})();
