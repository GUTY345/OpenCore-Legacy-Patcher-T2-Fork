"""
security.py: Class for handling macOS Security Patches, invocation from build.py
"""

import logging
import binascii
import sys
import wx
import threading

from . import support
from .. import constants
from ..support import utilities
from ..detections import device_probe
from ..datasets import (
    model_array,
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

# T2 Mac models that use Intel UHD 617 / Ice Lake LP and require graphics injection for stability.
_T2_LOW_POWER_MODELS = {
    "MacBookAir8,1",   # Air 2018
    "MacBookAir8,2",   # Air 2019
    "MacBookAir9,1",   # Air 2020 Intel
    "MacBookPro16,3",  # 13-inch 2020 (2 TB3)
}

# T2 Mac models that do not have an Intel iGPU, or where iGPU injection
# is not required/recommended.
_T2_NO_IGPU_MODELS = {
    "iMacPro1,1",      # iMac Pro 2017
}

_T2_TOUCH_BAR_MODELS = {
    "MacBookPro15,2",  # 13-inch 2018 (4 TB3)
    "MacBookPro15,4",  # 13-inch 2019 (2 TB3)
    "MacBookPro16,3",  # 13-inch 2020 (2 TB3)
    "MacBookPro15,1",  # 15-inch 2018 (UHD630 + Radeon)
    "MacBookPro15,3",  # 15-inch 2019 (UHD630 + Radeon)
    "MacBookPro16,1",  # 16-inch 2019 (UHD630 + Radeon)
    "MacBookPro16,4",  # 16-inch 2019 CTO (UHD630 + Radeon)
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
        self.is_tahoe_target: bool = False

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
        return (self.model in _T2_UHD630_MODELS or self.model in _T2_LOW_POWER_MODELS or self.model in _T2_IRIS_PLUS_MODELS)

    def _should_skip_t2_graphics_injection(self) -> bool:
        """Return True if this T2 model should explicitly skip Intel graphics injection."""
        return self.model in _T2_NO_IGPU_MODELS

    def _t2_uses_amfipass(self) -> bool:
        """T2 builds enable AMFIPass in misc._t2_handling (runs after security)."""
        return self._is_t2_mac()

    def _apply_t2_amfi_boot_args(self, apple_nvram_uuid: str) -> None:
        """Apply AMFI-related boot-args based on user path validation."""
        if self._t2_uses_amfipass():
            logging.info("  > T2 target utilizes AMFIPass layer. Ensuring -amfipassbeta presence.")
            self._update_nvram_string(apple_nvram_uuid, "boot-args", "-amfipassbeta")
            return

        # Fallback if AMFIPass pathing is completely stripped
        existing = self._read_nvram_string(apple_nvram_uuid, "boot-args")
        if "amfi=0x80" not in existing:
            logging.warning("  > AMFIPass bypassed. Falling back to amfi=0x80 absolute drop.")
            self._update_nvram_string(apple_nvram_uuid, "boot-args", "amfi=0x80 amfi_get_out_of_my_way=1")

    # ------------------------------------------------------------------
    # Graphics injection helpers
    # ------------------------------------------------------------------

    def _get_graphics_device_properties_path(self):
        """Return the probed PCI path for the integrated graphics device."""
        if self.constants.custom_model:
            logging.info("- Skipping T2 Intel graphics injection for custom model (no probed iGPU path)")
            return None

        igpu = getattr(self.computer, "igpu", None)
        if igpu and getattr(igpu, "pci_path", None):
            return igpu.pci_path

        for gpu in getattr(self.computer, "gpus", []) or []:
            if isinstance(gpu, device_probe.Intel) and getattr(gpu, "pci_path", None):
                return gpu.pci_path

        logging.info("- Skipping T2 Intel graphics injection (unable to confirm iGPU PCI path)")
        return None

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

    
    def _apply_t2_graphics_injection(self) -> None:
        """Inject connector-less Intel iGPU DeviceProperties for T2 Macs."""
        if self._should_skip_t2_graphics_injection() or not self._requires_t2_graphics_injection():
            logging.info(f"- Skipping Intel graphics injection for {self.model} (no iGPU or not required)")
            return

        graphics_path = self._get_graphics_device_properties_path()
        if not graphics_path:
            return

        self._ensure_path("DeviceProperties", "Add", graphics_path)
        gfx = self.config["DeviceProperties"]["Add"][graphics_path]

        APPLE_NVRAM_UUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"

        if self.model in _T2_LOW_POWER_MODELS:
            logging.info(f"- {self.model}: Injecting connector-less Intel UHD Graphics 617 and Amber Lake DeviceProperties (Tahoe fix)")
            gfx["AAPL,ig-platform-id"] = binascii.unhexlify("0900A53E")  # 0x3EA50009 LE
            gfx["device-id"]           = binascii.unhexlify("A53E0000")  # 0x3EA50000 LE
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "igfxgl=1 igfxmetal=1")
            logging.info("  > Added igfxgl=1 igfxmetal=1 (LP Display sync fix)")

        elif self.model in _T2_IRIS_PLUS_MODELS:
            logging.info(f"- {self.model}: Injecting connector-less Iris Plus DeviceProperties (Tahoe fix)")
            gfx["AAPL,ig-platform-id"] = binascii.unhexlify("0900A53E")  # 0x3EA50009 LE
            gfx["device-id"]           = binascii.unhexlify("A53E0000")  # 0x3EA50000 LE
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "igfxgl=1 igfxmetal=1")
            logging.info("  > Added igfxgl=1 igfxmetal=1 (LP Display sync fix)")


        elif self.model in _T2_UHD630_MODELS:
            logging.info(f"- {self.model}: Injecting connector-less UHD630 DeviceProperties (Tahoe fix)")
            gfx["AAPL,ig-platform-id"] = binascii.unhexlify("06009B3E")  # 0x3E9B0006 LE
            gfx["device-id"]           = binascii.unhexlify("9B3E0000")  # 0x3E9B0000 LE
        else:
            logging.error(f"FATAL: Model {self.model} lacks specific GPU patch data.")
            return
        try:
            # ── Common framebuffer patches (all T2 iGPU models) ──────────────
            gfx["framebuffer-patch-enable"] = binascii.unhexlify("01000000")
            gfx["framebuffer-con0-enable"]  = binascii.unhexlify("01000000")
            gfx["framebuffer-con0-type"]    = binascii.unhexlify("00040000")  # Unused/connector-less
            gfx["framebuffer-stolenmem"]    = binascii.unhexlify("00003001")  # 19 MB
            gfx["framebuffer-fbmem"]        = binascii.unhexlify("00009000")  # 9 MB
            logging.info("  > T2 iGPU connector-less injection complete")
        except Exception as e:
            logging.error(f"Whoops, injecting common framebuffer patches for {self.model} failed because of the following error:")
            logging.exception("Stack Trace:")
            logging.info("Please try again later.")
            sys.exit(3)

    def _apply_t2_memory_descriptor_overrides(self, apple_nvram_uuid: str) -> None:
        """Apply mandatory security overrides required for T2 Macs to boot."""
        logging.info("- Applying T2 memory descriptor overrides (T2 ONLY)")

        self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"
        self.config["Misc"]["Security"]["DmgLoading"]      = "Any"
        self.config["Misc"]["Security"]["ApECID"]          = int(0)

        if self.model == "MacBookPro15,1":
            logging.info("  > Forcing Native SMBIOS (MacBookPro15,1) to prevent Trust Cache mismatch")
            for section in ["Generic", "SMBIOS", "DataHub"]:
                if section in self.config.get("PlatformInfo", {}):
                    self.config["PlatformInfo"][section]["SystemProductName"] = "MacBookPro15,1"

        self._apply_t2_amfi_boot_args(apple_nvram_uuid)
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "ipc_control_port_options=0 -v keepsyms=1 nvme_shutdown_timestamp=0")

        if self.constants.detected_os >= os_data.os_data.tahoe:
            self.is_tahoe_target = True
            self._apply_cryptex_patches(apple_nvram_uuid)
        elif self.is_tahoe_target is False and self.constants.detected_os >= os_data.os_data.mojave and self.constants.detected_os < os_data.os_data.tahoe:
            logging.info("Popping up a popup to ask if the OS target is Tahoe or not since we couldn't identify...")
            self._unknown_target(apple_nvram_uuid)
        else:
            logging.error("Upgrading from macOS High Sierra to Tahoe is not possible. Please, upgrade to macOS Sequoia first. We'll skip any macOS 26-only patches.")
            return

    def _unknown_target(self, apple_nvram_uuid: str) -> None:
        """
        Safely maps the target OS version. If running inside a GUI app context,
        it dispatches UI rendering safely to the Main Thread. Otherwise, falls 
        back to an interactive CLI prompt.
        """
        app = wx.GetApp()
        # Ensure wx is running and we are calling from a worker thread
        if app and app.IsMainLoopRunning():
            logging.info("  > Active GUI environment detected. Thread proxying to Main Thread.")
            
            # Use a thread Event to halt this worker thread until the user interacts with the GUI
            evt = threading.Event()
            
            # wx.CallAfter safely pushes the execution onto the main AppKit thread loop
            wx.CallAfter(self._unknown_target_gui, apple_nvram_uuid, evt)
            
            # Sleep worker thread until Main Thread signals it's done
            evt.wait()
        else:
            logging.info("  > Headless/CLI environment detected. Falling back to terminal input.")
            self._unknown_target_cli(apple_nvram_uuid)

    def _unknown_target_gui(self, apple_nvram_uuid: str, event: threading.Event) -> None:
        """Handles target selection via a wxWidgets modal dialog (EXCECUTED ON MAIN THREAD)."""
        try:
            # We pass a valid parent if available, or None if TopWindow is missing
            parent = wx.GetApp().GetTopWindow()
            dlg = wx.Dialog(parent, title="Unknown Target", size=(450, 250))
            sizer = wx.BoxSizer(wx.VERTICAL)

            msg = wx.StaticText(dlg, label="What version would you like to run on your unsupported T2 Mac?")
            sizer.Add(msg, 0, wx.ALL | wx.CENTER, 20)

            btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
            
            macOS26_btn = wx.Button(dlg, label="macOS 26 Tahoe or newer")
            macOS26_btn.Bind(wx.EVT_BUTTON, lambda e: self._handle_selection(dlg, apple_nvram_uuid, target_is_tahoe=True))
            
            macOS15_btn = wx.Button(dlg, label="macOS 15 Sequoia or older")
            macOS15_btn.Bind(wx.EVT_BUTTON, lambda e: self._handle_selection(dlg, apple_nvram_uuid, target_is_tahoe=False))
            
            btn_sizer.Add(macOS26_btn, 0, wx.ALL, 5)
            btn_sizer.Add(macOS15_btn, 0, wx.ALL, 5)
            
            sizer.Add(btn_sizer, 0, wx.CENTER)
            dlg.SetSizer(sizer)
            
            dlg.ShowModal()
            dlg.Destroy()
        finally:
            # Crucial: Unblock the worker thread regardless of dialog outcome or failures
            event.set()

    def _handle_selection(self, dialog: wx.Dialog, apple_nvram_uuid: str, target_is_tahoe: bool) -> None:
        """Consolidated callback processor for wxButton events."""
        if target_is_tahoe:
            logging.info("GUI Selection: macOS 26 Tahoe target path validated.")
            self.is_tahoe_target = True
            self._apply_cryptex_patches(apple_nvram_uuid)
            dialog.EndModal(wx.ID_OK)
        else:
            logging.info("GUI Selection: Skipping Tahoe-specific patches (Sequoia or older).")
            self.is_tahoe_target = False
            dialog.EndModal(wx.ID_CANCEL)
    
    def _apply_cryptex_patches(self, apple_nvram_uuid: str) -> None:
        if self.is_tahoe_target is True:
            logging.info("Injecting cryptex=0 cs_allow_invalid=1 for macOS 26 Tahoe")
            self._update_nvram_string(apple_nvram_uuid, "boot-args", "cryptex=0 cs_allow_invalid=1")
        else:
            return
    
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
                "Enabled": True,
                "Identifier": "com.apple.driver.usb.AppleUSBXHCI",
                "Find": binascii.unhexlify("BA0A000000"),
                "Replace": binascii.unhexlify("BAFF000000"),
                "MinKernel": "25.0.0"
            })

        # 3. Bypass InternalHubPowerCheck
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

        # 6. Bypass corecrypto FIPS POST self-test on T2 Macs (Tahoe)
        # WHY: On T2 Macs running macOS Tahoe, the FIPS Power-On Self-Test in
        # com.apple.kec.corecrypto fails with error -2074 at _corecrypto_kext_start
        # because the T2 chip's SEP (Secure Enclave Processor) is not accessible
        # through the normal x86 path when booting via OpenCore.
        # The FIPS POST calls into SEP hardware that is gated behind T2 firmware
        # trust — which OpenCore's unsigned boot path cannot satisfy.
        # This patch replaces the POST failure branch (je = jump if equal/zero,
        # i.e. jump if POST failed) with a nop so boot continues regardless.
        # The T2 chip itself still enforces cryptographic security independently.
        if not patch_exists("Bypass corecrypto FIPS POST (T2 Tahoe fix)"):
            logging.info("  > Adding corecrypto FIPS POST bypass patch (T2 Tahoe)")
            kernel_patches.append({
                "Arch": "x86_64",
                "Comment": "Bypass corecrypto FIPS POST (T2 Tahoe fix)",
                "Enabled": True,
                "Identifier": "com.apple.kec.corecrypto",
                # fips_post_failed check: test eax,eax / je <panic>
                # 85 C0 = TEST EAX, EAX
                # 0F 84 = JE (near, 4-byte offset) — jump to panic if POST failed
                "Find":    binascii.unhexlify("85C00F84"),
                "Replace": binascii.unhexlify("85C09090"),  # replace JE with NOP NOP
                "Mask":    binascii.unhexlify("FFFFFFFF"),
                "ReplaceMask": binascii.unhexlify("FFFFFFFF"),
                "MinKernel": "25.0.0",
                "MaxKernel": "25.99.99",
                "Count": 1,
        
        if self.model in _T2_TOUCH_BAR_MODELS:
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
            
            # 1. Base initialization, overrides, graphics and kernel patches
            self._apply_t2_memory_descriptor_overrides(APPLE_NVRAM_UUID)
            self._apply_t2_graphics_injection()
            self._apply_t2_kernel_patches_tahoe()

            # 2. Structural boot arguments configuration (Clean tokenization strings)
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-disable_sidecar_mac -disable_media_analysis")

            # 3. Scope graphics injection flags strictly to active valid targets
            if self._requires_t2_graphics_injection():
                self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "igfxonln=1 igfxfw=2 forceRenderStandby=0 agdpmod=vit9696")

            # 4. Hard Structural Boundaries Pass
            logging.info("- Final T2 verification pass (Enforcing absolute boundaries)")
            self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"
            self.config["Misc"]["Security"]["ApECID"]          = 0
            self.config["Misc"]["Security"]["DmgLoading"]      = "Any"

            logging.info("  > Final T2 verification complete. Execution boundaries isolated.")
            return  # Clean break: T2 completely bypasses Branch B and Shared evaluations

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
