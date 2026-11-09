#!/usr/bin/env python3
"""Prepare a dedicated UTM Windows ARM guest without changing host software."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import secrets
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from typing import Any


NAME = "FlatOut 2 Sandbox"
DEFAULT_HOME = Path.home() / "Library/Application Support/FlatOut2VM"
UTM = Path("/Applications/UTM.app")
NS = "urn:schemas-microsoft-com:unattend"
ET.register_namespace("", NS)
ET.register_namespace("wcm", "http://schemas.microsoft.com/WMIConfig/2002/State")


def run(args: list[str]) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()


def verify_iso(path: Path, expected: str) -> None:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        raise ValueError("Supply the SHA256 published by Microsoft for this exact ISO.")
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest.lower() != expected.lower():
        raise ValueError("Windows ISO SHA256 mismatch; refusing to continue.")


def configuration(vm_id: str) -> dict[str, Any]:
    """UTM v5.0.8's version-4 plist schema; all media stays in the VM bundle."""
    drives = []
    for filename, image_type, interface in (
        ("windows.iso", "CD", "USB"),
        ("seed.iso", "CD", "USB"),
        ("system.raw", "Disk", "NVMe"),
    ):
        drives.append({
            "ImageName": filename, "ImageType": image_type, "Interface": interface,
            "InterfaceVersion": 1, "Identifier": str(uuid.uuid4()),
            "ReadOnly": image_type == "CD",
        })
    mac = "02:" + ":".join(f"{b:02x}" for b in secrets.token_bytes(5))
    return {
        "Backend": "QEMU", "ConfigurationVersion": 4,
        "Information": {"Name": NAME, "UUID": vm_id, "IconCustom": False},
        "System": {
            "Architecture": "aarch64", "Target": "virt", "CPU": "default",
            "CPUFlagsAdd": [], "CPUFlagsRemove": [], "CPUCount": 4,
            "ForceMulticore": False, "MemorySize": 8192, "JITCacheSize": 0,
        },
        "QEMU": {
            "DebugLog": False, "UEFIBoot": True, "RNGDevice": True,
            "BalloonDevice": False, "TPMDevice": True, "Hypervisor": True,
            "TSO": False, "RTCLocalTime": True, "PS2Controller": False,
            "AdditionalArguments": [],
        },
        "Input": {"UsbBusSupport": "3.0", "UsbSharing": False, "MaximumUsbShare": 0},
        "Sharing": {
            "DirectoryShareMode": "None", "DirectoryShareReadOnly": True,
            "ClipboardSharing": False,
        },
        "Display": [{
            "Hardware": "virtio-ramfb-gl", "DynamicResolution": False,
            "NativeResolution": False, "UpscalingFilter": "Linear",
            "DownscalingFilter": "Linear",
        }],
        "Drive": drives,
        "Network": [{
            "Mode": "Shared", "Hardware": "virtio-net-pci", "MacAddress": mac,
            "IsolateFromHost": True, "PortForward": [],
        }],
        "Serial": [], "Sound": [],
    }


