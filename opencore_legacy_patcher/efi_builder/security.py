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
    model_array,
    security_fallback,
    smbios_data,
    os_data
)

# T2 Mac models that use Intel UHD 630 and require connector-less
# ig-platform-id injection to avoid APFS volume group race condition
# on macOS Tahoe and later. (Coffee Lake GT2)
_T2_UHD630_MODELS = {
    "MacBookPro15,1",  # 15-inch 2018 (UHD630 + Radeon)
    "MacBookPro15,3",  # 15-inch 2019 (UHD630 + Radeon)
    "MacBookPro16,1",  # 16-inch 2019 (UHD630 + Radeon)
    "MacBookPro16,4",  # 16-inch 2019 CTO (UHD630 + Radeon)
    "Macmini8,1",      # Mac mini 2018 (UHD630)
}

# T2 Mac models with Intel Iris Plus Graphics (U-Series)
# Required for v1.0.6 logic isolation (iGPU-only).
_T2_IRIS_PLUS_MODELS = {
    "MacBookPro15,2",  # 13-inch 2018 (4 TB3)
    "MacBookPro15,4",  # 13-inch 2019 (2 TB3)
}

# T2 Mac models that use Intel UHD 617 and require graphics injection for stability.
_T2_UHD617_MODELS = {
    "MacBookAir8,1",   # Air 2018
    "MacBookAir8,2",   # Air 2019
    "MacBookAir9,1",   # Air 2020 Intel
    "MacBookPro16,3",  # 13-inch 2020 (2 TB3) — Amber Lake UHD 617
}

