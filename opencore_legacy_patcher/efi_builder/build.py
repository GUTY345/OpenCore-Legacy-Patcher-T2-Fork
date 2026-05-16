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

    def _remove_conflicting_t2_ssdt(self) -> None:
        """
        Removes SSDT-T2-Fake.aml if a T2 Mac is detected, to prevent conflicts
        with newer T2-specific kernel patches and boot-args.
        """
        # Check if the current model is a T2 Mac by checking for the "T2_CHIP" feature.
        # This relies on constants.device_properties being populated, which happens
        # during the defaults generation phase.
        is_t2_mac = "T2_CHIP" in self.constants.device_properties.get(self.model, {}).get("Features", [])

        if is_t2_mac:
            ssdt_path = self.constants.acpi_path / "SSDT-T2-Fake.aml"
            if ssdt_path.exists():
                logging.warning(f"Conflicting SSDT-T2-Fake.aml detected for T2 Mac ({self.model}). Removing to prevent Kernel Panic.")
                try:
                    ssdt_path.unlink()
                    logging.info(f"Successfully removed {ssdt_path.name}")
                except Exception as e:
                    logging.error(f"Failed to remove {ssdt_path.name}: {e}")
            else:
                logging.info(f"SSDT-T2-Fake.aml not found for T2 Mac ({self.model}), no action needed.")
        else:
            logging.info(f"Not a T2 Mac ({self.model}), skipping SSDT-T2-Fake.aml conflict check.")
    
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

        # Intel UHD 630 VMM Stall Fix (2018-2020 Models)
        _T2_UHD630_MODELS = ["MacBookPro15,1", "MacBookPro15,2", "MacBookPro15,3", "MacBookPro15,4", "MacBookPro16,1", "MacBookPro16,2", "MacBookPro16,3", "MacBookPro16,4", "Macmini8,1", "iMac19,1", "iMac19,2", "iMac20,1", "iMac20,2"]
        if self.model in _T2_UHD630_MODELS:
            logging.info(f"- Disabling VMM CPUID for {self.model} to prevent UHD 630 driver stall")
            self.constants.set_vmm_cpuid = False

        if "T2_CHIP" in self.constants.device_properties.get(self.model, {}).get("Features", []):
            try:
                logging.info("- Importing t2smbiossecurity")
                from ..efi_builder import t2smbiossecurity
                try:
                    logging.info("- Add Booter Quirks patches for T2 Macs ")
                    # Updated to match function name in t2smbiossecurity.py
                    t2smbiossecurity.finalize_t2_tahoe(self.constants.plist_path)
                except Exception as e:
                    logging.error("Whoops, the function finalize_t2_tahoe_internal failed to run because of the following error:")
                    logging.exception("Stack Trace:") # This prints the full technical error
                    logging.info("Please try again later.")
                    sys.exit(3)

                logging.info("- Adding T2-specific bypass NVRAM variables")
            
                # Append T2-specific boot args to the existing boot-args string
                t2_args = " -ibtcompatbeta -amfipassbeta"
                if "NVRAM" not in self.config:
                    self.config["NVRAM"] = {"Add": {}}
                    if "7C436110-AB2A-4BBB-A880-FE41995C9F82" not in self.config["NVRAM"]["Add"]:
                        self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"] = {"boot-args": ""}

                # Now safely append
                current_args = self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"].get("boot-args", "")
                self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] = current_args + t2_args
            
                # Ensure DisableIoMapper is True
                self.config["Kernel"]["Quirks"]["DisableIoMapper"] = True
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
    
