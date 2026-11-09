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
from urllib.parse import urlsplit


NAME = "FlatOut 2 Sandbox"
DEFAULT_HOME = Path.home() / "Library/Application Support/FlatOut2VM"
UTM = Path("/Applications/UTM.app")
WINDOWS_URL = (
    "https://software-static.download.prss.microsoft.com/dbazure/"
    "888969d5-f34g-4e03-ac9d-1f9786c66749/"
    "26200.6584.250915-1905.25h2_ge_release_svc_refresh_CLIENT_CONSUMER_a64fre_en-us.iso"
)
WINDOWS_SHA256 = "32cde0071ed8086b29bb6c8c3bf17ba9e3cdf43200537434a811a9b6cc2711a1"
DEFAULT_CACHE = Path.home() / "Library/Caches/portable-setups/flatout2-vm"
STARTUP_NSH = """@echo -off
map -r
for %i run (0 9)
  if exist fs%i:\\EFI\\Microsoft\\Boot\\bootmgfw.efi then
    fs%i:\\EFI\\Microsoft\\Boot\\bootmgfw.efi
  endif
endfor
for %i run (0 9)
  if exist fs%i:\\efi\\microsoft\\boot\\cdboot_noprompt.efi then
    fs%i:\\efi\\microsoft\\boot\\cdboot_noprompt.efi
  endif
endfor
echo No Windows boot manager found. Check the Windows installation media.
"""
NS = "urn:schemas-microsoft-com:unattend"
ET.register_namespace("", NS)
ET.register_namespace("wcm", "http://schemas.microsoft.com/WMIConfig/2002/State")


def run(args: list[str]) -> str:
    result = subprocess.run(args, text=True, capture_output=True)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "No diagnostic output."
        raise ValueError(f"{Path(args[0]).name} failed (exit {result.returncode}): {detail}")
    return result.stdout.strip()


def utm_id(value: str) -> str:
    """UTM's scripting lookup requires uppercase UUID text."""
    return str(uuid.UUID(value)).upper()


def verify_iso(path: Path, expected: str) -> None:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        raise ValueError("Supply a trusted SHA256 for this exact ISO.")
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest.lower() != expected.lower():
        raise ValueError("Windows ISO SHA256 mismatch; refusing to continue.")


def acquire_iso(args: argparse.Namespace) -> Path:
    """Fetch only the pinned image unless the caller explicitly overrides it."""
    expected = args.windows_sha256 or WINDOWS_SHA256
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        raise ValueError("Expected SHA256 must contain exactly 64 hexadecimal characters.")
    if args.windows_iso:
        iso = args.windows_iso.expanduser().resolve(strict=True)
        verify_iso(iso, expected)
        return iso
    url = args.windows_url or WINDOWS_URL
    if args.windows_url and not args.windows_sha256:
        raise ValueError("--windows-url requires an explicit --windows-sha256.")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("ISO download URL must use HTTPS without embedded credentials.")
    cache = args.cache.expanduser().resolve()
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    iso = cache / f"{expected.lower()}.iso"
    if iso.exists():
        if iso.is_symlink() or not iso.is_file():
            raise ValueError("Cached ISO must be a regular file, not a symlink.")
        verify_iso(iso, expected)
        print(f"Using verified cached ISO: {iso}")
        return iso
    # Each transfer owns its temporary file; failed downloads are not trusted or reused.
    partial = cache / f"{expected.lower()}.{uuid.uuid4()}.partial"
    try:
        print("Downloading pinned Windows image (about 6.8 GiB); verifying SHA256 afterward.", flush=True)
        subprocess.run([
            "/usr/bin/curl", "--fail", "--location", "--show-error", "--progress-bar",
            "--proto", "=https", "--proto-redir", "=https", "--connect-timeout", "30",
            "--max-time", "7200", "--output", str(partial), "--url", url,
        ], check=True)
        verify_iso(partial, expected)
        os.replace(partial, iso)
    finally:
        partial.unlink(missing_ok=True)
    return iso


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


