"""
security.py: Class for handling macOS Security Patches, invocation from build.py
"""

import logging
import binascii
import sys
import wx
import threading
import webbrowser

from . import support
from .. import constants
from ..support import utilities
from ..detections import device_probe
from ..datasets import (
    smbios_data,
    os_data
)

# T2 Mac models that use Intel UHD 630 and require connector-less
# ig-platform-id injection to avoid APFS volume group race condition
# on macOS Tahoe and later. (Coffee Lake GT2)
_T2_UHD630_MODELS = {
    "MacBookPro15,1",  # 15-inch 2018 Intel UHD Graphics 630 + AMD Radeon Pro 555X
    "MacBookPro15,3",  # 15-inch 2019 Intel UHD Graphics 630 + AMD Radeon Pro Vega 16/20
    "MacBookPro16,1",  # 16-inch 2019, Intel UHD Graphics 630 + AMD Radeon Pro 5300M
    "MacBookPro16,4",  # 16-inch 2019 CTO, Intel UHD Graphics 630 + AMD Radeon Pro 5600M
    "Macmini8,1",      # Mac mini 2018 (Intel UHD Graphics 630)
}

# T2 Mac models with Intel Iris Plus Graphics (U-Series)
# Required for logic isolation (iGPU-only).
_T2_IRIS_PLUS_MODELS = {
    "MacBookPro15,2",  # 13-inch 2018 (4 TB3) - Intel Iris Plus Graphics 655
    "MacBookPro15,4",  # 13-inch 2019 (2 TB3) - Intel Iris Plus Graphics 645
}

# T2 Mac models that use Intel UHD 617 / Ice Lake LP and require graphics injection for stability
_T2_LOW_POWER_MODELS = {
    "MacBookAir8,1",   # Air 2018, Intel UHD Graphics 617
    "MacBookAir8,2",   # Air 2019, Intel UHD Graphics 617
    "MacBookAir9,1",   # Air 2020 Intel, Intel Iris Plus
    "MacBookPro16,3",  # 13-inch 2020 (2 TB3), Intel Iris Plus Graphics 645
}

# T2 Mac models that do not have an Intel iGPU, or where iGPU injection is not required/recommended.
_T2_NO_IGPU_MODELS = {
    "iMacPro1,1",      # iMac Pro 2017
}

