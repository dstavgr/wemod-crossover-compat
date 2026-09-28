#!/usr/bin/env python3
"""Apply a reversible startup patch to the supported local WeMod 11.6 build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import struct
import tempfile

SUPPORTED = {
    'archive': 'e3dd93c7ebc3cdf092a22564480468bd4748670d4888bd5942cde1b297606b40',
    'executable': '2598ca2fba0f24b9f2e955d8dd1a2644be04b648f350adc92e7c266182412bfd',
}

MAIN_ENTRY = 'index.js'
RENDERER_ENTRY = 'app-7c36387c.adf761a433026a5b88dc.bundle.js'
FRAMELESS = b'minHeight:640,frame:false,backgroundColor:"#000"'
FRAMED = b'minHeight:640,frame:true,backgroundColor:"#000"'
LAUNCH_FLAGS = [
    '--no-sandbox',
    '--compat-force-window',
    '--compat-enable-gpu',
    '--use-angle=swiftshader',
    '--enable-unsafe-swiftshader',
    '--enable-features=Vulkan,UseSkiaRenderer',
    '--use-vulkan=swiftshader',
    '--ignore-gpu-blocklist',
    '--enable-gpu-compositing',
    '--disable-direct-composition',
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_asar(data):
    if len(data) < 16:
        raise ValueError('Truncated ASAR header')
    size, header_size, pickle_size, json_size = struct.unpack('<4I', data[:16])
    if (size != 4 or header_size != pickle_size + 4
            or json_size > pickle_size - 4 or 8 + header_size > len(data)):
        raise ValueError('Invalid ASAR header lengths')
    return json.loads(data[16:16 + json_size]), data[8 + header_size:], data[16:16 + json_size]


def entry_bytes(header, payload, name):
    entry = header['files'][name]
    if entry.get('unpacked') or 'link' in entry:
        raise ValueError(f'Unsupported packed entry: {name}')
    start, size = int(entry['offset']), entry['size']
    if start < 0 or size < 0 or start + size > len(payload):
        raise ValueError(f'Entry lies outside archive: {name}')
    return entry, payload[start:start + size]


def update_entry(entry, body, offset):
    entry['offset'], entry['size'] = str(offset), len(body)
    if 'integrity' not in entry:
        return
    block_size = entry['integrity'].get('blockSize', 4194304)
    if not isinstance(block_size, int) or block_size <= 0:
        raise ValueError('Invalid integrity block size')
    entry['integrity'] = {
        'algorithm': 'SHA256', 'hash': digest(body), 'blockSize': block_size,
        'blocks': [digest(body[i:i + block_size]) for i in range(0, len(body), block_size)],
    }


def patch_bytes(archive, executable, bootstrap, renderer_bootstrap):
    header, payload, original_header = parse_asar(archive)
    main_entry, original_main = entry_bytes(header, payload, MAIN_ENTRY)
    renderer_entry, original_renderer = entry_bytes(header, payload, RENDERER_ENTRY)
    if original_main.count(FRAMELESS) != 1:
        raise ValueError('Expected exactly one supported frameless window configuration')
    main = bootstrap + b'\n' + original_main.replace(FRAMELESS, FRAMED, 1)
    renderer = renderer_bootstrap + b'\n' + original_renderer
    update_entry(main_entry, main, len(payload))
    update_entry(renderer_entry, renderer, len(payload) + len(main))
    encoded = json.dumps(header, separators=(',', ':'), ensure_ascii=False).encode()
    padding = b'\0' * (-len(encoded) % 4)
    pickle = struct.pack('<II', 4 + len(encoded) + len(padding), len(encoded)) + encoded + padding
    result = struct.pack('<II', 4, len(pickle)) + pickle + payload + main + renderer
    old_hash, new_hash = digest(original_header).encode(), digest(encoded).encode()
    if executable.count(old_hash) != 1:
        raise ValueError('Expected exactly one embedded ASAR integrity digest')
    return result, executable.replace(old_hash, new_hash)


def atomic_write(path, data):
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(temporary, path.stat().st_mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def files(root):
    return {'archive': root / 'resources/app.asar', 'executable': root / 'WeMod.exe'}


def apply(root, bootstrap, renderer_bootstrap):
    targets = files(root)
    backup = root / 'crossover-compat'
    manifest_path = backup / 'manifest.json'
    existing = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    originals = {}
    for key, target in targets.items():
        saved = backup / (target.name + '.original')
        original = saved.read_bytes() if saved.exists() else target.read_bytes()
        if digest(original) != SUPPORTED[key]:
            raise ValueError(f'Unsupported original {target.name}; no files changed')
        current = digest(target.read_bytes())
        allowed = {SUPPORTED[key]}
        if existing:
            allowed.add(existing['patched'][key])
        if current not in allowed:
            raise ValueError(f'{target.name} changed outside this patcher; refusing to overwrite it')
        originals[key] = original
    new_archive, new_executable = patch_bytes(
        originals['archive'], originals['executable'], bootstrap, renderer_bootstrap)
    patched = {'archive': new_archive, 'executable': new_executable}
    backup.mkdir(exist_ok=True)
    for key, target in targets.items():
        saved = backup / (target.name + '.original')
        if not saved.exists():
            atomic_write(saved, originals[key])
    previous = {key: target.read_bytes() for key, target in targets.items()}
    try:
        for key, target in targets.items():
            atomic_write(target, patched[key])
        manifest = {'version': 1, 'original': SUPPORTED, 'patched': {k: digest(v) for k, v in patched.items()}}
        atomic_write(manifest_path, (json.dumps(manifest, indent=2) + '\n').encode())
    except BaseException:
        for key, target in targets.items():
            atomic_write(target, previous[key])
        raise
    print('Patched WeMod 11.6.0. Original EXE and ASAR backed up in crossover-compat/.')


def restore(root):
    targets = files(root)
    backup = root / 'crossover-compat'
    manifest = json.loads((backup / 'manifest.json').read_text())
    originals = {}
    for key, target in targets.items():
        original = (backup / (target.name + '.original')).read_bytes()
        if digest(original) != SUPPORTED[key]:
            raise ValueError('Original backup checksum mismatch')
        if digest(target.read_bytes()) not in {SUPPORTED[key], manifest['patched'][key]}:
            raise ValueError(f'{target.name} changed; refusing to overwrite an update')
        originals[key] = original
    previous = {key: target.read_bytes() for key, target in targets.items()}
    try:
        for key, target in targets.items():
            atomic_write(target, originals[key])
    except BaseException:
        for key, target in targets.items():
            atomic_write(target, previous[key])
        raise
    print('Original application restored. Bottle runtime and user profile are unchanged.')


def launcher(root, bottle, crossover):
    # Only support an app below this named bottle's C: drive.
    prefix = Path.home() / 'Library/Application Support/CrossOver/Bottles' / bottle
    relative = root.resolve().relative_to((prefix / 'drive_c').resolve())
    windows = 'C:\\' + str(relative / 'WeMod.exe').replace('/', '\\')
    wine = crossover / 'Contents/SharedSupport/CrossOver/bin/wine'
    if not wine.is_file():
        raise ValueError('CrossOver wine launcher not found')
    args = [str(wine), '--bottle', bottle, '--no-update', '--cx-app', windows, *LAUNCH_FLAGS]
    destination = root / 'crossover-compat/Launch WeMod.command'
    atomic_write(destination, ('#!/bin/zsh\nexec ' + shlex.join(args) + ' "$@"\n').encode())
    destination.chmod(0o755)
    print(f'Launcher: {destination}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['apply', 'restore'])
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--bottle', help='Generate a launcher for this CrossOver bottle')
    parser.add_argument('--crossover', type=Path, default=Path.home() / 'Applications/CrossOver.app')
    args = parser.parse_args()
    try:
        if args.action == 'restore':
            restore(args.app)
        else:
            if args.bottle:
                # Validate launcher paths before modifying the application.
                prefix = Path.home() / 'Library/Application Support/CrossOver/Bottles' / args.bottle / 'drive_c'
                args.app.resolve().relative_to(prefix.resolve())
                if not (args.crossover / 'Contents/SharedSupport/CrossOver/bin/wine').is_file():
                    raise ValueError('CrossOver wine launcher not found')
            apply(
                args.app,
                Path(__file__).with_name('bootstrap.js').read_bytes(),
                Path(__file__).with_name('renderer-bootstrap.js').read_bytes(),
            )
            if args.bottle:
                launcher(args.app, args.bottle, args.crossover)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()
