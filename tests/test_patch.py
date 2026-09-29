import importlib.util
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch as mock_patch

spec = importlib.util.spec_from_file_location('patcher', Path(__file__).parents[1] / 'patch.py')
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)

BOOTSTRAP = b'const renderer = __RENDERER_BOOTSTRAP_SOURCE__; // main bootstrap'
RENDERER_BOOTSTRAP = b';(() => { globalThis.fixtureRendererBootstrap = true; })();'


def add_record(root, path, record):
    node = root
    parts = path.split('/')
    for part in parts[:-1]:
        node = node.setdefault('files', {}).setdefault(part, {})
    node.setdefault('files', {})[parts[-1]] = record


def packed_record(body, offset):
    return {
        'offset': str(offset),
        'size': len(body),
        'integrity': {
            'algorithm': 'SHA256',
            'hash': patcher.digest(body),
            'blockSize': 8,
            'blocks': [patcher.digest(body[i:i + 8]) for i in range(0, len(body), 8)],
        },
    }


def fixture(main=None, product='WeMod', version='99.4.2', main_path='dist/background.js'):
    main = main or b'const options={minHeight:720, frame:!1, backgroundColor:"black"};'
    package = json.dumps({'name': product, 'version': version, 'main': main_path}).encode()
    renderer = b'"use strict";dashboard();'
    other = b'leave this asset unchanged'
    bodies = [('package.json', package), (main_path, main), ('assets/renderer.abc.js', renderer), ('asset.dat', other)]
    header = {'files': {}}
    payload = b''
    for name, body in bodies:
        add_record(header, name, packed_record(body, len(payload)))
        payload += body
    add_record(header, 'native.node', {'unpacked': True, 'size': 42})
    encoded = json.dumps(header, separators=(',', ':')).encode()
    padding = b'\0' * (-len(encoded) % 4)
    hp = struct.pack('<II', len(encoded) + len(padding) + 4, len(encoded)) + encoded + padding
    archive = struct.pack('<II', 4, len(hp)) + hp + payload
    executable = b'MZ-test-only-' + patcher.digest(encoded).encode() + b'-end'
    return archive, executable, main, renderer


def unpack(archive, name):
    header, payload, _ = patcher.parse_asar(archive)
    entry, body = patcher.entry_bytes(header, payload, name)
    return header, entry, body


def write_fixture_app(root, version='99.4.2'):
    archive, executable, _, _ = fixture(version=version)
    (root / 'resources').mkdir(parents=True)
    (root / 'resources/app.asar').write_bytes(archive)
    (root / 'WeMod.exe').write_bytes(executable)
    (root / 'support-file.txt').write_text('copied with the application')
    return archive, executable


