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
        if self.model == "MacBookPro15,1":
            return False
        return (self.model in _T2_UHD630_MODELS or self.model in _T2_LOW_POWER_MODELS or self.model in _T2_IRIS_PLUS_MODELS)

    def _should_skip_t2_graphics_injection(self) -> bool:
        """Return True if this T2 model should explicitly skip Intel graphics injection."""
        return self.model in _T2_NO_IGPU_MODELS

    def _t2_uses_amfipass(self) -> bool:
        """T2 builds enable AMFIPass in misc._t2_handling (runs after security)."""
        return self._is_t2_mac()

    def _apply_t2_amfi_boot_args(self, apple_nvram_uuid: str) -> None:
        """Apply AMFI-related boot-args based on user path validation."""
        if self.model == "MacBookPro15,1":
            logging.info("  > MacBookPro15,1: Skipping AMFIPass boot-arg while isolating persistent IOBufferCopyController bridge timeout.")
            return

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
        if self.model == "MacBookPro15,1":
            logging.info(f"- {self.model}: Skipping Intel graphics DeviceProperties while isolating persistent IOBufferCopyController bridge timeout.")
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
            logging.info("  > MacBookPro15,1: Aligning installer identity with Tahoe 26.2 PlatformSupport (MacBookPro16,4/J215).")
            platform_info = self.config.setdefault("PlatformInfo", {})
            platform_info.setdefault("Generic", {})["SystemProductName"] = "MacBookPro16,4"
            platform_info.setdefault("DataHub", {})["SystemProductName"] = "MacBookPro16,4"
            platform_info["DataHub"]["BoardProduct"] = "Mac-A61BADE1FDAD7B05"
            platform_info.setdefault("SMBIOS", {})["SystemProductName"] = "MacBookPro16,4"
            platform_info["SMBIOS"]["BoardProduct"] = "Mac-A61BADE1FDAD7B05"
            platform_info.setdefault("PlatformNVRAM", {})["BID"] = "Mac-A61BADE1FDAD7B05"

        self._apply_t2_amfi_boot_args(apple_nvram_uuid)
        if self.model == "MacBookPro15,1":
            logging.info("  > MacBookPro15,1: Using minimal T2 debug boot-args while isolating persistent IOBufferCopyController bridge timeout.")
            self._update_nvram_string(apple_nvram_uuid, "boot-args", "-v keepsyms=1")
        else:
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

    def _unknown_target_cli(self, apple_nvram_uuid: str) -> None:
        """Prompt for the target OS when building from a non-GUI CLI session."""
        logging.info("Select target OS for this T2 OpenCore build:")
        logging.info("  1. macOS 26 Tahoe or newer")
        logging.info("  2. macOS 15 Sequoia or older")

        while True:
            try:
                selection = input("Target OS [1/2]: ").strip()
            except EOFError as e:
                raise RuntimeError("Unable to determine target OS in CLI mode without input.") from e

            if selection == "1":
                logging.info("CLI Selection: macOS 26 Tahoe target path validated.")
                self.is_tahoe_target = True
                self._apply_cryptex_patches(apple_nvram_uuid)
                return
            if selection == "2":
                logging.info("CLI Selection: Skipping Tahoe-specific patches (Sequoia or older).")
                self.is_tahoe_target = False
                return

            logging.info("Please enter 1 for Tahoe or 2 for Sequoia or older.")

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

        if self.model == "MacBookPro15,1":
            logging.info("- Skipping AppleUSBXHCI binary patches on MacBookPro15,1; latest panic backtrace is inside AppleUSBXHCI command ring power-state handling.")
        else:
            # 1. Bypass AppleIntelUSBXHCI T2 handshake
            if not patch_exists("Bypass T2 USB handshake (Tahoe fix)"):
                kernel_patches.append({
                    "Arch": "x86_64",
                    "Comment": "Bypass T2 USB handshake (Tahoe fix)",
                    "Enabled": True,
                    "Identifier": "com.apple.driver.usb.AppleUSBXHCI",
                    # Matches: MOV RAX, qword ptr [RBX]; MOV RDI, RBX; CALL qword ptr [RAX + 0x38]
                    "Find": binascii.unhexlify("488B034889DFFF5038"),
                    "Mask": b"", # Exact binary instruction match; no wildcards needed
                    "MaxKernel": "",
                    "MinKernel": "25.0.0",
                    # Replaces 'FF 50 38' (CALL) with '31C090' (XOR EAX,EAX; NOP) to force return code 0 (Success)
                    "Replace": binascii.unhexlify("488B034889DF31C090"),
                    "ReplaceMask": b"",
                    "Skip": 0
                })

            # 3. Bypass InternalHubPowerCheck
            if not patch_exists("Bypass InternalHubPowerCheck (Tahoe fix)"):
                kernel_patches.append({
                    "Arch": "x86_64",
                    "Comment": "Bypass InternalHubPowerCheck via getUpstreamHub (Tahoe fix)",
                    "Enabled": True,
                    "Identifier": "com.apple.driver.usb.AppleUSBXHCI",
                    # Matches: PUSH RBP; MOV RBP, RSP; MOV RAX, qword ptr [RDI + 0x158]
                    "Find": binascii.unhexlify("554889E5488B8758010000"),
                    "Mask": b"",
                    "MaxKernel": "",
                    "MinKernel": "25.0.0",
                    # Replaces structure load with 'MOV RAX, RDI; NOP; NOP; NOP; NOP' to spoof a valid hub node response
                    "Replace": binascii.unhexlify("554889E54889F890909090"),
                    "ReplaceMask": b"",
                    "Skip": 0
                })
        
        if self.model in _T2_TOUCH_BAR_MODELS:
            logging.info("No touch bar patches available for now. Don't worry - your system should boot anyways.")
            logging.info("If it doesn't, please open an issue about the kernel panic that appears on your screen and include also which version of the patcher are you using.")
            logging.info("Keine Touch Bar Patches sind verfügbar. Macht euch keine Sorge - das System soll trotzdem starten.")
            logging.info("Falls den Mac gar nicht hochfährt und stattdessen einen Kernel Panic zeigt, Sie müssen das Problem melden und die Meldung muss auch die Version der Patcher, \n\ndie Sie gerade verwenden, enthalten.")
    
        """Injects corecrypto binary shims to bypass FIPS Kernel POST verification failures."""
        if self.model == "MacBookPro15,1":
            logging.info("- MacBookPro15,1: Skipping corecrypto FIPS shim while isolating persistent IOBufferCopyController bridge timeout.")
            return

        logging.info("- Injecting corecrypto FIPS POST binary shims for Tahoe targets")
    
        corecrypto_patch = {
            "Arch": "x86_64",
            "Base": "",  # Clear this out so it relies purely on the robust unique hex match
            "Comment": "Bypass FIPS Kernel POST Panic (-2074)",
            "Count": 1,
            "Enabled": True,
            # Matches the exact CMP and JBE instructions we found at 0xffffff8000333c28
            "Find": binascii.unhexlify("4883F98E767B"), 
            "Identifier": "com.apple.kec.corecrypto",
            "Limit": 0,
            "Mask": b"",  # No mask needed since our Find sequence is a direct, concrete binary match
            "MaxKernel": "",
            "MinKernel": "25.0.0", 
            # Replaces the 2-byte branch '76 7B' (JBE) with '90 90' (NOP NOP) to slide safely past the panic trigger
            "Replace": binascii.unhexlify("4883F98E9090"), 
            "ReplaceMask": b"",
            "Skip": 0
        }
    
        if "Patch" not in self.config["Kernel"]:
            self.config["Kernel"]["Patch"] = []
            
        self.config["Kernel"]["Patch"].append(corecrypto_patch)
        logging.info("  > corecrypto FIPS shim appended to Kernel->Patch array successfully.")

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
            if self.model == "MacBookPro15,1":
                logging.info("- MacBookPro15,1: Skipping Sidecar and mediaanalysis boot-args while isolating persistent IOBufferCopyController bridge timeout.")
            else:
                self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "-disable_sidecar_mac -disable_media_analysis")

            # 3. Scope graphics injection flags strictly to active valid targets
            if self._requires_t2_graphics_injection():
                self._update_nvram_string(APPLE_NVRAM_UUID, "boot-args", "igfxonln=1 igfxfw=2 forceRenderStandby=0 agdpmod=vit9696")

            # 4. Hard Structural Boundaries Pass
            logging.info("- Final T2 verification pass (Enforcing absolute boundaries)")
            self.config["Misc"]["Security"]["SecureBootModel"] = "Disabled"
            self.config["Misc"]["Security"]["ApECID"]          = 0
            self.config["Misc"]["Security"]["DmgLoading"]      = "Any"

            if self.model == "MacBookPro15,1":
                logging.info("  > MacBookPro15,1: Reasserting Tahoe installer APFS/compatibility NVRAM after final T2 pass.")
                self.is_tahoe_target = True
                self._apply_cryptex_patches(APPLE_NVRAM_UUID)
                self._update_nvram_string(OCLP_NVRAM_UUID, "OCLP-Settings", "-allow_fv")
                logging.info("  > MacBookPro15,1: RestrictEvents revpatch=sbvmm is applied in the miscellaneous build stage for Tahoe compatibility checks.")
                logging.info("  > MacBookPro15,1: Using j215 SecureBootModel to match staged Tahoe 26.2 MacBookPro16,4/J215 assets.")
                self.config["Misc"]["Security"]["SecureBootModel"] = "j215"
                self.config["Misc"]["Security"]["DmgLoading"] = "Signed"
                logging.info("  > MacBookPro15,1: Disabling EFI firmware updater for Tahoe stage-2; latest logs show FirmwareUpdateLauncher/efiupdater status 1 before MSU failure.")
                self._set_nvram_value(APPLE_NVRAM_UUID, "run-efi-updater", "No", overwrite=True)
                logging.info("  > MacBookPro15,1: Keeping APFS FileVault allowance patch enabled; latest removal regressed before installer UI.")
                support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(
                    self.config["Kernel"]["Patch"], "Comment", "Force FileVault on Broken Seal"
                )["Enabled"] = True

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
