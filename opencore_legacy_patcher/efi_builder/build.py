"""
build.py: Class for generating OpenCore Configurations tailored for Macs
"""

import copy
import pickle
import shutil
import logging
import zipfile
import plistlib
import logging
import sys

from pathlib import Path
from datetime import date

from .. import constants

from ..support import utilities

from .networking import (
wired,
wireless
)
from . import (
bluetooth,
firmware,
graphics_audio,
support,
storage,
smbios,
security,
misc
)

def rmtree_handler(func, path, exc_info) -> None:
    try:
        if exc_info[0] == FileNotFoundError:
            return
        # If it's not a FileNotFoundError, we log the failure to the GUI
        logging.error("Critical: rmtree_handler cannot start cleanup for path!")
        raise 
    except Exception as e:
        logging.error(f"Function Error: {e}")

class BuildOpenCore:
        
    """
    Core Build Library for generating and validating OpenCore EFI Configurations
    compatible with genuine Macs
    """
    
    def __init__(self, model: str, global_constants: constants.Constants) -> None:
        try:
            self.model: str = model
            self.config: dict = None
            self.constants: constants.Constants = global_constants

            if not hasattr(self.constants, "device_properties"):
                self.constants.device_properties = {}

            self._build_opencore()
        except Exception as e:
            logging.error(f"Function Error: {e}")
            sys.exit(3)

    
    def _build_efi(self) -> None:
        """
        Build EFI folder
        """

        utilities.cls()
        logging.info(f"Building Configuration {'for external' if self.constants.custom_model else 'on model'}: {self.model}")

        self._generate_base()
        self._set_revision()

        # Set Lilu and co.
        support.BuildSupport(self.model, self.constants, self.config).enable_kext("Lilu.kext", self.constants.lilu_version, self.constants.lilu_path)
        self.config["Kernel"]["Quirks"]["DisableLinkeditJettison"] = True
        # Kernel Quirks: Set PanicNoKextDump to True for better logging
        self.config["Kernel"]["Quirks"]["PanicNoKextDump"] = True
        
        # Ensure UEFI section exists
        if "UEFI" not in self.config:
            self.config["UEFI"] = {}
        # Ensure UEFI Quirks subsection exists
        if "Quirks" not in self.config["UEFI"]:
            self.config["UEFI"]["Quirks"] = {}

        # Check for T2 chip via device_properties or fallback to hardcoded list
        is_t2 = False
        if hasattr(self.constants, "device_properties"):
            if "T2_CHIP" in self.constants.device_properties.get(self.model, {}).get("Features", []):
                is_t2 = True
        # Fallback to known T2 models list if device_properties not yet populated
        if not is_t2 and self.model in ["MacBookAir8,1", "MacBookAir8,2", "MacBookAir9,1", "Macmini8,1", "iMacPro1,1", "MacBookPro15,2", "MacBookPro15,1", "MacBookPro15,3", "MacBookPro15,4", "MacBookPro16,1", "MacBookPro16,3", "MacBookPro16,4"]:
            is_t2 = True

        if is_t2:
            try:
                logging.info("- Adding T2-specific bypass NVRAM variables")

                # Append T2-specific boot args to the existing boot-args string
                t2_args = " -ibtcompatbeta -amfipassbeta vmmroot=1 -disable_ext_panics amfi_get_out_of_my_way=1 cs_allow_invalid=1 -arv ipc_control_port_options=0"
                if "NVRAM" not in self.config:
                    self.config["NVRAM"] = {"Add": {}}
                    if "7C436110-AB2A-4BBB-A880-FE41995C9F82" not in self.config["NVRAM"]["Add"]:
                        self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"] = {"boot-args": ""}

                # Now safely append
                current_args = self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"].get("boot-args", "")
                self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] = current_args + t2_args

                 # Force CPUID hypervisor bit for T2 root patch VM spoofing
                 # Except for Macmini8,1 which experiences GPU issues with CPUID masking
                 if self.model != "Macmini8,1":
                     self.constants.set_vmm_cpuid = True
                 self.constants.force_vmm = True
                 self.constants.apfs_trim_timeout = False
                if "UEFI" not in self.config:
                    self.config["UEFI"] = {}
                if "Quirks" not in self.config["UEFI"]:
                    self.config["UEFI"]["Quirks"] = {}
                self.config["UEFI"]["Quirks"]["ReleaseUsbOwnership"] = True

                # Ensure T2 SMBIOS masking is created and not merged with hardware values
                if "PlatformInfo" not in self.config:
                    self.config["PlatformInfo"] = {}
                self.config["PlatformInfo"]["UpdateSMBIOSMode"] = "Create"
                self.config["PlatformInfo"]["CustomSMBIOSGuid"] = True
                self.config["PlatformInfo"]["UpdateSMBIOS"] = True
                self.config["PlatformInfo"]["UpdateDataHub"] = True
                self.config["PlatformInfo"]["UpdateNVRAM"] = True
                if "Generic" not in self.config["PlatformInfo"]:
                    self.config["PlatformInfo"]["Generic"] = {}
                self.config["PlatformInfo"]["Generic"]["AdviseFeatures"] = True

                # Ensure DisableIoMapper is True
                self.config["Kernel"]["Quirks"]["DisableIoMapper"] = True
                self.config["Kernel"]["Quirks"]["AppleCpuPmCfgLock"] = True
                self.config["Kernel"]["Quirks"]["AppleXcpmCfgLock"] = True
                
                # UEFI Quirks for T2 Macs as requested
                self.config["UEFI"]["Quirks"]["JumpstartHotPlug"] = True
                self.config["UEFI"]["Quirks"]["UnblockFsConnect"] = False
                logging.info("- Setting PanicNoKextDump to True for T2 Macs")
                self.config["Kernel"]["Quirks"]["PanicNoKextDump"] = True

                # Add T2 bypass SSDT if available
                ssdt_file = "SSDT-T2-FAKE.aml"
                ssdt_src = self.constants.payload_path / "ACPI" / ssdt_file
                if ssdt_src.exists():
                    logging.info(f"- Adding {ssdt_file} for T2 bypass")
                    if "ACPI" not in self.config:
                        self.config["ACPI"] = {}
                    if "Add" not in self.config["ACPI"]:
                        self.config["ACPI"]["Add"] = []
                    acpi_add = self.config["ACPI"]["Add"]
                    # Check if already present
                    found = False
                    for item in acpi_add:
                        if item.get("Path") == ssdt_file:
                            item["Enabled"] = True
                            item["Comment"] = "Disable T2 peripherals to prevent bridge unresponsive panics"
                            found = True
                            break
                    if not found:
                        acpi_add.append({
                            "Comment": "Disable T2 peripherals to prevent bridge unresponsive panics",
                            "Enabled": True,
                            "Path": ssdt_file
                        })
                    # Copy SSDT to output ACPI directory
                    shutil.copy(ssdt_src, self.constants.acpi_path)
            except Exception as e:
                logging.error("Whoops, the app failed to inject the required kexts because of the following error:")
                logging.exception("Stack Trace:") # This prints the full technical error
                logging.info("Please try again later.")
                sys.exit(3)

        # macOS Sequoia support for Lilu plugins
        self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] += " -lilubetaall"

        # Call support functions
        for function in [
            firmware.BuildFirmware,
            wired.BuildWiredNetworking,
            wireless.BuildWirelessNetworking,
            graphics_audio.BuildGraphicsAudio,
            bluetooth.BuildBluetooth,
            storage.BuildStorage,
            smbios.BuildSMBIOS,
            security.BuildSecurity,
            misc.BuildMiscellaneous
        ]:
            function(self.model, self.constants, self.config)

        # Work-around ocvalidate
        if self.constants.validate is False:
            logging.info("- Adding bootmgfw.efi BlessOverride")
            if "BlessOverride" not in self.config["Misc"]:
                self.config["Misc"]["BlessOverride"] = []
                self.config["Misc"]["BlessOverride"].append("\\EFI\\Microsoft\\Boot\\bootmgfw.efi")
    
    
    def _generate_base(self) -> None:
        """
        Generate OpenCore base folder and config
        """

        if not Path(self.constants.build_path).exists():
            logging.info("Creating build folder")
            Path(self.constants.build_path).mkdir()
        else:
            logging.info("Build folder already present, skipping")

        if Path(self.constants.opencore_zip_copied).exists():
            logging.info("Deleting old copy of OpenCore zip")
            Path(self.constants.opencore_zip_copied).unlink()
        if Path(self.constants.opencore_release_folder).exists():
            logging.info("Deleting old copy of OpenCore folder")
            shutil.rmtree(self.constants.opencore_release_folder, onerror=rmtree_handler, ignore_errors=True)

        logging.info("")
        logging.info(f"- Adding OpenCore v{self.constants.opencore_version} {'DEBUG' if self.constants.opencore_debug is True else 'RELEASE'}")
        shutil.copy(self.constants.opencore_zip_source, self.constants.build_path)
        zipfile.ZipFile(self.constants.opencore_zip_copied).extractall(self.constants.build_path)

        # Setup config.plist for editing
        logging.info("- Adding config.plist for OpenCore")
        shutil.copy(self.constants.plist_template, self.constants.oc_folder)
        self.config = plistlib.load(Path(self.constants.plist_path).open("rb"))
    
    def _save_config(self) -> None:
        """
        Save config.plist to disk
        """
        try:
            plistlib.dump(
                self.config,
                Path(self.constants.plist_path).open("wb"),
                sort_keys=True,
        )
        except Exception as e:
            logging.error(f"Function Error while saving config: {e}")
            sys.exit(3)

    def _set_revision(self) -> None:
        """
        Set revision information in config.plist
        """
    
        # --- Safe access to #Revision ---
        rev = self.config.setdefault("#Revision", {})
        rev["Build-Version"] = f"{self.constants.patcher_version} - {date.today()}"
    
        if not self.constants.custom_model:
            rev["Build-Type"] = "OpenCore Built on Target Machine"
            computer_copy = copy.copy(self.constants.computer)
            computer_copy.ioregistry = None
            rev["Hardware-Probe"] = pickle.dumps(computer_copy)
        else:
            rev["Build-Type"] = "OpenCore Built for External Machine"
    
        rev["OpenCore-Version"] = (
            f"{self.constants.opencore_version} - "
            f"{'DEBUG' if self.constants.opencore_debug else 'RELEASE'}"
        )
        rev["Original-Model"] = self.model
    
        # --- Hardened NVRAM structure ---
        nvram = self.config.setdefault("NVRAM", {})
        add   = nvram.setdefault("Add", {})
    
        guid_key = "4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102"
        guid     = add.setdefault(guid_key, {})
    
        # Validate type to avoid malicious plist poisoning
        if not isinstance(guid, dict):
            logging.error(f"NVRAM GUID {guid_key} is not a dictionary — refusing to write metadata")
            return
    
        # --- Safe writes ---
        guid["OCLP-Version"] = f"{self.constants.patcher_version}"
        guid["OCLP-Model"]   = self.model

    
    
    def _build_opencore(self) -> None:
        """
        Kick off the build process

        This is the main function:
        - Generates the OpenCore configuration
        - Cleans working directory
        - Signs files
        - Validates generated EFI
        """

        # Generate OpenCore Configuration
        try:
            logging.info(f"Generating OpenCore configuration for {self.model} ...")
            self._build_efi()
        except Exception as e:
            logging.error(f"Whoops, Generating OpenCore configuration for {self.model} because of the following error:")
            logging.exception("Stack Trace:") # This prints the full technical error
            logging.info("Please try again later.")
            sys.exit(3)
        try:
            if self.constants.allow_oc_everywhere is False or self.constants.allow_native_spoofs is True or (self.constants.custom_serial_number != "" and self.constants.custom_board_serial_number != ""):
                smbios.BuildSMBIOS(self.model, self.constants, self.config).set_smbios()
            support.BuildSupport(self.model, self.constants, self.config).cleanup()
            self._save_config()
        except Exception as e:
            logging.error(f"Whoops, spoofing the SMBIOS for {self.model} failed because of the following error:")
            logging.exception("Stack Trace:") # This prints the full technical error
            logging.info("Please try again later.")
            sys.exit(3)

        # Post-build handling
        logging.info("Post-build handling")
        support.BuildSupport(self.model, self.constants, self.config).sign_files()
        support.BuildSupport(self.model, self.constants, self.config).validate_pathing()

        logging.info("")
        logging.info(f"Your OpenCore EFI for {self.model} has been built at:")
        logging.info(f"    {self.constants.opencore_release_folder}")
        logging.info("")
    
