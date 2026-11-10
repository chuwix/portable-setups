import argparse
import importlib.util
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location('flatout2_vm', Path(__file__).with_name('flatout2_vm.py'))
assert SPEC and SPEC.loader
vm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vm)


class GameMediaTests(unittest.TestCase):
    def fixture(self, root: Path) -> Path:
        for name in vm.GOG_PARTS:
            (root / name).write_bytes(b'fixture-' + name.encode())
        return root / vm.GOG_INSTALLER

    def test_detection_excludes_flatout1_sidecars_and_hidden_folders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            installer = self.fixture(root)
            for name in ('setup_flatout_1.1_(17772).exe', '._' + vm.GOG_INSTALLER):
                (root / name).write_bytes(b'ignored')
            hidden = root / '.Trashes'
            hidden.mkdir()
            self.fixture(hidden)
            self.assertEqual(vm.find_installers([root]), [installer])

    def test_known_layout_requires_nonempty_bin_and_rejects_other_builds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            installer = self.fixture(root)
            self.assertEqual([p.name for p in vm.installer_files(installer)], list(vm.GOG_PARTS))
            (root / vm.GOG_PARTS[1]).unlink()
            with self.assertRaisesRegex(ValueError, 'Missing'):
                vm.installer_files(installer)
            (root / vm.GOG_PARTS[1]).touch()
            with self.assertRaisesRegex(ValueError, 'empty'):
                vm.installer_files(installer)
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                vm.installer_files(root / 'setup_flatout_2_unknown.exe')

    def test_rejects_extra_parts_and_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            installer = self.fixture(root)
            extra = root / (installer.stem + '-2.bin')
            extra.touch()
            with self.assertRaisesRegex(ValueError, 'Unexpected BIN'):
                vm.installer_files(installer)
            extra.unlink()
            (root / vm.GOG_PARTS[1]).unlink()
            (root / vm.GOG_PARTS[1]).symlink_to(installer)
            with self.assertRaisesRegex(ValueError, 'symlinked'):
                vm.installer_files(installer)

    def test_ambiguous_source_requires_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            first = self.fixture(root)
            other = root / 'other'
            other.mkdir()
            self.fixture(other)
            candidates = vm.find_installers([root])
            with patch('builtins.input', return_value='2'):
                self.assertEqual(vm.choose_installer(root), candidates[1])
            with patch('builtins.input', return_value=''):
                with self.assertRaisesRegex(ValueError, 'Cancelled'):
                    vm.choose_installer(root)

    def test_declined_source_does_not_build_media(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.fixture(root)
            with patch('builtins.input', return_value='no'):
                with self.assertRaisesRegex(ValueError, 'Cancelled'):
                    vm.choose_installer(root)

    def test_copy_mismatch_never_publishes_iso(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            installer = self.fixture(root)
            def corrupt(source: Path, target: Path) -> None:
                target.write_bytes(b'corrupt')
            with patch.object(vm.shutil, 'copyfile', side_effect=corrupt), patch.object(vm, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    vm.build_game_media(installer, root / 'game.iso')
                run.assert_not_called()
            self.assertFalse((root / 'game.iso').exists())

    def test_iso_contains_only_selected_files_helpers_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            installer = self.fixture(root)
            (root / 'private.txt').write_text('not on CD')
            staged: Path | None = None
            def command(args: list[str]) -> str:
                nonlocal staged
                if args[1] == 'makehybrid':
                    staged = Path(args[-1])
                    self.assertEqual({p.name for p in staged.iterdir()},
                                     {*vm.GOG_PARTS, 'game-media.json', 'install-gog.cmd', 'install-gog.ps1'})
                    Path(args[args.index('-o') + 1]).write_bytes(b'iso')
                elif args[1] == 'attach':
                    mount = Path(args[args.index('-mountpoint') + 1])
                    assert staged is not None
                    for source in staged.iterdir():
                        (mount / source.name).write_bytes(source.read_bytes())
                return ''
            with patch.object(vm, 'run', side_effect=command) as run:
                vm.build_game_media(installer, root / 'game.iso')
                self.assertEqual(run.call_args_list[-1].args[0][1], 'detach')
            self.assertEqual((root / 'game.iso').read_bytes(), b'iso')
            self.assertEqual(installer.read_bytes(), b'fixture-' + vm.GOG_INSTALLER.encode())

    def guest(self, root: Path) -> tuple[Path, Path]:
        bundle = root / f'{vm.NAME}.utm'
        data = bundle / 'Data'
        data.mkdir(parents=True)
        config = vm.configuration(str(vm.uuid.uuid4()))
        (bundle / 'config.plist').write_bytes(plistlib.dumps(config))
        header = bytearray(8192)
        header[512:520] = b'EFI PART'
        (data / 'system.raw').write_bytes(header)
        return bundle, data

    def test_running_vm_never_changes_media_or_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            bundle, data = self.guest(root)
            before = (bundle / 'config.plist').read_bytes()
            with patch.object(vm, 'run', return_value='started'), patch.object(vm, 'choose_installer') as choose:
                with self.assertRaisesRegex(ValueError, 'Shut down'):
                    vm.game_media(argparse.Namespace(home=root, action='install-game', source_dir=None))
                choose.assert_not_called()
            self.assertEqual((bundle / 'config.plist').read_bytes(), before)
            self.assertFalse((data / 'game.iso').exists())

    def test_attach_preserves_seed_and_disk_detach_removes_only_game_iso(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            bundle, data = self.guest(root)
            (data / 'seed.iso').write_bytes(b'original-seed')
            before = (data / 'system.raw').read_bytes()
            def build(installer: Path, output: Path) -> None:
                output.write_bytes(b'game-media')
            with patch.object(vm, 'run', return_value='stopped'), patch.object(vm, 'reload_vm'), \
                    patch.object(vm, 'choose_installer', return_value=root / vm.GOG_INSTALLER), \
                    patch.object(vm, 'build_game_media', side_effect=build):
                vm.game_media(argparse.Namespace(home=root, action='install-game', source_dir=root))
                config = plistlib.loads((bundle / 'config.plist').read_bytes())
                self.assertEqual(config['Drive'][-1]['ImageName'], 'game.iso')
                self.assertTrue(config['Drive'][-1]['ReadOnly'])
                vm.game_media(argparse.Namespace(home=root, action='detach-game'))
            self.assertEqual((data / 'system.raw').read_bytes(), before)
            self.assertEqual((data / 'seed.iso').read_bytes(), b'original-seed')
            self.assertFalse((data / 'game.iso').exists())

    def test_reload_failure_restores_original_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            bundle, data = self.guest(root)
            before = (bundle / 'config.plist').read_bytes()
            def build(installer: Path, output: Path) -> None:
                output.write_bytes(b'game-media')
            with patch.object(vm, 'run', return_value='stopped'), patch.object(vm, 'reload_vm', side_effect=ValueError('reload failed')), \
                    patch.object(vm, 'choose_installer', return_value=root / vm.GOG_INSTALLER), \
                    patch.object(vm, 'build_game_media', side_effect=build):
                with self.assertRaisesRegex(ValueError, 'reload failed'):
                    vm.game_media(argparse.Namespace(home=root, action='install-game', source_dir=root))
            self.assertEqual((bundle / 'config.plist').read_bytes(), before)
            self.assertTrue((data / 'game.iso').exists())

    def test_guest_helper_keeps_signature_checks_and_limits_policy_to_process(self) -> None:
        script = Path(__file__).with_name('install-gog.ps1').read_text()
        for required in ('Get-AuthenticodeSignature', "-ne 'Valid'", 'Get-FileHash', 'RunAs', '/VERYSILENT',
                         '/NORESTART', '/RESTARTEXITCODE=3010', 'result.json', 'CommonDesktopDirectory'):
            self.assertIn(required, script)
        wrapper = Path(__file__).with_name('install-gog.cmd').read_text()
        self.assertIn('-NoProfile -ExecutionPolicy RemoteSigned -File', wrapper)
        self.assertIn("'-NoProfile', '-NoExit', '-ExecutionPolicy', 'RemoteSigned', '-File'", script)
        self.assertIn("$publisher -notin @('GOG Limited', 'GOG sp. z o.o', 'GOG sp. z o.o.')", script)
        self.assertIn('X509NameType]::SimpleName', script)
        self.assertIn("$publisher = ($publisher -replace '\\s+', ' ').Trim()", script)
        self.assertIn("Read-Host 'Press Enter to close this failed installation'", script)
        for content in (script, wrapper):
            for forbidden in ('Set-ExecutionPolicy', 'Bypass', 'Unrestricted', 'Set-MpPreference',
                              'net localgroup', 'Invoke-WebRequest'):
                self.assertNotIn(forbidden, content)

    def test_usb_discovery_excludes_non_usb_and_internal_volumes(self) -> None:
        listing = {'AllDisksAndPartitions': [{'Partitions': [
            {'MountPoint': '/Volumes/usb'}, {'MountPoint': '/Volumes/internal'},
            {'MountPoint': '/Volumes/thunderbolt'}]}]}
        def command(args: list[str]) -> str:
            if args[1] == 'list':
                return plistlib.dumps(listing).decode()
            return plistlib.dumps({'Internal': args[-1].endswith('internal'),
                                   'BusProtocol': 'Thunderbolt' if args[-1].endswith('thunderbolt') else 'USB'}).decode()
        with patch.object(vm, 'run', side_effect=command):
            self.assertEqual(vm.usb_roots(), [Path('/Volumes/usb')])

    def test_vm_started_during_copy_does_not_update_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            bundle, data = self.guest(root)
            before = (bundle / 'config.plist').read_bytes()
            with patch.object(vm, 'run', side_effect=['stopped', 'started']), \
                    patch.object(vm, 'choose_installer', return_value=root / vm.GOG_INSTALLER), \
                    patch.object(vm, 'build_game_media'), patch.object(vm, 'reload_vm') as reload:
                with self.assertRaisesRegex(ValueError, 'during media preparation'):
                    vm.game_media(argparse.Namespace(home=root, action='install-game', source_dir=root))
                reload.assert_not_called()
            self.assertEqual((bundle / 'config.plist').read_bytes(), before)

    def test_uninstalled_disk_is_never_attached_to_game_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            bundle, data = self.guest(root)
            (data / 'system.raw').write_bytes(bytes(8192))
            with patch.object(vm, 'run', return_value='stopped'), patch.object(vm, 'choose_installer') as choose:
                with self.assertRaisesRegex(ValueError, 'installed GPT'):
                    vm.game_media(argparse.Namespace(home=root, action='install-game', source_dir=root))
                choose.assert_not_called()


if __name__ == '__main__':
    unittest.main()
