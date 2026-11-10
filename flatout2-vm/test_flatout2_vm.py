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
    def test_oobe_uses_us_locale_and_keyboard(self) -> None:
        root = ET.fromstring(vm.unattended("a", "b"))
        ns = {"u": vm.NS}
        locale = root.find("u:settings[@pass='oobeSystem']/u:component[@name='Microsoft-Windows-International-Core']", ns)
        self.assertIsNotNone(locale)
        for key, value in (("InputLocale", "0409:00000409"), ("SystemLocale", "en-US"),
                           ("UILanguage", "en-US"), ("UserLocale", "en-US")):
            self.assertEqual(locale.findtext(f"u:{key}", namespaces=ns), value)

    def test_driver_path_uses_configuration_set_without_drive_letter(self) -> None:
        root = ET.fromstring(vm.unattended("a", "b"))
        ns = {"u": vm.NS}
        self.assertEqual(root.findtext(".//u:UseConfigurationSet", namespaces=ns), "true")
        driver = root.find("u:settings[@pass='windowsPE']/u:component[@name='Microsoft-Windows-PnpCustomizationsWinPE']", ns)
        self.assertEqual(driver.findtext(".//u:Path", namespaces=ns), r"%configsetroot%\drivers\NetKVM")
        self.assertNotIn(b"ForceUnsigned", vm.unattended("a", "b"))

    def test_accounts_are_distinct_and_xml_escapes_passwords(self) -> None:
        root = ET.fromstring(vm.unattended('admin<&"', 'player<&"'))
        ns = {"u": vm.NS}
        accounts = root.findall(".//u:LocalAccount", ns)
        values = {a.findtext("u:Name", namespaces=ns): (
            a.findtext("u:Group", namespaces=ns), a.findtext("u:Password/u:Value", namespaces=ns)
        ) for a in accounts}
        self.assertEqual(values["Player"], ("Users", 'player<&"'))
        self.assertEqual(values["VMAdmin"], ("Administrators", 'admin<&"'))
        for component in root.findall(".//u:component", ns):
            self.assertEqual(component.attrib["processorArchitecture"], "arm64")
        self.assertIsNone(root.find(".//u:AutoLogon", ns))

    def test_installs_only_on_guest_disk_zero_without_bypasses(self) -> None:
        xml = vm.unattended("a", "b")
        root = ET.fromstring(xml)
        ns = {"u": vm.NS}
        self.assertEqual([n.text for n in root.findall(".//u:DiskID", ns)], ["0", "0"])
        self.assertNotIn(b"Bypass", xml)
        self.assertNotIn(b"SkipMachineOOBE", xml)


class PrerequisiteTests(unittest.TestCase):
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
            destination = Path(directory)
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
            destination = Path(directory)
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
