"""
global_settings.py: Library for querying and writing global environment settings

Alternative to Apple's 'defaults' tool
Store data in '/Users/Shared'
This is to ensure compatibility when running without a user
ie. during automated patching
"""

import logging
import plistlib
import os
import subprocess
from pathlib import Path


class GlobalEnviromentSettings:
    """
    Library for querying and writing global environment settings
    """

    def __init__(self) -> None:
        self.file_name:              str = ".com.dortania.opencore-legacy-patcher.plist"
        self.global_settings_folder: str = "/Users/Shared"
        self.global_settings_plist:  str = f"{self.global_settings_folder}/{self.file_name}"

        self._generate_settings_file()
        self._convert_defaults_to_global_settings()


    def read_property(self, property_name: str) -> str:
        """
        Reads a property from the global settings file
        """
        if Path(self.global_settings_plist).is_symlink():
            logging.warning("Security Alert: Symlink detected during read. Ignoring.")
            return None

        if Path(self.global_settings_plist).exists():
            try:
                # Security: Verify ownership before loading data
                file_info = os.stat(self.global_settings_plist)
                if file_info.st_uid not in [0, os.getuid()]:
                    logging.error("Security Error: Settings file is owned by an untrusted user.")
                    return None

                plist = plistlib.load(Path(self.global_settings_plist).open("rb"))
                if property_name in plist:
                    return plist[property_name]
            except Exception as e:
                logging.error("Error: Unable to read global settings file")
                logging.error(e)
                return None
        return None


    def delete_property(self, property_name: str) -> None:
        """
        Deletes a property from the global settings file
        """
        if Path(self.global_settings_plist).exists():
            try:
                # Security: Verify ownership
                file_info = os.stat(self.global_settings_plist)
                if file_info.st_uid not in [0, os.getuid()]:
                    logging.error("Security Error: Settings file is owned by an untrusted user.")
                    return

                plist = plistlib.load(Path(self.global_settings_plist).open("rb"))
                if property_name in plist:
                    del plist[property_name]
                    plistlib.dump(plist, Path(self.global_settings_plist).open("wb"))
                    os.chmod(self.global_settings_plist, 0o600)
            except Exception as e:
                logging.error("Error: Unable to modify global settings file")
                logging.error(e)


    def write_property(self, property_name: str, property_value) -> None:
        """
        Writes a property to the global environment settings
        """
        # Security: Destroy symlinks
        if Path(self.global_settings_plist).is_symlink():
            logging.warning("Security Alert: Symlink detected. Unlinking.")
            Path(self.global_settings_plist).unlink()

        if Path(self.global_settings_plist).exists():
            try:
                # Security: Verify ownership
                file_info = os.stat(self.global_settings_plist)
                if file_info.st_uid not in [0, os.getuid()]:
                    logging.error("Security Error: Settings file is owned by an untrusted user.")
                    return

                plist = plistlib.load(Path(self.global_settings_plist).open("rb"))
                plist[property_name] = property_value
                
                plistlib.dump(plist, Path(self.global_settings_plist).open("wb"))
                os.chmod(self.global_settings_plist, 0o600)
            except Exception as e:
                logging.error("Failed to write to global settings file")
                logging.error(e)


    def _generate_settings_file(self) -> None:
        """
        Initializes the settings file and handles ownership conflicts
        """
        path = Path(self.global_settings_plist)

        # 1. Clear Symlinks
        if path.is_symlink():
            path.unlink()

        # 2. Ownership Conflict Resolution (Self-Healing)
        if path.exists():
            file_info = os.stat(self.global_settings_plist)
            if file_info.st_uid not in [0, os.getuid()]:
                logging.warning("Untrusted settings file detected. Attempting to remove...")
                try:
                    # Attempt to remove the file if we have directory write access
                    path.unlink()
                except PermissionError:
                    # If we fail, tell the user to use sudo
                    logging.error("CRITICAL: Cannot remove untrusted file. Please run:")
                    logging.error(f"sudo rm {self.global_settings_plist}")
                    return

        # 3. Create fresh file if missing
        if not path.exists():
            try:
                Path(self.global_settings_folder).mkdir(parents=True, exist_ok=True)
                plistlib.dump({"Developed by Dortania": True}, path.open("wb"))
                os.chmod(self.global_settings_plist, 0o600)
            except (PermissionError, OSError) as e:
                logging.info(f"Unable to initialize global settings file: {e}")


    def _convert_defaults_to_global_settings(self) -> None:
        """
        Converts legacy defaults to global settings
        """
        defaults_path = Path("~/Library/Preferences/com.dortania.opencore-legacy-patcher.plist").expanduser()

        if defaults_path.exists():
            try:
                defaults_plist = plistlib.load(defaults_path.open("rb"))
                
                if Path(self.global_settings_plist).exists():
                    global_settings_plist = plistlib.load(Path(self.global_settings_plist).open("rb"))
                else:
                    global_settings_plist = {}

                global_settings_plist.update(defaults_plist)
                
                plistlib.dump(global_settings_plist, Path(self.global_settings_plist).open("wb"))
                os.chmod(self.global_settings_plist, 0o600)
                
                defaults_path.unlink()
            except Exception as e:
                logging.error("Error during settings migration")
                logging.error(e)
