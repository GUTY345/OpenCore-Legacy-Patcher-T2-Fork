#!/usr/bin/env python3
"""
Inspect and optionally patch a staged macOS Tahoe installer UpdateBundle.

This is intentionally conservative:
- It only targets staged Tahoe 26 install data.
- It only uses identities already present in the staged BuildManifest.
- It refuses to invent serials, board IDs, paths, hashes, or mtree values.
- It defaults to dry-run unless --apply is passed.
"""

from __future__ import annotations

import argparse
import copy
import plistlib
import shutil
import subprocess
from pathlib import Path


TARGET_PRODUCT_TYPE = "MacBookPro16,4"
TARGET_HARDWARE_MODEL = "J215AP"
TARGET_DEVICE_CLASS = "MacBookPro"
TARGET_BOARD_ID = "j215ap"
NATIVE_PRODUCT_TYPE = "MacBookPro15,1"
NATIVE_HARDWARE_MODEL = "J680AP"
NATIVE_BOARD_ID = "Mac-937A206F2EE63C01"
NATIVE_DEVICE_CLASS = "j680ap"
TAHOE_MAJOR = "26."
MSU_VARIANTS = ("Customer Software Update", "macOS Customer Software Update")
LOG_FATAL_PATTERNS = (
    "Operation: OSIMSUInstallElement failed",
    "com.apple.osinstall:-81 > NSPOSIXErrorDomain:2",
    "Failed to get paths for system root hash/mtree manifest",
    "Operation: Install Mobile Software Update failed",
    "Error Domain=com.apple.osinstall Code=-81",
    "Removing incomplete system volume",
)
LOG_FAILURE_MARKERS = (
    "------- Install Failed -------",
)
LOG_IDENTITY_WARN_PATTERNS = (
    "AKAnisetteError",
    "AKAttestationErrorDomain",
    "AKAuthenticationError",
    "DeviceIdentity not available",
    "Failed to get localUserUUID",
    "No Anisette for you today",
    "Failed to get bridge device",
    "Failed to find incompatible apps list",
)


def _load_plist(path: Path) -> dict:
    with path.open("rb") as plist_file:
        return plistlib.load(plist_file)


def _save_plist(path: Path, data: dict) -> None:
    original_mode = path.stat().st_mode
    temporary_write = not path.exists() or not (original_mode & 0o200)
    if temporary_write:
        path.chmod(original_mode | 0o200)
    try:
        with path.open("wb") as plist_file:
            plistlib.dump(data, plist_file, sort_keys=False)
    finally:
        if temporary_write and path.exists():
            path.chmod(original_mode)


def _backup(path: Path) -> Path:
    backup = path.with_name(f"{path.name}.oclp-tahoe-stage2-backup")
    if not backup.exists():
        shutil.copy2(path, backup)
    return backup


def _candidate_roots(paths: list[str]) -> list[Path]:
    roots: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if path.is_dir():
            roots.append(path)
        install_data = path / "macOS Install Data"
        if install_data.is_dir():
            roots.append(install_data)
    for volume in Path("/Volumes").glob("*"):
        install_data = volume / "macOS Install Data"
        if install_data.is_dir():
            roots.append(install_data)

    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        resolved = str(root)
        if resolved not in seen:
            deduped.append(root)
            seen.add(resolved)
    return deduped


def _visible_volume_summary() -> list[str]:
    summaries: list[str] = []
    for volume in sorted(Path("/Volumes").glob("*")):
        try:
            if volume.is_symlink():
                continue
            install_data = volume / "macOS Install Data"
            suffix = " (has macOS Install Data)" if install_data.is_dir() else ""
            summaries.append(f"{volume}{suffix}")
        except OSError:
            continue
    return summaries


