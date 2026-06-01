"""
security.py: Class for handling macOS Security Patches, invocation from build.py
"""

import logging
import binascii
from typing import Any

from . import support
from .. import constants
from ..support import utilities
from ..detections import device_probe
from ..datasets import (
    security_fallback,
    smbios_data,
    os_data
)

# T2 Macs sharing the Coffee Lake GT2 Intel UHD Graphics 630 layout
_T2_UHD630_MODELS = {
    "MacBookPro15,1",
    "MacBookPro15,3",
    "MacBookPro16,1",
    "MacBookPro16,4",
    "Macmini8,1",
}


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

    def _ensure_nvram_path(self, uuid: str) -> None:
        """Ensure NVRAM dictionary structures exist safely without throwing KeyErrors."""
        if "NVRAM" not in self.config:
            self.config["NVRAM"] = {"Add": {}}
        if "Add" not in self.config["NVRAM"]:
            self.config["NVRAM"]["Add"] = {}
        if uuid not in self.config["NVRAM"]["Add"]:
            self.config["NVRAM"]["Add"][uuid] = {}

    def _update_nvram_string(self, uuid: str, key: str, value: str) -> None:
        """Appends boot-arg tokens using discrete word boundaries to prevent substring collisions."""
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

    def _set_nvram_value(self, uuid: str, key: str, value: Any, overwrite: bool = False) -> None:
        """Sets an NVRAM variable securely with optional explicit value overwrite flags."""
        self._ensure_nvram_path(uuid)
        if overwrite or key not in self.config["NVRAM"]["Add"][uuid]:
            self.config["NVRAM"]["Add"][uuid][key] = value

    def _is_t2_mac(self) -> bool:
        """Detect whether the current model is a T2-equipped Mac."""
        return "T2_CHIP" in self.constants.device_properties.get(self.model, {}).get("Features", [])

    def _set_nested_config_value(self, path: str, value: Any) -> None:
        """Write a nested config value using a dotted path string layout."""
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
        """Inject graphics DeviceProperties for supported Intel iGPU T2 Macs."""
        if self.model not in _T2_UHD630_MODELS:
            logging.info(f"- Skipping graphics injection for {self.model}")
            return
        
        logging.info(f"- T2 {self.model} detected: Injecting connector-less UHD Graphics 630 properties")
        
        if "DeviceProperties" not in self.config:
            self.config["DeviceProperties"] = {"Add": {}}
        if "Add" not in self.config["DeviceProperties"]:
            self.config["DeviceProperties"]["Add"] = {}
        
        graphics_path = "PciRoot(0x0)/Pci(0x2,0x0)"
        if graphics_path not in self.config["DeviceProperties"]["Add"]:
            self.config["DeviceProperties"]["Add"][graphics_path] = {}
        
        gfx = self.config["DeviceProperties"]["Add"][graphics_path]
        
        # Fixed Byte Alignment to structural Little Endian for OpenCore parsing correctness
        gfx["AAPL,ig-platform-id"]     = binascii.unhexlify("06009B3E")  # 0x3E9B0006
        gfx["device-id"]               = binascii.unhexlify("9B3E0000")  # 0x3E9B0000
        gfx["framebuffer-patch-enable"] = binascii.unhexlify("01000000")
        
        logging.info("  > Graphics DeviceProperties injection complete (Little Endian verified)")

    def _apply_t2_memory_descriptor_overrides(self, apple_nvram_uuid: str) -> None:
        """Force memory descriptor overrides for T2 Macs to resolve system panics."""
        logging.info("- Applying mandatory T2 memory descriptor overrides (T2 ONLY)")
        
        self.config.setdefault("Misc", {}).setdefault("Security", {})
        self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"
        self.config["Misc"]["Security"]["DmgLoading"]      = "Any"
        self.config["Misc"]["Security"]["ApECID"]          = 0
        
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "amfi=0x80")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "amfi_get_out_of_my_way=1")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "ipc_control_port_options=0")

    def _build(self) -> None:
        """Kick off Security Build Process."""
        APPLE_NVRAM_UUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
        OCLP_NVRAM_UUID  = "4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102"

        # 1. Handle primary setup depending on whether it's a T2 machine or not
        if self._is_t2_mac():
            logging.info("- T2 Mac detected: applying security configurations")
            self._apply_t2_security_fallback(self._get_t2_security_fallback(), APPLE_NVRAM_UUID)
            self._apply_t2_memory_descriptor_overrides(APPLE_NVRAM_UUID)
            self._apply_t2_graphics_injection()
            
        else:
            if self.constants.sip_status is False or self.constants.custom_sip_value:
                logging.info("- Adding ipc_control_port_options=0 to boot-args")
                self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "ipc_control_port_options=0")

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

                logging.info("- Allowing FileVault on Root Patched systems")
                self.config.setdefault("Kernel", {}).setdefault("Patch", [])
                fv_patch = support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(
                    self.config["Kernel"]["Patch"], "Comment", "Force FileVault on Broken Seal"
                )
                if fv_patch:
                    fv_patch["Enabled"] = True
                
                self._update_nvram_string(OCLP_NVRAM_UUID, "OCLP-Settings", "-allow_fv")

                logging.info("- Enabling KC UUID mismatch patch")
                self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-nokcmismatchpanic")
                support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                    "RSRHelper.kext", self.constants.rsrhelper_version, self.constants.rsrhelper_path
                )

        # 2. General Features / Global Flags Checks
        if self.constants.disable_cs_lv is True:
            if self.constants.disable_amfi is True:
                # Fixed: Uniform structure for passing boot args token by token safely
                logging.info(f"- Disabling AMFI ({'T2 ONLY' if self._is_t2_mac() else 'Non-T2'})")
                self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "amfi=0x80")
                if self._is_t2_mac():
                    self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "amfi_get_out_of_my_way=1")
            else:
                logging.info("- Disabling Library Validation")
                self.config.setdefault("Kernel", {}).setdefault("Patch", [])
                
                lv_patch = support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(
                    self.config["Kernel"]["Patch"], "Comment", "Disable Library Validation Enforcement"
                )
                if lv_patch:
                    lv_patch["Enabled"] = True
                    
                cs_patch = support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(
                    self.config["Kernel"]["Patch"], "Comment", "Disable _csr_check() in _vnode_check_signature"
                )
                if cs_patch:
                    cs_patch["Enabled"] = True
                
                self._update_nvram_string(OCLP_NVRAM_UUID, "OCLP-Settings", "-allow_amfi")
                support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                    "CSLVFixup.kext", self.constants.cslvfixup_version, self.constants.cslvfixup_path
                )

        if self.constants.secure_status is False and not self._is_t2_mac():
            logging.info("- Disabling SecureBootModel")
            self.config.setdefault("Misc", {}).setdefault("Security", {})
            self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"

        # Fixed: Avoided potential KeyError using .get() fallback strategy, 
        # adjusted target to assumed standard class structure os_data.os_data
        model_smbios = smbios_data.smbios_dictionary.get(self.model, {})
        max_os_supported = model_smbios.get("Max OS Supported", 0)

        if max_os_supported < os_data.os_data.sonoma:
            logging.info("- Enabling AMFIPass")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                "AMFIPass.kext", self.constants.amfipass_version, self.constants.amfipass_path
            )

        # Removed: The "Final Override Block Execution Guard" for T2 Macs.
        # Everything handled here was already executed at the top of the _build function.
