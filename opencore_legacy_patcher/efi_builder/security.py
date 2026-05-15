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
    "MacBookPro16,2",  # 13-inch 2020 (4 TB3)
    "MacBookPro16,3",  # 13-inch 2020 (2 TB3)
}

# T2 Mac models that do not have an Intel iGPU, or where iGPU injection
# is not required/recommended.
_T2_NO_IGPU_MODELS = {
    "MacPro7,1",       # Mac Pro 2019
    "iMacPro1,1",      # iMac Pro 2017
    "iMac19,1",        # iMac 27-inch 2019 (Radeon only, no iGPU injection needed)
    "iMac19,2",        # iMac 21.5-inch 2019
    "iMac20,1",        # iMac 27-inch 2020
    "iMac20,2",        # iMac 27-inch 2020 CTO
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

    def _update_nvram_string(self, uuid: str, key: str, value: str) -> None:
        """
        Appends boot-arg tokens to an NVRAM string variable, only for
        tokens not already present.

        Uses token-based deduplication (split on whitespace) to avoid
        substring false-positives. For example, "amfi=0x80" must NOT be
        treated as already present just because the current value contains
        "amfi=0x80 amfi_get_out_of_my_way=1" — they are separate tokens.
        """
        if uuid not in self.config["NVRAM"]["Add"]:
            self.config["NVRAM"]["Add"][uuid] = {}

        current_value = self.config["NVRAM"]["Add"][uuid].get(key, "")

        existing_tokens = set(current_value.split())
        new_tokens = value.strip().split()

        tokens_to_add = [t for t in new_tokens if t not in existing_tokens]
        if not tokens_to_add:
            return  # all tokens already present

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
        if uuid not in self.config["NVRAM"]["Add"]:
            self.config["NVRAM"]["Add"][uuid] = {}

        if overwrite or key not in self.config["NVRAM"]["Add"][uuid]:
            self.config["NVRAM"]["Add"][uuid][key] = value

    # ------------------------------------------------------------------
    # Model detection helpers
    # ------------------------------------------------------------------

    def _is_t2_mac(self) -> bool:
        """Return True if the current model has a T2 security chip."""
        return "T2_CHIP" in self.constants.device_properties.get(self.model, {}).get("Features", [])

    def _requires_t2_graphics_injection(self) -> bool:
        """Return True if this T2 model needs Intel graphics injection."""
        return (self.model in _T2_UHD630_MODELS or self.model in _T2_UHD617_MODELS or self.model in _T2_IRIS_PLUS_MODELS)

    def _should_skip_t2_graphics_injection(self) -> bool:
        """Return True if this T2 model should explicitly skip Intel graphics injection."""
        return self.model in _T2_NO_IGPU_MODELS

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
        """
        Inject connector-less Intel UHD 630 DeviceProperties for T2 Mac
        models listed in _T2_UHD630_MODELS.

        WHY connector-less ig-platform-id 0x3E9B0006 (bytes: 06 00 9B 3E)?
        -------------------------------------------------------------------        
        macOS Tahoe changed the ordering of APFS volume group initialization
        relative to GPU framebuffer enumeration. With a display-connected
        ig-platform-id (e.g., bytes: 00 00 9B 3E = 0x3E9B0000), the Intel
        framebuffer driver probes all connectors during early boot, stalling
        the IOService tree long enough that APFS fails with:

            nx_get_volume_group:669  - volume groups tree is not set up yet
            getVolumeGroupMountFrom:10003 - failed with error 2

        Using ig-platform-id 0x3E9B0006 (bytes: 06 00 9B 3E) tells
        AppleIntelCFLGraphicsFramebuffer to skip connector enumeration at
        boot, allowing APFS volume groups to mount before the GPU resumes
        display initialization.

        Non-T2 Macs are never affected—this method is only reachable
        when _is_t2_mac() is True AND the the model is in _T2_UHD630_MODELS
        or _T2_UHD617_MODELS.
        """
        if self._should_skip_t2_graphics_injection():
            logging.info(f"- Skipping Intel graphics injection for {self.model} (no iGPU or not required)")
            return

        if not self._requires_t2_graphics_injection():
            logging.info(f"- Skipping Intel graphics injection for {self.model} (not in supported iGPU list)")
            return

        logging.info(f"- {self.model}: Injecting connector-less UHD630 DeviceProperties (Tahoe fix)")

        if "DeviceProperties" not in self.config:
            self.config["DeviceProperties"] = {}
        if "Add" not in self.config["DeviceProperties"]:
            self.config["DeviceProperties"]["Add"] = {}

        graphics_path = "PciRoot(0x0)/Pci(0x2,0x0)"
        if graphics_path not in self.config["DeviceProperties"]["Add"]:
            self.config["DeviceProperties"]["Add"][graphics_path] = {}

        gfx = self.config["DeviceProperties"]["Add"][graphics_path]

        if self.model in _T2_IRIS_PLUS_MODELS:
            # v1.0.6: Intel Iris Plus (Coffee Lake-U GT3)
            # Using platform 0x3EA50009 (Connector-less) to fix Tahoe devfs stall.
            # Little-endian: 09 00 A5 3E
            logging.info("  > Injecting AAPL,ig-platform-id: 0900A53E (Iris Plus U-series)")
            gfx["AAPL,ig-platform-id"] = binascii.unhexlify("0900A53E")
            logging.info("  > device-id = A5 3E 00 00")
            gfx["device-id"] = binascii.unhexlify("A53E0000")
        else:
            # Branch for Coffee Lake GT2 (UHD 630 / 15-inch / Mac mini)
            # little-endian bytes: 06 00 9B 3E → platform 0x3E9B0006
            gfx["AAPL,ig-platform-id"] = binascii.unhexlify("06009B3E")
            logging.info("  > device-id = 9B 3E 00 00")
            gfx["device-id"] = binascii.unhexlify("9B3E0000")

        # Required for any framebuffer-* patch keys to take effect
        logging.info("  > framebuffer-patch-enable = 1")
        gfx["framebuffer-patch-enable"] = binascii.unhexlify("01000000")

        # Mark connector 0 as unused (type 0x4 = VGA/unused) so the driver
        # skips hotplug detection before APFS is ready.
        logging.info("  > framebuffer-con0-enable = 1, con0-type = 04 (unused/connector-less)")
        gfx["framebuffer-con0-enable"] = binascii.unhexlify("01000000")
        gfx["framebuffer-con0-type"]   = binascii.unhexlify("00040000")

        # เพิ่มหน่วยความจำกราฟิกเพื่อป้องกัน UI Stall ในหน้า Recovery
        logging.info("  > framebuffer-stolenmem = 19MB, framebuffer-fbmem = 9MB")
        gfx["framebuffer-stolenmem"]   = binascii.unhexlify("00003001")
        gfx["framebuffer-fbmem"]       = binascii.unhexlify("00009000")

        logging.info("  > T2 UHD630 connector-less injection complete")

    def _apply_t2_memory_descriptor_overrides(self, apple_nvram_uuid: str) -> None:
        """
        Apply mandatory security overrides required for T2 Macs to boot.
        ONLY called inside the T2 branch of _build().
        """
        logging.info("- Applying T2 memory descriptor overrides (T2 ONLY)")

        self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"
        self.config["Misc"]["Security"]["DmgLoading"]      = "Any"
        self.config["Misc"]["Security"]["ApECID"]          = 0

        # Bypassing SMBIOS spoofing for MacBookPro15,1 to fix Trust Cache mismatch
        if self.model == "MacBookPro15,1":
            logging.info("  > Forcing Native SMBIOS (MacBookPro15,1) to prevent Trust Cache mismatch")
            for section in ["Generic", "SMBIOS", "DataHub"]:
                if section in self.config["PlatformInfo"]:
                    self.config["PlatformInfo"][section]["SystemProductName"] = "MacBookPro15,1"

        # Cleaned-up Boot-args for stability
        # -v                             — Verbose mode to debug Panics
        # igfxonln=1                     — Force iGPU online for installer display
        # amfi_get_out_of_my_way=1       — Full AMFI bypass for Tahoe root access
        # ipc_control_port_options=0     — Critical T2 security stall fix
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "amfi=0x80")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "amfi_get_out_of_my_way=1")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "ipc_control_port_options=0")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "-v")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "igfxonln=1")

        # Legacy / Secondary boot-args
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "-disable_sidecar_mac")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "amfi_check_dyld_policy_at_eval=0")
        # Force bypass of the strict Cryptex security subsystem and runtime trust evaluations
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "cryptex=0")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "amfi_allow_any_signature=1")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "cs_allow_invalid=1")
        # resolving stall at dev_init:303 on macOS Tahoe (T2 ONLY)
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "nvme_shutdown_timestamp=0")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "keepsyms=1")

        logging.info("  > T2 memory descriptor overrides applied")

    def _apply_t2_kernel_patches_tahoe(self) -> None:
        """
        Inject Kernel patches for macOS Tahoe (25.x/26.x) to resolve:
        - USB/Mouse handshake stall
        - AppleSEPManager SEPOS kernel panic
        - AppleIntelUSBXHC Timeout (0x0A -> 0xFF)
        """
        if not self._is_t2_mac():
            return

        logging.info("- Injecting T2-specific Kernel patches for macOS Tahoe")

        kernel_patches = self.config["Kernel"]["Patch"]

        def patch_exists(comment: str) -> bool:
            return any(p.get("Comment") == comment for p in kernel_patches)

        # 1. Bypass AppleIntelUSBXHC T2 handshake
        # Prevents USB/Mouse from freezing during early boot
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
        # Resolves UI Stall on MacBookPro15,1 and other T2 Macs (Tahoe fix)
        if not patch_exists("Increase T2 USB Timeout (UI Stall fix)"):
            logging.info("  > Adding AppleIntelUSBXHC Timeout patch (0x0A -> 0xFF)")
            kernel_patches.append({
                "Arch": "x86_64",
                "Comment": "Increase T2 USB Timeout (UI Stall fix)",
                "Enabled": True,
                "Identifier": "com.apple.driver.usb.AppleUSBXHCI",
                "Find": binascii.unhexlify("BA0A000000"),      # 10ms timeout
                "Replace": binascii.unhexlify("BAFF000000"),   # 255ms timeout (T2 Handshake fix)
                "MinKernel": "25.0.0"                          # Matches Tahoe Kernel
            })

        # 3. Patch AppleSEPManager to change panic to return
        # Resolves SEPOS kernel panic during initialization
        if not patch_exists("Patch AppleSEPManager panic to return (Tahoe fix)"):
            kernel_patches.append({
                "Arch": "x86_64",
                "Comment": "Patch AppleSEPManager panic to return (Tahoe fix)",
                "Enabled": True,
                "Identifier": "com.apple.driver.AppleSEPManager",
                "Find": binascii.unhexlify("4883BFB003000000754F"),   # Check SEPOS status
                "Replace": binascii.unhexlify("31C0C390909090909090"),# Return Success (0)
                "MinKernel": "25.0.0"                                 # Target macOS 26 (Tahoe)
            })

        # 4. Bypass InternalHubPowerCheck in AppleIntelUSBXHC
        # ป้องกันระบบค้างรอสถานะการจ่ายไฟของ USB Hub บนชิป T2
        if not patch_exists("Bypass InternalHubPowerCheck (Tahoe fix)"):
            logging.info("  > Adding InternalHubPowerCheck bypass patch")
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
        # Resolves Touch Bar stall/hang on macOS Tahoe
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
        """
        Kick off Security Build Process.
        """

        APPLE_NVRAM_UUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
        OCLP_NVRAM_UUID  = "4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102"

        # ==============================================================
        # Branch A: T2 Mac
        # ==============================================================
        if self._is_t2_mac():
            logging.info("- T2 Mac detected — applying T2 security settings")

            self._apply_t2_security_fallback(self._get_t2_security_fallback(), APPLE_NVRAM_UUID)
            self._apply_t2_memory_descriptor_overrides(APPLE_NVRAM_UUID)

            # Graphics injection must run here (before the final override
            # pass at the bottom) so the connector-less platform-id is in
            # place before Tahoe's APFS volume group init window closes.
            self._apply_t2_graphics_injection()
            self._apply_t2_kernel_patches_tahoe()

        # ==============================================================
        # Branch B: Non-T2 Mac with SIP lowered
        # ==============================================================
        elif self.constants.sip_status is False or self.constants.custom_sip_value:
            logging.info("- Non-T2 Mac: SIP lowered — applying SIP-related settings")

            # Work-around macOS 12.3+ bug: Electron apps fail with SIP lowered
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
                self._set_nvram_value(
                    APPLE_NVRAM_UUID, "csr-active-config",
                    binascii.unhexlify("03080000"), overwrite=True
                )

            # apfs.kext FileVault patch
            logging.info("- Allowing FileVault on Root Patched systems")
            support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(
                self.config["Kernel"]["Patch"], "Comment", "Force FileVault on Broken Seal"
            )["Enabled"] = True
            self._update_nvram_string(OCLP_NVRAM_UUID, "OCLP-Settings", "-allow_fv")

            # Patch KC UUID panics caused by RSR installation
            logging.info("- Enabling KC UUID mismatch patch")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-nokcmismatchpanic")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                "RSRHelper.kext", self.constants.rsrhelper_version, self.constants.rsrhelper_path
            )

        # ==============================================================
        # Shared: AMFI / Library Validation (T2 and non-T2)
        # ==============================================================
        if self.constants.disable_cs_lv is True:
            if self.constants.disable_amfi is True:
                if self._is_t2_mac():
                    logging.info("- Disabling AMFI (T2 Mac)")
                    self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "amfi=0x80")
                    self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "amfi_check_dyld_policy_at_eval=0")
                else:
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

        # Non-T2 only: SecureBootModel override
        # (T2 equivalent lives in _apply_t2_memory_descriptor_overrides)
        if self.constants.secure_status is False and not self._is_t2_mac():
            logging.info("- Disabling SecureBootModel (non-T2)")
            self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"

        if smbios_data.smbios_dictionary[self.model]["Max OS Supported"] < os_data.os_data.sonoma:
            logging.info("- Enabling AMFIPass")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                "AMFIPass.kext", self.constants.amfipass_version, self.constants.amfipass_path
            )

        # ==============================================================
        # FINAL T2 OVERRIDE PASS
        # Must be the LAST operation in _build() — guarantees no earlier
        # code can overwrite T2 security settings.
        # Non-T2 Macs: this block is skipped entirely.
        # ==============================================================
        if self._is_t2_mac():
            logging.info("- Final T2 override pass (T2 ONLY — ensures no overwrites)")

            self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"
            self.config["Misc"]["Security"]["ApECID"]          = 0
            self.config["Misc"]["Security"]["DmgLoading"]      = "Any"

            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "amfi=0x80")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "igfxonln=1")             # Force UHD 630 online to prevent UI stall
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "igfxnoredir=1")         # Fix white/frozen screen on 15,1
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "forceRenderStandby=0")    # Prevent GPU power saving UI hang
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-disable_media_analysis") # Reduce background processing
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "agdpmod=vit9696")         # Disable board ID checks
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "igfxfw=2")               # Force Apple Graphics Firmware
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "amfi_check_dyld_policy_at_eval=0")
            # Force bypass of the strict Cryptex security subsystem and runtime trust evaluations
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "cryptex=0")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "amfi_allow_any_signature=1")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "cs_allow_invalid=1")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "ipc_control_port_options=0") # Improve T2 communication stall fix
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-disable_sidecar_mac")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "usbmuxd=0x3")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "nvme_shutdown_timestamp=0")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "keepsyms=1")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "apfs_nvidia_restrict=0")

            # Force APFS to bypass broken snapshot chains and relax root DMG trust signatures
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "apfs_read_only_nodownloads=1")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "root_dmg_trust_level=0")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-rootdmgboot")

            logging.info("  > T2 final overrides complete — ready for boot")