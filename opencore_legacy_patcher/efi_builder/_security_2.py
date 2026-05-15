"""
security.py: Class for handling macOS Security Patches, invocation from build.py
"""

import logging
import binascii

from . import support
from .. import constants
from ..support import utilities
from ..detections import device_probe
from ..datasets import (
    security_fallback,
    smbios_data,
    os_data
)


class BuildSecurity:
    """
    Build Library for Security Patch Support

    Invoke from build.py
    """

    def __init__(self, model: str, global_constants: constants.Constants, config: dict) -> None:
        self.model: str = model
        self.config: dict = config
        self.constants: constants.Constants = global_constants
        self.computer: device_probe.Computer = self.constants.computer

        self._build()

    def _update_nvram_string(self, uuid: str, key: str, value: str) -> None:
        """
        Appends a string value to an NVRAM variable only if it doesn't already exist.
        Ensures proper spacing between arguments.
        """
        if uuid not in self.config["NVRAM"]["Add"]:
            self.config["NVRAM"]["Add"][uuid] = {}
        
        current_value = self.config["NVRAM"]["Add"][uuid].get(key, "")
        
        if value not in current_value:
            if current_value == "":
                self.config["NVRAM"]["Add"][uuid][key] = value.strip()
            else:
                # Add a space only if the string isn't empty and doesn't already have one
                self.config["NVRAM"]["Add"][uuid][key] = f"{current_value.rstrip()} {value.strip()}"

    def _set_nvram_value(self, uuid: str, key: str, value: any, overwrite: bool = False) -> None:
        """
        Sets an NVRAM variable. If overwrite is False, it only sets if the key is missing.
        """
        if uuid not in self.config["NVRAM"]["Add"]:
            self.config["NVRAM"]["Add"][uuid] = {}
        
        if overwrite or key not in self.config["NVRAM"]["Add"][uuid]:
            self.config["NVRAM"]["Add"][uuid][key] = value

    def _is_t2_mac(self) -> bool:
        """Detect whether the current model is a T2-equipped Mac."""
        return "T2_CHIP" in self.constants.device_properties.get(self.model, {}).get("Features", [])

    def _is_macbookpro15_1(self) -> bool:
        """Check if the current model is specifically MacBookPro15,1 (2018 13-inch T2 Mac)."""
        return self.model == "MacBookPro15,1"

    def _set_nested_config_value(self, path: str, value: any) -> None:
        """Write a nested config value using a dotted path."""
        node = self.config
        keys = path.split('.')

        for part in keys[:-1]:
            if part not in node or not isinstance(node[part], dict):
                node[part] = {}
            node = node[part]

        node[keys[-1]] = value

    def _get_t2_security_fallback(self) -> dict:
        """Load T2 fallback security values from the external dataset."""
        return security_fallback.get_security_fallback(self.model)

    def _apply_t2_security_fallback(self, fallback: dict, apple_nvram_uuid: str) -> None:
        """Apply fallback security settings for a T2 Mac."""
        for key, value in fallback.items():
            if key == "csr-active-config":
                if isinstance(value, str):
                    value = binascii.unhexlify(value)
                self._set_nvram_value(apple_nvram_uuid, key, value, overwrite=True)
            elif key == "boot-args":
                if isinstance(value, list):
                    value = " ".join(value)
                self._update_nvram_string(apple_nvram_uuid, "boot-args", value)
            else:
                self._set_nested_config_value(key, value)

    def _apply_t2_graphics_injection(self) -> None:
        """
        Automatically inject graphics DeviceProperties for T2 Macs.
        Specifically targets the integrated Intel UHD Graphics 630 on MacBookPro15,1
        This method is ONLY called for T2 Macs to ensure non-T2 systems are not affected.
        """
        # Only inject graphics properties if this is MacBookPro15,1
        if not self._is_macbookpro15_1():
            logging.info("- Skipping graphics injection (not MacBookPro15,1)")
            return
        
        logging.info("- T2 MacBookPro15,1 detected: Injecting graphics DeviceProperties")
        
        # Ensure DeviceProperties structure exists
        if "DeviceProperties" not in self.config:
            self.config["DeviceProperties"] = {}
        if "Add" not in self.config["DeviceProperties"]:
            self.config["DeviceProperties"]["Add"] = {}
        
        # Graphics device path for integrated UHD Graphics 630
        graphics_path = "PciRoot(0x0)/Pci(0x2,0x0)"
        
        # Initialize or merge with existing graphics properties
        if graphics_path not in self.config["DeviceProperties"]["Add"]:
            self.config["DeviceProperties"]["Add"][graphics_path] = {}
        
        # Inject required graphics properties
        graphics_properties = self.config["DeviceProperties"]["Add"][graphics_path]
        
        # AAPL,ig-platform-id - Intel UHD Graphics 630 platform identifier
        logging.info("  > Injecting AAPL,ig-platform-id: 00009B3E (T2-specific)")
        graphics_properties["AAPL,ig-platform-id"] = binascii.unhexlify("00009B3E")
        
        # device-id - Ensure proper device identification
        logging.info("  > Injecting device-id: 9B3E0000 (T2-specific)")
        graphics_properties["device-id"] = binascii.unhexlify("9B3E0000")
        
        # framebuffer-patch-enable - Enable framebuffer patching for compatibility
        logging.info("  > Injecting framebuffer-patch-enable: 01000000 (T2-specific)")
        graphics_properties["framebuffer-patch-enable"] = binascii.unhexlify("01000000")
        
        logging.info("  > Graphics DeviceProperties injection complete for T2 MacBookPro15,1")

    def _apply_t2_memory_descriptor_overrides(self, apple_nvram_uuid: str) -> None:
        """
        Force memory descriptor overrides for T2 Macs to resolve 'populate_value_from_memory_descriptor md is NULL' panic.
        This method ensures critical security settings are forcefully applied to prevent boot failures.
        
        IMPORTANT: This method is ONLY called for T2 Macs. Non-T2 systems will never execute this code.
        """
        logging.info("- Applying mandatory T2 memory descriptor overrides (T2 ONLY)")
        
        # Force memory descriptor settings to prevent NULL reference panics
        logging.info("  > Forcing SecureBootModel to Disabled (T2-specific)")
        self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"
        
        logging.info("  > Forcing DmgLoading to Any (T2-specific)")
        self.config["Misc"]["Security"]["DmgLoading"] = "Any"
        
        logging.info("  > Forcing ApECID to 0 (T2-specific)")
        self.config["Misc"]["Security"]["ApECID"] = 0
        
        # Force required boot-args for T2 to bypass Root Hash verification and fix hanging/black screen issues
        logging.info("  > Injecting critical T2-only boot-args")
        logging.info("    - amfi=0x80 (disable AMFI)")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "amfi=0x80")
        
        logging.info("    - amfi_get_out_of_my_way=1 (remove AMFI from execution - T2 ONLY)")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "amfi_get_out_of_my_way=1")
        
        logging.info("    - ipc_control_port_options=0 (fix Setup hanging/black screen - T2 ONLY)")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "ipc_control_port_options=0")

    def _build(self) -> None:
        """
        Kick off Security Build Process
        """

        # UUID Constants for readability
        APPLE_NVRAM_UUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
        OCLP_NVRAM_UUID = "4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102"

        if self._is_t2_mac():
            logging.info("- T2 Mac detected: applying external T2 security fallback values")
            self._apply_t2_security_fallback(self._get_t2_security_fallback(), APPLE_NVRAM_UUID)
            
            # Apply mandatory T2-specific memory descriptor overrides
            logging.info("- Applying T2-specific memory descriptor fixes")
            self._apply_t2_memory_descriptor_overrides(APPLE_NVRAM_UUID)
            
            # Inject graphics properties for T2 Mac models that require it
            logging.info("- Applying T2 graphics property injection")
            self._apply_t2_graphics_injection()
        elif self.constants.sip_status is False or self.constants.custom_sip_value:
            # Work-around 12.3 bug where Electron apps no longer launch with SIP lowered
            logging.info("- Adding ipc_control_port_options=0 to boot-args")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "ipc_control_port_options=0")

            # Adds AutoPkgInstaller for Automatic OpenCore-Patcher installation
            if self.constants.wxpython_variant is True:
                support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                    "AutoPkgInstaller.kext", self.constants.autopkg_version, self.constants.autopkg_path
                )

            if self.constants.custom_sip_value:
                logging.info(f"- Setting SIP value to: {self.constants.custom_sip_value}")
                sip_hex = utilities.string_to_hex(self.constants.custom_sip_value.lstrip("0x"))
                self._set_nvram_value(APPLE_NVRAM_UUID, "csr-active-config", sip_hex, overwrite=True)
            
            elif self.constants.sip_status is False:
                logging.info("- Set SIP to allow Root Volume patching")
                self._set_nvram_value(APPLE_NVRAM_UUID, "csr-active-config", binascii.unhexlify("03080000"), overwrite=True)

            # apfs.kext FileVault patch
            logging.info("- Allowing FileVault on Root Patched systems")
            support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(
                self.config["Kernel"]["Patch"], "Comment", "Force FileVault on Broken Seal"
            )["Enabled"] = True
            
            self._update_nvram_string(OCLP_NVRAM_UUID, "OCLP-Settings", "-allow_fv")

            # Patch KC UUID panics due to RSR installation
            logging.info("- Enabling KC UUID mismatch patch")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-nokcmismatchpanic")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                "RSRHelper.kext", self.constants.rsrhelper_version, self.constants.rsrhelper_path
            )

        if self.constants.disable_cs_lv is True:
            if self.constants.disable_amfi is True:
                if self._is_t2_mac():
                    logging.info("- Disabling AMFI on T2 Macs (T2 ONLY)")
                    self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "amfi=0x80 amfi_get_out_of_my_way=1")
                else:
                    logging.info("- Disabling AMFI on non-T2 Macs")
                    self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "amfi=0x80")
            else:
                logging.info("- Disabling Library Validation")
                support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(
                    self.config["Kernel"]["Patch"], "Comment", "Disable Library Validation Enforcement"
                )["Enabled"] = True
                support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(
                    self.config["Kernel"]["Patch"], "Comment", "Disable _csr_check() in _vnode_check_signature"
                )["Enabled"] = True
                
                self._update_nvram_string(OCLP_NVRAM_UUID, "OCLP-Settings", "-allow_amfi")
                support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                    "CSLVFixup.kext", self.constants.cslvfixup_version, self.constants.cslvfixup_path
                )

        # Only apply secure_status override for non-T2 Macs (T2 Macs use dedicated T2 memory descriptor overrides)
        if self.constants.secure_status is False and not self._is_t2_mac():
            logging.info("- Disabling SecureBootModel")
            self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"

        if smbios_data.smbios_dictionary[self.model]["Max OS Supported"] < os_data.os_data.sonoma:
            logging.info("- Enabling AMFIPass")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                "AMFIPass.kext", self.constants.amfipass_version, self.constants.amfipass_path
            )

        # ========================================================================================
        # FINAL T2 MEMORY DESCRIPTOR OVERRIDE PASS - Ensure values are not overwritten
        # ========================================================================================
        # This must be the LAST operation in _build() to guarantee T2 security fixes persist
        # NON-T2 MACS ARE NOT AFFECTED - This entire block is skipped for non-T2 systems
        if self._is_t2_mac():
            logging.info("- Final T2 memory descriptor override pass (ensuring no overwrites - T2 ONLY)")
            
            # Hard override security settings - these are non-negotiable for T2 boot stability
            logging.info("  > Re-applying final SecureBootModel=Disabled override (T2 ONLY)")
            self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"
            
            logging.info("  > Re-applying final ApECID=0 override (T2 ONLY)")
            self.config["Misc"]["Security"]["ApECID"] = 0
            
            logging.info("  > Re-applying final DmgLoading=Any override (T2 ONLY)")
            self.config["Misc"]["Security"]["DmgLoading"] = "Any"
            
            # Ensure required T2-specific boot-args are present in final configuration
            logging.info("  > Verifying critical T2-only boot-args are present")
            logging.info("    - amfi=0x80 (T2 ONLY)")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "amfi=0x80")
            
            logging.info("    - amfi_get_out_of_my_way=1 (T2 ONLY - must not be on non-T2)")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "amfi_get_out_of_my_way=1")
            
            logging.info("    - ipc_control_port_options=0 (T2 ONLY - fixes Setup hanging/black screen)")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "ipc_control_port_options=0")
            
            logging.info("  > T2 memory descriptor overrides finalized - ready for boot")
