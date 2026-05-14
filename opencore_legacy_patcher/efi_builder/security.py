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

    def _build(self) -> None:
        """
        Kick off Security Build Process
        """

        # UUID Constants for readability
        APPLE_NVRAM_UUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
        OCLP_NVRAM_UUID = "4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102"

        # Helper to detect T2 with fallback
        def is_t2_model(model) -> bool:
            if hasattr(self.constants, "device_properties"):
                if "T2_CHIP" in self.constants.device_properties.get(model, {}).get("Features", []):
                    return True
            # Fallback list of known T2 models
            t2_models = ["MacBookAir8,1", "MacBookAir8,2", "MacBookAir9,1", "Macmini8,1",
                         "iMacPro1,1", "MacBookPro15,2", "MacBookPro15,1", "MacBookPro15,3",
                         "MacBookPro15,4", "MacBookPro16,1", "MacBookPro16,3", "MacBookPro16,4"]
            return model in t2_models

        if self.constants.sip_status is False or self.constants.custom_sip_value:
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
                if is_t2_model(self.model):
                    logging.info("- T2 Mac Detected: Set SIP for root patching (03080000)")
                    self._set_nvram_value(APPLE_NVRAM_UUID, "csr-active-config", binascii.unhexlify("03080000"), overwrite=True)
                    logging.info("- Disabling Authenticated Root for T2 Macs")
                    self._set_nvram_value(APPLE_NVRAM_UUID, "auth-root-status", binascii.unhexlify("00"), overwrite=True)
                    logging.info("- Adding T2 AMFI bypass boot args")
                    self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "amfi_get_out_of_my_way=1 cs_allow_invalid=1")
                else:
                    logging.info("- Set SIP to allow Root Volume patching on non-T2 Macs")
                    self._set_nvram_value(APPLE_NVRAM_UUID, "csr-active-config", binascii.unhexlify("03080000"), overwrite=True)
                
                # Add Authenticated Root override to reduce "Need authenticator (81)" errors
                self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-arv")

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
                if is_t2_model(self.model):
                    logging.info("- Disabling AMFI on T2 Macs")
                    self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "amfi=0x80 amfi_get_out_of_my_way=1 cs_allow_invalid=1")
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

        if self.constants.secure_status is False:
            logging.info("- Disabling SecureBootModel")
            self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"

        if smbios_data.smbios_dictionary[self.model]["Max OS Supported"] < os_data.os_data.sonoma:
            logging.info("- Enabling AMFIPass")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                "AMFIPass.kext", self.constants.amfipass_version, self.constants.amfipass_path
            )

        if is_t2_model(self.model):
            logging.info("- T2 Mac Detected: Forcing SecureBootModel to Disabled for Tahoe")
            self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"
            
            logging.info("- Setting ApECID to 0")
            self.config["Misc"]["Security"]["ApECID"] = 0
            if "UEFI" not in self.config:
                self.config["UEFI"] = {}
            if "Quirks" not in self.config["UEFI"]:
                self.config["UEFI"]["Quirks"] = {}
            self.config["UEFI"]["Quirks"]["ReleaseUsbOwnership"] = True
            
            self.config["Misc"]["Security"]["DmgLoading"] = "Any"
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-v")

            logging.info("- Forcing T2 NVRAM overrides for root patching and bypass policy")
            self._set_nvram_value(APPLE_NVRAM_UUID, "csr-active-config", binascii.unhexlify("03080000"), overwrite=True)
            self._set_nvram_value(APPLE_NVRAM_UUID, "auth-root-status", binascii.unhexlify("00"), overwrite=True)
            for arg in ["vmmroot=1", "amfi_get_out_of_my_way=1", "-arv"]:
                self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", arg)
