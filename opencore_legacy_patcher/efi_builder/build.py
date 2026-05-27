"""
build.py: Class for generating OpenCore Configurations tailored for Macs
"""

import copy
import pickle
import shutil
import logging
import zipfile
import plistlib
import sys
import subprocess
import re

from pathlib import Path
from datetime import date

from .. import constants

from ..support import utilities
from ..datasets import model_array

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
    
    def _get_physical_apfs_slice(self, boot_dev: str) -> str:
        """
        Returns the physical partition slice (e.g., disk0s2) backing the APFS container.
        Falls back to a safe regex strip if diskutil fails.
        """
        try:
            # Query diskutil for the disk's structural info
            result = subprocess.run(
                ["diskutil", "info", boot_dev], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True, 
                check=True
            )
            # Look for the physical store backing the container
            for line in result.stdout.splitlines():
                if "APFS Physical Store" in line or "Part Of Whole" in line:
                    match = re.search(r'(disk\d+s\d+)', line)
                    if match:
                        return match.group(1)
        except Exception:
            pass
    
        # Fallback: If boot_dev is "disk1s1" or "disk0s2s1", extract the primary slice "diskXsY"
        match = re.match(r"(disk\d+s\d+)", boot_dev)
        return match.group(1) if match else "disk0s2"
        
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
        _T2_UHD630_MODELS = ["MacBookPro15,1", "MacBookPro15,2", "MacBookPro15,3", "MacBookPro15,4", "MacBookPro16,1", "MacBookPro16,3", "MacBookPro16,4", "Macmini8,1", "iMac19,1", "iMac19,2", "iMac20,1", "iMac20,2"]
        if self.model in _T2_UHD630_MODELS:
            logging.info(f"- Disabling VMM CPUID for {self.model} to prevent UHD 630 driver stall")
            self.constants.set_vmm_cpuid = False

        # Determine T2 status upfront
        is_t2 = self.model in model_array.T2Macs or "T2_CHIP" in self.constants.device_properties.get(self.model, {}).get("Features", [])

        if is_t2:
            try:
                logging.info("- Importing t2smbiossecurity")
                from ..efi_builder import t2smbiossecurity
                try:
                    logging.info("- Add Booter Quirks patches for T2 Macs ")
                    t2smbiossecurity.finalize_t2_tahoe(self.constants.plist_path)
                except Exception as e:
                    logging.error("Whoops, the function finalize_t2_tahoe failed to run because of the following error:")
                    logging.exception("Stack Trace:")
                    logging.info("Please try again later.")
                    sys.exit(3)

                logging.info("- Adding T2-specific bypass NVRAM variables")
                
                if "NVRAM" not in self.config:
                    self.config["NVRAM"] = {"Add": {}, "Delete": {}}
                if "Delete" not in self.config["NVRAM"]:
                    self.config["NVRAM"]["Delete"] = {}

                if "7C436110-AB2A-4BBB-A880-FE41995C9F82" not in self.config["NVRAM"]["Add"]:
                    self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"] = {"boot-args": ""}

                # Ensure we strictly clean out legacy variables from NVRAM to prevent corecrypto mismatch
                if "7C436110-AB2A-4BBB-A880-FE41995C9F82" not in self.config["NVRAM"]["Delete"]:
                    self.config["NVRAM"]["Delete"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"] = []
                
                for target_arg in ["boot-args", "csr-active-config", "amfi-allow-arguments"]:
                    if target_arg not in self.config["NVRAM"]["Delete"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]:
                        self.config["NVRAM"]["Delete"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"].append(target_arg)

                # Fetch template boot-args, scrub any accidental Lilu flags inherited from template plists
                raw_args = self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"].get("boot-args", "")
                scrubbed_args = " ".join([arg for arg in raw_args.split() if not arg.startswith("-lilu")])
                
                # Append required T2 args safely without compounding spaces
                t2_args = "-ibtcompatbeta -amfipassbeta"
                self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] = f"{scrubbed_args} {t2_args}".strip()
                
                # Ensure WriteFlash is enabled to commit changes to SPI ROM
                self.config["NVRAM"]["WriteFlash"] = True
                
                # Force DisableIoMapper for stability
                self.config["Kernel"]["Quirks"]["DisableIoMapper"] = True

            except Exception as e:
                logging.error("Whoops, the app failed to inject the required kexts because of the following error:")
                logging.exception("Stack Trace:")
                logging.info("Please try again later.")
                sys.exit(3)
        else:
            # For Non-T2 Legacy Hardware
            if "NVRAM" not in self.config:
                self.config["NVRAM"] = {"Add": {}}
            if "7C436110-AB2A-4BBB-A880-FE41995C9F82" not in self.config["NVRAM"]["Add"]:
                self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"] = {"boot-args": ""}
                
            current_boot_args = self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"]
            
            # Target 2017 iMac models specifically to bypass vt-d/broadcom complications
            _IMAC_2017_MODELS = ["iMac18,1", "iMac18,2", "iMac18,3"]
            if self.model in _IMAC_2017_MODELS:
                if "dart=0" not in current_boot_args:
                    logging.info(f"- Appending dart=0 boot argument for 2017 iMac hardware target to fix WiFi/Bluetooth issues on macOS Tahoe ({self.model})")
                    current_boot_args = f"{current_boot_args} dart=0".strip()

            if "-lilubetaall" not in current_boot_args:
                current_boot_args = f"{current_boot_args} -lilubetaall".strip()
                
            self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] = current_boot_args

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
    
    def _mount_efi_partition(self) -> bool:
        """
        Locate and mount the custom 'OpenCore' partition. 
        If missing, extracts the physical slice size via a universal plist,
        shrinks the APFS container to create unallocated free space, and then
        initializes the FAT32 partition bounded to exactly 200M to accommodate
        interleaved multi-boot drive schemes.
        """
        import subprocess
        import logging
        import plistlib
        import re

        def run_with_sudo(cmd_str: str) -> bool:
            """Helper to run a shell command with administrator privileges via osascript."""
            logging.info(f"- Executing privileged command: {cmd_str}")
            osascript_cmd = [
                "osascript", "-e",
                f'do shell script "{cmd_str}" with administrator privileges'
            ]
            try:
                subprocess.run(osascript_cmd, check=True, capture_output=True)
                return True
            except subprocess.CalledProcessError as e:
                stderr_err = e.stderr.decode().strip() if e.stderr else ""
                logging.error(f"Sudo command failed: {stderr_err if stderr_err else e}")
                return False

        try:
            # 1. Scan for any existing 'OpenCore' volume allocation map
            logging.info("- Scanning disk topology for existing 'OpenCore' partition...")
            result = subprocess.check_output(["diskutil", "list"], text=True)
            
            opencore_dev = ""
            for line in result.splitlines():
                if "OpenCore" in line:
                    parts = line.strip().split()
                    if parts:
                        dev_candidate = parts[-1]
                        if dev_candidate.startswith("disk"):
                            opencore_dev = dev_candidate
                            break

            # 2. If it exists, manage its mount state exclusively and EXIT
            if opencore_dev:
                logging.info(f"- Found existing 'OpenCore' target partition on {opencore_dev}")
                info = subprocess.check_output(["diskutil", "info", opencore_dev], text=True)
                
                if "Mounted:               Yes" in info:
                    logging.info(f"- 'OpenCore' partition ({opencore_dev}) is already mounted and active.")
                    return True
                
                logging.info(f"- 'OpenCore' partition ({opencore_dev}) is present but unmounted. Attempting mount...")
                if run_with_sudo(f"diskutil mount {opencore_dev}"):
                    logging.info("- Successfully mounted existing partition.")
                    return True
                else:
                    logging.error("- Failed to mount the existing 'OpenCore' partition container.")
                    return False

            # 3. Partition completely missing — Safe shrinkage sequence begins
            logging.warning("- 'OpenCore' partition not found anywhere on disk. Initializing allocation logic...")

            # Determine primary system boot slice identifier
            info_root = subprocess.check_output(["diskutil", "info", "/"], text=True)
            boot_dev = ""
            for line in info_root.splitlines():
                if "Device Identifier:" in line:
                    boot_dev = line.split()[-1]
                    break
            
            if not boot_dev:
                logging.error("- Could not pinpoint the primary boot disk identifier.")
                return False

            create_cmd = ""
            if "APFS" in info_root:
                physical_slice = self._get_physical_apfs_slice(boot_dev)
                total_bytes = 0
                
                try:
                    # Query the physical slice directly (e.g., disk0s2)
                    slice_plist_raw = subprocess.check_output(["diskutil", "info", "-plist", physical_slice])
                    slice_data = plistlib.loads(slice_plist_raw)
                    total_bytes = slice_data.get("Size", 0)
                    logging.info(f"- Successfully extracted physical slice size: {total_bytes} Bytes")
                except Exception as plist_err:
                    logging.warning(f"- Plist structural parsing failed: {plist_err}")

                if total_bytes > 0:
                    # Deduct exactly 210,000,000 bytes (~200MB) from current container boundaries
                    target_bytes = total_bytes - 210000000
                    logging.info(f"- Executing atomic APFS shrink and FAT32 injection pass on {physical_slice}...")
                    
                    # By passing the filesystem type, volume label, and size directly to resizeContainer,
                    # diskutil performs the shrink, creation, and partition formatting as an atomic operation.
                    # This safely bypasses the auto-mount locks that cause error -69832.
                    atomic_cmd = f"diskutil apfs resizeContainer {physical_slice} {target_bytes}B FAT32 OpenCore 200M"
                    
                    if run_with_sudo(atomic_cmd):
                        logging.info("- APFS container successfully resized and 'OpenCore' volume initialized natively!")
                        create_cmd = "" # Clear this out so the script doesn't try a secondary execution pass
                    else:
                        logging.error("- Atomic drive partition mapping and formatting layout sequence failed.")
                        return False
            # Execute final partition layout transformation entries
            if create_cmd and run_with_sudo(create_cmd):
                logging.info("- Partition created out of macOS container space successfully.")
                return True
            else:
                logging.error("- Failed to finalize drive formatting structures.")
                return False

        except Exception as e:
            logging.error("- Critical exception encountered during disk block allocation management.")
            logging.exception(e)
            return False

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

        # Best-effort EFI mount before writing any files
        if not self._mount_efi_partition():
            logging.info("- Continuing without mounted EFI (may require manual mount later)")

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