def unattended(admin_password: str, gamer_password: str) -> bytes:
    """Install only to the guest's disk 0; no security or hardware-check bypasses."""
    root = ET.Element(f"{{{NS}}}unattend")

    def child(parent: ET.Element, name: str, text: str | None = None) -> ET.Element:
        node = ET.SubElement(parent, f"{{{NS}}}{name}")
        node.text = text
        return node

    def component(settings: ET.Element, name: str) -> ET.Element:
        return ET.SubElement(settings, f"{{{NS}}}component", {
            "name": name, "processorArchitecture": "arm64",
            "publicKeyToken": "31bf3856ad364e35", "language": "neutral",
            "versionScope": "nonSxS",
        })

    winpe = ET.SubElement(root, f"{{{NS}}}settings", {"pass": "windowsPE"})
    locale = component(winpe, "Microsoft-Windows-International-Core-WinPE")
    child(child(locale, "SetupUILanguage"), "UILanguage", "en-US")
    for key in ("InputLocale", "SystemLocale", "UILanguage", "UserLocale"):
        child(locale, key, "en-US")
    setup = component(winpe, "Microsoft-Windows-Setup")
    disk = child(child(setup, "DiskConfiguration"), "Disk")
    disk.set("{http://schemas.microsoft.com/WMIConfig/2002/State}action", "add")
    child(disk, "DiskID", "0")
    child(disk, "WillWipeDisk", "true")
    partitions = child(disk, "CreatePartitions")
    for order, kind, size in ((1, "EFI", 260), (2, "MSR", 16), (3, "Primary", None)):
        part = child(partitions, "CreatePartition")
        part.set("{http://schemas.microsoft.com/WMIConfig/2002/State}action", "add")
        child(part, "Order", str(order))
        child(part, "Type", kind)
        child(part, "Extend" if size is None else "Size", "true" if size is None else str(size))
    modifications = child(disk, "ModifyPartitions")
    for order, fmt in ((1, "FAT32"), (3, "NTFS")):
        part = child(modifications, "ModifyPartition")
        part.set("{http://schemas.microsoft.com/WMIConfig/2002/State}action", "add")
        child(part, "Order", str(1 if order == 1 else 2))
        child(part, "PartitionID", str(order))
        child(part, "Format", fmt)
        if order == 3:
            child(part, "Letter", "C")
    image = child(child(setup, "ImageInstall"), "OSImage")
    metadata = child(child(image, "InstallFrom"), "MetaData")
    metadata.set("{http://schemas.microsoft.com/WMIConfig/2002/State}action", "add")
    child(metadata, "Key", "/IMAGE/NAME")
    child(metadata, "Value", "Windows 11 Pro")
    target = child(image, "InstallTo")
    child(target, "DiskID", "0")
    child(target, "PartitionID", "3")
    child(image, "WillShowUI", "OnError")
    userdata = child(setup, "UserData")
    child(userdata, "AcceptEula", "true")
    # Microsoft's generic Pro installation key selects the edition, not activation.
    product = child(userdata, "ProductKey")
    child(product, "Key", "VK7JG-NPHTM-C97JM-9MPGT-3V66T")
    child(product, "WillShowUI", "OnError")
    oobe = ET.SubElement(root, f"{{{NS}}}settings", {"pass": "oobeSystem"})
    shell = component(oobe, "Microsoft-Windows-Shell-Setup")
    accounts = child(child(shell, "UserAccounts"), "LocalAccounts")
    for name, group, password in (
        ("VMAdmin", "Administrators", admin_password),
        ("Player", "Users", gamer_password),
    ):
        account = child(accounts, "LocalAccount")
        account.set("{http://schemas.microsoft.com/WMIConfig/2002/State}action", "add")
        child(account, "Name", name)
        child(account, "Group", group)
        pw = child(account, "Password")
        child(pw, "Value", password)
        child(pw, "PlainText", "true")
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def check_host() -> None:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ValueError("This prototype requires an Apple Silicon Mac.")
    with (UTM / "Contents/Info.plist").open("rb") as source:
        version = plistlib.load(source)["CFBundleShortVersionString"]
    numbers = tuple(int(n) for n in version.split("."))
    if numbers < (5, 0, 8):
        raise ValueError(
            f"UTM {version} is too old; need 5.0.8+. Update through your software manager. "
            "On an unmanaged Mac: brew install --cask utm (or brew upgrade --cask utm)."
        )


def audit(config: dict[str, Any]) -> None:
    if config["Backend"] != "QEMU" or config["System"]["Architecture"] != "aarch64":
        raise ValueError("Unexpected VM backend or architecture.")
    sharing = config["Sharing"]
    if sharing["DirectoryShareMode"] != "None" or sharing["ClipboardSharing"]:
        raise ValueError("Unsafe host sharing is enabled.")
    if config["Input"]["UsbSharing"] or config["QEMU"]["AdditionalArguments"]:
        raise ValueError("USB sharing or custom QEMU arguments are not allowed.")
    if config["Sound"]:
        raise ValueError("Audio devices are disabled until input isolation is verified.")
    if not config["QEMU"]["UEFIBoot"] or not config["QEMU"]["TPMDevice"]:
        raise ValueError("UEFI and TPM must remain enabled.")
    if config["Serial"]:
        raise ValueError("Unexpected serial channel.")
    for drive in config["Drive"]:
        name = drive.get("ImageName", "")
        if not name or Path(name).name != name or name in (".", ".."):
            raise ValueError("External or invalid drive backing file.")
        if drive["ImageType"] == "CD" and not drive["ReadOnly"]:
            raise ValueError("Installation media must be read-only.")
    networks = config["Network"]
    if len(networks) != 1 or networks[0]["PortForward"]:
        raise ValueError("Unexpected network interfaces or port forwards.")
    nic = networks[0]
    if nic["Mode"] not in ("Shared", "Bridged"):
        raise ValueError("Unexpected network mode.")
    if nic["Mode"] == "Shared" and not nic["IsolateFromHost"]:
        raise ValueError("Shared networking must enable host isolation.")


