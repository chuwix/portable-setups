import copy
import argparse
import hashlib
import importlib.util
from pathlib import Path
import plistlib
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("flatout2_vm", Path(__file__).with_name("flatout2_vm.py"))
assert SPEC is not None and SPEC.loader is not None
vm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vm)


class ConfigurationTests(unittest.TestCase):
    def test_system_disk_precedes_installation_media(self) -> None:
        drives = self.config["Drive"]
        self.assertEqual([drive["ImageName"] for drive in drives],
                         ["system.raw", "windows.iso", "seed.iso"])
        self.assertEqual(drives[0]["Interface"], "NVMe")
        self.assertFalse(drives[0]["ReadOnly"])
        self.assertTrue(all(drive["ReadOnly"] for drive in drives[1:]))

    def setUp(self) -> None:
        self.config = vm.configuration("f28a7d62-4bdd-47af-86fe-e60e96edca44")

    def test_plist_round_trip_and_audit(self) -> None:
        vm.audit(plistlib.loads(plistlib.dumps(self.config)))
        self.assertEqual(self.config["Display"][0]["Hardware"], "virtio-ramfb-gl")
        self.assertTrue(self.config["QEMU"]["Hypervisor"])
        self.assertEqual(self.config["System"]["CPUCount"], 4)
        self.assertEqual(self.config["System"]["MemorySize"], 8192)

    def test_rejects_host_integration(self) -> None:
        mutations = (
            ("Sharing", "DirectoryShareMode", "WebDAV"),
            ("Sharing", "ClipboardSharing", True),
            ("Input", "UsbSharing", True),
            ("QEMU", "AdditionalArguments", ["-drive file=/host"]),
            ("QEMU", "TPMDevice", False),
            ("QEMU", "UEFIBoot", False),
        )
        for section, key, value in mutations:
            with self.subTest(key=key):
                config = copy.deepcopy(self.config)
                config[section][key] = value
                with self.assertRaises(ValueError):
                    vm.audit(config)

    def test_rejects_external_writable_and_traversing_media(self) -> None:
        for name in ("/Users/example/private.raw", "../private.raw", "", ".", ".."):
            with self.subTest(name=name):
                config = copy.deepcopy(self.config)
                config["Drive"][0]["ImageName"] = name
                with self.assertRaises(ValueError):
                    vm.audit(config)
        self.config["Drive"][1]["ReadOnly"] = False
        with self.assertRaises(ValueError):
            vm.audit(self.config)

    def test_rejects_extra_channels(self) -> None:
        for key, value in (("Serial", [{}]), ("Sound", [{"Hardware": "intel-hda"}])):
            config = copy.deepcopy(self.config)
            config[key] = value
            with self.assertRaises(ValueError):
                vm.audit(config)

    def test_rejects_unsafe_networks(self) -> None:
        self.config["Network"][0]["IsolateFromHost"] = False
        with self.assertRaises(ValueError):
            vm.audit(self.config)
        self.config["Network"][0]["Mode"] = "Bridged"
        vm.audit(self.config)
        self.config["Network"][0]["PortForward"] = [{}]
        with self.assertRaises(ValueError):
            vm.audit(self.config)

    def test_identifiers_are_unique(self) -> None:
        other = vm.configuration("another")
        self.assertNotEqual(self.config["Network"][0]["MacAddress"], other["Network"][0]["MacAddress"])
        identifiers = [d["Identifier"] for d in self.config["Drive"]]
        self.assertEqual(len(identifiers), len(set(identifiers)))


