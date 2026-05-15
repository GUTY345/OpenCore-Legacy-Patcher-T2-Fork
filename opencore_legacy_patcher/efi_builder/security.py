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
# on macOS Tahoe and later.
_T2_UHD630_MODELS = {
    "MacBookPro15,1",  # 15-inch 2018
    "MacBookPro15,3",  # 15-inch 2019 (Vega)
    "MacBookPro16,1",  # 16-inch 2019
    "MacBookPro16,4",  # 16-inch 2019 (CTO)
    "MacBookAir8,1",   # Air 2018
    "MacBookAir8,2",   # Air 2019
    "MacBookAir9,1",   # Air 2020
    "Macmini8,1",      # Mac mini 2018
    "MacPro7,1",       # Mac Pro 2019
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
        """
        Return True if this T2 model needs connector-less Intel UHD 630
        graphics injection to prevent the APFS volume group race condition
        on macOS Tahoe and later.
        """
        return self.model in _T2_UHD630_MODELS

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
        macOS Tahoe changed the ordering of APFS volume group initialisation
        relative to GPU framebuffer enumeration. With a display-connected
        ig-platform-id (e.g. bytes: 00 00 9B 3E = 0x3E9B0000) the Intel
        framebuffer driver probes all connectors during early boot, stalling
        the IOService tree long enough that APFS fails with:

            nx_get_volume_group:669  - volume groups tree is not setup yet
            getVolumeGroupMountFrom:10003 - failed with error 2

        Using ig-platform-id 0x3E9B0006 (bytes: 06 00 9B 3E) tells
        AppleIntelCFLGraphicsFramebuffer to skip connector enumeration at
        boot, allowing APFS volume groups to mount before the GPU resumes
        display initialisation.

        Non-T2 Macs are never affected — this method is only reachable
        when _is_t2_mac() is True AND the model is in _T2_UHD630_MODELS.
        """
        if not self._requires_t2_graphics_injection():
            logging.info(f"- Skipping T2 UHD630 graphics injection (model {self.model} not in list)")
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

        # Connector-less ig-platform-id for Coffee Lake GT2 (UHD 630)
        # little-endian bytes: 06 00 9B 3E → platform 0x3E9B0006
        logging.info("  > AAPL,ig-platform-id = 06 00 9B 3E (connector-less)")
        gfx["AAPL,ig-platform-id"] = binascii.unhexlify("06009B3E")

        # device-id: Intel UHD 630 Coffee Lake GT2, little-endian
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

        # amfi=0x80                        — disable AMFI enforcement
        # amfi_check_dyld_policy_at_eval=0 — allow ASP init to complete before
        #                                     dyld policy enforcement is disabled
        # ipc_control_port_options=0       — fix Setup hanging / black screen
        # -disable_sidecar_mac             — disable Sidecar USB VHCI enumeration
        #                                     that causes AppleUSBVHCIPort to stall
        #                                     on macOS Tahoe during early boot (T2)
        # usbmuxd=0x3                      — restrict usbmuxd to prevent VHCI
        #                                     controller from blocking IOService tree
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "amfi=0x80")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "amfi_check_dyld_policy_at_eval=0")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "ipc_control_port_options=0")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "-disable_sidecar_mac")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "usbmuxd=0x3")
        # nvme_shutdown_timestamp=0 — prevent nx_mount from waiting on
        # NVMe checkpoint timestamp during APFS device_handle init,
        # resolving stall at dev_init:303 on macOS Tahoe (T2 ONLY)
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "nvme_shutdown_timestamp=0")
        # keepsyms=1             — retain kernel symbols so nx_mount journal
        #                          replay can complete without I/O stall at xid
        # apfs_nvidia_restrict=0 — disable APFS GPU restriction check that
        #                          causes checkpoint confirmation to hang (T2)
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "keepsyms=1")
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "apfs_nvidia_restrict=0")

        logging.info("  > T2 memory descriptor overrides applied")

    def _apply_t2_kernel_patches_tahoe(self) -> None:
        """
        Inject Kernel patches for macOS Tahoe (25.x/26.x) to resolve:
        - USB/Mouse handshake stall
        - IOBufferCopyController timeout panic
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
                "Mask": binascii.unhexlify("FFFFFFF0000000FFFFFFF0000000FFFFFFFFFF"),
                "ReplaceMask": binascii.unhexlify("FFFFFFF0000000FFFFFFF0000000FFFFFFFFFF"),
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
                "Find": binascii.unhexlify("BA0A000000"),
                "Replace": binascii.unhexlify("BAFF000000"),
                "MinKernel": "25.0.0"
            })

        # 3. Block com.apple.iokit.IOBufferCopyController
        # Prevents IOBCC timeout panic
        if not patch_exists("Block IOBufferCopyController (Tahoe fix)"):
            kernel_patches.append({
                "Arch": "x86_64",
                "Comment": "Block IOBufferCopyController (Tahoe fix)",
                "Enabled": True,
                "Identifier": "com.apple.iokit.IOBufferCopyController",
                "Find": binascii.unhexlify("554889E5"),
                "Replace": binascii.unhexlify("31C0C390"),
                "MinKernel": "25.0.0"
            })

        # 4. Patch AppleSEPManager to change panic to return
        # Resolves SEPOS kernel panic during initialization
        if not patch_exists("Patch AppleSEPManager panic to return (Tahoe fix)"):
            kernel_patches.append({
                "Arch": "x86_64",
                "Comment": "Patch AppleSEPManager panic to return (Tahoe fix)",
                "Enabled": True,
                "Identifier": "com.apple.driver.AppleSEPManager",
                "Find": binascii.unhexlify("4883BFB003000000754F"),
                "Replace": binascii.unhexlify("C3909090909090909090"),
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
                "Replace": binascii.unhexlify("31C04883C4085B415C415D415E415F5DC3"),
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

            # _update_nvram_string is idempotent via token-based dedup —
            # re-calling here is safe and acts as a final verification step.
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "amfi=0x80")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "igfxonln=1")             # Force UHD 630 online to prevent UI stall
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "forceRenderStandby=0")    # Prevent GPU power saving UI hang
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "agdpmod=vit9696")         # Disable board ID checks
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "igfxfw=2")               # Force Apple Graphics Firmware
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "amfi_check_dyld_policy_at_eval=0")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "ipc_control_port_options=0") # Improve T2 communication stall fix
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-disable_sidecar_mac")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "usbmuxd=0x3")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "nvme_shutdown_timestamp=0")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "keepsyms=1")
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "apfs_nvidia_restrict=0")

            logging.info("  > T2 final overrides complete — ready for boot")