class PatchTests(unittest.TestCase):
    def test_discovers_nested_main_and_preserves_unrelated_assets(self):
        original, exe, main, renderer = fixture()
        result, patched_exe = patcher.patch_bytes(
            original, exe, BOOTSTRAP, RENDERER_BOOTSTRAP)

        old_header, old_payload, _ = patcher.parse_asar(original)
        new_header, payload, encoded = patcher.parse_asar(result)
        self.assertEqual(payload[:len(old_payload)], old_payload)
        for name in ['package.json', 'assets/renderer.abc.js', 'asset.dat', 'native.node']:
            self.assertEqual(patcher.entry_record(old_header, name), patcher.entry_record(new_header, name))

        entry, body = patcher.entry_bytes(new_header, payload, 'dist/background.js')
        self.assertIn(RENDERER_BOOTSTRAP, body)
        self.assertNotIn(patcher.RENDERER_PLACEHOLDER, body)
        self.assertTrue(body.endswith(main.replace(b'frame:!1', b'frame:true')))
        self.assertEqual(entry['integrity']['hash'], patcher.digest(body))
        self.assertEqual(entry['integrity']['blocks'], [
            patcher.digest(body[i:i + 8]) for i in range(0, len(body), 8)])
        self.assertEqual(unpack(result, 'assets/renderer.abc.js')[2], renderer)
        self.assertIn(patcher.digest(encoded).encode(), patched_exe)
        self.assertEqual(len(exe), len(patched_exe))

    def test_arbitrary_structurally_compatible_version_is_accepted(self):
        archive, exe, _, _ = fixture(version='2031.7.19')
        result = patcher.inspect_bytes(archive, exe)
        self.assertEqual(result['product']['version'], '2031.7.19')
        self.assertEqual(result['product']['main'], 'dist/background.js')
        self.assertIsNone(result['tested'])

    def test_non_wemod_and_unsafe_main_are_rejected(self):
        archive, exe, _, _ = fixture(product='OtherApp')
        with self.assertRaisesRegex(ValueError, 'not a WeMod'):
            patcher.inspect_bytes(archive, exe)
        archive, exe, _, _ = fixture(main_path='../outside.js')
        with self.assertRaisesRegex(ValueError, 'Unsafe ASAR'):
            patcher.inspect_bytes(archive, exe)

    def test_missing_or_ambiguous_executable_digest_rejected(self):
        archive, exe, _, _ = fixture()
        for bad in [b'MZ-without-hash', exe + exe[2:]]:
            with self.subTest(bad=bad[:24]):
                with self.assertRaises(ValueError):
                    patcher.patch_bytes(archive, bad, BOOTSTRAP, RENDERER_BOOTSTRAP)

    def test_missing_or_ambiguous_window_configuration_rejected(self):
        valid = b'minHeight:640,frame:false,backgroundColor:"#000"'
        for main in [b'const options={frame:true};', valid + b';' + valid]:
            archive, exe, _, _ = fixture(main)
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                patcher.patch_bytes(archive, exe, BOOTSTRAP, RENDERER_BOOTSTRAP)

    def test_truncated_archive_rejected(self):
        archive, _, _, _ = fixture()
        for bad in [b'', archive[:12], archive[:20]]:
            with self.assertRaises(ValueError):
                patcher.parse_asar(bad)

    def test_apply_repeat_restore_and_update_protection(self):
        archive, exe, _, _ = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'resources').mkdir()
            (root / 'resources/app.asar').write_bytes(archive)
            (root / 'WeMod.exe').write_bytes(exe)
            patcher.apply(root, BOOTSTRAP, RENDERER_BOOTSTRAP)
            first = (root / 'resources/app.asar').read_bytes()
            manifest = json.loads((root / 'crossover-compat/manifest.json').read_text())
            self.assertEqual(manifest['version'], 2)
            self.assertEqual(manifest['product']['version'], '99.4.2')
            patcher.apply(root, BOOTSTRAP, RENDERER_BOOTSTRAP)
            self.assertEqual(first, (root / 'resources/app.asar').read_bytes())
            patcher.restore(root)
            self.assertEqual(archive, (root / 'resources/app.asar').read_bytes())
            self.assertEqual(exe, (root / 'WeMod.exe').read_bytes())
            (root / 'WeMod.exe').write_bytes(b'new-vendor-update')
            with self.assertRaises(ValueError):
                patcher.restore(root)
            with self.assertRaises(ValueError):
                patcher.apply(root, BOOTSTRAP, RENDERER_BOOTSTRAP)
            self.assertEqual(b'new-vendor-update', (root / 'WeMod.exe').read_bytes())

    def test_v1_manifest_is_migrated_without_replacing_backups(self):
        archive, exe, _, _ = fixture()
        old_archive, old_exe = patcher.patch_bytes(archive, exe, BOOTSTRAP, b'old renderer')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup = root / 'crossover-compat'
            (root / 'resources').mkdir()
            backup.mkdir()
            (root / 'resources/app.asar').write_bytes(old_archive)
            (root / 'WeMod.exe').write_bytes(old_exe)
            (backup / 'app.asar.original').write_bytes(archive)
            (backup / 'WeMod.exe.original').write_bytes(exe)
            (backup / 'manifest.json').write_text(json.dumps({
                'version': 1,
                'original': {'archive': patcher.digest(archive), 'executable': patcher.digest(exe)},
                'patched': {'archive': patcher.digest(old_archive), 'executable': patcher.digest(old_exe)},
            }))
            patcher.apply(root, BOOTSTRAP, RENDERER_BOOTSTRAP)
            manifest = json.loads((backup / 'manifest.json').read_text())
            self.assertEqual(manifest['version'], 2)
            self.assertEqual((backup / 'app.asar.original').read_bytes(), archive)

    def test_incompatible_package_leaves_files_untouched(self):
        archive, exe, _, _ = fixture(product='OtherApp')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'resources').mkdir()
            (root / 'resources/app.asar').write_bytes(archive)
            (root / 'WeMod.exe').write_bytes(exe)
            with self.assertRaises(ValueError):
                patcher.apply(root, BOOTSTRAP, RENDERER_BOOTSTRAP)
            self.assertFalse((root / 'crossover-compat').exists())
            self.assertEqual(archive, (root / 'resources/app.asar').read_bytes())
            self.assertEqual(exe, (root / 'WeMod.exe').read_bytes())

    def test_crossover_auto_detection_and_launcher(self):
        self.assertEqual(patcher.LAUNCH_FLAGS, [
            '--no-sandbox', '--compat-force-window', '--compat-enable-gpu',
            '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
            '--enable-features=Vulkan,UseSkiaRenderer', '--use-vulkan=swiftshader',
            '--ignore-gpu-blocklist', '--enable-gpu-compositing',
            '--disable-direct-composition',
        ])
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            crossover = home / 'Applications/CrossOver.app'
            wine = patcher.crossover_wine(crossover)
            wine.parent.mkdir(parents=True)
            wine.write_text('')
            bottles = home / 'Bottles'
            root = bottles / 'Any Game' / 'drive_c/Tools/WeMod'
            root.mkdir(parents=True)
            (root / 'WeMod.exe').write_bytes(b'MZ')
            with mock_patch.dict(os.environ, {'HOME': str(home)}), mock_patch.object(Path, 'home', return_value=home):
                self.assertEqual(patcher.locate_crossover(), crossover)
            patcher.launcher(root, 'Any Game', crossover, bottles)
            command = (root / 'crossover-compat/Launch WeMod.command').read_text()
            self.assertIn("--bottle 'Any Game'", command)
            self.assertIn("'C:\\Tools\\WeMod\\WeMod.exe'", command)
            with self.assertRaisesRegex(ValueError, '--app is not inside bottle'):
                patcher.bottle_relative_path(home / 'elsewhere', 'Any Game', bottles)

    def test_interactive_install_lists_bottles_and_copies_clean_source(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            crossover = home / 'CrossOver.app'
            wine = patcher.crossover_wine(crossover)
            wine.parent.mkdir(parents=True)
            wine.write_text('')
            bottles = home / 'Bottles'
            for name in ('Alpha', 'Beta Game'):
                (bottles / name / 'drive_c').mkdir(parents=True)
            source = home / 'Clean WeMod'
            original_archive, original_executable = write_fixture_app(source, version='88.1.0')
            output = []
            answers = iter(['2'])

            installed = patcher.interactive_install(
                bottles,
                crossover=crossover,
                source=source,
                input_fn=lambda _: next(answers),
                output=output.append,
            )

            self.assertEqual(installed, bottles / 'Beta Game/drive_c/WeMod')
            self.assertTrue((installed / 'crossover-compat/manifest.json').is_file())
            self.assertTrue((installed / 'crossover-compat/Launch WeMod.command').is_file())
            self.assertEqual((installed / 'support-file.txt').read_text(), 'copied with the application')
            self.assertEqual((source / 'resources/app.asar').read_bytes(), original_archive)
            self.assertEqual((source / 'WeMod.exe').read_bytes(), original_executable)
            transcript = '\n'.join(output)
            self.assertIn('[1] Alpha — WeMod not found', transcript)
            self.assertIn('[2] Beta Game — WeMod not found', transcript)
            self.assertIn('Selected bottle: Beta Game', transcript)
            self.assertIn('Installation complete.', transcript)
            command = (installed / 'crossover-compat/Launch WeMod.command').read_text()
            self.assertIn("--bottle 'Beta Game'", command)

    def test_discovers_existing_wemod_and_requested_bottle_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            bottles = Path(directory) / 'Bottles'
            bottle = bottles / 'Existing Game'
            app = bottle / 'drive_c/users/crossover/AppData/Local/WeMod/app-1.2.3'
            write_fixture_app(app)
            crossover = Path(directory) / 'CrossOver.app'
            wine = patcher.crossover_wine(crossover)
            wine.parent.mkdir(parents=True)
            wine.write_text('')
            self.assertEqual(patcher.discover_bottles(bottles), [bottle])
            self.assertEqual(patcher.discover_wemod_apps(bottle), [app.resolve()])
            with self.assertRaisesRegex(ValueError, 'bottle not found'):
                patcher.interactive_install(
                    bottles,
                    crossover=crossover,
                    requested_bottle='Missing',
                )

    def test_interactive_install_patches_existing_detected_application(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            crossover = root / 'CrossOver.app'
            wine = patcher.crossover_wine(crossover)
            wine.parent.mkdir(parents=True)
            wine.write_text('')
            bottles = root / 'Bottles'
            app = bottles / 'GOG Games/drive_c/WeMod116'
            write_fixture_app(app)
            output = []

            installed = patcher.interactive_install(
                bottles,
                crossover=crossover,
                requested_bottle='GOG Games',
                input_fn=lambda _: self.fail('No prompt expected for one detected application'),
                output=output.append,
            )

            self.assertEqual(installed, app.resolve())
            self.assertTrue((app / 'crossover-compat/manifest.json').is_file())
            self.assertIn('Using detected WeMod application:', '\n'.join(output))

    def test_choose_item_reprompts_and_can_cancel(self):
        answers = iter(['wrong', '9', '2'])
        output = []
        selected = patcher.choose_item(
            ['a', 'b'], ['Alpha', 'Beta'], 'Bottle', lambda _: next(answers), output.append)
        self.assertEqual(selected, 'b')
        self.assertEqual(output.count('Enter one of the displayed numbers.'), 2)
        with self.assertRaisesRegex(ValueError, 'cancelled'):
            patcher.choose_item(['a'], ['Alpha'], 'Bottle', lambda _: 'q', output.append)


if __name__ == '__main__':
    unittest.main()