class BootMediaTests(unittest.TestCase):
    def test_network_staging_copies_only_allowlisted_arm64_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            seed = Path(directory) / "seed"

            def mount_tools(args: list[str]) -> str:
                if args[1] == "attach":
                    mount = Path(args[args.index("-mountpoint") + 1])
                    source = mount / "Drivers/NetKVM/w11/ARM64"
                    source.mkdir(parents=True)
                    for name in ("netkvm.inf", "netkvm.sys", "netkvm.cat", "netkvmp.exe", "netkvmco.exe", "netkvmco.dll"):
                        (source / name).write_text("NTARM64\nCatalogFile = netkvm.cat")
                    (source / "unwanted.exe").write_bytes(b"not copied")
                    (mount / "Autounattend.xml").write_bytes(b"not copied")
                    (mount / "virtio-win_license.txt").write_text("license")
                return ""

            with patch.object(vm, "verify_iso") as verify, patch.object(vm, "run", side_effect=mount_tools) as run:
                vm.stage_network_driver(seed, Path("drivers.iso"))
            verify.assert_called_once_with(Path("drivers.iso"), vm.DRIVERS_SHA256)
            self.assertEqual(len(list((seed / "drivers/NetKVM").iterdir())), 7)
            self.assertFalse((seed / "Autounattend.xml").exists())
            self.assertFalse((seed / "drivers/NetKVM/unwanted.exe").exists())
            self.assertEqual(run.call_args_list[-1].args[0][1], "detach")

    def fixture(self) -> tuple[bytearray, bytes, bytes]:
        image = bytearray(100 * 2048)
        image[16 * 2048:16 * 2048 + 7] = b"\x00CD001\x01"
        image[16 * 2048 + 7:16 * 2048 + 30] = b"EL TORITO SPECIFICATION"
        struct.pack_into("<I", image, 16 * 2048 + 71, 22)
        image[17 * 2048:17 * 2048 + 7] = b"\xffCD001\x01"
        catalog = bytearray(2048)
        catalog[:2] = b"\x01\xef"
        catalog[30:32] = b"\x55\xaa"
        struct.pack_into("<H", catalog, 28, -sum(struct.unpack("<16H", catalog[:32])) % 65536)
        catalog[32] = 0x88
        struct.pack_into("<H", catalog, 38, 4)
        struct.pack_into("<I", catalog, 40, 90)
        image[22 * 2048:23 * 2048] = catalog
        prompt, noprompt = b"p" * 2048, b"n" * 2048
        image[90 * 2048:91 * 2048] = prompt
        return image, prompt, noprompt

    def test_only_default_boot_image_changes(self) -> None:
        image, prompt, noprompt = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            iso = Path(directory) / "windows.iso"
            iso.write_bytes(image)
            with patch.object(vm, "EFI_PROMPT_SHA256", hashlib.sha256(prompt).hexdigest()), \
                    patch.object(vm, "EFI_NOPROMPT_SHA256", hashlib.sha256(noprompt).hexdigest()):
                vm.patch_boot_image(iso, prompt, noprompt)
                vm.patch_boot_image(iso, prompt, noprompt)
            image[90 * 2048:91 * 2048] = noprompt
            self.assertEqual(iso.read_bytes(), image)

    def test_unexpected_media_is_never_modified(self) -> None:
        for mutation in ("hash", "catalog", "image", "size", "platform", "descriptor"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                image, prompt, noprompt = self.fixture()
                if mutation == "catalog":
                    image[22 * 2048 + 30] = 0
                elif mutation == "image":
                    image[90 * 2048] = 0
                elif mutation == "size":
                    image[22 * 2048 + 38] = 0
                elif mutation == "platform":
                    image[22 * 2048 + 1] = 0
                elif mutation == "descriptor":
                    image[16 * 2048 + 1] = 0
                iso = Path(directory) / "windows.iso"
                iso.write_bytes(image)
                with patch.object(vm, "EFI_PROMPT_SHA256", "0" * 64 if mutation == "hash" else hashlib.sha256(prompt).hexdigest()), \
                        patch.object(vm, "EFI_NOPROMPT_SHA256", hashlib.sha256(noprompt).hexdigest()):
                    with self.assertRaises(ValueError):
                        vm.patch_boot_image(iso, prompt, noprompt)
                self.assertEqual(iso.read_bytes(), image)

    def test_mount_is_detached_when_boot_images_are_missing(self) -> None:
        with patch.object(vm, "run") as run:
            with self.assertRaises(FileNotFoundError):
                vm.prepare_windows_media(Path("missing.iso"))
        self.assertEqual(run.call_args_list[0].args[0][1], "attach")
        self.assertEqual(run.call_args_list[-1].args[0][1], "detach")


class UnattendedTests(unittest.TestCase):
    def test_privacy_defaults_precede_network_and_disable_express_settings(self) -> None:
        root = ET.fromstring(vm.unattended("a", "b"))
        ns = {"u": vm.NS}
        self.assertEqual(root.findtext(".//u:OOBE/u:ProtectYourPC", namespaces=ns), "3")
        command = root.findtext(".//u:RunSynchronousCommand/u:Path", namespaces=ns)
        self.assertLessEqual(len(command), 259)
        self.assertIn("prepare-guest.cmd", command)
        wrapper = Path(__file__).with_name("prepare-guest.cmd").read_text()
        self.assertLess(wrapper.index("configure-privacy.cmd"), wrapper.index("install-network.cmd"))
        self.assertIn("if errorlevel 1 exit /b 10", wrapper)
        script = Path(__file__).with_name("configure-privacy.cmd").read_text()
        for name, value in (("DisableLocation", 1), ("AllowFindMyDevice", 0),
                            ("DisabledByGroupPolicy", 1), ("AllowTelemetry", 1),
                            ("AllowInputPersonalization", 0),
                            ("DisableTailoredExperiencesWithDiagnosticData", 1),
                            ("DisablePrivacyExperience", 1)):
            self.assertIn(f"{name} {value}", script)
        self.assertLess(script.index("DisableTailoredExperiencesWithDiagnosticData"),
                        script.index("DisablePrivacyExperience"))
        self.assertIn("reg unload HKU\\FlatOut2Default", script)

    def test_oobe_uses_us_locale_and_keyboard(self) -> None:
        root = ET.fromstring(vm.unattended("a", "b"))
        ns = {"u": vm.NS}
        locale = root.find("u:settings[@pass='oobeSystem']/u:component[@name='Microsoft-Windows-International-Core']", ns)
        self.assertIsNotNone(locale)
        for key, value in (("InputLocale", "0409:00000409"), ("SystemLocale", "en-US"),
                           ("UILanguage", "en-US"), ("UserLocale", "en-US")):
            self.assertEqual(locale.findtext(f"u:{key}", namespaces=ns), value)

    def test_driver_install_runs_before_oobe_without_fixed_drive_letter(self) -> None:
        root = ET.fromstring(vm.unattended("a", "b"))
        ns = {"u": vm.NS}
        driver = root.find("u:settings[@pass='specialize']/u:component[@name='Microsoft-Windows-Deployment']", ns)
        command = driver.findtext(".//u:Path", namespaces=ns)
        self.assertIn("flatout2-seed.tag", command)
        self.assertIn("prepare-guest.cmd", command)
        self.assertLessEqual(len(command), 259)
        self.assertIn("exit $LASTEXITCODE", command)
        self.assertEqual(driver.findtext(".//u:WillReboot", namespaces=ns), "OnRequest")
        self.assertNotIn("Bypass", command)
        self.assertNotIn(b"ForceUnsigned", vm.unattended("a", "b"))

    def test_network_script_maps_setup_reboot_and_failure_codes(self) -> None:
        script = Path(__file__).with_name("install-network.cmd").read_text()
        self.assertIn('if "%RESULT%"=="3010" exit /b 1', script)
        self.assertIn('if not "%RESULT%"=="0" exit /b 10', script)
        self.assertIn('/add-driver "%~dp0drivers\\NetKVM\\netkvm.inf" /install', script)
        self.assertIn("flatout2-network.log", script)
        self.assertNotIn("/reboot", script)

    def test_accounts_are_distinct_and_xml_escapes_passwords(self) -> None:
        root = ET.fromstring(vm.unattended('admin<&"', 'player<&"'))
        ns = {"u": vm.NS}
        accounts = root.findall(".//u:LocalAccount", ns)
        values = {a.findtext("u:Name", namespaces=ns): (
            a.findtext("u:Group", namespaces=ns), a.findtext("u:Password/u:Value", namespaces=ns)
        ) for a in accounts}
        self.assertEqual(values["Player"], ("Administrators", 'player<&"'))
        self.assertEqual(values["VMAdmin"], ("Administrators", 'admin<&"'))
        for component in root.findall(".//u:component", ns):
            self.assertEqual(component.attrib["processorArchitecture"], "arm64")
        login = root.find(".//u:AutoLogon", ns)
        self.assertEqual(login.findtext("u:Username", namespaces=ns), "Player")
        self.assertEqual(login.findtext("u:Enabled", namespaces=ns), "true")
        self.assertEqual(login.findtext("u:LogonCount", namespaces=ns), "999")
        self.assertEqual(login.findtext("u:Password/u:Value", namespaces=ns), 'player<&"')

    def test_startup_diagnostics_need_no_elevation_or_host_sharing(self) -> None:
        wrapper = Path(__file__).with_name("prepare-guest.cmd").read_text()
        self.assertIn('%ProgramFiles%\\FlatOut2VM\\guest-status.cmd', wrapper)
        self.assertIn('%ProgramData%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup', wrapper)
        self.assertLess(wrapper.index("guest-status.cmd"), wrapper.index("install-network.cmd"))
        script = Path(__file__).with_name("guest-status.cmd").read_text()
        self.assertIn('if /i not "%USERNAME%"=="Player" exit /b 0', script)
        self.assertIn('%LOCALAPPDATA%\\FlatOut2VM', script)
        self.assertIn('Game compatibility is NOT verified', script)
        self.assertIn('dxdiag.exe', script)
        self.assertIn('Startup run ID:', script)
        self.assertIn('Refusing stale results.', script)
        self.assertIn('/c:"Card name:"', script)
        self.assertLess(script.index('del "%OUT%\\dxdiag.txt"'), script.index('dxdiag.exe'))
        for forbidden in ('runas', 'ExecutionPolicy', 'net user', 'reg add', 'http://', 'https://'):
            self.assertNotIn(forbidden, script)

    def test_seed_contains_all_guest_startup_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            seed, data = Path(directory) / "seed", Path(directory) / "data"
            seed.mkdir()
            data.mkdir()
            def make_iso(command: list[str]) -> str:
                Path(command[command.index("-o") + 1]).write_bytes(b"iso")
                return ""
            with patch.object(vm, "run", side_effect=make_iso):
                vm.write_seed(seed, data)
            for name in ("prepare-guest.cmd", "configure-privacy.cmd", "install-network.cmd", "guest-status.cmd", *vm.GAME_HELPERS):
                self.assertEqual((seed / name).read_bytes(), Path(__file__).with_name(name).read_bytes())

    def test_installs_only_on_guest_disk_zero_without_bypasses(self) -> None:
        xml = vm.unattended("a", "b")
        root = ET.fromstring(xml)
        ns = {"u": vm.NS}
        self.assertEqual([n.text for n in root.findall(".//u:DiskID", ns)], ["0", "0"])
        self.assertNotIn(b"Bypass", xml)
        self.assertNotIn(b"SkipMachineOOBE", xml)


class HostFlowTests(unittest.TestCase):
    def test_stage_only_fresh_setup_never_interacts_with_utm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            firmware = root / 'UTM/Contents/Resources/qemu/edk2-arm-secure-vars.fd'
            firmware.parent.mkdir(parents=True)
            firmware.touch()
            iso = root / 'windows.iso'
            iso.touch()
            args = argparse.Namespace(home=root / 'home', source_dir=root, accept_windows_license=True,
                                      cache=root, stage_only=True)
            with patch.object(vm, 'UTM', root / 'UTM'), patch.object(vm, 'check_host'), \
                    patch.object(vm, 'choose_installer', return_value=root / vm.GOG_INSTALLER) as choose, \
                    patch.object(vm, 'acquire_iso', return_value=iso) as acquire, \
                    patch.object(vm, 'download_iso', return_value=iso), patch.object(vm, 'stage_network_driver'), \
                    patch.object(vm, 'prepare_windows_media'), patch.object(vm, 'write_seed'), \
                    patch.object(vm, 'build_game_media'), patch.object(vm, 'run') as run, \
                    patch.object(vm, 'start_setup_vm') as start, patch('builtins.print') as output:
                vm.setup(args)
                choose.assert_called_once()
                acquire.assert_called_once()
                run.assert_not_called()
                start.assert_not_called()
                self.assertIn('VM prepared, not started', output.call_args.args[0])
                self.assertNotIn('Windows setup has started', output.call_args.args[0])
                self.assertIn('docs/cleanup.md', output.call_args.args[0])
            config = plistlib.loads((args.home / f'{vm.NAME}.utm/config.plist').read_bytes())
            vm.audit(config)
            self.assertEqual(config['Sound'], [])
            self.assertEqual(config['Drive'][-1]['ImageName'], 'game.iso')

    def test_stage_only_blank_retry_preserves_state_without_registration_or_reload(self) -> None:
        for status in ('stopped', None, 'started'):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                home = Path(directory).resolve()
                bundle = home / f'{vm.NAME}.utm'
                data = bundle / 'Data'
                data.mkdir(parents=True)
                (bundle / 'config.plist').write_bytes(plistlib.dumps(vm.configuration(str(vm.uuid.uuid4()))))
                disk = data / 'system.raw'
                disk.write_bytes(bytes(1024 * 1024))
                seed = home / 'seed'
                (seed / 'drivers/NetKVM').mkdir(parents=True)
                (seed / 'drivers/NetKVM/netkvm.inf').touch()
                answer = seed / 'Autounattend.xml'
                answer.write_bytes(b'original answer')
                credentials = home / 'credentials.json'
                credentials.write_bytes(b'original accounts')
                before = {p: p.read_bytes() for p in (disk, answer, credentials)}

                def command(command: list[str]) -> str:
                    self.assertEqual(command[1], 'status')
                    if status is None:
                        raise ValueError('Virtual machine not found.')
                    return status

                with patch.object(vm, 'run', side_effect=command), patch.object(vm, 'choose_installer'), \
                        patch.object(vm, 'build_game_media') as build, patch.object(vm, 'prepare_windows_media'), \
                        patch.object(vm, 'write_seed') as write, patch.object(vm, 'reload_vm') as reload, \
                        patch.object(vm, 'start_setup_vm') as start:
                    if status == 'started':
                        with self.assertRaisesRegex(ValueError, 'Shut down'):
                            vm.refresh_seed(home, stage_only=True)
                        build.assert_not_called()
                        write.assert_not_called()
                    else:
                        vm.refresh_seed(home, stage_only=True)
                        build.assert_called_once()
                    reload.assert_not_called()
                    start.assert_not_called()
                self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_stage_only_installed_gpt_refuses_before_game_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            firmware = root / 'UTM/Contents/Resources/qemu/edk2-arm-secure-vars.fd'
            firmware.parent.mkdir(parents=True)
            firmware.touch()
            home = root / 'home'
            data = home / f'{vm.NAME}.utm/Data'
            data.mkdir(parents=True)
            header = bytearray(8192)
            header[512:520] = b'EFI PART'
            (data / 'system.raw').write_bytes(header)
            args = argparse.Namespace(home=home, source_dir=root, accept_windows_license=True, stage_only=True)
            with patch.object(vm, 'UTM', root / 'UTM'), patch.object(vm, 'check_host'), \
                    patch.object(vm, 'game_media') as game, patch.object(vm, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'installed GPT'):
                    vm.setup(args)
                game.assert_not_called()
                run.assert_not_called()
            self.assertEqual((data / 'system.raw').read_bytes(), header)

    def test_stage_only_rejected_for_every_non_setup_action(self) -> None:
        for action in ('audit', 'start', 'install-game', 'detach-game'):
            with self.subTest(action=action), patch.object(vm.sys, 'argv', ['flatout2_vm.py', action, '--stage-only']), \
                    patch.object(vm, 'check_host') as check, patch.object(vm, 'run') as run:
                with self.assertRaises(SystemExit) as error:
                    vm.main()
                self.assertEqual(error.exception.code, 2)
                check.assert_not_called()
                run.assert_not_called()

    def test_play_state_matrix_never_writes_media(self) -> None:
        for status in ('stopped', 'started', 'paused', 'suspended', 'starting', 'pausing', 'resuming', 'stopping', 'unknown'):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                bundle = Path(directory) / 'vm.utm'
                bundle.mkdir()
                evidence = bundle / 'game.iso'
                evidence.write_bytes(b'preserved')
                config = vm.configuration(str(vm.uuid.uuid4()))
                with patch.object(vm, 'run', return_value=status) as run, patch('builtins.print') as output:
                    if status in ('stopped', 'started'):
                        vm.play(bundle, config)
                        command = run.call_args_list[-1].args[0]
                        if status == 'stopped':
                            self.assertEqual(command[1], 'start')
                            self.assertIn('cannot confirm', output.call_args.args[0])
                        else:
                            self.assertEqual(command, ['/usr/bin/open', '-a', str(vm.UTM), str(bundle)])
                            self.assertIn('No game launch was requested', output.call_args.args[0])
                    else:
                        with self.assertRaisesRegex(ValueError, 'No media changed'):
                            vm.play(bundle, config)
                        self.assertEqual(run.call_count, 1)
                self.assertEqual(evidence.read_bytes(), b'preserved')

    def test_play_preserves_strict_audit_and_reports_unregistered_vm(self) -> None:
        config = vm.configuration(str(vm.uuid.uuid4()))
        config['Sound'] = [{'Hardware': 'intel-hda'}]
        with patch.object(vm, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'Audio devices'):
                vm.play(Path('vm.utm'), config)
            run.assert_not_called()
        config['Sound'] = []
        with patch.object(vm, 'run', side_effect=ValueError('Virtual machine not found')):
            with self.assertRaisesRegex(ValueError, 'register it'):
                vm.play(Path('vm.utm'), config)

    def test_fresh_configuration_stages_readonly_game_without_gpt_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            config = vm.configuration(str(vm.uuid.uuid4()))
            with patch.object(vm, 'build_game_media') as build, patch.object(vm, 'game_media') as existing:
                result = vm.first_boot_configuration(config, data / vm.GOG_INSTALLER, data)
                build.assert_called_once_with(data / vm.GOG_INSTALLER, data / 'game.iso')
                existing.assert_not_called()
            self.assertEqual([d['ImageName'] for d in result['Drive']],
                             ['system.raw', 'windows.iso', 'seed.iso', 'game.iso'])
            self.assertTrue(result['Drive'][-1]['ReadOnly'])
            vm.audit(result)

    def test_setup_source_cancellation_precedes_downloads_and_home_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            home = root / 'home'
            firmware = root / 'UTM/Contents/Resources/qemu/edk2-arm-secure-vars.fd'
            firmware.parent.mkdir(parents=True)
            firmware.touch()
            args = argparse.Namespace(home=home, source_dir=None, accept_windows_license=True)
            with patch.object(vm, 'UTM', root / 'UTM'), patch.object(vm, 'check_host'), \
                    patch.object(vm, 'choose_installer', side_effect=ValueError('Cancelled')), \
                    patch.object(vm, 'acquire_iso') as acquire, patch.object(vm, 'download_iso') as download:
                with self.assertRaisesRegex(ValueError, 'Cancelled'):
                    vm.setup(args)
                acquire.assert_not_called()
                download.assert_not_called()
            self.assertFalse(home.exists())

    def test_fresh_setup_boots_only_after_game_media_configuration_is_published(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            home = root / 'home'
            firmware = root / 'UTM/Contents/Resources/qemu/edk2-arm-secure-vars.fd'
            firmware.parent.mkdir(parents=True)
            firmware.touch()
            iso = root / 'windows.iso'
            iso.write_bytes(b'fixture')
            args = argparse.Namespace(home=home, source_dir=root, accept_windows_license=True, cache=root)
            events: list[str] = []

            def choose(source: Path) -> Path:
                events.append('consent')
                return root / vm.GOG_INSTALLER

            def acquire(arguments: argparse.Namespace) -> Path:
                self.assertEqual(events, ['consent'])
                return iso

            def build(installer: Path, output: Path) -> None:
                output.write_bytes(b'verified')
                events.append('verified')

            def start(bundle: Path, vm_id: str) -> None:
                self.assertEqual(events, ['consent', 'verified'])
                config = plistlib.loads((bundle / 'config.plist').read_bytes())
                self.assertEqual(config['Drive'][-1]['ImageName'], 'game.iso')
                self.assertEqual((bundle / 'Data/game.iso').read_bytes(), b'verified')
                events.append('boot')

            with patch.object(vm, 'UTM', root / 'UTM'), patch.object(vm, 'check_host'), \
                    patch.object(vm, 'choose_installer', side_effect=choose), patch.object(vm, 'acquire_iso', side_effect=acquire), \
                    patch.object(vm, 'download_iso', return_value=iso), patch.object(vm, 'stage_network_driver'), \
                    patch.object(vm, 'prepare_windows_media'), patch.object(vm, 'write_seed'), \
                    patch.object(vm, 'build_game_media', side_effect=build), patch.object(vm, 'start_setup_vm', side_effect=start):
                vm.setup(args)
            self.assertEqual(events, ['consent', 'verified', 'boot'])

    def test_game_media_failure_never_boots_fresh_setup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            firmware = root / 'UTM/Contents/Resources/qemu/edk2-arm-secure-vars.fd'
            firmware.parent.mkdir(parents=True)
            firmware.touch()
            iso = root / 'windows.iso'
            iso.touch()
            args = argparse.Namespace(home=root / 'home', source_dir=root, accept_windows_license=True, cache=root)
            with patch.object(vm, 'UTM', root / 'UTM'), patch.object(vm, 'check_host'), \
                    patch.object(vm, 'choose_installer', return_value=root / vm.GOG_INSTALLER), \
                    patch.object(vm, 'acquire_iso', return_value=iso), patch.object(vm, 'download_iso', return_value=iso), \
                    patch.object(vm, 'stage_network_driver'), patch.object(vm, 'prepare_windows_media'), \
                    patch.object(vm, 'write_seed'), patch.object(vm, 'build_game_media', side_effect=ValueError('readback failed')), \
                    patch.object(vm, 'start_setup_vm') as start:
                with self.assertRaisesRegex(ValueError, 'readback failed'):
                    vm.setup(args)
                start.assert_not_called()

    def test_failed_fresh_setup_recovers_unregistered_blank_home_without_recreating_state(self) -> None:
        for published in (False, True):
            with self.subTest(published=published), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                home = root / 'home'
                firmware = root / 'UTM/Contents/Resources/qemu/edk2-arm-secure-vars.fd'
                firmware.parent.mkdir(parents=True)
                firmware.touch()
                iso = root / 'windows.iso'
                iso.touch()
                args = argparse.Namespace(home=home, source_dir=root, accept_windows_license=True, cache=root)
                registered = False
                opens: list[list[str]] = []

                def command(command: list[str]) -> str:
                    nonlocal registered
                    if command[0] == '/usr/bin/open':
                        opens.append(command)
                        registered = True
                        return ''
                    self.assertEqual(command[1], 'status')
                    if not registered:
                        raise ValueError('utmctl failed (exit 1): Virtual machine not found.')
                    return 'stopped'

                def network(seed: Path, media: Path) -> None:
                    (seed / 'drivers/NetKVM').mkdir(parents=True)
                    (seed / 'drivers/NetKVM/netkvm.inf').touch()

                def fail_build(installer: Path, output: Path) -> None:
                    if published:
                        output.write_bytes(b'verified retained ISO')
                    raise ValueError('staging interrupted')

                with patch.object(vm, 'UTM', root / 'UTM'), patch.object(vm, 'check_host'), \
                        patch.object(vm, 'choose_installer', return_value=root / vm.GOG_INSTALLER), \
                        patch.object(vm, 'acquire_iso', return_value=iso), patch.object(vm, 'download_iso', return_value=iso), \
                        patch.object(vm, 'stage_network_driver', side_effect=network), patch.object(vm, 'prepare_windows_media'), \
                        patch.object(vm, 'write_seed'), patch.object(vm, 'run', side_effect=command), \
                        patch.object(vm, 'reload_vm'), patch.object(vm, 'start_setup_vm') as start:
                    with patch.object(vm, 'build_game_media', side_effect=fail_build):
                        with self.assertRaisesRegex(ValueError, 'staging interrupted'):
                            vm.setup(args)
                    self.assertFalse(registered)
                    start.assert_not_called()
                    bundle = home / f'{vm.NAME}.utm'
                    disk = bundle / 'Data/system.raw'
                    answer = home / 'seed/Autounattend.xml'
                    credentials = home / 'credentials.json'
                    before = (disk.stat(), answer.read_bytes(), credentials.read_bytes())

                    def build(installer: Path, output: Path) -> None:
                        output.write_bytes(b'verified replacement ISO')

                    with patch.object(vm, 'build_game_media', side_effect=build) as build_mock, \
                            patch.object(vm, 'verify_game_media') as verify:
                        vm.setup(args)
                        self.assertEqual(build_mock.call_count, 0 if published else 1)
                        self.assertEqual(verify.call_count, 1 if published else 0)
                    self.assertEqual(opens, [['/usr/bin/open', '-a', str(vm.UTM), str(bundle)]])
                    start.assert_called_once()
                    self.assertEqual(disk.stat().st_ino, before[0].st_ino)
                    self.assertEqual(disk.stat().st_size, before[0].st_size)
                    self.assertEqual(disk.stat().st_mtime_ns, before[0].st_mtime_ns)
                    with disk.open('rb') as source:
                        self.assertEqual(source.read(1024 * 1024), bytes(1024 * 1024))
                    self.assertEqual(answer.read_bytes(), before[1])
                    self.assertEqual(credentials.read_bytes(), before[2])

    def test_setup_completion_has_concrete_cleanup_path_and_save_warning(self) -> None:
        with patch('builtins.print') as output:
            vm.setup_guidance()
        message = output.call_args.args[0]
        self.assertIn(str(Path(vm.__file__).resolve().parent / 'docs/cleanup.md'), message)
        self.assertIn('Permanent VM deletion loses game saves', message)
        self.assertIn('installation is not complete', message)

    def test_blank_retry_stages_missing_media_without_recreating_accounts_or_disk(self) -> None:
        for retained in (False, True):
            with self.subTest(retained=retained), tempfile.TemporaryDirectory() as directory:
                home = Path(directory).resolve()
                bundle = home / f'{vm.NAME}.utm'
                data = bundle / 'Data'
                data.mkdir(parents=True)
                config = vm.configuration(str(vm.uuid.uuid4()))
                (bundle / 'config.plist').write_bytes(plistlib.dumps(config))
                disk = data / 'system.raw'
                disk.write_bytes(bytes(1024 * 1024))
                seed = home / 'seed'
                (seed / 'drivers/NetKVM').mkdir(parents=True)
                (seed / 'drivers/NetKVM/netkvm.inf').touch()
                answer = seed / 'Autounattend.xml'
                answer.write_bytes(b'original credentials')
                if retained:
                    (data / 'game.iso').write_bytes(b'retained')
                with patch.object(vm, 'run', return_value='stopped'), patch.object(vm, 'prepare_windows_media'), \
                        patch.object(vm, 'write_seed'), patch.object(vm, 'start_setup_vm') as start, \
                        patch.object(vm, 'reload_vm'), patch.object(vm, 'choose_installer', return_value=home / vm.GOG_INSTALLER) as choose, \
                        patch.object(vm, 'build_game_media') as build, patch.object(vm, 'verify_game_media') as verify:
                    vm.refresh_seed(home)
                    if retained:
                        choose.assert_not_called()
                        build.assert_not_called()
                        verify.assert_called_once_with(data / 'game.iso')
                    else:
                        choose.assert_called_once()
                        build.assert_called_once()
                    start.assert_called_once()
                self.assertEqual(disk.read_bytes(), bytes(1024 * 1024))
                self.assertEqual(answer.read_bytes(), b'original credentials')
                self.assertEqual(plistlib.loads((bundle / 'config.plist').read_bytes())['Drive'][-1]['ImageName'], 'game.iso')


class PrerequisiteTests(unittest.TestCase):
    def test_unregistered_retry_never_opens_partitioned_or_unaudited_bundle(self) -> None:
        for unsafe in ('partitioned', 'sharing', 'status-error'):
            with self.subTest(unsafe=unsafe), tempfile.TemporaryDirectory() as directory:
                home = Path(directory).resolve()
                bundle = home / f'{vm.NAME}.utm'
                data = bundle / 'Data'
                data.mkdir(parents=True)
                config = vm.configuration(str(vm.uuid.uuid4()))
                if unsafe == 'sharing':
                    config['Sharing']['ClipboardSharing'] = True
                (bundle / 'config.plist').write_bytes(plistlib.dumps(config))
                (data / 'system.raw').write_bytes((b'partitioned' if unsafe == 'partitioned' else b'') + bytes(1024 * 1024))
                message = 'Automation permission denied' if unsafe == 'status-error' else 'Virtual machine not found.'
                with patch.object(vm, 'run', side_effect=ValueError(message)) as run:
                    with self.assertRaises(ValueError):
                        vm.refresh_seed(home)
                self.assertTrue(all(call.args[0][1] == 'status' for call in run.call_args_list))

    def test_retry_registration_requires_confirmed_stopped_state_before_media_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory).resolve()
            bundle = home / f'{vm.NAME}.utm'
            data = bundle / 'Data'
            data.mkdir(parents=True)
            original = plistlib.dumps(vm.configuration(str(vm.uuid.uuid4())))
            (bundle / 'config.plist').write_bytes(original)
            (data / 'system.raw').write_bytes(bytes(1024 * 1024))
            seed = home / 'seed'
            (seed / 'drivers/NetKVM').mkdir(parents=True)
            (seed / 'drivers/NetKVM/netkvm.inf').touch()
            (seed / 'Autounattend.xml').write_bytes(b'preserved')
            with patch.object(vm, 'run', side_effect=[ValueError('Virtual machine not found.'), '', 'started']), \
                    patch.object(vm, 'build_game_media') as build, patch.object(vm, 'write_seed') as write, \
                    patch.object(vm, 'start_setup_vm') as start:
                with self.assertRaisesRegex(ValueError, 'registered and stopped'):
                    vm.refresh_seed(home)
                build.assert_not_called()
                write.assert_not_called()
                start.assert_not_called()
            self.assertEqual((bundle / 'config.plist').read_bytes(), original)

    def test_utm_ids_use_uppercase(self) -> None:
        self.assertEqual(vm.utm_id("2b87543d-5230-48a2-9255-161e7f1fe843"),
                         "2B87543D-5230-48A2-9255-161E7F1FE843")

    def test_command_failure_reports_stderr(self) -> None:
        result = vm.subprocess.CompletedProcess(["utmctl"], 1, "", "Virtual machine not found.")
        with patch.object(vm.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(ValueError, "Virtual machine not found"):
                vm.run(["utmctl", "status", "missing"])

    def test_retry_refuses_partitioned_disk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve()
            bundle = destination / f"{vm.NAME}.utm"
            data = bundle / "Data"
            data.mkdir(parents=True)
            (bundle / "config.plist").write_bytes(plistlib.dumps(vm.configuration(str(vm.uuid.uuid4()))))
            (data / "system.raw").write_bytes(b"partitioned" + bytes(1024 * 1024))
            with patch.object(vm, "run", return_value="stopped"), patch.object(vm, "write_seed") as write:
                with self.assertRaisesRegex(ValueError, "no longer blank"):
                    vm.refresh_seed(destination)
                write.assert_not_called()

    def test_retry_refuses_running_vm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve()
            bundle = destination / f"{vm.NAME}.utm"
            bundle.mkdir()
            (bundle / "config.plist").write_bytes(plistlib.dumps(vm.configuration(str(vm.uuid.uuid4()))))
            with patch.object(vm, "run", return_value="started"), patch.object(vm, "write_seed") as write:
                with self.assertRaisesRegex(ValueError, "Shut down"):
                    vm.refresh_seed(destination)
                write.assert_not_called()

    def test_declining_license_does_not_download(self) -> None:
        args = argparse.Namespace(accept_windows_license=False)
        with patch.object(vm, "check_host"), patch.object(vm.sys.stdin, "isatty", return_value=True), \
                patch("builtins.input", return_value="no"), patch.object(vm, "acquire_iso") as acquire:
            with self.assertRaisesRegex(ValueError, "Cancelled"):
                vm.setup(args)
            acquire.assert_not_called()

    def test_noninteractive_run_requires_explicit_acceptance(self) -> None:
        args = argparse.Namespace(accept_windows_license=False)
        with patch.object(vm, "check_host"), patch.object(vm.sys.stdin, "isatty", return_value=False), \
                patch.object(vm, "acquire_iso") as acquire:
            with self.assertRaisesRegex(ValueError, "interactive terminal"):
                vm.setup(args)
            acquire.assert_not_called()

    def arguments(self, directory: str, **overrides: object) -> argparse.Namespace:
        values = dict(windows_iso=None, windows_url=None, windows_sha256=None, cache=Path(directory))
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_download_uses_pinned_url_and_checks_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            expected = hashlib.sha256(b"fixture").hexdigest()
            args = self.arguments(directory, windows_sha256=expected)

            def download(command: list[str], **kwargs: object) -> None:
                self.assertIn(vm.WINDOWS_URL, command)
                self.assertIn("--proto-redir", command)
                Path(command[command.index("--output") + 1]).write_bytes(b"fixture")

            with patch.object(vm.subprocess, "run", side_effect=download) as download_mock:
                iso = vm.acquire_iso(args)
                self.assertEqual(iso.read_bytes(), b"fixture")
                vm.acquire_iso(args)
                self.assertEqual(download_mock.call_count, 1)

    def test_override_requires_hash_and_https(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cases = (
                dict(windows_url="https://example.com/custom.iso"),
                dict(windows_url="http://example.com/custom.iso", windows_sha256="0" * 64),
                dict(windows_url="https://user:secret@example.com/a.iso", windows_sha256="0" * 64),
            )
            with patch.object(vm.subprocess, "run") as download:
                for overrides in cases:
                    with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                        vm.acquire_iso(self.arguments(directory, **overrides))
                download.assert_not_called()

    def test_bad_download_is_not_cached(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            def download(command: list[str], **kwargs: object) -> None:
                Path(command[command.index("--output") + 1]).write_bytes(b"corrupt")

            with patch.object(vm.subprocess, "run", side_effect=download):
                with self.assertRaises(ValueError):
                    vm.acquire_iso(self.arguments(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cached_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            target.write_bytes(b"data")
            (Path(directory) / f"{vm.WINDOWS_SHA256}.iso").symlink_to(target)
            with self.assertRaises(ValueError):
                vm.acquire_iso(self.arguments(directory))

    def test_iso_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            iso = Path(directory) / "windows.iso"
            iso.write_bytes(b"fixture")
            vm.verify_iso(iso, hashlib.sha256(b"fixture").hexdigest())
            for value in ("bad", "0" * 64):
                with self.assertRaises(ValueError):
                    vm.verify_iso(iso, value)

    def test_unsupported_host_does_not_run_commands(self) -> None:
        with patch.object(vm.platform, "system", return_value="Linux"), patch.object(vm, "run") as run:
            with self.assertRaises(ValueError):
                vm.check_host()
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
