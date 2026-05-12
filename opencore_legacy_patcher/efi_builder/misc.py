"""
misc.py: Class for handling Misc Patches, invocation from build.py
"""

import shutil
import logging
import binascii
import sys
import os
import plistb

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


    def _build(self) -> None:
        """
        Kick off Misc Build Process
        """

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
        """
        FeatureUnlock Handler
        """

        if self.constants.fu_status is False:
            return

        if not self.model in smbios_data.smbios_dictionary:
            return

        if smbios_data.smbios_dictionary[self.model]["Max OS Supported"] >= os_data.os_data.sonoma:
            return

        support.BuildSupport(self.model, self.constants, self.config).enable_kext("FeatureUnlock.kext", self.constants.featureunlock_version, self.constants.featureunlock_path)
        if self.constants.fu_arguments is not None and self.constants.fu_arguments != "":
            logging.info(f"- Adding additional FeatureUnlock args: {self.constants.fu_arguments}")
            self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] += self.constants.fu_arguments


    def _restrict_events_handling(self) -> None:
        """
        RestrictEvents Handler
        """

        block_args = ",".join(self._re_generate_block_arguments())
        patch_args = ",".join(self._re_generate_patch_arguments())

        if block_args != "":
            logging.info(f"- Setting RestrictEvents block arguments: {block_args}")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("RestrictEvents.kext", self.constants.restrictevents_version, self.constants.restrictevents_path)
            self.config["NVRAM"]["Add"]["4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102"]["revblock"] = block_args

        if block_args != "" and patch_args == "":
            # Disable unneeded Userspace patching (cs_validate_page is quite expensive)
            patch_args = "none"

        if patch_args != "":
            logging.info(f"- Setting RestrictEvents patch arguments: {patch_args}")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("RestrictEvents.kext", self.constants.restrictevents_version, self.constants.restrictevents_path)
            self.config["NVRAM"]["Add"]["4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102"]["revpatch"] = patch_args

        if support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("RestrictEvents.kext")["Enabled"] is False:
            # Ensure this is done at the end so all previous RestrictEvents patches are applied
            # RestrictEvents and EFICheckDisabler will conflict if both are injected
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("EFICheckDisabler.kext", "", self.constants.efi_disabler_path)


    def _re_generate_block_arguments(self) -> list:
        """
        Generate RestrictEvents block arguments

        Returns:
            list: RestrictEvents block arguments
        """

        re_block_args = []

        # Resolve GMUX switching in Big Sur+
        if self.model in ["MacBookPro6,1", "MacBookPro6,2", "MacBookPro9,1", "MacBookPro10,1"]:
            re_block_args.append("gmux")

        # Resolve memory error reporting on MacPro7,1 SMBIOS
        if self.model in model_array.MacPro:
            logging.info("- Disabling memory error reporting")
            re_block_args.append("pcie")

        # Resolve mediaanalysisd crashing on 3802 GPUs
        # Applicable for systems that are the primary iCloud Photos library host, with large amounts of unprocessed faces
        if self.constants.disable_mediaanalysisd is True:
            logging.info("- Disabling mediaanalysisd")
            re_block_args.append("media")

        return re_block_args


    def _re_generate_patch_arguments(self) -> list:
        """
        Generate RestrictEvents patch arguments

        Returns:
            list: Patch arguments
        """

        re_patch_args = []

        # Alternative approach to the kern.hv_vmm_present patch
        # Dynamically sets the property to 1 if software update/installer is detected
        # Always enabled in installers/recovery environments
        if self.constants.allow_oc_everywhere is False and (self.constants.serial_settings == "None" or self.constants.secure_status is False):
            re_patch_args.append("sbvmm")

        # Resolve CoreGraphics.framework crashing on Ivy Bridge in macOS 13.3+
        # Ref: https://github.com/acidanthera/RestrictEvents/pull/12
        if smbios_data.smbios_dictionary[self.model]["CPU Generation"] == cpu_data.CPUGen.ivy_bridge.value:
            logging.info("- Fixing CoreGraphics support on Ivy Bridge")
            re_patch_args.append("f16c")

        return re_patch_args


    def _cpu_friend_handling(self) -> None:
        """
        CPUFriend Handler
        """

        if self.constants.allow_oc_everywhere is False and self.model not in ["iMac7,1", "Xserve2,1", "Dortania1,1"] and self.constants.disallow_cpufriend is False and self.constants.serial_settings != "None":
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("CPUFriend.kext", self.constants.cpufriend_version, self.constants.cpufriend_path)

            # CPUFriendDataProvider handling
            pp_map_path = Path(self.constants.platform_plugin_plist_path) / Path(f"{self.model}/Info.plist")
            if not pp_map_path.exists():
                raise Exception(f"{pp_map_path} does not exist!!! Please file an issue stating file is missing for {self.model}.")
            Path(self.constants.pp_kext_folder).mkdir()
            Path(self.constants.pp_contents_folder).mkdir()
            shutil.copy(pp_map_path, self.constants.pp_contents_folder)
            support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("CPUFriendDataProvider.kext")["Enabled"] = True


    def _firewire_handling(self) -> None:
        """
        FireWire Handler
        """

        if self.constants.firewire_boot is False:
            return
        if generate_smbios.check_firewire(self.model) is False:
            return

        # Enable FireWire Boot Support
        # Applicable for both native FireWire and Thunderbolt to FireWire adapters
        logging.info("- Enabling FireWire Boot Support")
        support.BuildSupport(self.model, self.constants, self.config).enable_kext("IOFireWireFamily.kext", self.constants.fw_kext, self.constants.fw_family_path)
        support.BuildSupport(self.model, self.constants, self.config).enable_kext("IOFireWireSBP2.kext", self.constants.fw_kext, self.constants.fw_sbp2_path)
        support.BuildSupport(self.model, self.constants, self.config).enable_kext("IOFireWireSerialBusProtocolTransport.kext", self.constants.fw_kext, self.constants.fw_bus_path)
        support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("IOFireWireFamily.kext/Contents/PlugIns/AppleFWOHCI.kext")["Enabled"] = True


    def _topcase_handling(self) -> None:
        """
        USB/SPI Top Case Handler
        """

        # macOS 14.4 Beta 1 strips SPI-based top case support for Broadwell through Kaby Lake MacBooks (and MacBookAir6,x)
        if self.model.startswith("MacBook") and self.model in smbios_data.smbios_dictionary:
            if self.model.startswith("MacBookAir6") or (cpu_data.CPUGen.broadwell <= smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.kaby_lake):
                logging.info("- Enabling SPI-based top case support")
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleHSSPISupport.kext", self.constants.apple_spi_version, self.constants.apple_spi_path)
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleHSSPIHIDDriver.kext", self.constants.apple_spi_hid_version, self.constants.apple_spi_hid_path)
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleTopCaseInjector.kext", self.constants.topcase_inj_version, self.constants.top_case_inj_path)


        # On-device probing
        if not self.constants.custom_model and self.computer.internal_keyboard_type and self.computer.trackpad_type:

            support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleUSBTopCase.kext", self.constants.topcase_version, self.constants.top_case_path)
            support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("AppleUSBTopCase.kext/Contents/PlugIns/AppleUSBTCButtons.kext")["Enabled"] = True
            support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("AppleUSBTopCase.kext/Contents/PlugIns/AppleUSBTCKeyboard.kext")["Enabled"] = True
            support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("AppleUSBTopCase.kext/Contents/PlugIns/AppleUSBTCKeyEventDriver.kext")["Enabled"] = True

            if self.computer.internal_keyboard_type == "Legacy":
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("LegacyKeyboardInjector.kext", self.constants.legacy_keyboard, self.constants.legacy_keyboard_path)
            if self.computer.trackpad_type == "Legacy":
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleUSBTrackpad.kext", self.constants.apple_trackpad, self.constants.apple_trackpad_path)
            elif self.computer.trackpad_type == "Modern":
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleUSBMultitouch.kext", self.constants.multitouch_version, self.constants.multitouch_path)

        # Predefined fallback
        else:
            # Multi Touch Top Case support for macOS Ventura+
            if smbios_data.smbios_dictionary[self.model]["CPU Generation"] < cpu_data.CPUGen.skylake.value:
                if self.model.startswith("MacBook"):
                    # These units got the Force Touch top case, so ignore them
                    if self.model not in ["MacBookPro11,4", "MacBookPro11,5", "MacBookPro12,1", "MacBook8,1"]:
                        support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleUSBTopCase.kext", self.constants.topcase_version, self.constants.top_case_path)
                        support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("AppleUSBTopCase.kext/Contents/PlugIns/AppleUSBTCButtons.kext")["Enabled"] = True
                        support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("AppleUSBTopCase.kext/Contents/PlugIns/AppleUSBTCKeyboard.kext")["Enabled"] = True
                        support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("AppleUSBTopCase.kext/Contents/PlugIns/AppleUSBTCKeyEventDriver.kext")["Enabled"] = True
                        support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleUSBMultitouch.kext", self.constants.multitouch_version, self.constants.multitouch_path)

            # Two-finger Top Case support for macOS High Sierra+
            if self.model == "MacBook5,2":
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleUSBTrackpad.kext", self.constants.apple_trackpad, self.constants.apple_trackpad_path) # Also requires AppleUSBTopCase.kext
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("LegacyKeyboardInjector.kext", self.constants.legacy_keyboard, self.constants.legacy_keyboard_path) # Inject legacy personalities into AppleUSBTCKeyboard and AppleUSBTCKeyEventDriver


    def _thunderbolt_handling(self) -> None:
        """
        Thunderbolt Handler
        """

        if self.constants.disable_tb is True and self.model in ["MacBookPro11,1", "MacBookPro11,2", "MacBookPro11,3", "MacBookPro11,4", "MacBookPro11,5"]:
            logging.info("- Disabling 2013-2014 laptop Thunderbolt Controller")
            if self.model in ["MacBookPro11,3", "MacBookPro11,5"]:
                # 15" dGPU models: IOACPIPlane:/_SB/PCI0@0/PEG1@10001/UPSB@0/DSB0@0/NHI0@0
                tb_device_path = "PciRoot(0x0)/Pci(0x1,0x1)/Pci(0x0,0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)"
            else:
                # 13" and 15" iGPU 2013-2014 models: IOACPIPlane:/_SB/PCI0@0/P0P2@10000/UPSB@0/DSB0@0/NHI0@0
                tb_device_path = "PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)"

            self.config["DeviceProperties"]["Add"][tb_device_path] = {"class-code": binascii.unhexlify("FFFFFFFF"), "device-id": binascii.unhexlify("FFFF0000")}


    def _webcam_handling(self) -> None:
        """
        iSight Handler
        """
        if self.model in smbios_data.smbios_dictionary:
            if "Legacy iSight" in smbios_data.smbios_dictionary[self.model]:
                if smbios_data.smbios_dictionary[self.model]["Legacy iSight"] is True:
                    support.BuildSupport(self.model, self.constants, self.config).enable_kext("LegacyUSBVideoSupport.kext", self.constants.apple_isight_version, self.constants.apple_isight_path)

        if not self.constants.custom_model:
            if self.constants.computer.pcie_webcam is True:
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleCameraInterface.kext", self.constants.apple_camera_version, self.constants.apple_camera_path)
        else:
            if self.model.startswith("MacBook") and self.model in smbios_data.smbios_dictionary:
                if cpu_data.CPUGen.haswell <= smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.kaby_lake:
                    support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleCameraInterface.kext", self.constants.apple_camera_version, self.constants.apple_camera_path)


    def _usb_handling(self) -> None:
        """
        USB Handler
        """
        
        if self.model not in ["MacBookAir8,1", "MacBookAir8,2", "MacBookAir9,1", "MacBookPro16,3"]:
            logging.info("Your Mac is not affected by Unsupported Mantissa speed kernel panics, so we continue with USB port mapping.")
            # USB Map
            usb_map_path = Path(self.constants.plist_folder_path) / Path("AppleUSBMaps/Info.plist")
            usb_map_tahoe_path = Path(self.constants.plist_folder_path) / Path("AppleUSBMaps/Info-Tahoe.plist")
            if (
                usb_map_path.exists()
                and usb_map_tahoe_path.exists()
                and (self.constants.allow_oc_everywhere is False or self.constants.allow_native_spoofs is True)
                and self.model not in ["Xserve2,1", "Dortania1,1"]
                and (
                    (self.model in model_array.Missing_USB_Map or self.model in model_array.Missing_USB_Map_Ventura)
                    or self.constants.serial_settings in ["Moderate", "Advanced"])
            ):
                logging.info("- Adding USB-Map.kext and USB-Map-Tahoe.kext")
                Path(self.constants.map_kext_folder).mkdir()
                Path(self.constants.map_kext_folder_tahoe).mkdir()
                Path(self.constants.map_contents_folder).mkdir()
                Path(self.constants.map_contents_folder_tahoe).mkdir()
                shutil.copy(usb_map_path, self.constants.map_contents_folder)
                # for the tahoe, need to copy but rename to Info.plist
                shutil.copy(usb_map_tahoe_path, self.constants.map_contents_folder_tahoe / Path("Info.plist"))
                support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB-Map.kext")["Enabled"] = True
                support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB-Map-Tahoe.kext")["Enabled"] = True
                if self.model in model_array.Missing_USB_Map_Ventura and self.constants.serial_settings not in ["Moderate", "Advanced"]:
                    support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB-Map.kext")["MinKernel"] = "22.0.0"
    
            # Add UHCI/OHCI drivers
            # All Penryn Macs lack an internal USB hub to route USB 1.1 devices to the EHCI controller
            # And MacPro4,1, MacPro5,1 and Xserve3,1 are the only post-Penryn Macs that lack an internal USB hub
            # - Ref: https://techcommunity.microsoft.com/t5/microsoft-usb-blog/reasons-to-avoid-companion-controllers/ba-p/270710
            #
            # To be paired for usb11.py's 'Legacy USB 1.1' patchset
            #
            # Note: With macOS 14.1, injection of these kexts causes a panic.
            #       To avoid this, a MaxKernel is configured with XNU 23.0.0 (macOS 14.0).
            #       Additionally sys_patch.py stack will now patches the bins onto disk for 14.1+.
            #       Reason for keeping the dual logic is due to potential conflicts of in-cache vs injection if we start
            #       patching pre-14.1 hosts.
            if (
                smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.penryn.value or \
                self.model in ["MacPro4,1", "MacPro5,1", "Xserve3,1"]
            ):
                logging.info("- Adding UHCI/OHCI USB support")
                shutil.copy(self.constants.apple_usb_11_injector_path, self.constants.kexts_path)
                support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB1.1-Injector.kext/Contents/PlugIns/AppleUSBOHCI.kext")["Enabled"] = True
                support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB1.1-Injector.kext/Contents/PlugIns/AppleUSBOHCIPCI.kext")["Enabled"] = True
                support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB1.1-Injector.kext/Contents/PlugIns/AppleUSBUHCI.kext")["Enabled"] = True
                support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB1.1-Injector.kext/Contents/PlugIns/AppleUSBUHCIPCI.kext")["Enabled"] = True
    
                # Also remove MaxKernel from the USB-Map.kext, as USB stack will be downgraded after root patching
                support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB-Map.kext")["MaxKernel"] = ""
        else:
            logging.info("Your Mac is affected by Unsupported Mantissa speed kernel panics. Skipping USB port mapping.")                

    def _debug_handling(self) -> None:
        """
        Debug Handler for OpenCorePkg and Kernel Space
        """

        if self.constants.verbose_debug is True:
            logging.info("- Enabling Verbose boot")
            self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] += " -v"

        if self.constants.kext_debug is True:
            logging.info("- Enabling DEBUG Kexts")
            self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] += " -liludbgall liludump=90"
            # Disabled due to macOS Monterey crashing shortly after kernel init
            # Use DebugEnhancer.kext instead
            # self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] += " msgbuf=1048576"
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("DebugEnhancer.kext", self.constants.debugenhancer_version, self.constants.debugenhancer_path)

        if self.constants.opencore_debug is True:
            logging.info("- Enabling DEBUG OpenCore")
            self.config["Misc"]["Debug"]["Target"] = 0x43
            self.config["Misc"]["Debug"]["DisplayLevel"] = 0x80000042


    def _general_oc_handling(self) -> None:
        """
        General OpenCorePkg Handler
        """

        logging.info("- Adding OpenCanopy GUI")
        shutil.copy(self.constants.gui_path, self.constants.oc_folder)
        support.BuildSupport(self.model, self.constants, self.config).get_efi_binary_by_path("OpenCanopy.efi", "UEFI", "Drivers")["Enabled"] = True
        support.BuildSupport(self.model, self.constants, self.config).get_efi_binary_by_path("OpenRuntime.efi", "UEFI", "Drivers")["Enabled"] = True
        support.BuildSupport(self.model, self.constants, self.config).get_efi_binary_by_path("OpenLinuxBoot.efi", "UEFI", "Drivers")["Enabled"] = True
        support.BuildSupport(self.model, self.constants, self.config).get_efi_binary_by_path("ResetNvramEntry.efi", "UEFI", "Drivers")["Enabled"] = True

        if self.constants.showpicker is False:
            logging.info("- Hiding OpenCore picker")
            self.config["Misc"]["Boot"]["ShowPicker"] = False

        if self.constants.oc_timeout != 5:
            logging.info(f"- Setting custom OpenCore picker timeout to {self.constants.oc_timeout} seconds")
            self.config["Misc"]["Boot"]["Timeout"] = self.constants.oc_timeout

        if self.constants.vault is True:
            logging.info("- Setting Vault configuration")
            self.config["Misc"]["Security"]["Vault"] = "Secure"

    def _t1_handling(self) -> None:
            """
            T1 Security Chip Handler with Crash Protection
            """
            if self.model not in ["MacBookPro13,2", "MacBookPro13,3", "MacBookPro14,2", "MacBookPro14,3"]:
                return
        
            logging.info("- Enabling T1 Security Chip support")
        
            try:
                # Initialize the helper once to avoid repeated overhead and potential race conditions
                builder = support.BuildSupport(self.model, self.constants, self.config)
        
                # 1. Unblock Kernel Drivers
                # We use a helper list to iterate; this makes it easier to catch specific failures
                identifiers = ["com.apple.driver.AppleSSE", "com.apple.driver.AppleKeyStore", "com.apple.driver.AppleCredentialManager"]
                
                for identifier in identifiers:
                    item = builder.get_item_by_kv(self.config["Kernel"]["Block"], "Identifier", identifier)
                    if item:
                        item["Enabled"] = True
                    else:
                        logging.warning(f"  - Could not find block entry for {identifier}")
        
                # 2. Enable Kexts
                # Using a list of tuples to keep the logic clean and dry (DRY principle)
                kexts_to_enable = [
                    ("corecrypto_T1.kext", self.constants.t1_corecrypto_version, self.constants.t1_corecrypto_path),
                    ("AppleSSE.kext", self.constants.t1_sse_version, self.constants.t1_sse_path),
                    ("AppleKeyStore.kext", self.constants.t1_key_store_version, self.constants.t1_key_store_path),
                    ("AppleCredentialManager.kext", self.constants.t1_credential_version, self.constants.t1_credential_path),
                    ("KernelRelayHost.kext", self.constants.kernel_relay_version, self.constants.kernel_relay_path),
                ]
        
                for name, version, path in kexts_to_enable:
                    builder.enable_kext(name, version, path)
        
            except (KeyError, TypeError, AttributeError) as e:
                logging.error(f"CRITICAL: Failed to configure T1 Security Chip due to data structure mismatch: {e}")
                # In a security-sensitive context, you might want to raise a custom error 
                # or exit gracefully rather than continuing in an undefined state.
            except Exception as e:
                logging.error(f"UNEXPECTED ERROR in T1 handling: {e}")
                sys.exit(3)
            
    def _t2_handling(self) -> None:
        """
        T2 Security Chip Handler
        T2 Macs shouldn't be patched with T1 patches because on T2 Macs, the T2 controlls the USB controller, while on T1 Macs, that's not the case.
        """
        if self.model not in ["MacBookAir8,1", "MacBookAir8,2", "MacBookAir9,1", "Macmini8,1", "iMacPro1,1", "MacBookPro15,2", "MacBookPro15,1", "MacBookPro15,3", "MacBookPro15,4", "MacBookPro16,3"]:
            return

        builder = support.BuildSupport(self.model, self.constants, self.config)
        logging.info("- Enabling WhateverGreen")
        
        if support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("WhateverGreen.kext").get("Enabled") is not True:
            support.BuildSupport(self.model, self.constants, self.config).enable_kext(
                "WhateverGreen.kext", self.constants.whatevergreen_version, self.constants.whatevergreen_path
            )
        try:
            logging.info("Enabling CryptexFixup.kext")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("CryptexFixup.kext", "1.0.5", self.constants.kexts_path)
        except Exception as e:
            logging.error("Injecting CryptexFixup.kext failed because of the following error:")
            logging.exception("Stack Trace:") # This prints the full technical error
            logging.info("Please try again later.")
            sys.exit(3)
        try:
            logging.info("Enabling AMFIPass.kext")
            # AMFIPass is critical for root patching (GPU drivers) on Tahoe
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("AMFIPass.kext", "1.4.1", self.constants.kexts_path)
        except Exception as e:
            logging.error("Injecting AMFIPass.kext failed because of the following error:")
            logging.exception("Stack Trace:") # This prints the full technical error
            logging.info("Please try again later.")
            sys.exit(3)
        if self.model in ["MacBookAir8,1", "MacBookAir8,2", "MacBookAir9,1", "MacBookPro16,3"]:
            logging.info(f"- {self.model}: Applying Unsupported Mantissa Speed kernel panic patches")
            logging.info(f"- {self.model}: Disable USB-Map.kext or/and USB-Map-Tahoe.kext if enabled to avoid unsupported mantissa speed panics.")
            # Disable USB-Map.kext and USB-Map-Tahoe.kext since on these models I can't rely on guesswork whether USB mapping that must be disabled on T2 macs is there or not.
            try:
                if support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB-Map.kext")["Enabled"] == True:
                    logging.info("We found USB-Map.kext. Disabling...")
                    support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB-Map.kext")["Enabled"] = False
                if support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB-Map-Tahoe.kext")["Enabled"] == True:
                    logging.info("We found USB-Map-Tahoe.kext. Disabling...")
                    support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB-Map-Tahoe.kext")["Enabled"] = False
                else:
                    logging.info("This is an extra check to make sure that no USB port mapping is injected onto Macs affected by Unsupported Mantissa speed panics.")
                    logging.info("No USB-Map.kext or USB-Tahoe.kext is found. Continuing onto the next step...")
                try:
                    logging.info("Injecting Disable AppleUSBHostPort power state timeout patches...")
                    # Define and append the HostPort Patch
                    logging.info("  - Injecting AppleUSBHostPort power state timeout patch")
                    usb_host_patch = {
                        "Arch": "x86_64",
                        "Comment": "Disable AppleUSBHostPort power state timeout",
                        "Enabled": True,
                        "Identifier": "com.apple.driver.AppleUSBHostPort",
                        "Find": b"\x48\x85\xC0\x74\x08\x48\x8B\x00\x48\x8B\x40\x28\xFF\xE0",
                        "Replace": b"\xEB\x0C\x90\x90\x90\x90\x90\x90\x90\x90\x90\x90\x90\x90",
                        "MinKernel": "24.0.0"
                    }
                    self.config["Kernel"]["Patch"].append(usb_host_patch)
                except Exception as e:
                    logging.error("We have some troubles injecting AppleUSBHostPort power state timeout patches. The error is the following:")
                    logging.exception("Stack Trace:") # This prints the full technical error
                    logging.info("Aborting...")
                    sys.exit(3)
                try:
                    # Define and append the VHCI Patch
                    logging.info("  - Injecting AppleUSBVHCI transition timeout patch")
                    vhci_patch = {
                        "Arch": "x86_64",
                        "Comment": "Patch AppleUSBVHCI to skip transition timeout",
                        "Enabled": True,
                        "Identifier": "com.apple.driver.AppleUSBVHCI",
                        "Find": b"\x48\x8B\x05\x00\x00\x00\x00\x48\x8D\x0D\x00\x00\x00\x00\x41\xBB\x01\x00\x00\x00",
                        "Replace": b"\x48\x8B\x05\x00\x00\x00\x00\x48\x8D\x0D\x00\x00\x00\x00\x41\xBB\x00\x00\x00\x00",
                        "MinKernel": "24.0.0"
                    }
                    self.config["Kernel"]["Patch"].append(vhci_patch)
                except Exception as E:
                    logging.error("We have some troubles injecting AppleUSBVHCI transition timeout patches. The error is the following:")
                    logging.exception("Stack Trace:") # This prints the full technical error
                    logging.info("Aborting...")
                    sys.exit(3)
                    
            except Exception as E:
                logging.error("We have some troubles injecting Unsupported Mantissa speed patches. It may be because files are missing or the syntax is invalid. The error is the following:")
                logging.exception("Stack Trace:") # This prints the full technical error
                logging.info("Aborting...")
                sys.exit(3)
            try:
                logging.info("- Skipping Language and Region selection")
                # Sets the language to English (Universal) and avoid the initial picker
                self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["prev-lang:kbd"] = "en-US:0"
            except Exception as e:
                logging.error("Skipping language and region selection failed because of the following error:")
                logging.exception("Stack Trace:") # This prints the full technical error
                logging.info("Please try again later.")
                logging.info(f"On your {self.model}, skipping the language selection is absolutely required to avoid Unsupported Mantissa speed kernel panics.")
                sys.exit(3)

        # T2 Support: Enable disk access (AMFI bypass), graphics fixes, and boot delay
        try:
            logging.info("- Adding T2-specific boot arguments for macOS 15/26")
            self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] += " -v rddelay=5 amfi=0x80 igfxfw=2 igfxonln=1 -disable_ext_panics -no_compat_check"
        except Exception as e:
            logging.error("Adding T2 specific boot arguments failed because of the following error:")
            logging.exception("Stack Trace:") # This prints the full technical error
            logging.info("Please try again later.")
            sys.exit(3)
            
        # Target the Delete section
        try:
            if "7C436110-AB2A-4BBB-A880-FE41995C9F82" not in self.config["NVRAM"]["Delete"]:
                logging.info("-Add 7C436110-AB2A-4BBB-A880-FE41995C9F82 to the delete section in OpenCore")
                self.config["NVRAM"]["Delete"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"] = []
            
            # Add variables to the list so they get cleared on boot
            delete_node = self.config["NVRAM"]["Delete"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]
            if "boot-args" not in delete_node:
                delete_node.append("boot-args")
        except Exception as e:
            logging.error("Adding the following NVRAM variable 7C436110-AB2A-4BBB-A880-FE41995C9F82 failed to be added to the delete section due to the following error:")
            logging.exception("Stack Trace:") # This prints the full technical error
            logging.info("Please try again later.")
            sys.exit(3)
        try:
            logging.info("- Disabling Library Validation")
            support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(
                self.config["Kernel"]["Patch"], "Comment", "Disable Library Validation Enforcement"
            )["Enabled"] = True
        except Exception as e:
            logging.error("Disabling Library Validation Enforcement due to the following error:")
            logging.exception("Stack Trace:") # This prints the full technical error
            logging.info("Please try again later.")
            sys.exit(3)
        try:
            logging.info("- Set SIP to 0x803")
            self._set_nvram_value(APPLE_NVRAM_UUID, "csr-active-config", binascii.unhexlify("03080000"), overwrite=True)
        except Exception as e:
            logging.error("Setting SIP to 0x803 failed due to the following error:")
            logging.exception("Stack Trace:") # This prints the full technical error
            logging.info("Please try again later.")
            sys.exit(3)

         # Target: NVRAM -> Add -> UUID -> auth-root-status
         try:
             logging.info("Setting auth-root-status to 00")
             self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["auth-root-status"] = "00"
         except Exception as e:
             logging.error("We couldn't set auth-root-status to 00 because of the following error:")
             logging.exception("Stack Trace:") # This prints the full technical error
             logging.info("Please try again later.")
             sys.exit(3)

        try:
            logging.info("Enabling CPUID masking")
            vmm_spoof_val = "AAAAAAAAAAAAAIAAAAAAAAAAAA=="
    
            self.config["Kernel"]["Emulate"]["Cpuid1Data"] = vmm_spoof_val
            self.config["Kernel"]["Emulate"]["Cpuid1Mask"] = vmm_spoof_val
        except Exception as e:
            logging.error("CPUID masking failed because of the following error:")
            logging.exception("Stack Trace:") # This prints the full technical error
            logging.info("Please try again later.")
            sys.exit(3)
        try:
            logging.info("Set ReleaseUsbOwnership to True")
            self.config["UEFI"]["Quirks"]["ReleaseUsbOwnership"] = True
        except Exception as e:
            logging.error("Setting ReleaseUsbOwnership to True failed because of the following error:")
            logging.exception("Stack Trace:") # This prints the full technical error
            logging.info("Please try again later.")
            sys.exit(3)
        try:
            logging.info("Add mitigations for delays when booting from external bootable media")
            self.config["UEFI"]["APFS"]["SetApfsTrimTimeout"] = -1
        except Exception as e:
            logging.error("Setting SetApfsTrimTimeout to -1 failed because of the following error:")
            logging.exception("Stack Trace:") # This prints the full technical error
            logging.info("Please try again later.")
            sys.exit(3)
        
        # After ~20 SEP mailbox timeouts AppleSEPManagerIntel panics.
        # Patch converts the panic call to an early return.
        # 5. SEP Panic Patch Injection
        try:
            logging.info("- Enabling AppleSEPManager timeout panic patch for T2 Macs")
            new_patch = {
                "Arch": "x86_64",
                "Comment": "Prevent AppleSEPManager SEP timeout panic",
                "Enabled": True,
                "Identifier": "com.apple.driver.AppleSEPManager",
                "Find": b"\x48\x83\xBF\xB0\x03\x00\x00\x00\x75\x4F",
                "Replace": b"\x48\x83\xBF\xB0\x03\x00\x00\x00\xEB\x4F",
                "MinKernel": "24.0.0"
            }
            self.config["Kernel"]["Patch"].append(new_patch)
        except Exception as e:
            logging.error("Enabling AppleSEPManager timeout panic patch for T2 Macs failed due to the following error:")
            logging.exception("Stack Trace:") # This prints the full technical error
            logging.info("Please try again later.")
            sys.exit(3)
