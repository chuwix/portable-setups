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
import struct
import tempfile
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
EFI_PROMPT_SHA256 = "0be1d959458b3a83ba84c7f58b1f4d0ca080abccecd53eae157c8d2f9bff2f98"
EFI_NOPROMPT_SHA256 = "70eedc9e6a37f7ac688ed9b3eefe48ec26156e48cda669e520ccaad44130d113"
DRIVERS_URL = "https://github.com/utmapp/qemu/releases/download/v10.0.2-utm/utm-guest-tools-0.1.271.iso"
DRIVERS_SHA256 = "65b6a69b392ee01dd314c10f3dad9ebbf9c4160be43f5f0dd6bb715944d9095b"
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
    return download_iso(url, expected, args.cache, "Windows image (about 6.8 GiB)")


def download_iso(url: str, expected: str, cache: Path, label: str) -> Path:
    cache = cache.expanduser().resolve()
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    iso = cache / f"{expected.lower()}.iso"
    if iso.exists():
        if iso.is_symlink() or not iso.is_file():
            raise ValueError("Cached ISO must be a regular file, not a symlink.")
        verify_iso(iso, expected)
        print(f"Using verified cached {label}: {iso}")
        return iso
    # Each transfer owns its temporary file; failed downloads are not trusted or reused.
    partial = cache / f"{expected.lower()}.{uuid.uuid4()}.partial"
    try:
        print(f"Downloading pinned {label}; verifying SHA256 afterward.", flush=True)
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


