import argparse
import importlib.util
import json
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

    def test_source_menu_offers_only_offline_installer_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            installer = self.fixture(root)
            with patch.object(vm, 'usb_roots', return_value=[root]), patch('builtins.input', side_effect=['1', 'y']), patch('builtins.print') as output:
                self.assertEqual(vm.choose_installer(None), installer)
            menu = output.call_args_list[0].args[0]
            self.assertIn('USB', menu)
            self.assertNotIn('Steam', menu)
            self.assertNotIn('inside Windows', menu)

    def test_unavailable_source_choices_cancel_before_scanning(self) -> None:
        for choice in ('', '3', '4'):
            with self.subTest(choice=choice), patch('builtins.input', return_value=choice), patch.object(vm, 'find_installers') as scan:
                with self.assertRaisesRegex(ValueError, 'Cancelled'):
                    vm.choose_installer(None)
                scan.assert_not_called()

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
                                     {*vm.GOG_PARTS, 'game-media.json', *vm.GAME_HELPERS})
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

    def test_iso_readback_rejects_extra_missing_or_changed_helpers(self) -> None:
        for change in ('extra', 'missing', 'changed'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                installer = self.fixture(root)
                staged: Path | None = None

                def command(args: list[str]) -> str:
                    nonlocal staged
                    if args[1] == 'makehybrid':
                        staged = Path(args[-1])
                        Path(args[args.index('-o') + 1]).write_bytes(b'iso')
                    elif args[1] == 'attach':
                        mount = Path(args[args.index('-mountpoint') + 1])
                        assert staged is not None
                        for source in staged.iterdir():
                            (mount / source.name).write_bytes(source.read_bytes())
                        if change == 'extra':
                            (mount / 'private.txt').touch()
                        elif change == 'missing':
                            (mount / 'guest-install.ps1').unlink()
                        else:
                            (mount / 'guest-start.ps1').write_text('changed')
                    return ''

                with patch.object(vm, 'run', side_effect=command) as run, patch.object(vm, 'source_released') as released:
                    with self.assertRaises(ValueError):
                        vm.build_game_media(installer, root / 'game.iso')
                    released.assert_not_called()
                    self.assertEqual(run.call_args_list[-1].args[0][1], 'detach')
                self.assertFalse((root / 'game.iso').exists())

    def test_source_release_is_after_verified_iso_publication(self) -> None:
        with patch('builtins.print') as output:
            vm.source_released()
        message = output.call_args.args[0]
        for text in ('source folder is no longer needed', 'Finder', 'installation is not complete'):
            self.assertIn(text, message)

    def test_retained_retry_iso_requires_current_helpers_and_both_payload_hashes(self) -> None:
        for change in ('none', 'helper', 'payload', 'schema'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                media = root / 'game.iso'
                media.write_bytes(b'retained')

                def command(args: list[str]) -> str:
                    if args[1] == 'attach':
                        mount = Path(args[args.index('-mountpoint') + 1])
                        entries: list[dict[str, object]] = []
                        for name in vm.GOG_PARTS:
                            path = mount / name
                            path.write_bytes(b'payload')
                            entries.append({'name': name, 'size': path.stat().st_size, 'sha256': vm.file_hash(path)})
                        (mount / 'game-media.json').write_text(json.dumps({'schema': 2 if change == 'schema' else 1, 'files': entries}))
                        for name in vm.GAME_HELPERS:
                            (mount / name).write_bytes(Path(__file__).with_name(name).read_bytes())
                        if change == 'helper':
                            (mount / 'guest-install.ps1').write_bytes(b'outdated')
                        elif change == 'payload':
                            (mount / vm.GOG_PARTS[1]).write_bytes(b'corrupt')
                    return ''

                with patch.object(vm, 'run', side_effect=command) as run, patch.object(vm, 'source_released') as released:
                    if change == 'none':
                        vm.verify_game_media(media)
                        released.assert_called_once()
                    else:
                        with self.assertRaises(ValueError):
                            vm.verify_game_media(media)
                        released.assert_not_called()
                    self.assertEqual(run.call_args_list[-1].args[0][1], 'detach')
                self.assertEqual(media.read_bytes(), b'retained')

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
            args = argparse.Namespace(home=root, action='install-game', source_dir=root)
            with patch.object(vm, 'run', return_value='stopped'), patch.object(vm, 'choose_installer') as choose:
                with self.assertRaisesRegex(ValueError, 'Unattached game ISO'):
                    vm.game_media(args)
                choose.assert_not_called()
            args.action = 'detach-game'
            with patch.object(vm, 'run', return_value='stopped'), patch('builtins.input', return_value='yes'), \
                    patch.object(vm, 'reload_vm') as reload:
                vm.game_media(args)
                reload.assert_not_called()
            self.assertFalse((data / 'game.iso').exists())
            backups = list(data.glob('game-orphan-*.iso'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), b'game-media')
            self.assertEqual((bundle / 'config.plist').read_bytes(), before)
            args.action = 'install-game'
            with patch.object(vm, 'run', return_value='stopped'), patch.object(vm, 'reload_vm'), \
                    patch.object(vm, 'choose_installer', return_value=root / vm.GOG_INSTALLER), \
                    patch.object(vm, 'build_game_media', side_effect=build):
                vm.game_media(args)
            self.assertEqual((data / 'game.iso').read_bytes(), b'game-media')
            self.assertEqual(backups[0].read_bytes(), b'game-media')

    def test_media_paths_reject_symlinks_before_reading_or_running(self) -> None:
        for target in ('home', 'bundle', 'Data', 'config.plist', 'game.iso'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                home = root / 'home'
                bundle, data = self.guest(home)
                if target == 'home':
                    path = home
                elif target == 'bundle':
                    path = bundle
                elif target == 'game.iso':
                    path = data / target
                    path.write_bytes(b'unrecognized')
                else:
                    path = bundle / target
                original = path.with_name(path.name + '-original')
                path.rename(original)
                path.symlink_to(original, target_is_directory=original.is_dir())
                for action in ('install-game', 'detach-game'):
                    with patch.object(vm, 'run') as run:
                        with self.assertRaisesRegex(ValueError, 'symlinks'):
                            vm.game_media(argparse.Namespace(home=home, action=action, source_dir=None))
                        run.assert_not_called()

    def test_orphan_quarantine_requires_confirmation_and_preserves_other_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            bundle, data = self.guest(root)
            for name in ('game.iso', 'seed.iso', 'windows.iso', 'game-orphan-existing.iso', 'unrelated.iso'):
                (data / name).write_bytes(name.encode())
            before = {path: path.read_bytes() for path in data.iterdir()}
            config = (bundle / 'config.plist').read_bytes()
            args = argparse.Namespace(home=root, action='detach-game')
            for answer in ('', 'no'):
                with patch.object(vm, 'run', return_value='stopped'), patch('builtins.input', return_value=answer), \
                        patch.object(vm, 'reload_vm') as reload:
                    with self.assertRaisesRegex(ValueError, 'Cancelled'):
                        vm.game_media(args)
                    reload.assert_not_called()
                self.assertEqual({path: path.read_bytes() for path in data.iterdir()}, before)
            with patch.object(vm, 'run', return_value='stopped'), patch('builtins.input', return_value='y'), \
                    patch.object(vm, 'reload_vm') as reload, \
                    patch.object(vm.uuid, 'uuid4', side_effect=['existing', 'unique']):
                vm.game_media(args)
                vm.game_media(args)
                reload.assert_not_called()
            self.assertEqual((bundle / 'config.plist').read_bytes(), config)
            for path, content in before.items():
                if path.name != 'game.iso':
                    self.assertEqual(path.read_bytes(), content)
            backups = set(data.glob('game-orphan-*.iso')) - {data / 'game-orphan-existing.iso'}
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups.pop().read_bytes(), b'game.iso')
            self.assertFalse((data / 'game.iso').exists())

    def test_orphan_recovery_rechecks_stopped_state_and_configuration(self) -> None:
        for change in ('running', 'configuration'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                bundle, data = self.guest(root)
                (data / 'game.iso').write_bytes(b'unrecognized')
                config_path = bundle / 'config.plist'
                original = config_path.read_bytes()
                changed = original + b'\n'
                def confirm(prompt: str) -> str:
                    if change == 'configuration':
                        config_path.write_bytes(changed)
                    return 'yes'
                with patch.object(vm, 'run', side_effect=['stopped', 'started' if change == 'running' else 'stopped']), \
                        patch('builtins.input', side_effect=confirm), patch.object(vm, 'reload_vm') as reload:
                    with self.assertRaisesRegex(ValueError, 'refusing quarantine'):
                        vm.game_media(argparse.Namespace(home=root, action='detach-game'))
                    reload.assert_not_called()
                self.assertEqual((data / 'game.iso').read_bytes(), b'unrecognized')
                self.assertFalse(list(data.glob('game-orphan-*.iso')))
                self.assertEqual(config_path.read_bytes(), changed if change == 'configuration' else original)

    def test_detach_missing_backing_file_is_retry_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            bundle, data = self.guest(root)
            config_path = bundle / 'config.plist'
            config = plistlib.loads(config_path.read_bytes())
            config['Drive'].append({'ImageName': 'game.iso', 'ImageType': 'CD', 'Interface': 'USB',
                                    'InterfaceVersion': 1, 'Identifier': str(vm.uuid.uuid4()), 'ReadOnly': True})
            config_path.write_bytes(plistlib.dumps(config))
            before = (data / 'system.raw').read_bytes()
            with patch.object(vm, 'run', return_value='stopped'), patch.object(vm, 'reload_vm') as reload, \
                    patch('builtins.input') as confirm:
                args = argparse.Namespace(home=root, action='detach-game')
                vm.game_media(args)
                vm.game_media(args)
                reload.assert_called_once()
                confirm.assert_not_called()
            self.assertEqual(plistlib.loads(config_path.read_bytes())['Drive'], config['Drive'][:-1])
            self.assertEqual((data / 'system.raw').read_bytes(), before)

    def test_detach_refuses_unrecognized_drive_and_non_file_media(self) -> None:
        for kind in ('disk', 'directory', 'unsafe-audit'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                bundle, data = self.guest(root)
                config_path = bundle / 'config.plist'
                config = plistlib.loads(config_path.read_bytes())
                if kind == 'disk':
                    config['Drive'].append({'ImageName': 'game.iso', 'ImageType': 'Disk', 'Interface': 'NVMe',
                                            'ReadOnly': False})
                if kind == 'unsafe-audit':
                    config['Sharing']['ClipboardSharing'] = True
                config_path.write_bytes(plistlib.dumps(config))
                original = config_path.read_bytes()
                if kind == 'directory':
                    (data / 'game.iso').mkdir()
                else:
                    (data / 'game.iso').write_bytes(b'unrecognized')
                with patch.object(vm, 'run', return_value='stopped'), patch('builtins.input') as confirm:
                    with self.assertRaises(ValueError):
                        vm.game_media(argparse.Namespace(home=root, action='detach-game'))
                    confirm.assert_not_called()
                self.assertEqual(config_path.read_bytes(), original)
                self.assertTrue((data / 'game.iso').exists())

    def test_guest_helper_keeps_signature_checks_and_limits_policy_to_process(self) -> None:
        script = Path(__file__).with_name('install-gog.ps1').read_text()
        dispatcher = Path(__file__).with_name('guest-start.ps1').read_text()
        shared = Path(__file__).with_name('guest-install.ps1').read_text()
        for required in ('Get-AuthenticodeSignature', "-ne 'Valid'", 'Get-FileHash', '/VERYSILENT',
                         '/NORESTART', '/RESTARTEXITCODE=3010', 'result.json'):
            self.assertIn(required, script)
        self.assertIn('RunAs', dispatcher)
        self.assertIn('CommonDesktopDirectory', shared)
        wrapper = Path(__file__).with_name('install-gog.cmd').read_text()
        self.assertIn('-NoProfile -ExecutionPolicy RemoteSigned -File', wrapper)
        self.assertIn('RemoteSigned', dispatcher)
        self.assertIn("$publisher -notin @('GOG Limited', 'GOG sp. z o.o', 'GOG sp. z o.o.')", script)
        self.assertIn('X509NameType]::SimpleName', script)
        self.assertIn("$publisher = ($publisher -replace '\\s+', ' ').Trim()", script)
        for content in (script, wrapper, dispatcher, shared):
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

    def test_vm_or_config_changed_during_copy_preserves_actual_iso(self) -> None:
        for change in ('running', 'configuration'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                bundle, data = self.guest(root)
                before = (bundle / 'config.plist').read_bytes()
                def build(installer: Path, output: Path) -> None:
                    output.write_bytes(b'completed-iso')
                    if change == 'configuration':
                        (bundle / 'config.plist').write_bytes(before + b'\n')
                with patch.object(vm, 'run', side_effect=['stopped', 'started' if change == 'running' else 'stopped']), \
                        patch.object(vm, 'choose_installer', return_value=root / vm.GOG_INSTALLER), \
                        patch.object(vm, 'build_game_media', side_effect=build), patch.object(vm, 'reload_vm') as reload:
                    with self.assertRaisesRegex(ValueError, 'during media preparation'):
                        vm.game_media(argparse.Namespace(home=root, action='install-game', source_dir=root))
                    reload.assert_not_called()
                self.assertEqual((bundle / 'config.plist').read_bytes(), before + b'\n' if change == 'configuration' else before)
                self.assertEqual((data / 'game.iso').read_bytes(), b'completed-iso')

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