def _candidate_log_paths(paths: list[str]) -> list[Path]:
    candidates: list[Path] = []
    explicit_paths = [Path(item).expanduser() for item in paths]
    search_roots = explicit_paths if explicit_paths else [Path("/Volumes")]

    for root in search_roots:
        if root.is_file():
            candidates.append(root)
            continue
        if not root.exists() or not root.is_dir():
            continue
        for name in (
            "macOS Install Data/ia.log",
            "macOS Install Data/install.log",
            "install-log-latest.log",
        ):
            candidate = root / name
            if candidate.exists():
                candidates.append(candidate)
        try:
            candidates.extend(root.glob("**/Installer Log*.txt"))
            candidates.extend(root.glob("**/install-log*.log"))
        except OSError:
            continue

    system_log = Path("/var/log/install.log")
    if system_log.exists():
        candidates.append(system_log)

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = str(candidate)
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(candidate)
    return deduped


def _tail_text(path: Path, byte_limit: int = 1_000_000) -> str:
    try:
        with path.open("rb") as log_file:
            log_file.seek(0, 2)
            size = log_file.tell()
            log_file.seek(max(0, size - byte_limit))
            return log_file.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _diagnose_install_logs(paths: list[str]) -> bool:
    logs = _candidate_log_paths(paths)
    printed = False
    fatal_hits: list[str] = []
    failure_markers: list[str] = []
    warning_hits: list[str] = []

    for log_path in logs:
        text = _tail_text(log_path)
        if not text:
            continue
        for line in text.splitlines():
            if any(pattern in line for pattern in LOG_FATAL_PATTERNS):
                fatal_hits.append(f"{log_path}: {line.strip()}")
            elif any(pattern in line for pattern in LOG_FAILURE_MARKERS):
                failure_markers.append(f"{log_path}: {line.strip()}")
            elif any(pattern in line for pattern in LOG_IDENTITY_WARN_PATTERNS):
                warning_hits.append(f"{log_path}: {line.strip()}")

    if fatal_hits:
        print("\nInstall log fatal indicators:")
        for item in fatal_hits[-12:]:
            print(f"  {item}")
        printed = True

    if failure_markers:
        print("\nInstall failure markers without a parsed cause:")
        for item in failure_markers[-8:]:
            print(f"  {item}")
        print("  Note: a failure marker proves the installer stopped, but it does not identify the cause by itself.")
        printed = True

    if warning_hits:
        print("\nInstall log identity/network warnings:")
        for item in warning_hits[-12:]:
            print(f"  {item}")
        print(
            "  Note: these warnings are not treated as the fatal cause unless an OSInstaller "
            "Install Failed line ties them to the failure."
        )
        printed = True

    if not printed and logs:
        print("\nInstall log scan: no known Tahoe Stage-2 fatal indicators found in scanned logs.")
        printed = True
    elif not logs:
        print("\nInstall log scan: no installer logs found on mounted volumes or /var/log/install.log.")
        printed = True

    return bool(fatal_hits)


def _required_paths_exist(asset_data: Path, identity: dict, *, require_additional_paths: bool = True) -> tuple[bool, list[str]]:
    missing: list[str] = []
    manifest = identity.get("Manifest", {})
    for key in ("x86,SystemVolume", "x86,SystemVolumeCanonicalMetadata"):
        item = manifest.get(key)
        if not item:
            missing.append(f"{key}: missing manifest entry")
            continue
        info = item.get("Info", {})
        source_value = info.get("Path")
        if not source_value:
            missing.append(f"{key}: missing Info/Path")
            continue
        if not _resolve_existing_manifest_path(asset_data, source_value):
            missing.append(f"{key}: Path does not exist: {source_value}")

        additional_value = info.get("AdditionalManifestPath")
        if not additional_value:
            missing.append(f"{key}: missing Info/AdditionalManifestPath")
            continue
        if require_additional_paths:
            for destination in _manifest_destination_candidates(asset_data, additional_value):
                if not destination.exists():
                    missing.append(f"{key}: AdditionalManifestPath does not exist: {destination.relative_to(asset_data)}")
    return not missing, missing


def _resolve_existing_manifest_path(asset_data: Path, value: str) -> Path | None:
    for candidate in (asset_data / value, asset_data / "boot" / value):
        if candidate.exists():
            return candidate
    return None