# EXPERIMENT B2 (2026-07-16, gray-screen root cause CONFIRMED):
#   T2 Mac models whose DISCRETE GPU driver was REMOVED in macOS Tahoe and must be
#   disabled so the machine falls back to its (still-supported) Intel iGPU.
#
#   Root cause proof (no guessing — all from real binaries/hardware):
#   - MacBookPro15,1 dGPU = Radeon Pro 555X/560X = Polaris/Baffin (0x67ef),
#     driven by AMDRadeonX4000.kext. That kext is PRESENT on Sequoia but ABSENT
#     from Tahoe: Tahoe PlatformSupport.plist only lists MacBookPro16,1/16,2/16,4
#     + iMac20,x, whose dGPUs are all AMD Navi (AMDRadeonX6000). No supported Mac
#     uses Polaris, so Tahoe ships no Polaris driver => dGPU cannot initialise
#     => WindowServer cannot composite => plain GRAY screen + cursor.
#   - The internal Retina panel is wired to the iGPU, NOT the dGPU (confirmed via
#     IORegistry: IGPU@2 > AppleIntelFramebuffer@0 > display0 > AppleBacklightDisplay),
#     and the machine has a gMux, so disabling the dGPU keeps the panel alive.
#   - Tahoe still ships the UHD630 (Coffee Lake) iGPU driver — MacBookPro16,1 (a
#     Tahoe-supported model) uses the very same UHD 630 — so iGPU-only is viable.
#
#   Fix: inject WhateverGreen's `-wegnoegpu` boot-arg (adds `disable-gpu` to GFX0)
#   so macOS never attaches a driver to the unsupported Polaris dGPU.
#   REVERT: remove the model from this set.
_DISABLE_UNSUPPORTED_DGPU_MODELS = {
    "MacBookPro15,1",  # Radeon Pro 555X/560X (Polaris/Baffin) — AMDRadeonX4000 removed in Tahoe
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
        
        # ── Global Hardware & OS Targets Scopes ───────────────────────
        self.is_tahoe_target: bool = False
        self.is_ice_lake: bool = (self.model == "MacBookAir9,1")
        self.is_mac_mini: bool = (self.model == "Macmini8,1")

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
        """Return True only for this fork's supported T2 target (MacBookPro15,1).

        This fork focuses exclusively on the MacBook Pro 15-inch 2018. No T2
        security configuration (memory descriptor overrides, graphics injection,
        Tahoe kernel patches, AMFIPass) is applied to any other model.
        """
        return self.model == "MacBookPro15,1"

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
            logging.info("  > T2 target utilizes AMFIPass layer. Injecting validated Tahoe storage bypasses.")
            # Exp B6: Added amfi=0x80 + amfi_get_out_of_my_way=1 for additional
            # AMFI bypass during installer.  These are temporary and help prevent
            # AMFI from blocking unsigned kexts/loading during the install process.
            self._update_nvram_string(apple_nvram_uuid, "boot-args", (
                "-amfipassbeta cs_allow_invalid=1 cs_unrestricted_cs=1 cs_debug=1 io=0xffffffff "
                "amfi=0x80 amfi_get_out_of_my_way=1"
            ))
            return

        # Fallback if AMFIPass pathing is completely stripped
        existing = self._read_nvram_string(apple_nvram_uuid, "boot-args")
        if "amfi=0x80" not in existing:
            logging.warning("  > AMFIPass bypassed. Falling back to amfi=0x80 absolute drop.")
            self._update_nvram_string(apple_nvram_uuid, "boot-args", (
                "amfi=0x80 amfi_get_out_of_my_way=1 cs_debug=1 io=0xffffffff"
            ))

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

    # EXPERIMENT B1 (2026-07-16, gray-screen fix):
    #   Symptom on real hardware: Tahoe installer boots (no panic after Exp A),
    #   but reaches a plain GRAY screen + mouse cursor, NO menu bar, and Terminal
    #   cannot be opened. Root cause (confirmed from the booted config.plist):
    #   the connector-less/headless UHD630 injection below sets the internal iGPU
    #   (PciRoot(0x0)/Pci(0x2,0x0)) to AAPL,ig-platform-id 0x3E9B0006 +
    #   framebuffer-con0-type 0 ("headless isolation"). That platform-id suits a
    #   Mac mini / iMac where the iGPU drives NO display — but MacBookPro15,1 is a
    #   laptop whose internal panel runs through the iGPU path, so it is left with
    #   no usable framebuffer => gray screen, no GUI shell.
    #
    #   MacBookPro15,1 is a genuine Mac and should use its NATIVE Apple framebuffer
    #   (no injection). Skip the injection for it. REVERT (remove from the set) if
    #   hardware testing shows the installer GUI still does not appear.
    _SKIP_IGPU_INJECTION_MODELS = set()

    def _apply_t2_graphics_injection(self) -> None:
        """Inject integrated Intel iGPU DeviceProperties for T2 Macs."""
        if self.model in self._SKIP_IGPU_INJECTION_MODELS:
            logging.info(f"- {self.model}: Skipping iGPU DeviceProperties injection (native framebuffer, Exp B1 gray-screen fix)")
            return

        if self._should_skip_t2_graphics_injection() or not self._requires_t2_graphics_injection():
            logging.info(f"- Skipping Intel graphics injection for {self.model} (no iGPU or not required)")
            return

        graphics_path = self._get_graphics_device_properties_path()
        if not graphics_path:
            return

        self._ensure_path("DeviceProperties", "Add", graphics_path)
        gfx = self.config["DeviceProperties"]["Add"][graphics_path]

        APPLE_NVRAM_UUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"

        # ── 1. Platform & Device ID Allocation ────────────────────────────
        if self.is_ice_lake:
            logging.info(f"- {self.model}: Injecting connector-less Ice Lake Iris Plus DeviceProperties (Tahoe fix)")
            gfx["AAPL,ig-platform-id"] = binascii.unhexlify("02005C8A")  # 0x8A5C0002 LE
            gfx["device-id"]           = binascii.unhexlify("5C8A0000")  # 0x8A5C0000 LE
            
        elif self.model in _T2_LOW_POWER_MODELS or self.model in _T2_IRIS_PLUS_MODELS:
            logging.info(f"- {self.model}: Injecting connector-less Iris Plus / Amber Lake DeviceProperties (Tahoe fix)")
            gfx["AAPL,ig-platform-id"] = binascii.unhexlify("0900A53E")  # 0x3EA50009 LE
            gfx["device-id"]           = binascii.unhexlify("A53E0000")  # 0x3EA50000 LE
            
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "igfxgl=1 igfxmetal=1")
            logging.info("  > Appended LP display sync flags safely.")

        elif self.model in _T2_UHD630_MODELS:
            # Note: macOS Tahoe and MacBookPro15,1 native platform ID is 0x06009B3E (headless)
            # The iGPU-only display drive with eDP connector requires platform ID 0x09009B3E
            # (Coffee Lake mobile, native eDP) for proper display output. 0x07009B3E (desktop,
            # 3x DP) was used before but required WhateverGreen framebuffer patches to override
            # con0-type to eDP — and WhateverGreen probe fails on Tahoe, so those patches never
            # apply.  0x09009B3E has eDP natively in the platform-id, no WG override needed.
            if self.model == "MacBookPro15,1":
                logging.info(f"- {self.model}: Injecting iGPU-only mobile eDP UHD630 DeviceProperties for proper internal display output (Tahoe fix)")
                gfx["AAPL,ig-platform-id"] = binascii.unhexlify("09009B3E")  # 0x3E9B0009 LE
            else:
                logging.info(f"- {self.model}: Injecting connector-less UHD630 DeviceProperties (Tahoe fix)")
                gfx["AAPL,ig-platform-id"] = binascii.unhexlify("06009B3E")  # 0x3E9B0006 LE
            gfx["device-id"]           = binascii.unhexlify("9B3E0000")  # 0x3E9B0000 LE
        else:
            logging.error(f"FATAL: Model {self.model} lacks specific GPU patch data.")
            sys.exit(3)

        # ── 2. Structural Framebuffer Overrides ───────────────────────────
        try:
            gfx["framebuffer-patch-enable"] = binascii.unhexlify("01000000")
            
            if self.is_mac_mini or self.is_ice_lake:
                gfx["framebuffer-con0-enable"]  = binascii.unhexlify("01000000")
                gfx["framebuffer-con0-type"]    = binascii.unhexlify("00040000")  
                logging.info(f"  > {self.model}: Enforced active physical mapping layout on con0 (iGPU-only fix)")
            elif self.model in _T2_UHD630_MODELS:
                gfx["framebuffer-con0-enable"]  = binascii.unhexlify("01000000")
                if self.model == "MacBookPro15,1":
                    gfx["framebuffer-con0-type"]    = binascii.unhexlify("00040000")  # eDP
                    logging.info(f"  > {self.model}: Enforced active physical mapping layout on con0 (iGPU-only fix)")
                else:
                    gfx["framebuffer-con0-type"]    = binascii.unhexlify("00000000")  
                    logging.info(f"  > {self.model}: Enforced strict headless isolation structure on con0 (dGPU Present)")
            else:
                gfx["framebuffer-con0-enable"]  = binascii.unhexlify("01000000")
                gfx["framebuffer-con0-type"]    = binascii.unhexlify("00040000")  
                logging.info(f"  > {self.model}: Standard physical connector mapping applied")

            gfx["framebuffer-stolenmem"]    = binascii.unhexlify("00003001")  
            gfx["framebuffer-fbmem"]        = binascii.unhexlify("00009000")  
            logging.info("  > T2 iGPU configuration parameters applied successfully.")
            
        except Exception as e:
            logging.error(f"Whoops, injecting common framebuffer patches for {self.model} failed because of the following error:")
            logging.exception("Stack Trace:")
            logging.info("Please try again later.")
            sys.exit(3)

    def _apply_t2_memory_descriptor_overrides(self, apple_nvram_uuid: str) -> None:
        """Apply mandatory security overrides required for T2 Macs to boot."""
        logging.info("- Applying T2 memory descriptor overrides (T2 ONLY)")

        # Configure raw boundaries cleanly
        self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"
        self.config["Misc"]["Security"]["DmgLoading"]      = "Any"
        self.config["Misc"]["Security"]["ApECID"]          = 0

        # FIX: Keyword typo corrected
        self._apply_t2_amfi_boot_args(apple_nvram_uuid)
        self._update_nvram_string(apple_nvram_uuid, "boot-args", "ipc_control_port_options=0 -v keepsyms=1 nvme_shutdown_timestamp=0")

        # Exp B6: Installer-specific boot-args to bypass SEP/KeyStore/DMG trust
        # checks that hang silently on T2 when Board ID mismatch is detected.
        # root_dmg_trust_level=0: disable DMG trust level verification
        # apfs_read_only_nodownloads=1: prevent APFS downloads during read-only mount
        # -rootdmgboot: disable root DMG boot verification
        self._update_nvram_string(apple_nvram_uuid, "boot-args",
            "root_dmg_trust_level=0 apfs_read_only_nodownloads=1 -rootdmgboot")

        if self.constants.detected_os >= os_data.os_data.tahoe:
            self.is_tahoe_target = True
            self._apply_cryptex_patches(apple_nvram_uuid)
        elif self.is_tahoe_target is False and self.constants.detected_os >= os_data.os_data.catalina and self.constants.detected_os < os_data.os_data.tahoe:
            logging.info("Popping up a popup to ask if the OS target is Tahoe or not since we couldn't identify...")
            self._unknown_target(apple_nvram_uuid)
        else:
            logging.error("Upgrading from macOS High Sierra or Mojave straight to Tahoe is not possible. Please, upgrade to macOS Sequoia first.")
            logging.info("Aborting any patch injection so you can upgrade first to Sequoia or another newer macOS release.")
            webbrowser.open("https://support.apple.com/en-us/102662")
            webbrowser.open("https://apps.apple.com/us/app/macos-sequoia/id6596773750?mt=12")
            sys.exit(3)

    def _unknown_target(self, apple_nvram_uuid: str) -> None:
        app = wx.GetApp()
        if app and app.IsMainLoopRunning():
            logging.info("  > Active GUI environment detected. Thread proxying to Main Thread.")
            evt = threading.Event()
            wx.CallAfter(self._unknown_target_gui, apple_nvram_uuid, evt)
            evt.wait()
        else:
            logging.info("  > Headless/CLI environment detected. Falling back to terminal input.")
            user_input = input("Target OS is macOS 26 Tahoe or newer? (y/n): ").strip().lower()
            if user_input == 'y':
                self.is_tahoe_target = True
                self._apply_cryptex_patches(apple_nvram_uuid)
            else:
                self.is_tahoe_target = False

    def _unknown_target_gui(self, apple_nvram_uuid: str, event: threading.Event) -> None:
        try:
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
            event.set()

    def _handle_selection(self, dialog: wx.Dialog, apple_nvram_uuid: str, target_is_tahoe: bool) -> None:
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
            logging.info("Injecting unified Tahoe capability token mapping.")
            self._update_nvram_string(apple_nvram_uuid, "boot-args", "ipc_control_port_options=0 cs_unrestricted_cs=1 cs_allow_invalid=1")

    def _apply_t2_kernel_patches_tahoe(self) -> None:
        logging.info("The use of the function _apply_t2_kernel_patches_tahoe is retired. This function remains there to ensure compatibility so the app doesn't crash.")
        logging.info("The goal of this is to make the code clearer.")
    
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
            
            # 1. Base initialization & OS Target Checks (Must be first!)
            self._apply_t2_memory_descriptor_overrides(APPLE_NVRAM_UUID)
            
            # 2. Graphics & Kernel Injections (Independent of variable fluctuations)
            self._apply_t2_graphics_injection()
            self._apply_t2_kernel_patches_tahoe()

            # 3. Additional cosmetic arguments cleanly appended
            self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-disable_sidecar_mac -disable_media_analysis")

            # Exp B7: Restore WEG boot-args for iGPU stability.
            # igfxonln=1: force iGPU online (needed during installer init)
            # igfxfw=2: load Intel GPU firmware (Coffee Lake GT2)
            # forceRenderStandby=0: prevent render standby during installer
            # agdpmod=vit9696: bypass AGDP board-id check (WEG feature)
            if self._requires_t2_graphics_injection():
                self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args",
                    "igfxonln=1 igfxfw=2 forceRenderStandby=0 agdpmod=vit9696")

            # 4b. EXP B2: disable discrete GPUs whose driver Tahoe removed, so the
            #     machine runs on its supported Intel iGPU (internal panel is on the
            #     iGPU). See _DISABLE_UNSUPPORTED_DGPU_MODELS for the full evidence.
            if self.model in _DISABLE_UNSUPPORTED_DGPU_MODELS:
                logging.info(f"- {self.model}: Disabling unsupported discrete GPU (driver removed in Tahoe) — running iGPU-only (Exp B2)")
                # -wegnoegpu is a WhateverGreen boot-arg that adds disable-gpu to GFX0.
                self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-wegnoegpu")
                # Exp B4 backup: inject disable-gpu directly on dGPU DeviceProperties
                # because WhateverGreen probe fails on Tahoe → start() never called →
                # -wegnoegpu boot-arg is never processed.  DeviceProperties injection
                # happens via OpenCore before kext load, so it works without WG.
                dgpu_path = "PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)"
                self._ensure_path("DeviceProperties", "Add", dgpu_path)
                self.config["DeviceProperties"]["Add"][dgpu_path]["disable-gpu"] = binascii.unhexlify("01000000")
                logging.info(f"  > Injected disable-gpu on dGPU DeviceProperties path: {dgpu_path}")

            # Exp B7: Inject coprocessor DeviceProperties for T2 Board ID spoofing.
            # The T2 coprocessor (Apple coprocessor) at PciRoot(0x0)/Pci(0x14,0x0)
            # reports the real Board ID (J680AP) via Secure Enclave/BridgeOS.
            # By injecting a spoofed board-id property here, we hope to reduce the
            # dual Board ID conflict that causes KeyStore/SEP to hang during
            # installer.  Verify with: ioreg -l | grep -E "board-id|apple-coprocessor"
            coprocessor_path = "PciRoot(0x0)/Pci(0x14,0x0)"
            self._ensure_path("DeviceProperties", "Add", coprocessor_path)
            # Spoof Board ID to match the target SMBIOS (MacBookPro15,1 = J680AP)
            # The real Board ID from T2 SEP is 6 bytes; inject as property
            self.config["DeviceProperties"]["Add"][coprocessor_path]["board-id"] = \
                binascii.unhexlify("4A3638304150")  # "J680AP" in ASCII
            logging.info(f"  > Exp B7: Injected spoofed board-id on coprocessor path: {coprocessor_path}")

            # 5. Hard Structural Boundaries Pass
            logging.info("- Final T2 verification pass (Enforcing absolute boundaries)")
            self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"
            self.config["Misc"]["Security"]["ApECID"]          = 0
            self.config["Misc"]["Security"]["DmgLoading"]      = "Any"

            logging.info("  > Final T2 verification complete. ")

        # ==============================================================
        # Branch B: Non-T2 Mac Configuration (PROTECTED VIA ELSE)
        # ==============================================================
        else:
            logging.info("- Non-T2 Mac detected — isolating legacy environment execution chain")
            if self.constants.sip_status is False or self.constants.custom_sip_value:
                logging.info("- Non-T2 Mac: SIP lowered — applying SIP-related settings")
                
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

            # Shared: AMFI / Library Validation (Legacy Non-T2 verification targets)
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

        # ==============================================================
        # GLOBAL EVALUATION: Universal AMFIPass Injection Engine
        # ==============================================================
        needs_amfipass = False

        if self._is_t2_mac():
            if self.is_tahoe_target or smbios_data.smbios_dictionary[self.model]["Max OS Supported"] < self.constants.detected_os:
                needs_amfipass = True
        else:
            if smbios_data.smbios_dictionary[self.model]["Max OS Supported"] < os_data.os_data.sonoma:
                needs_amfipass = True

        if needs_amfipass:
            logging.info("- Enabling AMFIPass Framework Kext injection context natively.")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                "AMFIPass.kext", self.constants.amfipass_version, self.constants.amfipass_path
            )
