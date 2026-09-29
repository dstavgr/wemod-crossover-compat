#!/usr/bin/env python3
"""Install, check, apply, or restore the WeMod CrossOver compatibility patch."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import struct
import tempfile


TESTED_BUILDS = {
    (
        'e3dd93c7ebc3cdf092a22564480468bd4748670d4888bd5942cde1b297606b40',
        '2598ca2fba0f24b9f2e955d8dd1a2644be04b648f350adc92e7c266182412bfd',
    ): 'WeMod 11.6.0 / Electron 34 / CrossOver 26.3',
}

FRAME_PATTERN = re.compile(
    rb'\bminHeight\s*:\s*\d+\s*,\s*frame\s*:\s*'
    rb'(?P<value>false|!1)(?=\s*,\s*backgroundColor\s*:)',
)
RENDERER_PLACEHOLDER = b'__RENDERER_BOOTSTRAP_SOURCE__'
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
    try:
        header = json.loads(data[16:16 + json_size])
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('Invalid ASAR header JSON') from error
    return header, data[8 + header_size:], data[16:16 + json_size]


def safe_entry_path(name):
    if not isinstance(name, str):
        raise ValueError('ASAR entry path is not a string')
    path = PurePosixPath(name.replace('\\', '/'))
    if path.is_absolute() or not path.parts or any(part in ('', '.', '..') for part in path.parts):
        raise ValueError(f'Unsafe ASAR entry path: {name!r}')
    return path


def entry_record(header, name):
    path = safe_entry_path(name)
    node = header
    for part in path.parts:
        files = node.get('files')
        if not isinstance(files, dict) or part not in files:
            raise ValueError(f'Missing packed ASAR entry: {name}')
        node = files[part]
    return node


def entry_bytes(header, payload, name):
    entry = entry_record(header, name)
    if entry.get('unpacked') or 'link' in entry or 'files' in entry:
        raise ValueError(f'Unsupported packed ASAR entry: {name}')
    try:
        start, size = int(entry['offset']), int(entry['size'])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f'Invalid packed ASAR entry: {name}') from error
    if start < 0 or size < 0 or start + size > len(payload):
        raise ValueError(f'Entry lies outside archive: {name}')
    return entry, payload[start:start + size]


def package_metadata(header, payload):
    _, body = entry_bytes(header, payload, 'package.json')
    try:
        package = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('Invalid package.json in app.asar') from error
    identities = {str(package.get(key, '')).strip().lower() for key in ('name', 'productName')}
    if 'wemod' not in identities:
        raise ValueError('app.asar is not a WeMod Electron package')
    main = package.get('main')
    safe_entry_path(main)
    return {
        'name': package.get('productName') or package.get('name'),
        'version': str(package.get('version') or 'unknown'),
        'main': main.replace('\\', '/'),
    }


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


def render_bootstrap(bootstrap, renderer_bootstrap):
    if bootstrap.count(RENDERER_PLACEHOLDER) != 1:
        raise ValueError('Main bootstrap renderer placeholder is missing or ambiguous')
    try:
        renderer_source = renderer_bootstrap.decode('utf-8')
    except UnicodeDecodeError as error:
        raise ValueError('Renderer bootstrap is not UTF-8') from error
    return bootstrap.replace(
        RENDERER_PLACEHOLDER,
        json.dumps(renderer_source, ensure_ascii=False).encode('utf-8'),
    )


def inspect_bytes(archive, executable):
    if not executable.startswith(b'MZ'):
        raise ValueError('WeMod.exe is not a Windows PE executable')
    header, payload, encoded_header = parse_asar(archive)
    product = package_metadata(header, payload)
    _, main = entry_bytes(header, payload, product['main'])
    matches = list(FRAME_PATTERN.finditer(main))
    if len(matches) != 1:
        raise ValueError('Expected exactly one compatible primary frameless window configuration')
    embedded = digest(encoded_header).encode('ascii')
    if executable.count(embedded) != 1:
        raise ValueError('Expected exactly one embedded ASAR integrity digest in WeMod.exe')
    hashes = {'archive': digest(archive), 'executable': digest(executable)}
    tested = TESTED_BUILDS.get((hashes['archive'], hashes['executable']))
    return {'product': product, 'hashes': hashes, 'tested': tested}


def patch_bytes(archive, executable, bootstrap, renderer_bootstrap):
    inspection = inspect_bytes(archive, executable)
    header, payload, original_header = parse_asar(archive)
    main_entry, original_main = entry_bytes(header, payload, inspection['product']['main'])
    match = next(FRAME_PATTERN.finditer(original_main))
    framed_main = original_main[:match.start('value')] + b'true' + original_main[match.end('value'):]
    main = render_bootstrap(bootstrap, renderer_bootstrap) + b'\n' + framed_main
    update_entry(main_entry, main, len(payload))

    encoded = json.dumps(header, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    padding = b'\0' * (-len(encoded) % 4)
    pickle = struct.pack('<II', 4 + len(encoded) + len(padding), len(encoded)) + encoded + padding
    patched_archive = struct.pack('<II', 4, len(pickle)) + pickle + payload + main

    old_hash, new_hash = digest(original_header).encode(), digest(encoded).encode()
    if executable.count(old_hash) != 1:
        raise ValueError('Expected exactly one embedded ASAR integrity digest in WeMod.exe')
    return patched_archive, executable.replace(old_hash, new_hash)


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
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
    executable = root / 'WeMod.exe'
    if not executable.is_file() and root.is_dir():
        candidates = [path for path in root.iterdir() if path.is_file() and path.name.lower() == 'wemod.exe']
        if len(candidates) == 1:
            executable = candidates[0]
    return {'archive': root / 'resources/app.asar', 'executable': executable}


def read_manifest(path):
    try:
        manifest = json.loads(path.read_text())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('Invalid compatibility manifest') from error
    if manifest.get('version') not in (1, 2):
        raise ValueError('Unsupported compatibility manifest version')
    for state in ('original', 'patched'):
        if not isinstance(manifest.get(state), dict):
            raise ValueError(f'Compatibility manifest has no {state} checksums')
    return manifest


def original_inputs(root):
    targets = files(root)
    backup = root / 'crossover-compat'
    manifest_path = backup / 'manifest.json'
    manifest = read_manifest(manifest_path) if manifest_path.exists() else None
    if not manifest and any((backup / (target.name + '.original')).exists() for target in targets.values()):
        raise ValueError('Original backups exist without a manifest; refusing to guess their provenance')

    originals = {}
    for key, target in targets.items():
        saved = backup / (target.name + '.original')
        if manifest:
            if not saved.is_file():
                raise ValueError(f'Missing original backup: {saved.name}')
            original = saved.read_bytes()
            if digest(original) != manifest['original'].get(key):
                raise ValueError(f'Original backup checksum mismatch: {saved.name}')
            current_hash = digest(target.read_bytes())
            allowed = {manifest['original'][key], manifest['patched'].get(key)}
            if current_hash not in allowed:
                raise ValueError(f'{target.name} changed outside this patcher; refusing to overwrite it')
        else:
            original = target.read_bytes()
        originals[key] = original
    return targets, backup, manifest, originals


def check(root):
    _, _, _, originals = original_inputs(root)
    result = inspect_bytes(originals['archive'], originals['executable'])
    status = f"tested: {result['tested']}" if result['tested'] else 'structurally compatible, not yet listed as a tested build'
    product = result['product']
    print(f"Compatible {product['name']} {product['version']} ({status}).")
    print(f"Main entry: {product['main']}")
    return result


def apply(root, bootstrap, renderer_bootstrap):
    targets, backup, _, originals = original_inputs(root)
    inspection = inspect_bytes(originals['archive'], originals['executable'])
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
        manifest = {
            'version': 2,
            'product': inspection['product'],
            'testedBuild': inspection['tested'],
            'original': inspection['hashes'],
            'patched': {key: digest(value) for key, value in patched.items()},
            'transformations': ['main-process bootstrap', 'native window frame', 'renderer stream bootstrap'],
        }
        atomic_write(backup / 'manifest.json', (json.dumps(manifest, indent=2) + '\n').encode())
    except BaseException:
        for key, target in targets.items():
            atomic_write(target, previous[key])
        raise
    status = 'tested build' if inspection['tested'] else 'structurally compatible build'
    print(f"Patched {inspection['product']['name']} {inspection['product']['version']} ({status}).")
    print('Original EXE and ASAR are backed up in crossover-compat/.')


def restore(root):
    targets = files(root)
    backup = root / 'crossover-compat'
    manifest = read_manifest(backup / 'manifest.json')
    originals = {}
    for key, target in targets.items():
        original = (backup / (target.name + '.original')).read_bytes()
        if digest(original) != manifest['original'].get(key):
            raise ValueError(f'Original backup checksum mismatch: {target.name}')
        if digest(target.read_bytes()) not in {manifest['original'][key], manifest['patched'].get(key)}:
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


def crossover_wine(crossover):
    return crossover / 'Contents/SharedSupport/CrossOver/bin/wine'


def locate_crossover(explicit=None):
    if explicit is not None:
        if not crossover_wine(explicit).is_file():
            raise ValueError(f'CrossOver wine launcher not found below {explicit}')
        return explicit
    candidates = [Path.home() / 'Applications/CrossOver.app', Path('/Applications/CrossOver.app')]
    found = [path for path in candidates if crossover_wine(path).is_file()]
    if not found:
        raise ValueError('CrossOver was not found in ~/Applications or /Applications; pass --crossover')
    return found[0]


def discover_bottles(bottles_root):
    if not bottles_root.is_dir():
        raise ValueError(f'CrossOver bottle directory not found: {bottles_root}')
    return sorted(
        (path for path in bottles_root.iterdir() if path.is_dir() and (path / 'drive_c').is_dir()),
        key=lambda path: path.name.casefold(),
    )


def is_wemod_app_root(path):
    targets = files(path)
    return targets['executable'].is_file() and targets['archive'].is_file()


def discover_wemod_apps(bottle_root):
    drive_c = bottle_root / 'drive_c'
    candidates = set()

    def consider(path):
        if is_wemod_app_root(path):
            candidates.add(path.resolve())

    if not drive_c.is_dir():
        return []
    for path in drive_c.iterdir():
        if path.is_dir() and any(token in path.name.casefold() for token in ('wemod', 'wand')):
            consider(path)
            for child in path.glob('app-*'):
                if child.is_dir():
                    consider(child)
    users = drive_c / 'users'
    if users.is_dir():
        for user in users.iterdir():
            local = user / 'AppData/Local'
            if not local.is_dir():
                continue
            for product in ('WeMod', 'Wand', 'Programs/WeMod'):
                parent = local / product
                consider(parent)
                if parent.is_dir():
                    for child in parent.glob('app-*'):
                        if child.is_dir():
                            consider(child)
    return sorted(candidates, key=lambda path: str(path).casefold())


def choose_item(items, labels, prompt, input_fn=None, output=print):
    if not items:
        raise ValueError(f'No {prompt.lower()} options are available')
    if input_fn is None:
        input_fn = input
    for index, label in enumerate(labels, 1):
        output(f'  [{index}] {label}')
    while True:
        try:
            answer = input_fn(f'{prompt} [1-{len(items)}] (q to quit): ').strip()
        except EOFError as error:
            raise ValueError('Installation cancelled: no selection was provided') from error
        if answer.casefold() in {'q', 'quit', 'exit'}:
            raise ValueError('Installation cancelled')
        try:
            selected = int(answer)
        except ValueError:
            output('Enter one of the displayed numbers.')
            continue
        if 1 <= selected <= len(items):
            return items[selected - 1]
        output('Enter one of the displayed numbers.')


def next_install_destination(drive_c):
    names = ['WeMod', 'WeMod-compat']
    names.extend(f'WeMod-compat-{number}' for number in range(2, 100))
    for name in names:
        destination = drive_c / name
        if not destination.exists():
            return destination
    raise ValueError('Could not choose a free WeMod directory in the bottle')


def copy_unmodified_app(source, bottle_root):
    source = source.expanduser().resolve()
    source_targets = files(source)
    inspection = inspect_bytes(
        source_targets['archive'].read_bytes(),
        source_targets['executable'].read_bytes(),
    )
    drive_c = bottle_root / 'drive_c'
    destination = next_install_destination(drive_c)
    staging = Path(tempfile.mkdtemp(prefix='.wemod-install-', dir=drive_c))
    try:
        # Copy symlink targets so the bottle remains self-contained if the
        # extracted source uses links on the host filesystem.
        shutil.copytree(source, staging, dirs_exist_ok=True)
        os.replace(staging, destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination, inspection


def interactive_install(bottles_root, crossover=None, source=None, requested_bottle=None,
                        input_fn=None, output=print):
    if input_fn is None:
        input_fn = input
    crossover = locate_crossover(crossover)
    bottles = discover_bottles(bottles_root)
    if not bottles:
        raise ValueError(f'No CrossOver bottles found below {bottles_root}')

    output(f'CrossOver: {crossover}')
    output(f'Bottles: {bottles_root}')
    if requested_bottle:
        matching = [path for path in bottles if path.name == requested_bottle]
        if not matching:
            raise ValueError(f'CrossOver bottle not found: {requested_bottle}')
        bottle_root = matching[0]
    else:
        output('\nChoose the bottle that runs your game:')
        labels = []
        for bottle in bottles:
            count = len(discover_wemod_apps(bottle))
            status = f'WeMod found ({count})' if count else 'WeMod not found'
            labels.append(f'{bottle.name} — {status}')
        bottle_root = choose_item(bottles, labels, 'Bottle', input_fn, output)

    output(f'\nSelected bottle: {bottle_root.name}')
    if source is not None:
        output(f'Checking clean source: {source.expanduser()}')
        root, inspection = copy_unmodified_app(source, bottle_root)
        output(f"Copied {inspection['product']['name']} {inspection['product']['version']} to {root}")
    else:
        apps = discover_wemod_apps(bottle_root)
        if not apps:
            output('\nNo WeMod application was found in that bottle.')
            try:
                raw = input_fn(
                    'Path to a clean extracted WeMod directory containing WeMod.exe (q to quit): '
                ).strip()
            except EOFError as error:
                raise ValueError('Installation cancelled: no source path was provided') from error
            if raw.casefold() in {'q', 'quit', 'exit'}:
                raise ValueError('Installation cancelled')
            source_path = Path(raw.strip('"').strip("'")).expanduser()
            root, inspection = copy_unmodified_app(source_path, bottle_root)
            output(f"Copied {inspection['product']['name']} {inspection['product']['version']} to {root}")
        elif len(apps) == 1:
            root = apps[0]
            output(f'Using detected WeMod application: {root}')
        else:
            output('\nChoose the WeMod application to patch:')
            root = choose_item(apps, [str(path) for path in apps], 'Application', input_fn, output)

    check(root)
    apply(
        root,
        Path(__file__).with_name('bootstrap.js').read_bytes(),
        Path(__file__).with_name('renderer-bootstrap.js').read_bytes(),
    )
    launcher(root, bottle_root.name, crossover, bottles_root)
    command = root / 'crossover-compat/Launch WeMod.command'
    output('\nInstallation complete.')
    output(f'Launch WeMod with:\n  open {shlex.quote(str(command))}')
    output('Start the store and game from the same CrossOver bottle.')
    return root


def bottle_relative_path(root, bottle, bottles_root):
    prefix = bottles_root / bottle
    try:
        return root.resolve().relative_to((prefix / 'drive_c').resolve())
    except ValueError as error:
        raise ValueError(f'--app is not inside bottle {bottle!r} below {bottles_root}') from error


def launcher(root, bottle, crossover, bottles_root):
    relative = bottle_relative_path(root, bottle, bottles_root)
    windows = 'C:\\' + str(relative / files(root)['executable'].name).replace('/', '\\')
    wine = crossover_wine(crossover)
    if not wine.is_file():
        raise ValueError('CrossOver wine launcher not found')
    args = [str(wine), '--bottle', bottle, '--no-update', '--cx-app', windows, *LAUNCH_FLAGS]
    destination = root / 'crossover-compat/Launch WeMod.command'
    atomic_write(destination, ('#!/bin/zsh\nexec ' + shlex.join(args) + ' "$@"\n').encode())
    destination.chmod(0o755)
    print(f'Launcher: {destination}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'check', 'apply', 'restore'])
    parser.add_argument('--app', type=Path, help='directory containing WeMod.exe')
    parser.add_argument('--bottle', help='select this CrossOver bottle without a menu')
    parser.add_argument('--source', type=Path, help='clean extracted WeMod directory for install')
    parser.add_argument('--crossover', type=Path, help='CrossOver.app (auto-detected when omitted)')
    parser.add_argument(
        '--bottles-root', type=Path,
        default=Path.home() / 'Library/Application Support/CrossOver/Bottles',
        help='CrossOver bottle directory',
    )
    args = parser.parse_args()
    try:
        bottles_root = args.bottles_root.expanduser()
        explicit_crossover = args.crossover.expanduser() if args.crossover else None
        if args.action == 'install':
            if args.app:
                raise ValueError('install uses --source for clean files; omit --app')
            interactive_install(
                bottles_root,
                explicit_crossover,
                args.source,
                args.bottle,
            )
            return
        if not args.app:
            raise ValueError(f'{args.action} requires --app')
        if args.source:
            raise ValueError('--source is only valid with install')
        root = args.app.expanduser()
        if args.action == 'restore':
            restore(root)
            return
        check(root)
        if args.action == 'check':
            return
        crossover = None
        if args.bottle:
            crossover = locate_crossover(explicit_crossover)
            bottle_relative_path(root, args.bottle, bottles_root)
        apply(
            root,
            Path(__file__).with_name('bootstrap.js').read_bytes(),
            Path(__file__).with_name('renderer-bootstrap.js').read_bytes(),
        )
        if args.bottle:
            launcher(root, args.bottle, crossover, bottles_root)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()