def _manifest_destination_candidates(asset_data: Path, value: str) -> list[Path]:
    candidates: list[Path] = []
    for candidate in (asset_data / value, asset_data / "boot" / value):
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _copy_manifest_if_needed(source: Path, destination: Path, asset_data: Path, apply: bool) -> list[str]:
    messages: list[str] = []
    if destination.exists():
        if destination.read_bytes() == source.read_bytes():
            messages.append(f"Additional manifest already exists and matches: {destination.relative_to(asset_data)}")
            return messages
        raise RuntimeError(
            "Refusing materialize patch: destination already exists with different content: "
            f"{destination}"
        )

    messages.append(f"Materialize {destination.relative_to(asset_data)} from {source.relative_to(asset_data)}")
    if apply:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        messages.append(f"Applied additional manifest copy: {destination}")
    return messages


def _identity_info(identity: dict) -> dict:
    info = identity.get("Info", {})
    return {
        "variant": info.get("Variant"),
        "device_class": info.get("DeviceClass"),
        "product_type": info.get("Ap,ProductType"),
    }


def _read_host_platform_identity() -> dict[str, str]:
    try:
        output = subprocess.run(
            ["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        ).stdout
    except OSError:
        return {}

    identity: dict[str, str] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        for key in ("model", "board-id", "bridge-model"):
            prefix = f'"{key}" = '
            if not line.startswith(prefix):
                continue
            value = line[len(prefix):].strip()
            if value.startswith("<\"") and value.endswith("\">"):
                value = value[2:-2]
            elif value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            identity[key] = value
    return identity


def _verified_native_device_class() -> str | None:
    identity = _read_host_platform_identity()
    expected = {
        "model": NATIVE_PRODUCT_TYPE,
        "board-id": NATIVE_BOARD_ID,
        "bridge-model": NATIVE_HARDWARE_MODEL,
    }
    if all(identity.get(key) == value for key, value in expected.items()):
        return NATIVE_DEVICE_CLASS
    return None


def _find_j215_install_identity(asset_data: Path, manifest: dict, *, require_additional_paths: bool = True) -> dict | None:
    for identity in manifest.get("BuildIdentities", []):
        info = _identity_info(identity)
        if info["variant"] != "CustomerInstall":
            continue
        if info["device_class"] != TARGET_BOARD_ID:
            continue
        ok, _missing = _required_paths_exist(asset_data, identity, require_additional_paths=require_additional_paths)
        if ok:
            return identity
    return None


def _has_msu_identity(asset_data: Path, manifest: dict, device_class: str) -> bool:
    for identity in manifest.get("BuildIdentities", []):
        info = _identity_info(identity)
        if info["variant"] not in MSU_VARIANTS:
            continue
        if info["device_class"] != device_class:
            continue
        ok, _missing = _required_paths_exist(asset_data, identity)
        if ok:
            return True
    return False


def _materialize_additional_manifests(asset_data: Path, identity: dict, apply: bool) -> list[str]:
    messages: list[str] = []
    manifest = identity.get("Manifest", {})
    for key in ("x86,SystemVolume", "x86,SystemVolumeCanonicalMetadata"):
        item = manifest.get(key)
        if not item:
            raise RuntimeError(f"Refusing materialize patch: {key} is missing from source identity.")
        info = item.get("Info", {})
        source_value = info.get("Path")
        destination_value = info.get("AdditionalManifestPath")
        if not source_value or not destination_value:
            raise RuntimeError(f"Refusing materialize patch: {key} lacks Path or AdditionalManifestPath.")

        source = _resolve_existing_manifest_path(asset_data, source_value)
        if not source:
            raise RuntimeError(f"Refusing materialize patch: source manifest does not exist: {source_value}")

        for destination in _manifest_destination_candidates(asset_data, destination_value):
            messages.extend(_copy_manifest_if_needed(source, destination, asset_data, apply))
    return messages


def _bootcache_destination_for(asset_data: Path, object_name: str) -> Path | None:
    bootcaches_path = asset_data / "boot" / "usr" / "standalone" / "bootcaches.plist"
    if not bootcaches_path.exists():
        return None

    bootcaches = _load_plist(bootcaches_path)
    boot_objects = bootcaches.get("bless2", {}).get("BootObjects", {})
    if not isinstance(boot_objects, dict):
        return None

    entry = boot_objects.get(object_name)
    if not isinstance(entry, dict):
        return None

    destination = entry.get("DestinationPath")
    if not isinstance(destination, str) or not destination.startswith("./"):
        return None

    return asset_data / "boot" / destination[2:]


def _materialize_bootcache_system_volume(asset_data: Path, identity: dict, apply: bool) -> list[str]:
    messages: list[str] = []
    destination = _bootcache_destination_for(asset_data, "SystemVolume")
    if not destination:
        return ["bootcaches.plist does not request a SystemVolume destination; skipping bootcache root hash materialization."]

    manifest_item = identity.get("Manifest", {}).get("x86,SystemVolume")
    if not manifest_item:
        raise RuntimeError("Refusing bootcache root hash patch: x86,SystemVolume is missing from source identity.")

    source_value = manifest_item.get("Info", {}).get("Path")
    if not source_value:
        raise RuntimeError("Refusing bootcache root hash patch: x86,SystemVolume lacks Info/Path.")

    source = _resolve_existing_manifest_path(asset_data, source_value)
    if not source:
        raise RuntimeError(f"Refusing bootcache root hash patch: source manifest does not exist: {source_value}")

    if destination.exists():
        if destination.read_bytes() == source.read_bytes():
            return [f"bootcaches SystemVolume root hash already exists and matches: {destination}"]
        raise RuntimeError(f"Refusing bootcache root hash patch: destination already exists with different content: {destination}")

    messages.append(f"Materialize bootcaches SystemVolume root hash {destination.relative_to(asset_data)} from {source.relative_to(asset_data)}")
    if apply:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        messages.append(f"Applied bootcaches SystemVolume root hash copy: {destination}")
    return messages


def _patch_info_plist(info_path: Path, apply: bool) -> list[str]:
    info = _load_plist(info_path)
    messages: list[str] = []
    product_version = str(info.get("ProductVersion", ""))
    if not product_version.startswith(TAHOE_MAJOR):
        raise RuntimeError(f"Refusing Info.plist patch: ProductVersion is {product_version!r}, not Tahoe 26.x")

    desired = {
        "ProductType": TARGET_PRODUCT_TYPE,
        "HardwareModel": TARGET_HARDWARE_MODEL,
        "DeviceClass": TARGET_DEVICE_CLASS,
    }
    changes = {key: (info.get(key), value) for key, value in desired.items() if info.get(key) != value}
    if not changes:
        return ["Info.plist already matches MacBookPro16,4/J215AP identity."]

    for key, (old, new) in changes.items():
        messages.append(f"Info.plist: {key}: {old!r} -> {new!r}")
        info[key] = new

    if apply:
        backup = _backup(info_path)
        _save_plist(info_path, info)
        messages.append(f"Applied Info.plist patch. Backup: {backup}")
    return messages


def _patch_asset_supported_models(info_path: Path, native_device_class: str | None, apply: bool) -> list[str]:
    info = _load_plist(info_path)
    messages: list[str] = []
    properties = info.get("MobileAssetProperties")
    if not isinstance(properties, dict):
        return ["UpdateBundle Info.plist has no MobileAssetProperties; skipping supported-device fallback."]

    os_version = str(properties.get("OSVersion", ""))
    if not os_version.startswith(TAHOE_MAJOR):
        raise RuntimeError(f"Refusing supported-device patch: OSVersion is {os_version!r}, not Tahoe 26.x")

    supported = properties.get("SupportedDeviceModels")
    if not isinstance(supported, list):
        return ["UpdateBundle Info.plist has no SupportedDeviceModels array; skipping supported-device fallback."]

    desired = [TARGET_HARDWARE_MODEL, "Mac-A61BADE1FDAD7B05", TARGET_PRODUCT_TYPE]
    if native_device_class:
        desired.extend([NATIVE_HARDWARE_MODEL, NATIVE_BOARD_ID, NATIVE_PRODUCT_TYPE])

    changed = False
    existing_lower = {str(item).lower() for item in supported}
    for value in desired:
        if value.lower() in existing_lower:
            continue
        supported.append(value)
        existing_lower.add(value.lower())
        changed = True
        messages.append(f"UpdateBundle Info.plist: add SupportedDeviceModels entry {value!r}")

    if not changed:
        return ["UpdateBundle Info.plist already has required supported-device entries."]

    if apply:
        backup = _backup(info_path)
        _save_plist(info_path, info)
        messages.append(f"Applied UpdateBundle supported-device patch. Backup: {backup}")
    return messages


def _patch_msu_manifest(
    asset_data: Path,
    manifest_path: Path,
    apply: bool,
    native_device_class: str | None,
    allow_missing_additional_paths: bool,
) -> list[str]:
    manifest = _load_plist(manifest_path)
    messages: list[str] = []
    source_identity = _find_j215_install_identity(asset_data, manifest, require_additional_paths=False)
    if not source_identity:
        raise RuntimeError("Refusing MSU manifest patch: no CustomerInstall/j215ap identity with existing x86 root_hash and mtree source paths.")

    complete, missing = _required_paths_exist(asset_data, source_identity)
    if not complete and not allow_missing_additional_paths:
        joined_missing = "; ".join(missing)
        raise RuntimeError(
            "Refusing MSU manifest patch: CustomerInstall/j215ap additional manifest paths are not materialized. "
            f"Missing: {joined_missing}. Re-run with --materialize-additional-manifests."
        )

    source_info = _identity_info(source_identity)
    messages.append(
        "Found source identity: "
        f"Variant={source_info['variant']}, DeviceClass={source_info['device_class']}, ProductType={source_info['product_type']}"
    )
    if not complete:
        messages.append(
            "CustomerInstall/j215ap additional manifest files are not present yet; "
            "continuing because --materialize-additional-manifests is part of this run."
        )

    existing_variants = {
        _identity_info(identity)["variant"]
        for identity in manifest.get("BuildIdentities", [])
    }
    variants_to_add = [variant for variant in MSU_VARIANTS if variant in existing_variants]
    if not variants_to_add:
        raise RuntimeError("Refusing MSU manifest patch: this BuildManifest has no MSU variant names to mirror.")

    target_device_classes = [TARGET_BOARD_ID]
    if native_device_class and native_device_class not in target_device_classes:
        target_device_classes.append(native_device_class)

    additions: list[dict] = []
    for device_class in target_device_classes:
        if _has_msu_identity(asset_data, manifest, device_class):
            messages.append(f"BuildManifest already has a usable {device_class} MSU identity.")
            continue
        for variant in variants_to_add:
            clone = copy.deepcopy(source_identity)
            clone_info = clone.setdefault("Info", {})
            clone_info["Variant"] = variant
            clone_info["DeviceClass"] = device_class
            additions.append(clone)
            messages.append(f"BuildManifest: add cloned {device_class} identity for Variant={variant!r}")

    if apply:
        if additions:
            backup = _backup(manifest_path)
            manifest.setdefault("BuildIdentities", []).extend(additions)
            _save_plist(manifest_path, manifest)
            messages.append(f"Applied BuildManifest patch. Backup: {backup}")
        else:
            messages.append("No BuildManifest changes required.")
    return messages


def _inspect(root: Path, apply: bool, materialize_additional: bool, materialize_bootcache_system_volume: bool, patch_msu: bool) -> None:
    asset_data = root / "UpdateBundle" / "AssetData"
    info_path = asset_data / "Info.plist"
    update_bundle_info_path = root / "UpdateBundle" / "Info.plist"
    manifest_path = asset_data / "boot" / "BuildManifest.plist"
    if not info_path.exists() or not manifest_path.exists():
        return

    print(f"\nStaged install data: {root}")
    info = _load_plist(info_path)
    print(
        "Info.plist identity: "
        f"ProductVersion={info.get('ProductVersion')}, "
        f"ProductType={info.get('ProductType')}, "
        f"HardwareModel={info.get('HardwareModel')}, "
        f"DeviceClass={info.get('DeviceClass')}"
    )

    manifest = _load_plist(manifest_path)
    source_identity = _find_j215_install_identity(asset_data, manifest, require_additional_paths=False)
    native_device_class = _verified_native_device_class()
    print(f"Has CustomerInstall/j215ap x86 root_hash+mtree source identity: {bool(source_identity)}")
    if source_identity:
        complete, missing = _required_paths_exist(asset_data, source_identity)
        print(f"CustomerInstall/j215ap additional manifest paths materialized: {complete}")
        if not complete:
            for item in missing:
                print(f"  Missing source materialization: {item}")
    print(f"Has valid MSU/j215ap x86 root_hash+mtree identity: {_has_msu_identity(asset_data, manifest, TARGET_BOARD_ID)}")
    if native_device_class:
        print(f"Verified native MacBookPro15,1 bridge model fallback: {native_device_class}")
        print(f"Has valid MSU/{native_device_class} x86 root_hash+mtree identity: {_has_msu_identity(asset_data, manifest, native_device_class)}")
    else:
        print("Native MacBookPro15,1 bridge model fallback not verified on this host; skipping native fallback.")

    for message in _patch_info_plist(info_path, apply):
        print(message)
    if update_bundle_info_path.exists():
        for message in _patch_asset_supported_models(update_bundle_info_path, native_device_class, apply):
            print(message)
    if materialize_additional:
        candidate = _find_j215_install_identity(asset_data, manifest, require_additional_paths=False)
        if not candidate:
            raise RuntimeError("Refusing materialize patch: no CustomerInstall/j215ap identity with existing x86 source paths found.")
        for message in _materialize_additional_manifests(asset_data, candidate, apply):
            print(message)
    if materialize_bootcache_system_volume:
        candidate = source_identity
        if not candidate:
            raise RuntimeError("Refusing bootcache root hash patch: no CustomerInstall/j215ap identity with existing x86 source paths found.")
        for message in _materialize_bootcache_system_volume(asset_data, candidate, apply):
            print(message)
    if patch_msu:
        for message in _patch_msu_manifest(asset_data, manifest_path, apply, native_device_class, materialize_additional):
            print(message)


def main() -> None:
    parser = argparse.ArgumentParser(description="Patch staged Tahoe stage-2 installer metadata for MacBookPro15,1 testing.")
    parser.add_argument("paths", nargs="*", help="Volume, macOS Install Data, or staged target path. Defaults to /Volumes/*.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Without this, only reports planned changes.")
    parser.add_argument(
        "--diagnose-logs",
        action="store_true",
        help="Scan visible installer logs for known Tahoe Stage-2 fatal indicators and identity warnings.",
    )
    parser.add_argument(
        "--patch-msu-manifest",
        action="store_true",
        help="Experimental: clone the verified CustomerInstall/j215ap identity into existing MSU variants.",
    )
    parser.add_argument(
        "--materialize-additional-manifests",
        action="store_true",
        help="Create the usr/standalone/OS.dmg root_hash and mtree paths referenced by the j215ap identity.",
    )
    parser.add_argument(
        "--materialize-bootcache-system-volume",
        action="store_true",
        help="Create the bootcaches.plist SystemVolume root_hash.img4 destination from the verified x86 SystemVolume manifest payload.",
    )
    args = parser.parse_args()

    roots = _candidate_roots(args.paths)
    if not roots:
        print("No mounted macOS Install Data folders found.")
        print("Visible volumes:")
        for volume in _visible_volume_summary():
            print(f"  {volume}")
        print(
            "\nThis patch is intentionally staged-data only. Run it after the Tahoe installer "
            "has copied files to the target and created macOS Install Data, before booting "
            "the macOS Installer stage again."
        )
        _diagnose_install_logs(args.paths)
        raise SystemExit(1)

    touched = False
    for root in roots:
        before = touched
        _inspect(
            root,
            args.apply,
            args.materialize_additional_manifests,
            args.materialize_bootcache_system_volume,
            args.patch_msu_manifest,
        )
        touched = before or (root / "UpdateBundle" / "AssetData" / "Info.plist").exists()

    if not touched:
        _diagnose_install_logs(args.paths)
        raise SystemExit("No staged Tahoe UpdateBundle/AssetData/Info.plist found.")

    if args.diagnose_logs:
        _diagnose_install_logs(args.paths)

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to write guarded patches.")


if __name__ == "__main__":
    main()