def setup(args: argparse.Namespace) -> None:
    check_host()
    if not args.accept_windows_license:
        raise ValueError("Read the Windows license, then pass --accept-windows-license to accept it.")
    if not args.windows_iso or not args.windows_sha256:
        raise ValueError("Provide --windows-iso and --windows-sha256 from Microsoft's download page.")
    iso = args.windows_iso.resolve(strict=True)
    verify_iso(iso, args.windows_sha256)
    firmware = UTM / "Contents/Resources/qemu/edk2-arm-secure-vars.fd"
    if not firmware.is_file():
        raise ValueError(f"UTM Secure Boot template is missing: {firmware}")
    destination = args.home.expanduser().resolve()
    if destination.exists():
        raise ValueError(f"Refusing to overwrite existing state in {destination}")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    bundle = destination / f"{NAME}.utm"
    data = bundle / "Data"
    data.mkdir(parents=True, mode=0o700)
    vm_id = str(uuid.uuid4())
    config = configuration(vm_id)
    audit(config)
    with (bundle / "config.plist").open("wb") as output:
        plistlib.dump(config, output)
    shutil.copyfile(firmware, data / "efi_vars.fd")
    with (data / "system.raw").open("xb") as disk:
        disk.truncate(80 * 1024**3)
    shutil.copyfile(iso, data / "windows.iso")
    admin, player = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    credentials = {"VMAdmin": admin, "Player": player}
    (destination / "credentials.json").write_text(json.dumps(credentials, indent=2) + "\n")
    seed = destination / "seed"
    seed.mkdir(mode=0o700)
    (seed / "Autounattend.xml").write_bytes(unattended(admin, player))
    shutil.copyfile(Path(__file__).with_name("guest-setup.ps1"), seed / "guest-setup.ps1")
    run(["/usr/bin/hdiutil", "makehybrid", "-iso", "-joliet", "-default-volume-name",
         "FLATOUTSETUP", "-o", str(data / "seed.iso"), str(seed)])
    (destination / "vm-id").write_text(vm_id + "\n")
    run(["/usr/bin/open", "-a", str(UTM), str(bundle)])
    print(f"VM prepared: {bundle}\nCredentials: {destination / 'credentials.json'}")
    print("Start it in UTM and press a key at the Windows boot prompt. See README.md for remaining steps.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "audit", "start"))
    parser.add_argument("--home", type=Path, default=DEFAULT_HOME)
    parser.add_argument("--windows-iso", type=Path)
    parser.add_argument("--windows-sha256")
    parser.add_argument("--accept-windows-license", action="store_true")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or later is required.")
    os.umask(0o077)
    try:
        if args.action == "setup":
            setup(args)
        else:
            bundle = args.home.expanduser() / f"{NAME}.utm"
            # Symlinks would defeat the bundle-local backing-file restriction.
            if bundle.is_symlink() or (bundle / "Data").is_symlink():
                raise ValueError("VM bundle and Data directory must not be symlinks.")
            for path in bundle.rglob("*"):
                if path.is_symlink():
                    raise ValueError(f"Symlink in VM bundle: {path}")
            with (bundle / "config.plist").open("rb") as source:
                config = plistlib.load(source)
            audit(config)
            for drive in config["Drive"]:
                if not (bundle / "Data" / drive["ImageName"]).is_file():
                    raise ValueError(f"Missing backing file: {drive['ImageName']}")
            print("Configuration audit passed (not a proof of VM security).")
            if args.action == "start":
                check_host()
                vm_id = config["Information"]["UUID"]
                uuid.UUID(vm_id)
                run([str(UTM / "Contents/MacOS/utmctl"), "start", vm_id])
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
