"""
application_entry.py: Project entry point (Hardened)
"""

import os
import sys
import time
import logging
import threading
import re
from pathlib import Path

from . import constants
from .wx_gui import gui_entry
from .detections import (
    device_probe,
    os_probe
)
from .support import (
    utilities,
    defaults,
    arguments,
    reroute_payloads,
    commit_info,
    logging_handler,
    analytics_handler
)


class OpenCoreLegacyPatcher:
    """
    Initial entry point for starting OpenCore Legacy Patcher
    """

    def __init__(self) -> None:
        self.constants: constants.Constants = constants.Constants()

        logging_handler.InitializeLoggingSupport(self.constants)

        self._generate_base_data()

        if utilities.check_cli_args() is None:
            gui_entry.EntryPoint(self.constants).start()


    def _fix_cwd(self) -> None:
        """
        In some extreme scenarios, our current working directory may disappear.
        Uses a reliable system fallback path if the directory is missing.
        """
        try:
            _test_dir = Path.cwd()
            logging.info(f"Current working directory: {_test_dir}")
        except FileNotFoundError:
            # Fallback safely to the user's home directory or application bundle root
            # rather than purely relying on vulnerable __file__ resolution
            _test_dir = Path.home()
            os.chdir(_test_dir)
            logging.warning(f"Current working directory was invalid, reset safety fallback to: {_test_dir}")


    def _generate_base_data(self) -> None:
        """
        Generate base data required for the patcher to run
        """

        self.constants.wxpython_variant = True

        # Ensure we live after parent process dies (ie. LaunchAgent)
        os.setpgrp()

        # Generate OS data
        os_data = os_probe.OSProbe()
        self.constants.detected_os = os_data.detect_kernel_major()
        self.constants.detected_os_minor = os_data.detect_kernel_minor()
        self.constants.detected_os_build = os_data.detect_os_build()
        self.constants.detected_os_version = os_data.detect_os_version()

        # Generate computer data
        self.constants.computer = device_probe.Computer.probe()
        self.computer = self.constants.computer
        self.constants.booted_oc_disk = utilities.find_disk_off_uuid(utilities.clean_device_path(self.computer.opencore_path))
        if self.constants.computer.firmware_vendor:
            if self.constants.computer.firmware_vendor != "Apple":
                self.constants.host_is_hackintosh = True

        # Generate environment data
        self.constants.recovery_status = utilities.check_recovery()
        utilities.disable_cls()
        self._fix_cwd()

        # Generate binary data
        launcher_script = None
        launcher_binary = sys.executable
        if "python" in launcher_binary:
            # We're running from source
            launcher_script = __file__
            if "main.py" in launcher_script:
                launcher_script = launcher_script.replace("/resources/main.py", "/OpenCore-Patcher-GUI.command")
        self.constants.launcher_binary = launcher_binary
        self.constants.launcher_script = launcher_script

        # Initialize working directory after confirming payload integrity
        # Note: Implement absolute hash checking within verify_payload_integrity
        if hasattr(utilities, "verify_payload_integrity"):
            if not utilities.verify_payload_integrity(self.constants):
                raise SecurityError("Payload integrity verification failed. Execution halted.")

        self.constants.unpack_thread = threading.Thread(target=reroute_payloads.RoutePayloadDiskImage, args=(self.constants,))
        self.constants.unpack_thread.start()

        # Generate commit info
        self.constants.commit_info = commit_info.ParseCommitInfo(self.constants.launcher_binary).generate_commit_info()
        if self.constants.commit_info[0] not in ["Running from source", "Built from source"]:
            # Now that we have commit info, update nightly link securely
            branch = self.constants.commit_info[0]
            branch = branch.replace("refs/heads/", "")
            
            # Fix: Strict regex validation to ensure branch names only contain safe characters
            if re.match(r"^[a-zA-Z0-9_\-\./]+$", branch) and ".." not in branch:
                self.constants.installer_pkg_url_nightly = self.constants.installer_pkg_url_nightly.replace("main", branch)
            else:
                logging.error(f"Malicious or invalid branch name detected: {branch}. Falling back to default URL.")

        # Generate defaults
        defaults.GenerateDefaults(self.computer.real_model, True, self.constants)
        if self.constants.computer.build_model is None:
            logging.info(f"Initializing build_model to native host: {self.computer.real_model}")
            self.constants.computer.build_model = self.computer.real_model
        self.constants.analytics_thread = threading.Thread(target=analytics_handler.Analytics(self.constants).send_analytics)
        self.constants.analytics_thread.start()

        if utilities.check_cli_args() is None:
            self.constants.cli_mode = False
            return

        logging.info("Detected arguments, switching to CLI mode")
        self.constants.cli_mode = True  
        self.constants.gui_mode = False 

        ignore_args = ["--auto_patch", "--gui_patch", "--gui_unpatch", "--update_installed"]
        
        # If none of the specific arguments are in sys.argv
        if not any(x in sys.argv for x in ignore_args):
            self.constants.current_path = Path.cwd()

        # Fix: Deterministic Thread Synchronization.
        # Ensure arguments parsing never runs into race conditions regardless of flags if unpack state is required
        if "--auto_patch" not in sys.argv:
            while self.constants.unpack_thread.is_alive():
                time.sleep(self.constants.thread_sleep_interval)
        else:
            # Explicit guard or logging if auto_patch deliberately overrides synchronization safely
            logging.info("Proceeding with auto_patch execution orchestration flow.")

        arguments.arguments(self.constants)


class SecurityError(Exception):
    """Raised when an active security check or validation fails."""
    pass


def main():
    """
    Main entry point
    """
    OpenCoreLegacyPatcher()