def stage_network_driver(seed: Path, media: Path) -> None:
    """Copy only NetKVM ARM64 files; Windows enforces their catalog signature."""
    verify_iso(media, DRIVERS_SHA256)
    with tempfile.TemporaryDirectory(prefix="flatout2-drivers-") as directory:
        mount = Path(directory) / "drivers"
        mount.mkdir()
        run(["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(media)])
        try:
            source = mount / "Drivers/NetKVM/w11/ARM64"
            inf = (source / "netkvm.inf").read_text()
            if "NTARM64" not in inf or "CatalogFile = netkvm.cat" not in inf:
                raise ValueError("Unexpected NetKVM ARM64 driver manifest.")
            target = seed / "drivers/NetKVM"
            target.mkdir(parents=True, exist_ok=True)
            for name in ("netkvm.inf", "netkvm.sys", "netkvm.cat", "netkvmp.exe", "netkvmco.exe", "netkvmco.dll"):
                shutil.copyfile(source / name, target / name)
            shutil.copyfile(mount / "virtio-win_license.txt", target / "virtio-win_license.txt")
        finally:
            run(["/usr/bin/hdiutil", "detach", str(mount)])


def patch_boot_image(iso: Path, prompt: bytes, noprompt: bytes) -> None:
    """Replace only the validated default EFI image, never the cached source ISO."""
    if (hashlib.sha256(prompt).hexdigest() != EFI_PROMPT_SHA256
            or hashlib.sha256(noprompt).hexdigest() != EFI_NOPROMPT_SHA256
            or len(prompt) != len(noprompt)):
        raise ValueError("Unrecognized Microsoft EFI images; refusing to modify installation media.")
    with iso.open("r+b") as output:
        boot_records = []
        for sector in range(16, 80):
            output.seek(sector * 2048)
            record = output.read(2048)
            if len(record) != 2048 or record[1:7] != b"CD001\x01":
                raise ValueError("Invalid ISO volume descriptor.")
            if record[0] == 255:
                break
            if record[0] == 0 and record[7:39].rstrip(b"\0") == b"EL TORITO SPECIFICATION":
                boot_records.append(struct.unpack_from("<I", record, 71)[0])
        else:
            raise ValueError("Missing ISO descriptor terminator.")
        if len(boot_records) != 1:
            raise ValueError("Expected exactly one El Torito catalog.")
        output.seek(boot_records[0] * 2048)
        catalog = output.read(2048)
        if (len(catalog) != 2048 or catalog[:2] != b"\x01\xef"
                or catalog[30:32] != b"\x55\xaa"
                or sum(struct.unpack("<16H", catalog[:32])) % 65536
                or catalog[32:34] != b"\x88\x00"
                or any(catalog[64:])):
            raise ValueError("Unexpected EFI boot catalog; refusing to patch.")
        size = struct.unpack_from("<H", catalog, 38)[0] * 512
        offset = struct.unpack_from("<I", catalog, 40)[0] * 2048
        if size != len(prompt) or offset < 80 * 2048:
            raise ValueError("Unexpected EFI boot image extent.")
        output.seek(offset)
        current = output.read(size)
        if current == noprompt:
            return
        if current != prompt:
            raise ValueError("Default EFI image does not match Microsoft's prompt image.")
        output.seek(offset)
        output.write(noprompt)
        output.flush()
        os.fsync(output.fileno())
        output.seek(offset)
        if output.read(size) != noprompt:
            raise ValueError("EFI image write verification failed.")


def prepare_windows_media(iso: Path) -> None:
    """Read Microsoft's embedded images via a read-only, private mount."""
    with tempfile.TemporaryDirectory(prefix="flatout2-media-") as directory:
        mount = Path(directory) / "windows"
        mount.mkdir()
        run(["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(iso)])
        try:
            boot = mount / "efi/microsoft/boot"
            prompt = (boot / "efisys.bin").read_bytes()
            noprompt = (boot / "efisys_noprompt.bin").read_bytes()
        finally:
            run(["/usr/bin/hdiutil", "detach", str(mount)])
    patch_boot_image(iso, prompt, noprompt)
    print("VM-local Windows media now uses Microsoft's verified no-prompt EFI image.")


def configuration(vm_id: str) -> dict[str, Any]:
    """UTM v5.0.8's version-4 plist schema; all media stays in the VM bundle."""
    drives = []
    for filename, image_type, interface in (
        ("system.raw", "Disk", "NVMe"),
        ("windows.iso", "CD", "USB"),
        ("seed.iso", "CD", "USB"),
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
    specialize = ET.SubElement(root, f"{{{NS}}}settings", {"pass": "specialize"})
    deployment = component(specialize, "Microsoft-Windows-Deployment")
    command = child(child(deployment, "RunSynchronous"), "RunSynchronousCommand")
    command.set("{http://schemas.microsoft.com/WMIConfig/2002/State}action", "add")
    child(command, "Order", "1")
    child(command, "Description", "Install pinned ARM64 network driver before OOBE")
    child(command, "Path", 'powershell.exe -NoProfile -NonInteractive -Command "'
          "$m=@(Get-PSDrive -PSProvider FileSystem | Where-Object {Test-Path ($_.Root+'flatout2-seed.tag')}); "
          "if($m.Count -ne 1){exit 10}; & ($m[0].Root+'install-network.cmd'); exit $LASTEXITCODE\"")
    child(command, "WillReboot", "OnRequest")
    oobe = ET.SubElement(root, f"{{{NS}}}settings", {"pass": "oobeSystem"})
    locale = component(oobe, "Microsoft-Windows-International-Core")
    for key, value in (("InputLocale", "0409:00000409"), ("SystemLocale", "en-US"),
                       ("UILanguage", "en-US"), ("UserLocale", "en-US")):
        child(locale, key, value)
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
    if not (seed / "drivers/NetKVM/netkvm.inf").is_file():
        raise ValueError("This older setup lacks staged network drivers. Use a fresh --home directory for the updated installer.")
    prepare_windows_media(data / "windows.iso")
    write_seed(seed, data)
    start_setup_vm(bundle, vm_id)


def write_seed(seed: Path, data: Path) -> None:
    (seed / "startup.nsh").unlink(missing_ok=True)
    (seed / "flatout2-seed.tag").write_text("portable-setups FlatOut 2 installation media\n")
    shutil.copyfile(Path(__file__).with_name("install-network.cmd"), seed / "install-network.cmd")
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
    print("VM started. Windows Setup should boot without a keypress; a Shell> prompt is a failed boot test.")


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
    driver_media = download_iso(DRIVERS_URL, DRIVERS_SHA256, args.cache, "UTM driver media (about 121 MiB)")
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
    prepare_windows_media(data / "windows.iso")
    admin, player = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    credentials = {"VMAdmin": admin, "Player": player}
    (destination / "credentials.json").write_text(json.dumps(credentials, indent=2) + "\n")
    seed = destination / "seed"
    seed.mkdir(mode=0o700)
    (seed / "Autounattend.xml").write_bytes(unattended(admin, player))
    stage_network_driver(seed, driver_media)
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
