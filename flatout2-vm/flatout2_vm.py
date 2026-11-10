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
GAME_HELPERS = ("install-gog.cmd", "install-gog.ps1", "guest-start.cmd", "guest-start.ps1", "guest-install.ps1")
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
    child(command, "Description", "Apply privacy defaults and install ARM64 networking before OOBE")
    child(command, "Path", 'powershell.exe -NoProfile -NonInteractive -Command "'
          "$m=@(Get-PSDrive -PSProvider FileSystem | Where-Object {Test-Path ($_.Root+'flatout2-seed.tag')}); "
          "if($m.Count -ne 1){exit 10}; & ($m[0].Root+'prepare-guest.cmd'); exit $LASTEXITCODE\"")
    child(command, "WillReboot", "OnRequest")
    oobe = ET.SubElement(root, f"{{{NS}}}settings", {"pass": "oobeSystem"})
    locale = component(oobe, "Microsoft-Windows-International-Core")
    for key, value in (("InputLocale", "0409:00000409"), ("SystemLocale", "en-US"),
                       ("UILanguage", "en-US"), ("UserLocale", "en-US")):
        child(locale, key, value)
    shell = component(oobe, "Microsoft-Windows-Shell-Setup")
    child(child(shell, "OOBE"), "ProtectYourPC", "3")
    autologon = child(shell, "AutoLogon")
    child(autologon, "Enabled", "true")
    child(autologon, "Username", "Player")
    child(autologon, "LogonCount", "999")
    password = child(autologon, "Password")
    child(password, "Value", gamer_password)
    child(password, "PlainText", "true")
    accounts = child(child(shell, "UserAccounts"), "LocalAccounts")
    for name, group, password in (
        ("VMAdmin", "Administrators", admin_password),
        ("Player", "Administrators", gamer_password),
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


def retry_status(vm_id: str) -> str | None:
    """Distinguish missing registration from other status-query failures."""
    try:
        return run([str(UTM / "Contents/MacOS/utmctl"), "status", vm_id])
    except ValueError as error:
        if "Virtual machine not found" not in str(error):
            raise
        return None


def refresh_seed(destination: Path, source_dir: Path | None = None, stage_only: bool = False) -> None:
    """Refresh installer media only for a stopped VM whose disk is unpartitioned."""
    bundle = destination / f"{NAME}.utm"
    if any(p.is_symlink() for p in (destination, *destination.parents, bundle)) or any(p.is_symlink() for p in destination.rglob("*")):
        raise ValueError("Refusing setup state containing symlinks.")
    config_path = bundle / "config.plist"
    original = config_path.read_bytes()
    config = plistlib.loads(original)
    audit(config)
    vm_id = utm_id(config["Information"]["UUID"])
    status = retry_status(vm_id)
    if status is not None and status != "stopped":
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
    if status is None and not stage_only:
        # Opening a .utm bundle registers/selects it, without issuing a start.
        # Only audited, still-blank retry state is eligible for this recovery.
        if config_path.read_bytes() != original:
            raise ValueError("Configuration changed before retry registration; refusing to open the VM.")
        run(["/usr/bin/open", "-a", str(UTM), str(bundle)])
        if run([str(UTM / "Contents/MacOS/utmctl"), "status", vm_id]) != "stopped":
            raise ValueError("Retry VM was not registered and stopped. Check UTM, shut down Windows normally, then retry setup.")
        with (data / "system.raw").open("rb") as disk:
            registered_header = disk.read(1024 * 1024)
        if registered_header != header or config_path.read_bytes() != original:
            raise ValueError("VM disk or configuration changed during retry registration; refusing unattended setup.")
        status = "stopped"
    attached = [d for d in config["Drive"] if d["ImageName"] == "game.iso"]
    if attached and (len(attached) != 1 or attached[0]["ImageType"] != "CD"
                     or attached[0]["Interface"] != "USB" or not attached[0]["ReadOnly"]):
        raise ValueError("Unrecognized game.iso drive; preserve this home and use a fresh --home directory.")
    media = data / "game.iso"
    if media.exists():
        # A previously published ISO may survive a failed config reload. Recheck it,
        # never overwrite it or infer success from guest files.
        verify_game_media(media)
    else:
        build_game_media(choose_installer(source_dir), media)
    if not attached:
        config["Drive"].append(game_drive())
    audit(config)
    if retry_status(vm_id) != status or config_path.read_bytes() != original:
        raise ValueError("VM started or configuration changed during media preparation; refusing setup retry.")
    prepare_windows_media(data / "windows.iso")
    write_seed(seed, data)
    with (data / "system.raw").open("rb") as disk:
        current_header = disk.read(1024 * 1024)
    if current_header != header or retry_status(vm_id) != status or config_path.read_bytes() != original:
        raise ValueError("VM disk, state, or configuration changed during setup retry; refusing to boot unattended media.")
    publish_configuration(bundle, vm_id, original, config, reload=not stage_only)
    if stage_only:
        setup_guidance(stage_only=True)
        return
    start_setup_vm(bundle, vm_id)
    setup_guidance()


def write_seed(seed: Path, data: Path) -> None:
    (seed / "startup.nsh").unlink(missing_ok=True)
    (seed / "flatout2-seed.tag").write_text("portable-setups FlatOut 2 installation media\n")
    shutil.copyfile(Path(__file__).with_name("install-network.cmd"), seed / "install-network.cmd")
    shutil.copyfile(Path(__file__).with_name("configure-privacy.cmd"), seed / "configure-privacy.cmd")
    shutil.copyfile(Path(__file__).with_name("prepare-guest.cmd"), seed / "prepare-guest.cmd")
    shutil.copyfile(Path(__file__).with_name("guest-status.cmd"), seed / "guest-status.cmd")
    shutil.copyfile(Path(__file__).with_name("guest-setup.ps1"), seed / "guest-setup.ps1")
    for name in GAME_HELPERS:
        shutil.copyfile(Path(__file__).with_name(name), seed / name)
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
    destination = args.home.expanduser().absolute()
    if any(p.is_symlink() for p in (destination, *destination.parents)):
        raise ValueError("Refusing setup state containing symlinks.")
    if destination.exists():
        disk_path = destination / f"{NAME}.utm/Data/system.raw"
        if disk_path.is_file() and not disk_path.is_symlink():
            with disk_path.open("rb") as disk:
                header = disk.read(8192)
            if header[512:520] == b"EFI PART" or header[4096:4104] == b"EFI PART":
                if getattr(args, "stage_only", False):
                    raise ValueError("--stage-only requires a blank setup disk; installed GPT guests must not be restaged.")
                args.action = "install-game"
                game_media(args)
                return
        refresh_seed(destination, args.source_dir, stage_only=getattr(args, "stage_only", False))
        return
    # Both Windows and game license consent precede downloads and VM creation.
    installer = choose_installer(args.source_dir)
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
    config = first_boot_configuration(config, installer, data)
    (bundle / "config.plist").write_bytes(plistlib.dumps(config))
    (destination / "vm-id").write_text(vm_id + "\n")
    print(f"VM prepared: {bundle}\nCredentials: {destination / 'credentials.json'}")
    if getattr(args, "stage_only", False):
        setup_guidance(stage_only=True)
        return
    start_setup_vm(bundle, vm_id)
    setup_guidance()


def setup_guidance(stage_only: bool = False) -> None:
    guide = Path(__file__).resolve().parent / "docs/cleanup.md"
    if stage_only:
        print("VM prepared, not started (--stage-only). No bundle open, registration, or start was requested.\n"
              "Windows and game installation are not complete.\n"
              f"Shutdown, installer-media cleanup, and permanent removal guide: {guide}\n"
              "Permanent VM deletion loses game saves and Windows state. Preserve the stopped VM first.")
        return
    print("Windows setup has started; game installation is not complete. At Player login, the guest helper\n"
          "attempts installation and asks for normal Windows Yes/No UAC consent. Check its result in Windows.\n"
          "After denial or failure, use the guest Retry action; the host cannot verify success.\n"
          f"Shutdown, installer-media cleanup, and permanent removal guide: {guide}\n"
          "Permanent VM deletion loses game saves and Windows state. Preserve the stopped VM first.")


def game_drive() -> dict[str, Any]:
    return {"ImageName": "game.iso", "ImageType": "CD", "Interface": "USB",
            "InterfaceVersion": 1, "Identifier": str(uuid.uuid4()), "ReadOnly": True}


def first_boot_configuration(config: dict[str, Any], installer: Path, data: Path) -> dict[str, Any]:
    """Construct fresh-VM media before registration, separate from installed-GPT attachment."""
    if any(d["ImageName"] == "game.iso" for d in config["Drive"]):
        raise ValueError("Fresh configuration already contains game media.")
    build_game_media(installer, data / "game.iso")
    config["Drive"].append(game_drive())
    audit(config)
    return config


# The initial offline flow knows the complete file layout for this GOG build only.
GOG_INSTALLER = "setup_flatout_2_1.0_(26697).exe"
GOG_PARTS = (GOG_INSTALLER, "setup_flatout_2_1.0_(26697)-1.bin")
GOG_PATTERN = re.compile(r"setup_flatout_2_.+\.exe", re.IGNORECASE)


def installer_files(installer: Path) -> list[Path]:
    if any(path.is_symlink() for path in installer.absolute().parents):
        raise ValueError("Installer directory must not contain symlinks.")
    if installer.name != GOG_INSTALLER:
        raise ValueError(f"Unsupported GOG installer build: {installer.name}. Expected {GOG_INSTALLER}.")
    files = [installer.parent / name for name in GOG_PARTS]
    for path in files:
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing, empty, or symlinked installer part: {path}")
    extras = set(installer.parent.glob(installer.stem + "-*.bin")) - set(files)
    if extras:
        raise ValueError("Unexpected BIN parts for this supported build; select a clean installer folder.")
    return files


def find_installers(roots: list[Path]) -> list[Path]:
    candidates: list[Path] = []
    visited = 0
    for root in roots:
        root = root.expanduser()
        if root.is_symlink() or not root.is_dir():
            raise ValueError(f"Source must be an existing non-symlink directory: {root}")
        for directory, children, files in os.walk(root, followlinks=False):
            visited += 1
            if visited > 5000:
                raise ValueError("Source scan too large; select a more specific installer directory.")
            parent = Path(directory)
            depth = len(parent.relative_to(root).parts)
            children[:] = sorted(name for name in children if depth < 3 and not name.startswith(".")
                                 and name != "System Volume Information" and not (parent / name).is_symlink())
            for name in files:
                path = parent / name
                if GOG_PATTERN.fullmatch(name) and not path.is_symlink() and path.is_file():
                    candidates.append(path)
    return sorted(set(candidates))


def usb_roots() -> list[Path]:
    listing = plistlib.loads(run(["/usr/sbin/diskutil", "list", "-plist", "external", "physical"]).encode())
    roots: list[Path] = []

    def visit(entry: dict[str, Any]) -> None:
        mount = entry.get("MountPoint")
        if mount:
            info = plistlib.loads(run(["/usr/sbin/diskutil", "info", "-plist", mount]).encode())
            if info.get("BusProtocol") == "USB" and not info.get("Internal", True):
                roots.append(Path(mount))
        for child in entry.get("Partitions", []):
            visit(child)

    for entry in listing.get("AllDisksAndPartitions", []):
        visit(entry)
    return roots


def choose_installer(source: Path | None) -> Path:
    if source is None:
        print("Game source:\n  1. Detect GOG offline installer on USB\n  2. Select installer folder")
        choice = input("Choose [1-2] (Enter cancels): ").strip()
        if choice == "2":
            source = Path(input("Installer source folder (paste its path, without surrounding quotes): ").strip())
        elif choice != "1":
            raise ValueError("Cancelled; choose a listed source option.")
    candidates = find_installers([source] if source is not None else usb_roots())
    if not candidates:
        raise ValueError("No FlatOut 2 GOG offline installer found within three subfolders. Use --source-dir with its folder.")
    for index, path in enumerate(candidates, 1):
        print(f"  {index}. {path}")
    if len(candidates) == 1:
        if input("Use this installer and accept its applicable game license terms? [y/N] ").strip().lower() not in ("y", "yes"):
            raise ValueError("Cancelled; no game files copied.")
        selected = candidates[0]
    else:
        answer = input("Select installer number (selection accepts its applicable game license terms; Enter cancels): ").strip()
        if not answer.isdecimal() or not 1 <= int(answer) <= len(candidates):
            raise ValueError("Cancelled; no valid installer selected.")
        selected = candidates[int(answer) - 1]
    installer_files(selected)
    return selected


def file_hash(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def build_game_media(installer: Path, output: Path) -> None:
    files = installer_files(installer)
    if output.exists() or output.is_symlink():
        raise ValueError("Game media destination already exists; refusing overwrite.")
    with tempfile.TemporaryDirectory(prefix="flatout2-game-", dir=output.parent) as directory:
        stage = Path(directory) / "media"
        stage.mkdir()
        manifest: list[dict[str, Any]] = []
        for source in files:
            print(f"Copying and verifying {source.name} ...", flush=True)
            expected = file_hash(source)
            target = stage / source.name
            shutil.copyfile(source, target)
            if target.stat().st_size != source.stat().st_size or file_hash(target) != expected:
                raise ValueError(f"Installer copy checksum mismatch: {source.name}")
            manifest.append({"name": source.name, "size": target.stat().st_size, "sha256": expected})
        (stage / "game-media.json").write_text(json.dumps({"schema": 1, "files": manifest}, indent=2) + "\n")
        for name in GAME_HELPERS:
            shutil.copyfile(Path(__file__).with_name(name), stage / name)
        temporary = Path(directory) / "game.iso"
        run(["/usr/bin/hdiutil", "makehybrid", "-iso", "-joliet", "-default-volume-name",
             "FLATOUTGAME", "-o", str(temporary), str(stage)])
        mount = Path(directory) / "verify"
        mount.mkdir()
        run(["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(temporary)])
        try:
            if {p.name for p in mount.iterdir()} != {*GOG_PARTS, "game-media.json", *GAME_HELPERS}:
                raise ValueError("Built game ISO has unexpected or missing files.")
            for entry in manifest:
                if ((mount / entry["name"]).stat().st_size != entry["size"]
                        or file_hash(mount / entry["name"]) != entry["sha256"]):
                    raise ValueError("Built game ISO failed readback verification.")
            for name in ("game-media.json", *GAME_HELPERS):
                if (mount / name).read_bytes() != (stage / name).read_bytes():
                    raise ValueError("Built game ISO helper/manifest failed verification.")
        finally:
            run(["/usr/bin/hdiutil", "detach", str(mount)])
        os.replace(temporary, output)
        source_released()


def source_released() -> None:
    print("Verified game ISO published. The source folder is no longer needed; you may eject the external\n"
          "drive in Finder. Game installation is not complete; check the result inside Windows.")


def verify_game_media(media: Path) -> None:
    """Validate retained retry media against its payload manifest and current helper contract."""
    if media.is_symlink() or not media.is_file():
        raise ValueError("Retained game ISO is not a regular file; use a fresh --home directory.")
    with tempfile.TemporaryDirectory(prefix="flatout2-retry-") as directory:
        mount = Path(directory)
        run(["/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(media)])
        try:
            if {p.name for p in mount.iterdir()} != {*GOG_PARTS, "game-media.json", *GAME_HELPERS}:
                raise ValueError("Retained game ISO is outdated or unrecognized; preserve it and use a fresh --home directory.")
            manifest = json.loads((mount / "game-media.json").read_text())
            entries = manifest["files"]
            if manifest["schema"] != 1 or [entry["name"] for entry in entries] != list(GOG_PARTS):
                raise ValueError("Retained game ISO has an unrecognized manifest.")
            for entry in entries:
                path = mount / entry["name"]
                if path.stat().st_size != entry["size"] or file_hash(path) != entry["sha256"]:
                    raise ValueError("Retained game ISO payload failed readback verification.")
            for name in GAME_HELPERS:
                if (mount / name).read_bytes() != Path(__file__).with_name(name).read_bytes():
                    raise ValueError("Retained game ISO helpers are outdated; preserve it and use a fresh --home directory.")
        finally:
            run(["/usr/bin/hdiutil", "detach", str(mount)])
    source_released()


def reload_vm(vm_id: str) -> None:
    # Pass the UUID as data, never interpolate media paths into AppleScript.
    run(["/usr/bin/osascript", "-e", 'on run argv\ntell application "UTM" to reload configuration '
         '(first virtual machine whose id is (item 1 of argv))\nend run', vm_id])


def publish_configuration(bundle: Path, vm_id: str, original: bytes, config: dict[str, Any], reload: bool = True) -> None:
    """Restore original config on reload failure, retaining completed media as evidence."""
    temporary = bundle / f"config-{uuid.uuid4()}.plist"
    try:
        temporary.write_bytes(plistlib.dumps(config))
        os.replace(temporary, bundle / "config.plist")
        if reload:
            reload_vm(vm_id)
    except Exception:
        temporary.write_bytes(original)
        os.replace(temporary, bundle / "config.plist")
        raise
    finally:
        temporary.unlink(missing_ok=True)


def game_media(args: argparse.Namespace) -> None:
    destination = args.home.expanduser().absolute()
    bundle = destination / f"{NAME}.utm"
    if any(path.is_symlink() for path in (bundle, *bundle.parents)) or any(p.is_symlink() for p in bundle.rglob("*")):
        raise ValueError("Refusing VM state containing symlinks.")
    config_path = bundle / "config.plist"
    original = config_path.read_bytes()
    config = plistlib.loads(original)
    audit(config)
    vm_id = utm_id(config["Information"]["UUID"])
    if run([str(UTM / "Contents/MacOS/utmctl"), "status", vm_id]) != "stopped":
        raise ValueError("Shut down Windows normally, then rerun this command. No VM files were changed.")
    data = bundle / "Data"
    with (data / "system.raw").open("rb") as disk:
        header = disk.read(8192)
    if header[512:520] != b"EFI PART" and header[4096:4104] != b"EFI PART":
        raise ValueError("No installed GPT guest disk found. Finish Windows setup first; its disk will not be changed.")
    attached = [d for d in config["Drive"] if d["ImageName"] == "game.iso"]
    media = data / "game.iso"
    if media.exists() and not media.is_file():
        raise ValueError("Game media backing path is not a regular file; refusing to change it.")
    if attached and (len(attached) != 1 or attached[0]["ImageType"] != "CD"
                     or attached[0]["Interface"] != "USB" or not attached[0]["ReadOnly"]):
        raise ValueError("Unrecognized game.iso drive; refusing to detach or remove its backing file.")
    if args.action == "detach-game":
        if not attached:
            if not media.exists():
                print("No game CD is attached and no local game ISO exists.")
                return
            print(f"Unattached game ISO found: {media}. Its contents are unrecognized and will not be deleted.")
            answer = input("Quarantine this ISO in a unique bundle-local backup so installation can be retried? [y/N] ")
            if answer.strip().lower() not in ("y", "yes"):
                raise ValueError("Cancelled; unattached game ISO preserved unchanged.")
            if run([str(UTM / "Contents/MacOS/utmctl"), "status", vm_id]) != "stopped" or config_path.read_bytes() != original:
                raise ValueError("VM started or configuration changed during media preparation; refusing quarantine.")
            backup = data / f"game-orphan-{uuid.uuid4()}.iso"
            while backup.exists() or backup.is_symlink():
                backup = data / f"game-orphan-{uuid.uuid4()}.iso"
            media.rename(backup)
            print(f"Unattached game ISO quarantined: {backup}. No configuration or guest disk changed; installation can be retried.")
            return
        config["Drive"] = [d for d in config["Drive"] if d["ImageName"] != "game.iso"]
    else:
        if not attached and media.exists():
            raise ValueError("Unattached game ISO exists. Run detach-game while stopped to confirm quarantine before retrying.")
        if attached:
            raise ValueError("Game media already exists. Use it inside Windows, or run detach-game while stopped before retrying.")
        installer = choose_installer(args.source_dir)
        build_game_media(installer, media)
        config["Drive"].append(game_drive())
    audit(config)
    if run([str(UTM / "Contents/MacOS/utmctl"), "status", vm_id]) != "stopped" or config_path.read_bytes() != original:
        raise ValueError("VM started or configuration changed during media preparation; refusing configuration update.")
    # Only the configuration is replaced; setup CDs and the guest disk are untouched.
    publish_configuration(bundle, vm_id, original, config)
    if args.action == "detach-game":
        media.unlink(missing_ok=True)
        print("Game CD detached and its local ISO removed; source files and guest installation preserved.")
        return
    run([str(UTM / "Contents/MacOS/utmctl"), "start", vm_id])
    print("Windows started with the read-only FLATOUTGAME CD. Updated guests attempt setup once at Player login.\n"
          "For an older guest or an explicit retry, open that CD and run install-gog.cmd.\n"
          "Approve the Windows Yes/No elevation prompt. New VMs use an administrator Player account.\n"
          "An older standard-Player VM needs an administrator migration before this password-free flow.\n"
          "Do not run the GOG EXE directly.\n"
          "The helper checks hashes/signature, installs silently, and reports its result inside Windows.\n"
          "Then use the public FlatOut 2 shortcut as Player. This host command cannot observe installation success.\n"
          "After success, shut down Windows and run detach-game to remove temporary installer media.")


def play(bundle: Path, config: dict[str, Any]) -> None:
    """Boot only a stopped VM; never send guest input or inspect guest receipts."""
    audit(config)
    vm_id = utm_id(config["Information"]["UUID"])
    try:
        status = run([str(UTM / "Contents/MacOS/utmctl"), "status", vm_id])
    except ValueError as error:
        raise ValueError("Cannot find/query this VM in UTM. Open its .utm bundle in UTM to register it, "
                         "then retry Play. No media changed.") from error
    if status == "stopped":
        run([str(UTM / "Contents/MacOS/utmctl"), "start", vm_id])
        print("Windows started. At Player login, the guest dispatcher handles validated game launch or setup.\n"
              "This host command cannot confirm installation or game launch; check Windows for the result.")
    elif status == "started":
        # UTM's sdef has no VM 'show' command. Opening the registered bundle selects
        # it through UTM's supported file-open handler; no removed URL commands/input.
        run(["/usr/bin/open", "-a", str(UTM), str(bundle)])
        print("Windows is already running; UTM brought forward with this VM selected.\n"
              "If needed, open its display in UTM. Use the FlatOut 2 guest shortcut as Player.\n"
              "No game launch was requested by the host. Use the guest Retry action after setup failure.")
    elif status in ("paused", "suspended"):
        raise ValueError("VM is paused/suspended. Resume it manually in UTM, then shut down Windows normally "
                         "before a cold-start Play, or use its guest shortcut after resuming. No media changed.")
    else:
        raise ValueError(f"VM state is {status!r}. Wait for UTM to finish the transition, then retry Play. No media changed.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "audit", "start", "install-game", "detach-game"))
    parser.add_argument("--source-dir", type=Path, help="Directory containing the GOG offline installer")
    parser.add_argument("--home", type=Path, default=DEFAULT_HOME)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--windows-iso", type=Path, help="Use local media instead of downloading")
    source.add_argument("--windows-url", help="Override the pinned HTTPS URL; requires --windows-sha256")
    parser.add_argument("--windows-sha256")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--accept-windows-license", action="store_true")
    parser.add_argument("--stage-only", action="store_true", help="Prepare setup media without opening, registering, or starting the VM")
    args = parser.parse_args()
    if args.stage_only and args.action != "setup":
        parser.error("--stage-only is supported only with setup.")
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or later is required.")
    os.umask(0o077)
    try:
        if args.action in ("install-game", "detach-game"):
            check_host()
            game_media(args)
        elif args.action == "setup":
            setup(args)
        else:
            bundle = args.home.expanduser() / f"{NAME}.utm"
            if not (bundle / "config.plist").is_file():
                raise ValueError(f"VM is missing at {bundle}. Run setup first, or select the correct --home.")
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
                play(bundle, config)
    except (OSError, ValueError, KeyError, TypeError, EOFError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