# T2 Mac models that do not have an Intel iGPU, or where iGPU injection
# is not required/recommended.
_T2_NO_IGPU_MODELS = {
    "iMacPro1,1",      # iMac Pro 2017
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

    # ------------------------------------------------------------------
    # NVRAM helpers
    # ------------------------------------------------------------------

    def _read_nvram_string(self, uuid: str, key: str) -> str:
        """Utility helper to read an existing NVRAM string safely."""
        if uuid in self.config.get("NVRAM", {}).get("Add", {}):
            return self.config["NVRAM"]["Add"][uuid].get(key, "")
        return ""

    def _update_nvram_string(self, uuid: str, key: str, value: str) -> None:
        """
        Appends boot-arg tokens to an NVRAM string variable, only for
        tokens not already present.
        """
        if "NVRAM" not in self.config:
            self.config["NVRAM"] = {"Add": {}}
        if "Add" not in self.config["NVRAM"]:
            self.config["NVRAM"]["Add"] = {}
        if uuid not in self.config["NVRAM"]["Add"]:
            self.config["NVRAM"]["Add"][uuid] = {}

        current_value = self.config["NVRAM"]["Add"][uuid].get(key, "")

        existing_tokens = set(current_value.split())
        new_tokens = value.strip().split()

        tokens_to_add = [t for t in new_tokens if t not in existing_tokens]
        if not tokens_to_add:
            return

        if current_value.strip():
            self.config["NVRAM"]["Add"][uuid][key] = (
                current_value.rstrip() + " " + " ".join(tokens_to_add)
            )
        else:
            self.config["NVRAM"]["Add"][uuid][key] = " ".join(tokens_to_add)

    def _set_nvram_value(self, uuid: str, key: str, value: any, overwrite: bool = False) -> None:
        """
        Sets an NVRAM variable. If overwrite is False, only sets if the
        key is absent.
        """
        if "NVRAM" not in self.config:
            self.config["NVRAM"] = {"Add": {}}
        if "Add" not in self.config["NVRAM"]:
            self.config["NVRAM"]["Add"] = {}
        if uuid not in self.config["NVRAM"]["Add"]:
            self.config["NVRAM"]["Add"][uuid] = {}

        if overwrite or key not in self.config["NVRAM"]["Add"][uuid]:
            self.config["NVRAM"]["Add"][uuid][key] = value

    # ------------------------------------------------------------------
    # Model detection helpers
    # ------------------------------------------------------------------

    def _ensure_path(self, *keys, default=dict):
        """Utility helper to ensure a nested dict path exists."""
        node = self.config
        for key in keys:
            node = node.setdefault(key, default() if isinstance(default, type) else default)
        return node

    def _is_t2_mac(self) -> bool:
        """Return True if the current model has a T2 security chip."""
        if self.model in model_array.T2Macs:
            return True
        return "T2_CHIP" in self.constants.device_properties.get(self.model, {}).get("Features", [])

    def _requires_t2_graphics_injection(self) -> bool:
        """Return True if this T2 model needs Intel graphics injection."""
        return (self.model in _T2_UHD630_MODELS or self.model in _T2_UHD617_MODELS or self.model in _T2_IRIS_PLUS_MODELS)

    def _should_skip_t2_graphics_injection(self) -> bool:
        """Return True if this T2 model should explicitly skip Intel graphics injection."""
        return self.model in _T2_NO_IGPU_MODELS

    def _t2_uses_amfipass(self) -> bool:
        """T2 builds enable AMFIPass in misc._t2_handling (runs after security)."""
        return self._is_t2_mac()

    def _apply_t2_amfi_boot_args(self, apple_nvram_uuid: str) -> None:
        """Apply AMFI-related boot-args only when AMFIPass is not the T2 boot path."""
        if self._t2_uses_amfipass():
            logging.info("  > Skipping amfi=0x80 (T2 uses AMFIPass + -amfipassbeta)")
            self._update_nvram_string(apple_nvram_uuid, "boot-args", "amfi_get_out_of_my_way=1")
            return

        # Guard against duplicate insertion of amfi arguments if not using AMFIPass
        existing = self._read_nvram_string(apple_nvram_uuid, "boot-args")
        if "amfi=0x80" not in existing:
            self._update_nvram_string(apple_nvram_uuid, "boot-args", "amfi=0x80")
        if "amfi_get_out_of_my_way=1" not in existing:
            self._update_nvram_string(apple_nvram_uuid, "boot-args", "amfi_get_out_of_my_way=1")
        if "amfi_check_dyld_policy_at_eval=0" not in existing:
            self._update_nvram_string(apple_nvram_uuid, "boot-args", "amfi_check_dyld_policy_at_eval=0")
        if "amfi_allow_any_signature=1" not in existing:
            self._update_nvram_string(apple_nvram_uuid, "boot-args", "amfi_allow_any_signature=1")

    # ------------------------------------------------------------------
    # Graphics injection helpers
    # ------------------------------------------------------------------

    def _get_graphics_device_properties_path(self) -> str:
        """Return the PCI path for the integrated graphics device."""
        return "PciRoot(0x0)/Pci(0x2,0x0)"

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def _set_nested_config_value(self, path: str, value: any) -> None:
        """Write a value into a nested config dict using a dotted path."""
        node = self.config
        keys = path.split('.')
        for part in keys[:-1]:
            if part not in node or not isinstance(node[part], dict):
                node[part] = {}
            node = node[part]
        node[keys[-1]] = value

    # ------------------------------------------------------------------
    # T2 security helpers
    # ------------------------------------------------------------------

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
        """Inject connector-less Intel iGPU DeviceProperties for T2 Macs."""
        if self._should_skip_t2_graphics_injection():
            logging.info(f"- Skipping Intel graphics injection for {self.model} (no iGPU or not required)")
            return

        if not self._requires_t2_graphics_injection():
            logging.info(f"- Skipping Intel graphics injection for {self.model} (not in supported iGPU list)")
            return

        graphics_path = self._get_graphics_device_properties_path()
        self._ensure_path("DeviceProperties", "Add", graphics_path)
        gfx = self.config["DeviceProperties"]["Add"][graphics_path]

        # ── UHD 617 / Iris Plus 655 (Amber Lake GT3e, 0x3EA5) ────────────
        if self.model in _T2_UHD617_MODELS or self.model in _T2_IRIS_PLUS_MODELS:
            logging.info(f"- {self.model}: Injecting connector-less UHD617/Iris Plus DeviceProperties (Tahoe fix)")
            gfx["AAPL,ig-platform-id"] = binascii.unhexlify("0900A53E")  # 0x3EA50009 LE
            gfx["device-id"]           = binascii.unhexlify("A53E0000")  # 0x3EA50000 LE
            
            APPLE_NVRAM_UUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "igfxgl=1")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "igfxmetal=1")
            logging.info("  > Added igfxgl=1 igfxmetal=1 (UHD617 grey screen fix)")

        # ── UHD 630 (Coffee Lake GT2, 0x3E9B) ────────────────────────────
        else:
            logging.info(f"- {self.model}: Injecting connector-less UHD630 DeviceProperties (Tahoe fix)")
            gfx["AAPL,ig-platform-id"] = binascii.unhexlify("06009B3E")  # 0x3E9B0006 LE
            gfx["device-id"]           = binascii.unhexlify("9B3E0000")  # 0x3E9B0000 LE

        # ── Common framebuffer patches (all T2 iGPU models) ──────────────
        gfx["framebuffer-patch-enable"] = binascii.unhexlify("01000000")
        gfx["framebuffer-con0-enable"]  = binascii.unhexlify("01000000")
        gfx["framebuffer-con0-type"]    = binascii.unhexlify("00040000")  # Unused/connector-less
        gfx["framebuffer-stolenmem"]    = binascii.unhexlify("00003001")  # 19 MB
        gfx["framebuffer-fbmem"]        = binascii.unhexlify("00009000")  # 9 MB
        logging.info("  > T2 iGPU connector-less injection complete")

    def _apply_t2_memory_descriptor_overrides(self, apple_nvram_uuid: str) -> None:
        """Apply mandatory security overrides required for T2 Macs to boot."""
        logging.info("- Applying T2 memory descriptor overrides (T2 ONLY)")

        self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"
        self.config["Misc"]["Security"]["DmgLoading"]      = "Any"
        self.config["Misc"]["Security"]["ApECID"]          = 0

        if self.model == "MacBookPro15,1":
            logging.info("  > Forcing Native SMBIOS (MacBookPro15,1) to prevent Trust Cache mismatch")
            for section in ["Generic", "SMBIOS", "DataHub"]:
                if section in self.config.get("PlatformInfo", {}):
                    self.config["PlatformInfo"][section]["SystemProductName"] = "MacBookPro15,1"

        self._apply_t2_amfi_boot_args(apple_nvram_uuid)
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "ipc_control_port_options=0")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "-v")

        if self.constants.detected_os >= os_data.os_data.tahoe:
            self._update_nvram_string(apple_nvram_uuid, "boot-args", "cryptex=0 cs_allow_invalid=1")
        
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "nvme_shutdown_timestamp=0")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "keepsyms=1")

    def _apply_t2_kernel_patches_tahoe(self) -> None:
        """Inject Kernel patches for macOS Tahoe to fix stalls and corecrypto failures."""
        if not self._is_t2_mac():
            return

        logging.info("- Injecting T2-specific Kernel patches for macOS Tahoe")
        self.config.setdefault('Kernel', {}).setdefault('Patch', [])
        kernel_patches = self.config['Kernel']['Patch']

        def patch_exists(comment: str) -> bool:
            return any(p.get("Comment") == comment for p in kernel_patches)

        # 1. Bypass AppleIntelUSBXHC T2 handshake
        if not patch_exists("Bypass T2 USB handshake (Tahoe fix)"):
            kernel_patches.append({
                "Arch": "x86_64",
                "Comment": "Bypass T2 USB handshake (Tahoe fix)",
                "Enabled": True,
                "Identifier": "com.apple.driver.usb.AppleUSBXHCI",
                "Find": binascii.unhexlify("488D3D00000000488B0500000000488B4028FFD0"),
                "Replace": binascii.unhexlify("488D3D00000000488B0500000000488B40289090"),
                "Mask": binascii.unhexlify("FFFFFFF0000000FFFFFFF0000000FFFFFFFFFFFF"),
                "ReplaceMask": binascii.unhexlify("FFFFFFF0000000FFFFFFF0000000FFFFFFFFFFFF"),
                "MinKernel": "25.0.0"
            })

        # 2. Increase AppleIntelUSBXHC Timeout (0x0A -> 0xFF)
        if not patch_exists("Increase T2 USB Timeout (UI Stall fix)"):
            kernel_patches.append({
                "Arch": "x86_64",
                "Comment": "Increase T2 USB Timeout (UI Stall fix)",
                "Enabled": False,
                "Identifier": "com.apple.driver.usb.AppleUSBXHCI",
                "Find": binascii.unhexlify("BA0A000000"),
                "Replace": binascii.unhexlify("BAFF000000"),
                "MinKernel": "25.0.0"
            })

        # 3. Patch AppleSEPManager panic to return
        if not patch_exists("Patch AppleSEPManager panic to return (Tahoe fix)"):
            kernel_patches.append({
                "Arch": "x86_64",
                "Comment": "Patch AppleSEPManager panic to return (Tahoe fix)",
                "Enabled": True,
                "Identifier": "com.apple.driver.AppleSEPManager",
                "Find": binascii.unhexlify("4883BFB003000000754F"),
                "Replace": binascii.unhexlify("31C0C390909090909090"),
                "MinKernel": "25.0.0"
            })

        # 4. Bypass InternalHubPowerCheck
        if not patch_exists("Bypass InternalHubPowerCheck (Tahoe fix)"):
            kernel_patches.append({
                "Arch": "x86_64",
                "Comment": "Bypass InternalHubPowerCheck (Tahoe fix)",
                "Enabled": True,
                "Identifier": "com.apple.driver.usb.AppleUSBXHCI",
                "Find": binascii.unhexlify("4183BC24F80100000075"),
                "Replace": binascii.unhexlify("4183BC24F801000000EB"),
                "MinKernel": "25.0.0"
            })

        # 5. Patch AppleTouchBarHIDEventDriver
        if not patch_exists("Patch AppleTouchBarHIDEventDriver (Tahoe fix)"):
            kernel_patches.append({
                "Arch": "x86_64",
                "Comment": "Patch AppleTouchBarHIDEventDriver (Tahoe fix)",
                "Enabled": True,
                "Identifier": "com.apple.driver.AppleTouchBarHIDEventDriver",
                "Find": binascii.unhexlify("4883C4085B415C415D415E415F5DC3"),
                "Replace": binascii.unhexlify("31C090905B415C415D415E415F5DC3"),
                "MinKernel": "25.0.0"
            })

    # ------------------------------------------------------------------
    # Main build entry point
    # ------------------------------------------------------------------

    def _build(self) -> None:
        """Kick off Security Build Process."""
        APPLE_NVRAM_UUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
        OCLP_NVRAM_UUID  = "4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102"

        # ==============================================================
        # Branch A: T2 Mac Consolidated Security Configuration
        # ==============================================================
        if self._is_t2_mac():
            logging.info("- T2 Mac detected — applying consolidated T2 security settings")
            
            # 1. Base initialization and external fallbacks
            self._apply_t2_security_fallback(self._get_t2_security_fallback(), APPLE_NVRAM_UUID)
            self._apply_t2_memory_descriptor_overrides(APPLE_NVRAM_UUID)
            self._apply_t2_graphics_injection()
            self._apply_t2_kernel_patches_tahoe()

            # 2. Hard Overrides (Guarantees safety against structural contamination)
            logging.info("- Final T2 verification pass (Enforcing absolute boundaries)")
            self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"
            self.config["Misc"]["Security"]["ApECID"]          = 0
            self.config["Misc"]["Security"]["DmgLoading"]      = "Any"

            # 3. Base structural boot arguments
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-v keepsyms=1")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "ipc_control_port_options=0")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "nvme_shutdown_timestamp=0")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-disable_sidecar_mac")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-disable_media_analysis")

            # 4. Scope graphics injection boot-args strictly to active iGPU targets
            if self._requires_t2_graphics_injection():
                self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "igfxonln=1")
                self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "igfxfw=2")
                self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "forceRenderStandby=0")
                self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "agdpmod=vit9696")
                
                if self.model in _T2_UHD630_MODELS:
                    self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "igfxnoredir=1")

            # 5. Scope modern OS bypass flags cleanly
            if self.constants.detected_os >= os_data.os_data.tahoe:
                self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "cryptex=0")
                self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "cs_allow_invalid=1")

            logging.info("  > Final T2 verification complete. Ghost arguments excluded.")
            return  # Clean break: T2 machines completely skip Branch B and Shared evaluations

        # ==============================================================
        # Branch B: Non-T2 Mac with SIP lowered
        # ==============================================================
        if self.constants.sip_status is False or self.constants.custom_sip_value:
            logging.info("- Non-T2 Mac: SIP lowered — applying SIP-related settings")
            
            # Electron app crash fix under modified SIP
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
            support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(
                self.config["Kernel"]["Patch"], "Comment", "Force FileVault on Broken Seal"
            )["Enabled"] = True
            self._update_nvram_string(OCLP_NVRAM_UUID, "OCLP-Settings", "-allow_fv")

            logging.info("- Enabling KC UUID mismatch patch")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-nokcmismatchpanic")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                "RSRHelper.kext", self.constants.rsrhelper_version, self.constants.rsrhelper_path
            )

        # ==============================================================
        # Shared: AMFI / Library Validation (Legacy Non-T2 verification targets)
        # ==============================================================
        if self.constants.disable_cs_lv is True:
            if self.constants.disable_amfi is True:
                logging.info("- Disabling AMFI (non-T2 Mac)")
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
            logging.info("- Disabling SecureBootModel (non-T2)")
            self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"

        if smbios_data.smbios_dictionary[self.model]["Max OS Supported"] < os_data.os_data.sonoma:
            logging.info("- Enabling AMFIPass")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                "AMFIPass.kext", self.constants.amfipass_version, self.constants.amfipass_path
            )
