import copy
import hashlib
import importlib.util
from pathlib import Path
import plistlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("flatout2_vm", Path(__file__).with_name("flatout2_vm.py"))
assert SPEC is not None and SPEC.loader is not None
vm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vm)


class ConfigurationTests(unittest.TestCase):
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
        self.config["Drive"][0]["ReadOnly"] = False
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


class UnattendedTests(unittest.TestCase):
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