def refresh_seed(destination: Path) -> None:
    """Refresh installer media only for a stopped VM whose disk is unpartitioned."""
    bundle = destination / f"{NAME}.utm"
    if destination.is_symlink() or any(p.is_symlink() for p in destination.rglob("*")):
        raise ValueError("Refusing setup state containing symlinks.")
    with (bundle / "config.plist").open("rb") as source:
        config = plistlib.load(source)
    audit(config)
    vm_id = utm_id(config["Information"]["UUID"])
    status = run([str(UTM / "Contents/MacOS/utmctl"), "status", vm_id])
    if status != "stopped":
        raise ValueError("Shut down the VM before retrying setup; its disk will not be changed.")
    data = bundle / "Data"
    with (data / "system.raw").open("rb") as disk:
        header = disk.read(1024 * 1024)
    if len(header) != 1024 * 1024 or any(header):
        raise ValueError("Guest disk is no longer blank. Refusing to reattach an unattended installer that could erase it.")
    seed = destination / "seed"
    if not (seed / "Autounattend.xml").is_file():
        raise ValueError("Original unattended file is missing; refusing to regenerate accounts.")
    write_seed(seed, data)
    start_setup_vm(bundle, vm_id)


def write_seed(seed: Path, data: Path) -> None:
    (seed / "startup.nsh").write_bytes(STARTUP_NSH.replace("\n", "\r\n").encode("ascii"))
    shutil.copyfile(Path(__file__).with_name("guest-setup.ps1"), seed / "guest-setup.ps1")
    temporary = data / f"seed-{uuid.uuid4()}.iso"
    try:
        run(["/usr/bin/hdiutil", "makehybrid", "-iso", "-joliet", "-default-volume-name",
             "FLATOUTSETUP", "-o", str(temporary), str(seed)])
        os.replace(temporary, data / "seed.iso")
    finally:
        temporary.unlink(missing_ok=True)


def start_setup_vm(bundle: Path, vm_id: str) -> None:
    run(["/usr/bin/open", "-a", str(UTM), str(bundle)])
    run([str(UTM / "Contents/MacOS/utmctl"), "start", utm_id(vm_id)])
    print("VM started. Firmware fallback should launch Windows Setup; report a Shell> prompt if it does not.")


def setup(args: argparse.Namespace) -> None:
    check_host()
    if not args.accept_windows_license:
        if not sys.stdin.isatty():
            raise ValueError("Windows license acceptance requires an interactive terminal or --accept-windows-license.")
        print("This experimental setup downloads about 6.8 GiB and creates an 80 GiB sparse Windows VM.")
        print("A valid Windows 11 Pro license is required. No activation license is included.")
        print("Read Microsoft's terms: https://www.microsoft.com/useterms")
        print("The guest has network access. VM isolation does not guarantee host or LAN safety.")
        answer = input("Do you accept the applicable Windows license terms and want to continue? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            raise ValueError("Cancelled; no download or VM creation performed.")
    firmware = UTM / "Contents/Resources/qemu/edk2-arm-secure-vars.fd"
    if not firmware.is_file():
        raise ValueError(f"UTM Secure Boot template is missing: {firmware}")
    destination = args.home.expanduser().resolve()
    if destination.exists():
        refresh_seed(destination)
        return
    iso = acquire_iso(args)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    bundle = destination / f"{NAME}.utm"
    data = bundle / "Data"
    data.mkdir(parents=True, mode=0o700)
    vm_id = str(uuid.uuid4()).upper()
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
    write_seed(seed, data)
    (destination / "vm-id").write_text(vm_id + "\n")
    print(f"VM prepared: {bundle}\nCredentials: {destination / 'credentials.json'}")
    start_setup_vm(bundle, vm_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "audit", "start"))
    parser.add_argument("--home", type=Path, default=DEFAULT_HOME)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--windows-iso", type=Path, help="Use local media instead of downloading")
    source.add_argument("--windows-url", help="Override the pinned HTTPS URL; requires --windows-sha256")
    parser.add_argument("--windows-sha256")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
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
                vm_id = utm_id(config["Information"]["UUID"])
                run([str(UTM / "Contents/MacOS/utmctl"), "start", vm_id])
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
