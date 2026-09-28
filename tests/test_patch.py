import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch as mock_patch

spec = importlib.util.spec_from_file_location('patcher', Path(__file__).parents[1] / 'patch.py')
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


def fixture(main=None):
    main = main or b'const options={minHeight:640,frame:false,backgroundColor:"#000"};'
    renderer = b'"use strict";dashboard();'
    other = b'leave this asset unchanged'
    header = {'files': {
        'index.js': {'offset': '0', 'size': len(main), 'integrity': {
            'algorithm': 'SHA256', 'hash': patcher.digest(main), 'blockSize': 8,
            'blocks': [patcher.digest(main[i:i+8]) for i in range(0, len(main), 8)]}},
        patcher.RENDERER_ENTRY: {'offset': str(len(main)), 'size': len(renderer), 'integrity': {
            'algorithm': 'SHA256', 'hash': patcher.digest(renderer), 'blockSize': 8,
            'blocks': [patcher.digest(renderer[i:i+8]) for i in range(0, len(renderer), 8)]}},
        'asset.dat': {'offset': str(len(main) + len(renderer)), 'size': len(other)},
        'native.node': {'unpacked': True, 'size': 42},
    }}
    encoded = json.dumps(header, separators=(',', ':')).encode()
    padding = b'\0' * (-len(encoded) % 4)
    hp = struct.pack('<II', len(encoded) + len(padding) + 4, len(encoded)) + encoded + padding
    archive = struct.pack('<II', 4, len(hp)) + hp + main + renderer + other
    executable = b'MZ-test-only-' + patcher.digest(encoded).encode() + b'-end'
    return archive, executable, main, renderer


class PatchTests(unittest.TestCase):
    def test_archive_integrity_and_unchanged_assets(self):
        original, exe, main, renderer = fixture()
        result, patched_exe = patcher.patch_bytes(
            original, exe, b'//bootstrap', b'//renderer-bootstrap')
        old, old_payload, _ = patcher.parse_asar(original)
        new, payload, encoded = patcher.parse_asar(result)
        self.assertEqual(payload[:len(old_payload)], old_payload)
        for name in ['asset.dat', 'native.node']:
            self.assertEqual(old['files'][name], new['files'][name])
        entry = new['files']['index.js']
        body = payload[int(entry['offset']):int(entry['offset'])+entry['size']]
        expected_main = main.replace(patcher.FRAMELESS, patcher.FRAMED)
        self.assertEqual(body, b'//bootstrap\n' + expected_main)
        self.assertEqual(entry['integrity']['hash'], patcher.digest(body))
        self.assertEqual(entry['integrity']['blocks'], [patcher.digest(body[i:i+8]) for i in range(0, len(body), 8)])
        renderer_entry = new['files'][patcher.RENDERER_ENTRY]
        renderer_body = payload[int(renderer_entry['offset']):int(renderer_entry['offset'])+renderer_entry['size']]
        self.assertEqual(renderer_body, b'//renderer-bootstrap\n' + renderer)
        self.assertEqual(renderer_entry['integrity']['hash'], patcher.digest(renderer_body))
        self.assertEqual(renderer_entry['integrity']['blocks'], [
            patcher.digest(renderer_body[i:i+8]) for i in range(0, len(renderer_body), 8)])
        self.assertIn(patcher.digest(encoded).encode(), patched_exe)
        self.assertEqual(len(exe), len(patched_exe))

    def test_missing_or_ambiguous_executable_digest_rejected(self):
        archive, exe, _, _ = fixture()
        for bad in [b'MZ-without-hash', exe + exe]:
            with self.assertRaises(ValueError):
                patcher.patch_bytes(archive, bad, b'bootstrap', b'renderer')

    def test_missing_or_ambiguous_window_configuration_rejected(self):
        for main in [b'const options={frame:true};', patcher.FRAMELESS + patcher.FRAMELESS]:
            archive, exe, _, _ = fixture(main)
            with self.assertRaises(ValueError):
                patcher.patch_bytes(archive, exe, b'bootstrap', b'renderer')

    def test_truncated_archive_rejected(self):
        archive, _, _, _ = fixture()
        for bad in [b'', archive[:12], archive[:20]]:
            with self.assertRaises(ValueError):
                patcher.parse_asar(bad)

    def test_apply_repeat_restore_and_update_protection(self):
        archive, exe, _, _ = fixture()
        supported = {'archive': patcher.digest(archive), 'executable': patcher.digest(exe)}
        with tempfile.TemporaryDirectory() as directory, mock_patch.object(patcher, 'SUPPORTED', supported):
            root = Path(directory)
            (root / 'resources').mkdir()
            (root / 'resources/app.asar').write_bytes(archive)
            (root / 'WeMod.exe').write_bytes(exe)
            patcher.apply(root, b'bootstrap', b'renderer')
            first = (root / 'resources/app.asar').read_bytes()
            patcher.apply(root, b'bootstrap', b'renderer')
            self.assertEqual(first, (root / 'resources/app.asar').read_bytes())
            patcher.restore(root)
            self.assertEqual(archive, (root / 'resources/app.asar').read_bytes())
            self.assertEqual(exe, (root / 'WeMod.exe').read_bytes())
            (root / 'WeMod.exe').write_bytes(b'new-vendor-update')
            with self.assertRaises(ValueError):
                patcher.restore(root)
            with self.assertRaises(ValueError):
                patcher.apply(root, b'bootstrap', b'renderer')
            self.assertEqual(b'new-vendor-update', (root / 'WeMod.exe').read_bytes())

    def test_unknown_build_leaves_files_untouched(self):
        archive, exe, _, _ = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'resources').mkdir()
            (root / 'resources/app.asar').write_bytes(archive)
            (root / 'WeMod.exe').write_bytes(exe)
            with self.assertRaises(ValueError):
                patcher.apply(root, b'bootstrap', b'renderer')
            self.assertFalse((root / 'crossover-compat').exists())
            self.assertEqual(archive, (root / 'resources/app.asar').read_bytes())

    def test_launcher_uses_verified_renderer_path(self):
        self.assertEqual(patcher.LAUNCH_FLAGS, [
            '--no-sandbox', '--compat-force-window', '--compat-enable-gpu',
            '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
            '--enable-features=Vulkan,UseSkiaRenderer', '--use-vulkan=swiftshader',
            '--ignore-gpu-blocklist', '--enable-gpu-compositing',
            '--disable-direct-composition',
        ])


if __name__ == '__main__':
    unittest.main()
