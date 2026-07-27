"""
misc.py: Class for handling Misc Patches, invocation from build.py
"""

import shutil
import logging
import binascii
import sys
import os
import subprocess
from pathlib import Path

from . import support
from .. import constants
from ..support import generate_smbios
from ..detections import device_probe
from ..datasets import (
    model_array,
    smbios_data,
    cpu_data,
    os_data
)


class PatchValidationError(Exception):
    """
    Raised when a kernel Find/Replace patch fails validation
    (e.g. Find and Replace byte lengths differ).

    Raising a dedicated exception instead of calling sys.exit() keeps the
    guardrail intact in production (BuildOpenCore aborts the build) while
    making _validate_patch unit-testable — a test can assert the exception
    is raised instead of the whole interpreter exiting.
    """
    pass


class BuildMiscellaneous:
    """
    Build Library for Miscellaneous Hardware and Software Support
    Invoke from build.py
    """

    def __init__(self, model: str, global_constants: constants.Constants, config: dict) -> None:
        self.model: str = model
        self.config: dict = config
        self.constants: constants.Constants = global_constants
        self.computer: device_probe.Computer = self.constants.computer

        self._build()

    def _ensure_nvram_path(self, uuid: str) -> None:
        """Ensure core NVRAM dictionary structures exist safely to avoid KeyErrors."""
        if "NVRAM" not in self.config:
            self.config["NVRAM"] = {}
        if "Add" not in self.config["NVRAM"]:
            self.config["NVRAM"]["Add"] = {}
        if uuid not in self.config["NVRAM"]["Add"]:
            self.config["NVRAM"]["Add"][uuid] = {}

    def _update_nvram_string(self, uuid: str, key: str, value: str) -> None:
        """Appends string flags using precise word boundaries to prevent substring collisions."""
        self._ensure_nvram_path(uuid)
        
        current_value = self.config["NVRAM"]["Add"][uuid].get(key, "")
        
        existing_tokens = set(current_value.split())
        new_tokens = value.strip().split()
        
        tokens_to_add = [t for t in new_tokens if t not in existing_tokens]
        if not tokens_to_add:
            return

        if current_value.strip():
            self.config["NVRAM"]["Add"][uuid][key] = current_value.rstrip() + " " + " ".join(tokens_to_add)
        else:
            self.config["NVRAM"]["Add"][uuid][key] = " ".join(tokens_to_add)

    def _set_nvram_value(self, uuid: str, key: str, value: any, overwrite: bool = False) -> None:
        """Sets an NVRAM variable. If overwrite is False, it only sets if the key is missing."""
        self._ensure_nvram_path(uuid)
        if overwrite or key not in self.config["NVRAM"]["Add"][uuid]:
            self.config["NVRAM"]["Add"][uuid][key] = value

    def _is_t2_mac(self) -> bool:
        """Check whether the current model is this fork's sole supported T2 target.

        This fork focuses exclusively on the MacBook Pro 15-inch 2018
        (MacBookPro15,1). No T2-specific patches, kexts, boot-args or NVRAM
        overrides may be applied to any other model, so we treat MacBookPro15,1
        as the only "T2" target we recognise.
        """
        return self.model == "MacBookPro15,1"

    def _build(self) -> None:
        """Kick off Misc Build Process."""
        self._feature_unlock_handling()
        self._restrict_events_handling()
        self._firewire_handling()
        self._topcase_handling()
        self._thunderbolt_handling()
        self._webcam_handling()
        self._usb_handling()
        self._debug_handling()
        self._cpu_friend_handling()
        self._general_oc_handling()
        self._t1_handling()
        self._t2_handling()

    def _feature_unlock_handling(self) -> None:
        """FeatureUnlock Handler."""
        if self.constants.fu_status is False:
            return

        if self.model not in smbios_data.smbios_dictionary:
            return

        if smbios_data.smbios_dictionary[self.model]["Max OS Supported"] >= os_data.os_data.sonoma:
            return

        APPLE_UUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
        support.BuildSupport(self.model, self.constants, self.config).enable_kext(
            "FeatureUnlock.kext", self.constants.featureunlock_version, self.constants.featureunlock_path
        )
        if self.constants.fu_arguments:
            logging.info(f"- Adding additional FeatureUnlock args: {self.constants.fu_arguments}")
            self._update_nvram_string(APPLE_UUID, "boot-args", self.constants.fu_arguments)

    def _restrict_events_handling(self) -> None:
        """RestrictEvents Handler."""
        OCLP_UUID = "4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102"
        block_args = ",".join(self._re_generate_block_arguments())
        patch_args = ",".join(self._re_generate_patch_arguments())

        if block_args:
            logging.info(f"- Setting RestrictEvents block arguments: {block_args}")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                "RestrictEvents.kext", self.constants.restrictevents_version, self.constants.restrictevents_path
            )
            self._set_nvram_value(OCLP_UUID, "revblock", block_args, overwrite=True)

        if block_args and not patch_args:
            patch_args = "none"

        if patch_args:
            logging.info(f"- Setting RestrictEvents patch arguments: {patch_args}")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                "RestrictEvents.kext", self.constants.restrictevents_version, self.constants.restrictevents_path
            )
            self._set_nvram_value(OCLP_UUID, "revpatch", patch_args, overwrite=True)

        kext_obj = support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("RestrictEvents.kext")
        if kext_obj and kext_obj.get("Enabled") is False:
            support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                "EFICheckDisabler.kext", "", self.constants.efi_disabler_path
            )

    def _re_generate_block_arguments(self) -> list:
        """Generate RestrictEvents block arguments."""
        re_block_args = []
        if self.model in ["MacBookPro6,1", "MacBookPro6,2", "MacBookPro9,1", "MacBookPro10,1"]:
            re_block_args.append("gmux")

        if self.model in model_array.MacPro:
            logging.info("- Disabling memory error reporting")
            re_block_args.append("pcie")

        if self.constants.disable_mediaanalysisd is True:
            logging.info("- Disabling mediaanalysisd")
            re_block_args.append("media")

        return re_block_args
    
    def _re_generate_patch_arguments(self) -> list:
        """Generate RestrictEvents patch arguments.

        sbvmm must be injected for T2 Macs regardless of serial_settings because
        macOS Tahoe's installer preflight checks SupportedDeviceModels via
        RestrictEvents at install time.  When serial_settings is "Advanced" the
        original condition (serial_settings == "None" or secure_status is False)
        never fires, leaving revpatch=sbvmm absent from the 4D1FDA02 NVRAM key
        and causing BIPreflightError Code 9 (J680AP / MacBookPro15,1 confirmed).
        """
        
        re_patch_args = []
        # Exp B6: sbvmm MUST be injected for T2 Macs regardless of allow_oc_everywhere
        # or serial_settings.  macOS Tahoe's installer preflight checks
        # SupportedDeviceModels via RestrictEvents at install time.  Without sbvmm,
        # T2 boards (J680AP / MacBookPro15,1) fail with BIPreflightError Code 9.
        if self._is_t2_mac():
            re_patch_args.append("sbvmm")
        elif self.constants.allow_oc_everywhere is False and (self.constants.serial_settings == "None" or self.constants.secure_status is False):
            re_patch_args.append("sbvmm")

        if self.model in smbios_data.smbios_dictionary:
            if smbios_data.smbios_dictionary[self.model]["CPU Generation"] == cpu_data.CPUGen.ivy_bridge.value:
                logging.info("- Fixing CoreGraphics support on Ivy Bridge")
                re_patch_args.append("f16c")

        return re_patch_args

    def _cpu_friend_handling(self) -> None:
        """CPUFriend Handler."""
        if self.constants.allow_oc_everywhere is False and self.model not in ["iMac7,1", "Xserve2,1", "Dortania1,1"] and self.constants.disallow_cpufriend is False and self.constants.serial_settings != "None":
            support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                "CPUFriend.kext", self.constants.cpufriend_version, self.constants.cpufriend_path
            )

            pp_map_path = Path(self.constants.platform_plugin_plist_path) / Path(f"{self.model}/Info.plist")
            if not pp_map_path.exists():
                raise Exception(f"{pp_map_path} does not exist for {self.model}.")
            
            Path(self.constants.pp_kext_folder).mkdir(parents=True, exist_ok=True)
            Path(self.constants.pp_contents_folder).mkdir(parents=True, exist_ok=True)
            shutil.copy(pp_map_path, self.constants.pp_contents_folder)
            
            kf_obj = support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("CPUFriendDataProvider.kext")
            if kf_obj:
                kf_obj["Enabled"] = True

    def _firewire_handling(self) -> None:
        """FireWire Handler."""
        if self.constants.firewire_boot is False:
            return
        if generate_smbios.check_firewire(self.model) is False:
            return

        logging.info("- Enabling FireWire Boot Support")
        builder = support.BuildSupport(self.model, self.constants, self.config)
        builder.enable_kext("IOFireWireFamily.kext", self.constants.fw_kext, self.constants.fw_family_path)
        builder.enable_kext("IOFireWireSBP2.kext", self.constants.fw_kext, self.constants.fw_sbp2_path)
        builder.enable_kext("IOFireWireSerialBusProtocolTransport.kext", self.constants.fw_kext, self.constants.fw_bus_path)
        
        fw_plugin = builder.get_kext_by_bundle_path("IOFireWireFamily.kext/Contents/PlugIns/AppleFWOHCI.kext")
        if fw_plugin:
            fw_plugin["Enabled"] = True

    def _topcase_handling(self) -> None:
        """USB/SPI Top Case Handler."""
        if self.model.startswith("MacBook") and self.model in smbios_data.smbios_dictionary:
            cpu_gen = smbios_data.smbios_dictionary[self.model]["CPU Generation"]
            if self.model.startswith("MacBookAir6") or (cpu_data.CPUGen.broadwell <= cpu_gen <= cpu_data.CPUGen.kaby_lake):
                logging.info("- Enabling SPI-based top case support")
                builder = support.BuildSupport(self.model, self.constants, self.config)
                builder.enable_kext("AppleHSSPISupport.kext", self.constants.apple_spi_version, self.constants.apple_spi_path)
                builder.enable_kext("AppleHSSPIHIDDriver.kext", self.constants.apple_spi_hid_version, self.constants.apple_spi_hid_path)
                builder.enable_kext("AppleTopCaseInjector.kext", self.constants.topcase_inj_version, self.constants.top_case_inj_path)

        if not self.constants.custom_model and self.computer.internal_keyboard_type and self.computer.trackpad_type:
            builder = support.BuildSupport(self.model, self.constants, self.config)
            builder.enable_kext("AppleUSBTopCase.kext", self.constants.topcase_version, self.constants.top_case_path)
            
            for part in ["AppleUSBTCButtons.kext", "AppleUSBTCKeyboard.kext", "AppleUSBTCKeyEventDriver.kext"]:
                obj = builder.get_kext_by_bundle_path(f"AppleUSBTopCase.kext/Contents/PlugIns/{part}")
                if obj:
                    obj["Enabled"] = True

            if self.computer.internal_keyboard_type == "Legacy":
                builder.enable_kext("LegacyKeyboardInjector.kext", self.constants.legacy_keyboard, self.constants.legacy_keyboard_path)
            if self.computer.trackpad_type == "Legacy":
                builder.enable_kext("AppleUSBTrackpad.kext", self.constants.apple_trackpad, self.constants.apple_trackpad_path)
            elif self.computer.trackpad_type == "Modern":
                builder.enable_kext("AppleUSBMultitouch.kext", self.constants.multitouch_version, self.constants.multitouch_path)
        else:
            if self.model in smbios_data.smbios_dictionary and smbios_data.smbios_dictionary[self.model]["CPU Generation"] < cpu_data.CPUGen.skylake.value:
                if self.model.startswith("MacBook") and self.model not in ["MacBookPro11,4", "MacBookPro11,5", "MacBookPro12,1", "MacBook8,1"]:
                    builder = support.BuildSupport(self.model, self.constants, self.config)
                    builder.enable_kext("AppleUSBTopCase.kext", self.constants.topcase_version, self.constants.top_case_path)
                    for part in ["AppleUSBTCButtons.kext", "AppleUSBTCKeyboard.kext", "AppleUSBTCKeyEventDriver.kext"]:
                        obj = builder.get_kext_by_bundle_path(f"AppleUSBTopCase.kext/Contents/PlugIns/{part}")
                        if obj:
                            obj["Enabled"] = True
                    builder.enable_kext("AppleUSBMultitouch.kext", self.constants.multitouch_version, self.constants.multitouch_path)

            if self.model == "MacBook5,2":
                builder = support.BuildSupport(self.model, self.constants, self.config)
                builder.enable_kext("AppleUSBTrackpad.kext", self.constants.apple_trackpad, self.constants.apple_trackpad_path)
                builder.enable_kext("LegacyKeyboardInjector.kext", self.constants.legacy_keyboard, self.constants.legacy_keyboard_path)

    def _thunderbolt_handling(self) -> None:
        """Thunderbolt Handler."""
        if self.constants.disable_tb is True and self.model in ["MacBookPro11,1", "MacBookPro11,2", "MacBookPro11,3", "MacBookPro11,4", "MacBookPro11,5"]:
            logging.info("- Disabling 2013-2014 laptop Thunderbolt Controller")
            tb_device_path = (
                "PciRoot(0x0)/Pci(0x1,0x1)/Pci(0x0,0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)"
                if self.model in ["MacBookPro11,3", "MacBookPro11,5"]
                else "PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)"
            )
            self.config.setdefault("DeviceProperties", {}).setdefault("Add", {})
            self.config["DeviceProperties"]["Add"][tb_device_path] = {
                "class-code": binascii.unhexlify("FFFFFFFF"),
                "device-id": binascii.unhexlify("FFFF0000")
            }

    def _webcam_handling(self) -> None:
        """iSight Handler."""
        if self.model in smbios_data.smbios_dictionary:
            if smbios_data.smbios_dictionary[self.model].get("Legacy iSight") is True:
                support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                    "LegacyUSBVideoSupport.kext", self.constants.apple_isight_version, self.constants.apple_isight_path
                )

        if not self.constants.custom_model:
            if self.constants.computer.pcie_webcam is True:
                support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                    "AppleCameraInterface.kext", self.constants.apple_camera_version, self.constants.apple_camera_path
                )
        else:
            if self.model.startswith("MacBook") and self.model in smbios_data.smbios_dictionary:
                if cpu_data.CPUGen.haswell <= smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.kaby_lake:
                    support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                        "AppleCameraInterface.kext", self.constants.apple_camera_version, self.constants.apple_camera_path
                    )

    def _usb_handling(self) -> None:
        """USB Handler."""
        if not self._is_t2_mac():
            logging.info("Your Mac is not affected by Unsupported Mantissa speed kernel panics, continuing with USB mapping.")
            usb_map_path = Path(self.constants.plist_folder_path) / Path("AppleUSBMaps/Info.plist")
            usb_map_tahoe_path = Path(self.constants.plist_folder_path) / Path("AppleUSBMaps/Info-Tahoe.plist")
            
            if (
                usb_map_path.exists() and usb_map_tahoe_path.exists()
                and (self.constants.allow_oc_everywhere is False or self.constants.allow_native_spoofs is True)
                and self.model not in ["Xserve2,1", "Dortania1,1"]
                and ((self.model in model_array.Missing_USB_Map or self.model in model_array.Missing_USB_Map_Ventura)
                     or self.constants.serial_settings in ["Moderate", "Advanced"])
            ):
                logging.info("- Adding USB-Map.kext and USB-Map-Tahoe.kext")
                Path(self.constants.map_kext_folder).mkdir(parents=True, exist_ok=True)
                Path(self.constants.map_kext_folder_tahoe).mkdir(parents=True, exist_ok=True)
                Path(self.constants.map_contents_folder).mkdir(parents=True, exist_ok=True)
                Path(self.constants.map_contents_folder_tahoe).mkdir(parents=True, exist_ok=True)
                
                shutil.copy(usb_map_path, self.constants.map_contents_folder)
                shutil.copy(usb_map_tahoe_path, self.constants.map_contents_folder_tahoe / Path("Info.plist"))
                
                builder = support.BuildSupport(self.model, self.constants, self.config)
                m1 = builder.get_kext_by_bundle_path("USB-Map.kext")
                m2 = builder.get_kext_by_bundle_path("USB-Map-Tahoe.kext")
                if m1: m1["Enabled"] = True
                if m2: m2["Enabled"] = True
                
                if self.model in model_array.Missing_USB_Map_Ventura and self.constants.serial_settings not in ["Moderate", "Advanced"]:
                    if m1: m1["MinKernel"] = "22.0.0"

            if self.model in smbios_data.smbios_dictionary and (
                smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.penryn.value or \
                self.model in ["MacPro4,1", "MacPro5,1", "Xserve3,1"]
            ):
                logging.info("- Adding UHCI/OHCI USB support")
                shutil.copy(self.constants.apple_usb_11_injector_path, self.constants.kexts_path)
                builder = support.BuildSupport(self.model, self.constants, self.config)
                for injector in ["AppleUSBOHCI.kext", "AppleUSBOHCIPCI.kext", "AppleUSBUHCI.kext", "AppleUSBUHCIPCI.kext"]:
                    obj = builder.get_kext_by_bundle_path(f"USB1.1-Injector.kext/Contents/PlugIns/{injector}")
                    if obj: obj["Enabled"] = True
                
                m1 = builder.get_kext_by_bundle_path("USB-Map.kext")
                if m1: m1["MaxKernel"] = ""
        else:
            logging.info("Your Mac is affected by Unsupported Mantissa speed kernel panics. Skipping USB port mapping.")

    def _debug_handling(self) -> None:
        """Debug Handler for OpenCorePkg and Kernel Space."""
        APPLE_UUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
        if self.constants.verbose_debug is True:
            logging.info("- Enabling Verbose boot")
            self._update_nvram_string(APPLE_UUID, "boot-args", "-v")

        if self.constants.kext_debug is True:
            logging.info("- Enabling DEBUG Kexts")
            self._update_nvram_string(APPLE_UUID, "boot-args", "-liludbgall liludump=90")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                "DebugEnhancer.kext", self.constants.debugenhancer_version, self.constants.debugenhancer_path
            )

        if self.constants.opencore_debug is True:
            logging.info("- Enabling DEBUG OpenCore")
            self.config.setdefault("Misc", {}).setdefault("Debug", {})
            self.config["Misc"]["Debug"]["Target"] = 0x43
            self.config["Misc"]["Debug"]["DisplayLevel"] = 0x80000042

    def _general_oc_handling(self) -> None:
        """General OpenCorePkg Handler."""
        logging.info("- Adding OpenCanopy GUI")
        shutil.copy(self.constants.gui_path, self.constants.oc_folder)
        builder = support.BuildSupport(self.model, self.constants, self.config)
        
        for efi_bin in ["OpenCanopy.efi", "OpenRuntime.efi", "OpenLinuxBoot.efi", "ResetNvramEntry.efi"]:
            obj = builder.get_efi_binary_by_path(efi_bin, "UEFI", "Drivers")
            if obj: obj["Enabled"] = True

        self.config.setdefault("Misc", {}).setdefault("Boot", {})
        if self.constants.showpicker is False:
            logging.info("- Hiding OpenCore picker")
            self.config["Misc"]["Boot"]["ShowPicker"] = False

        if self.constants.oc_timeout != 5:
            logging.info(f"- Setting custom OpenCore picker timeout to {self.constants.oc_timeout} seconds")
            self.config["Misc"]["Boot"]["Timeout"] = self.constants.oc_timeout

        if self.constants.vault is True:
            logging.info("- Setting Vault configuration")
            self.config.setdefault("Misc", {}).setdefault("Security", {})
            self.config["Misc"]["Security"]["Vault"] = "Secure"

    def _t1_handling(self) -> None:
        """T1 Security Chip Handler with Crash Protection."""
        if self.model not in ["MacBookPro13,2", "MacBookPro13,3", "MacBookPro14,2", "MacBookPro14,3"]:
            return

        logging.info("- Enabling T1 Security Chip support")
        try:
            builder = support.BuildSupport(self.model, self.constants, self.config)
            identifiers = ["com.apple.driver.AppleSSE", "com.apple.driver.AppleKeyStore", "com.apple.driver.AppleCredentialManager"]
            
            self.config.setdefault("Kernel", {}).setdefault("Block", [])
            for identifier in identifiers:
                item = builder.get_item_by_kv(self.config["Kernel"]["Block"], "Identifier", identifier)
                if item: item["Enabled"] = True

            kexts_to_enable = [
                ("corecrypto_T1.kext", self.constants.t1_corecrypto_version, self.constants.t1_corecrypto_path),
                ("AppleSSE.kext", self.constants.t1_sse_version, self.constants.t1_sse_path),
                ("AppleKeyStore.kext", self.constants.t1_key_store_version, self.constants.t1_key_store_path),
                ("AppleCredentialManager.kext", self.constants.t1_credential_version, self.constants.t1_credential_path),
                ("KernelRelayHost.kext", self.constants.kernel_relay_version, self.constants.kernel_relay_path),
            ]
            for name, version, path in kexts_to_enable:
                builder.enable_kext(name, version, path)
        except Exception as e:
            logging.error(f"CRITICAL: Failed to configure T1 Security Chip: {e}")
            logging.exception("Stack Trace:")
            logging.info("Please try again later.")
            sys.exit(3)

    def _validate_patch(self, patch_dict):
        """
        Validate a kernel Find/Replace patch before it is injected.

        Returns True when the patch is safe to append. Raises
        PatchValidationError when the patch is invalid (Find/Replace length
        mismatch, or the byte fields cannot be measured). Callers that want
        the build to abort should let the exception propagate to
        BuildOpenCore, which logs it and exits.
        """
        comment = patch_dict.get("Comment")

        # Measure the byte fields. This is deliberately kept in a narrow
        # try/except so that an unexpected shape (e.g. Find is None) becomes a
        # PatchValidationError rather than being confused with the length
        # mismatch case below.
        try:
            find_bytes = patch_dict.get("Find")
            replace_bytes = patch_dict.get("Replace")
            find_len = len(find_bytes)
            replace_len = len(replace_bytes)
        except Exception as e:
            logging.error("We have an issue comparing the bytes length.")
            raise PatchValidationError(
                f"Cannot measure Find/Replace byte lengths for patch '{comment}': {e}"
            ) from e

        # Length comparison — Find and Replace MUST be the same length.
        if find_len != replace_len:
            logging.error(f"LENGTH ISSUE in '{comment}': "
                          f"Find={find_len} Bytes, Replace={replace_len} Bytes.")
            raise PatchValidationError(
                f"Length mismatch in patch '{comment}': "
                f"Find={find_len} bytes, Replace={replace_len} bytes"
            )

        # Audit trail: report exactly which bytes this patch will inject.
        # This is the core guardrail against guessing — every injected patch
        # must show its Find/Replace lengths matching here before it ships.
        find_hex = binascii.hexlify(find_bytes).decode().upper()
        replace_hex = binascii.hexlify(replace_bytes).decode().upper()
        logging.info(
            f"[patch-audit] {comment} | "
            f"Identifier={patch_dict.get('Identifier')} | "
            f"Base={patch_dict.get('Base') or '<byte-signature>'} | "
            f"Find({find_len}B)={find_hex} Replace({replace_len}B)={replace_hex}"
        )
        return True
    
    def _t2_handling(self) -> None:
        """T2 Security Chip Handler."""
        if not self._is_t2_mac():
            return
        # 2026-07-27: Disabled the VHCI experimental patches.
        # Boot was freezing right after AppleUSBVHCI port registration on
        # MacBookPro15,1. processInterrupts was being NOPed which broke USB
        # interrupt handling completely. Turning these off to verify that's
        # what's causing the hang before reworking the patches.
        enable_experimental_patches = False
        logging.info("If you want to enable optional patches that haven't been tested yet, you should download go to releases")
        logging.info(", then download the zip file, extract it, and then, open up misc.py.")
        logging.info("And afterwards, you need manually to set enable_experimental_patches from False to True")
        builder = support.BuildSupport(self.model, self.constants, self.config)
        self.config.setdefault("Kernel", {}).setdefault("Patch", [])

        if enable_experimental_patches==False:
            logging.info("Injecting optional patches are not enabled. That's the standard behavior.")
        elif enable_experimental_patches==True:
            logging.info("ATTENTION! Injecting optional patches are enabled. These patches haven't been tested yet and may have bugs, which could lead to for example kernel panics.")
        else:
            logging.error("We couldn't verify if injecting optional patcges are enabled or not, but they must be disabled if the variable is not set to True.")

        # Prerequisite kext checks
        for kext, ver, path in [
            ("WhateverGreen.kext", self.constants.whatevergreen_version, self.constants.whatevergreen_path),
            ("CryptexFixup.kext", "1.0.5", self.constants.kexts_path),
            ("AMFIPass.kext", "1.4.1", self.constants.kexts_path)
        ]:
            obj = builder.get_kext_by_bundle_path(kext)
            if not obj or obj.get("Enabled") is not True:
                logging.info(f"- Enabling {kext}")
                builder.enable_kext(kext, ver, path)

        # Exp B7: WhateverGreen is KEPT ENABLED for T2 to process igfxonln=1,
        # igfxfw=2, agdpmod=vit9696, -wegnoegpu boot-args.  Note: WEG probe()
        # may fail on Tahoe — if so, these args are simply not processed (harmless).
        # DeviceProperties injection (ig-platform-id, disable-gpu) works without WEG
        # regardless.  If WEG causes GUI hang during installer, disable it manually
        # via boot-args by adding -igfxnoigpuoutput or by removing WEG.kext.

        # Handle explicit performance/timeout panics on specific MacBook lines
        # MinKernel is 24.0.0 (Sequoia's Darwin version) instead of 25.x.x because the installer runs on Darwin 24, even for macOS 26 Tahoe.
        if self.model in ["MacBookAir8,1", "MacBookAir8,2", "MacBookAir9,1", "MacBookPro16,3"]:
            logging.info(f"- {self.model}: Applying Unsupported Mantissa Speed kernel panic patches")
            try:
                logging.info(f"- {self.model}: Disabling USB-Map.kext and USB-Map-Tahoe.kext if any is there")
                m1 = builder.get_kext_by_bundle_path("USB-Map.kext")
                m2 = builder.get_kext_by_bundle_path("USB-Map-Tahoe.kext")
                if m1: m1["Enabled"] = False
                if m2: m2["Enabled"] = False
            except Exception as e:
                logging.info(f"- {self.model}: Great news! We tried disabling USB-Map.kext and USB-Map-Tahoe.kext but we didn't find them.")
                logging.info("You don't have to worry about this message.")
        APPLE_NVRAM_UUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"

        # DISABLED 2026-07-27: Setting prev-lang:kbd / AppleLanguages / AppleLocale
        # caused the macOS Tahoe installer to show a gray screen with no UI on
        # MacBookPro15,1 (and possibly other T2 models).  Re-enabling requires
        # verifying that the installer windows still appear correctly.
        #
        # try:
        #     logging.info("- Skipping Language and Region selection (all T2 models)")
        #     prev_lang_bytes = b"en-US:0"
        #     self._set_nvram_value(APPLE_NVRAM_UUID, "prev-lang:kbd", prev_lang_bytes, overwrite=True)
        #     self._set_nvram_value(APPLE_NVRAM_UUID, "AppleLanguages", ["en-US"], overwrite=True)
        #     self._set_nvram_value(APPLE_NVRAM_UUID, "AppleLocale", "en_US", overwrite=True)
        # except Exception as e:
        #     logging.error("We failed to skip language and region selection. It failed to do so because of the following error:")
        #     logging.exception("Stack Trace:")
        #     logging.info("Please try again later.")
        #     sys.exit(3)

        try:
            logging.info("- Adding T2-specific boot arguments for macOS 15/26")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-v rddelay=10 -disable_ext_panics -no_compat_check bpr_initialdelay=500 bpr_finaldelay=500")
        except Exception as e:
            logging.error("Injecting T2 specific boot arguments failed due to the following error:")
            logging.exception("Stack Trace:")
            logging.info("Please try again later.")
            sys.exit(3)
        
        if self.model in ["MacBookAir8,1", "MacBookAir8,2"]:
            try:
                logging.info("Applying patches for MacBookAir8,1 or 8,2 to fix CPU topology / thread pooling panic layouts")
                self.config["Kernel"]["Quirks"]["ProvideCurrentCpuInfo"] = True
            except Exception as e:
                logging.error("Applying patches to fix this specific kernel panic failed due to the following error:")
                logging.exception("Stack Trace:")
                logging.info("Please try again later.")
                sys.exit(3)
            
        # Structure guarding for OpenCore NVRAM delete layout
        self.config.setdefault("NVRAM", {}).setdefault("Delete", {})
        if APPLE_NVRAM_UUID not in self.config["NVRAM"]["Delete"]:
            self.config["NVRAM"]["Delete"][APPLE_NVRAM_UUID] = []
        if "boot-args" not in self.config["NVRAM"]["Delete"][APPLE_NVRAM_UUID]:
            self.config["NVRAM"]["Delete"][APPLE_NVRAM_UUID].append("boot-args")

        # Bypass library validation enforcement on T2 hardware to prevent early kernel panics
        logging.info("- Bypassing Library Validation Enforcement hook patches for T2 core integrity protection.")

        try:
            logging.info("- Set SIP to 0x803")
            self._set_nvram_value(APPLE_NVRAM_UUID, "csr-active-config", binascii.unhexlify("03080000"), overwrite=True)
        except Exception as e:
            logging.error("Setting SIP to 0x803 failed due to the following error:")
            logging.exception("Stack Trace:")
            logging.info("Please try again later.")
            sys.exit(3)
        
        # Allows booting macOS 26 Tahoe's installer via OpenCore on T2 Macs
        self.config.setdefault('Kernel', {}).setdefault('Patch', [])
        kernel_patches = self.config['Kernel']['Patch']
        
        # Validate all patches via _validate_patch before injection (ensures Find/Replace byte lengths match)
        
        try:
            # 1. Disable xART validation capacity loop checks safely (Symbolic Base Path)
            if not any(p.get("Comment") == "Bypass XARTDisableLog limits (Tahoe Cache Fix)" for p in kernel_patches):
                new_patch = {
                    "Arch": "x86_64",
                    "Identifier": "com.apple.driver.AppleSEPManager",
                    "Base": "__ZN14XARTDisableLog16register_disableEj",
                    "Comment": "Bypass XARTDisableLog limits (Tahoe Cache Fix)",  # VERIFIED 2026-07-15: symbol __ZN14XARTDisableLog16register_disableEj @0xffffff8001badf34 prolog=554889e5 (BootKernelExtensions.kc)
                    "Count": 1,
                    "Enabled": True,
                    "MinKernel": "24.0.0",
                            "Find": binascii.unhexlify("554889E5"),        # push rbp; mov rbp, rsp
                            "Replace": binascii.unhexlify("31C0C390"),     # xor eax, eax; ret; nop
                    "Mask": b"",
                    "ReplaceMask": b"",
                    "Limit": 0,
                    "Skip": 0
                }
                if self._validate_patch(new_patch):
                    logging.info("- Injecting Bypass XARTDisableLog limits patch")
                    kernel_patches.append(new_patch)

            # The former "Hardcode SEP OOL Max Send Pages Limit" patch was
            # intentionally removed from the shared T2 path: its Find
            # sequence is 4 bytes while its Replace sequence is 6 bytes.
            # Without a verified same-length replacement, do not inject or
            # invent bytes for any model.

            # 3. AppleKeyStoreUserClient deadline check bypass
            if not any(p.get("Comment") == "Bypass AppleKeyStore Deadline Mismatch (Tahoe Fix)" for p in kernel_patches):
                new_patch = {
                     "Arch": "x86_64",
                    # 2026-07-16 RE-VERIFIED against REAL Tahoe 26.5.2 binary
                    # (BootKernelExtensions.kc, /Volumes/Install macOS Tahoe).
                    # Symbol '__ZN23AppleKeyStoreUserClient26check_lock_assert_deadlineEv'
                    # EXISTS @0xffffff8001a7a25a (__REGION142) with prolog
                    # 554889E5415741565350... which MATCHES Find exactly.
                    # That prolog is GENERIC (88x in AppleKeyStore alone); Base:"" +
                    # Count:1 would patch the FIRST match -> WRONG function. So bind
                    # Base to the exact symbol: OpenCore patches ONLY this function.
                    "Base": "__ZN23AppleKeyStoreUserClient26check_lock_assert_deadlineEv",
                    "Comment": "Bypass AppleKeyStore Deadline Mismatch (Tahoe Fix)",
                    "Count": 1,
                    "Enabled": True,
                    "Identifier": "com.apple.driver.AppleKeyStore",
                    "Find": binascii.unhexlify("554889E5415741565350"),
                    "Mask": b"",
                    "Replace": binascii.unhexlify("31C0C390909090909090"),
                    "ReplaceMask": b"",
                    "MinKernel": "25.0.0",  # Tahoe (Darwin 25); not Sequoia 24
                    "MaxKernel": "",
                    "Limit": 0,
                    "Skip": 0
                }
                if self._validate_patch(new_patch):
                    logging.info("  > Injecting AppleKeyStore Tahoe deadline check bypass")
                    kernel_patches.append(new_patch)

            # 4. Bypass AppleIntelUSBXHCI T2 handshake (Modernized for Tahoe vtable shifts)
            if not any(p.get("Comment") == "Bypass T2 USB handshake (Tahoe fix)" for p in kernel_patches):
                new_patch = {
                    "Arch": "x86_64",
                    "Base": "",  # Suche über Byte-Signatur, da Symbole gestrippt sind
                    "Comment": "Bypass T2 USB handshake (Tahoe fix)",
                    "Count": 1,   # Verhindert Kollateralschäden durch Mehrfachtreffer
                    # DISABLED 2026-07-15: verified NOT-FOUND in real Tahoe binary
                    # (BootKernelExtensions.kc -> com.apple.driver.usb.AppleUSBXHCI). No
                    # 'Handshake' function matches Find 554889E54156534883EC10488B05; the
                    # bytes are absent. Per project rule (HANDOFF.md) disable rather than
                    # guess. Re-enable only after RE identifies the correct T2 handshake
                    # function + prolog in Tahoe.
                    "Enabled": False,
                    "Identifier": "com.apple.driver.usb.AppleUSBXHCI",
                    "MinKernel": "24.0.0",
                    "MaxKernel": "",
                    "Limit": 0,
                    "Skip": 0,
                    "Mask": b"",
                    "ReplaceMask": b"",
                    "Find": binascii.unhexlify("554889E54156534883EC10488B05"),
                    "Replace": binascii.unhexlify("31C0C39090909090909090909090")
                }
                if self._validate_patch(new_patch):
                    logging.info("- Injecting modernized AppleUSBXHCI T2 handshake bypass")
                    kernel_patches.append(new_patch)

            # 5. Bypass AppleBCMWLANCore long start timeout
            if not any(p.get("Comment") == "Bypass AppleBCMWLANCore long start timeout" for p in kernel_patches):
                new_patch = {
                    "Arch": "x86_64",
                    "Comment": "Bypass AppleBCMWLANCore long start timeout",
                    "Enabled": False,
                    # Identifier corrected 2026-07-15: real Tahoe bundle id is
                    # com.apple.driver.AppleBCMWLANCoreMac (was wrong:
                    # com.apple.iokit.AppleBCMWLANCore). Patch is DISABLED because Find
                    # 554889E54157415641554154 is NOT-FOUND in the real Tahoe binary
                    # (BootKernelExtensions.kc) and 'initWithAddressAndPeerManager' no
                    # longer exists. Per project rule (HANDOFF.md) disable rather than
                    # guess. Re-enable only after RE confirms Find in Tahoe.
                    "Identifier": "com.apple.driver.AppleBCMWLANCoreMac", # Tahoe real bundle id
                    "MaxKernel": "",
                    "MinKernel": "24.0.0",
                    "Find": binascii.unhexlify("554889E54157415641554154"),
                    "Replace": binascii.unhexlify("C39090909090909090909090"),
                        
                    "Limit": 0,
                    "Skip": 0,
                    "Count": 1
                }
                if self._validate_patch(new_patch):
                    logging.info("- Injecting Bypass AppleBCMWLANCore long start timeout")
                    kernel_patches.append(new_patch)

            # Experimental Patches
            if enable_experimental_patches == True:
                # Experimental Patch 1: processInterrupts
                if not any(p.get("Comment") == "Bypass AppleUSBVHCI::processInterrupts to prevent protocol-driven panics" for p in kernel_patches):
                    new_patch = {
                        "Arch": "x86_64",
                        "Comment": "Bypass AppleUSBVHCI::processInterrupts to prevent protocol-driven panics",
                        "Enabled": True,
                        "Identifier": "com.apple.driver.usb.AppleUSBVHCI",
                        "Base": "", "Count": 1, "MinKernel": "24.0.0", "MaxKernel": "", "Mask": b"", "ReplaceMask": b"", "Limit": 0, "Skip": 0,
                        "Find": binascii.unhexlify("554889E54157415641554154534883EC28"),
                        "Replace": binascii.unhexlify("C390909090909090909090909090909090")
                    }
                    if self._validate_patch(new_patch):
                        kernel_patches.append(new_patch)

                # Experimental Patch 2: hardwareException
                if not any(p.get("Comment") == "Bypass AppleUSBVHCI::hardwareException (Suppress firmware exceptions)" for p in kernel_patches):
                    new_patch = {
                        "Arch": "x86_64",
                        "Comment": "Bypass AppleUSBVHCI::hardwareException (Suppress firmware exceptions)",
                        "Enabled": True,
                        "Identifier": "com.apple.driver.usb.AppleUSBVHCI",
                        "Base": "", "Count": 1, "MinKernel": "24.0.0", "MaxKernel": "", "Mask": b"", "ReplaceMask": b"", "Limit": 0, "Skip": 0,
                        "Find": binascii.unhexlify("554889E5488B87A80300000FB6B7D0000000"),
                        "Replace": binascii.unhexlify("C39090909090909090909090909090909090")
                    }
                    if self._validate_patch(new_patch):
                        kernel_patches.append(new_patch)

            # Exp B7: AppleSEPKeyStore / AppleSEPManager board-id and imageboot
            # bypass patches — RE-VERIFIED 2026-07-27 against real Tahoe 26.x
            # BootKernelExtensions.kc.  Both patches are DEFERRED because:
            #
            # 1) The board-id comparison during imageboot happens in the kernel
            #    (imageboot.c), NOT in the AppleKeyStore kext.  The only LEA
            #    xref to "board-id" inside AppleKeyStore is in the getter
            #    _kernel_shared_platform_get_board_id (0xffffff8001aa71a2),
            #    which simply returns the string — it does NOT compare.
            #
            # 2) All attestation/ECID/model symbols (_encode_attestation,
            #    _gen_attestation_request, _aks_attest_context_verify, etc.)
            #    live in com.apple.driver.AppleKeyStore, NOT in
            #    com.apple.driver.AppleSEPManager.  The SEPManager kext has
            #    zero attestation-related symbols.
            #
            # 3) Generic prolog Find patterns (Base:"") match hundreds of
            #    functions and would patch the WRONG function.  Until exact
            #    target symbols are identified, these must stay disabled.
            #
            # The board-id mismatch is already addressed at the firmware layer:
            # - Booter patches "Skip Board ID check" + "Reroute HW_BID to OC_BID"
            # - Coprocessor DeviceProperties injection (board-id spoof "J680AP")

            # [DEFERRED] Patch: Bypass AppleKeyStore board-id validation during imageboot
            # RE finding: No board-id COMPARISON function exists in AppleKeyStore.
            # The "board-id" string xref is only in _kernel_shared_platform_get_board_id
            # which is a getter, not a checker.  The actual board-id check is in the
            # kernel's imageboot.c (not patchable via kext patch).
            # DEFERRED: Need kernel-level patch approach, or rely on Booter patches.
            if not any(p.get("Comment") == "Bypass SEPKeyStore board-id check (imageboot)" for p in kernel_patches):
                new_patch = {
                    "Arch": "x86_64",
                    "Base": "",
                    "Comment": "Bypass SEPKeyStore board-id check (imageboot)",
                    "Count": 1,
                    "Enabled": False,  # DEFERRED: no valid target function in AppleKeyStore
                    "Identifier": "com.apple.driver.AppleKeyStore",
                    "MinKernel": "25.0.0",
                    "MaxKernel": "",
                    "Find": binascii.unhexlify("554889E5415741565350"),
                    "Replace": binascii.unhexlify("31C0C390909090909090"),
                    "Mask": b"",
                    "ReplaceMask": b"",
                    "Limit": 0,
                    "Skip": 0
                }
                if self._validate_patch(new_patch):
                    logging.info("- Exp B7: SEPKeyStore board-id patch (DEFERRED — no target in AppleKeyStore)")
                    kernel_patches.append(new_patch)

            # [DEFERRED] Patch: Bypass AppleSEPManager ECID/hardware model validation
            # RE finding: All attestation/ECID symbols are in com.apple.driver.AppleKeyStore,
            # NOT in com.apple.driver.AppleSEPManager.  Wrong kext identifier.
            # DEFERRED: Need to identify correct kext + exact target symbol.
            if not any(p.get("Comment") == "Bypass SEPManager ECID/model check (installer)" for p in kernel_patches):
                new_patch = {
                    "Arch": "x86_64",
                    "Base": "",
                    "Comment": "Bypass SEPManager ECID/model check (installer)",
                    "Count": 1,
                    "Enabled": False,  # DEFERRED: wrong kext, no attestation symbols in SEPManager
                    "Identifier": "com.apple.driver.AppleSEPManager",
                    "MinKernel": "25.0.0",
                    "MaxKernel": "",
                    "Find": binascii.unhexlify("554889E541574156534883EC"),
                    "Replace": binascii.unhexlify("31C0C3909090909090909090"),
                    "Mask": b"",
                    "ReplaceMask": b"",
                    "Limit": 0,
                    "Skip": 0
                }
                if self._validate_patch(new_patch):
                    logging.info("- Exp B7: SEPManager ECID/model patch (DEFERRED — wrong kext target)")
                    kernel_patches.append(new_patch)

        except Exception as e:
            logging.error("Failed to inject critical patches for your T2 Mac due to the following error:")
            logging.exception("Stack Trace:")
            logging.info("Please try again later.")
            sys.exit(3)

            
        # Bypass osinstallersetupd bridge device validation checks (Fixes Attestation Error -10000)
        try:
            logging.info("- Injecting User-Space Attestation bypass flags (Fixes Error -10000)")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-oas_skip_attestation")
            self._set_nvram_value(APPLE_NVRAM_UUID, "IAS_ENV_SKIP_ATTESTATION", "1", overwrite=True)
        except Exception as e:
            logging.error("Failed to inject Attestation Error -10000 bypass flags:")
            logging.exception("Stack Trace:")
            logging.info("Please try again later.")
            sys.exit(3)
        

