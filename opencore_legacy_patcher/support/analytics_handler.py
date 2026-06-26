"""
analytics_handler.py: Analytics and Crash Reporting Handler
"""

import json
import datetime
import plistlib
from pathlib import Path

from .. import constants
from . import (
    network_handler,
    global_settings
)

DATE_FORMAT:      str = "%Y-%m-%d %H-%M-%S"
ANALYTICS_SERVER: str = ""
SITE_KEY:          str = ""
CRASH_URL:          str = ANALYTICS_SERVER + "/crash"

VALID_ANALYTICS_ENTRIES: dict = {
    'KEY':                 str,               # Prevent abuse (embedded at compile time)
    'UNIQUE_IDENTITY':     str,               # Host's UUID as SHA1 hash
    'APPLICATION_NAME':    str,               # ex. OpenCore Legacy Patcher
    'APPLICATION_VERSION': str,               # ex. 0.2.0
    'OS_VERSION':          str,               # ex. 10.15.7
    'MODEL':               str,               # ex. MacBookPro11,5
    'GPUS':                list,              # ex. ['Intel Iris Pro', 'AMD Radeon R9 M370X']
    'FIRMWARE':            str,               # ex. APPLE
    'LOCATION':            str,               # ex. 'US' (just broad region, don't need to be specific)
    'TIMESTAMP':           datetime.datetime, # ex. 2021-09-01-12-00-00
}

VALID_CRASH_ENTRIES: dict = {
    'KEY':                 str,               # Prevent abuse (embedded at compile time)
    'APPLICATION_VERSION': str,               # ex. 0.2.0
    'APPLICATION_COMMIT':  str,               # ex. 0.2.0 or {commit hash if not a release}
    'OS_VERSION':          str,               # ex. 10.15.7
    'MODEL':               str,               # ex. MacBookPro11,5
    'TIMESTAMP':           datetime.datetime, # ex. 2021-09-01-12-00-00
    'CRASH_LOG':           str,               # ex. "This is a crash log"
}


class Analytics:

    def __init__(self, global_constants: constants.Constants) -> None:
        self.constants: constants.Constants = global_constants
        self.unique_identity = str(self.constants.computer.uuid_sha1)
        self.application =     str(self.constants.patcher_name)
        self.version =         str(self.constants.patcher_version)
        self.os =              str(self.constants.detected_os_version)
        self.model =           str(self.constants.computer.real_model)
        self.date =            str(datetime.datetime.now().strftime(DATE_FORMAT))
        self.gpus: list = []
        self.firmware: str = ""
        self.location: str = ""
        self.data: dict = {}


    def send_analytics(self) -> None:
        if global_settings.GlobalEnviromentSettings().read_property("DisableCrashAndAnalyticsReporting") is True:
            return

        self._generate_base_data()
        self._post_analytics_data()


    def send_crash_report(self, log_file: Path) -> None:
        if not ANALYTICS_SERVER or not SITE_KEY:
            return
        if global_settings.GlobalEnviromentSettings().read_property("DisableCrashAndAnalyticsReporting") is True:
            return
        if not log_file.exists():
            return
        if self.constants.commit_info[0].startswith("refs/tags"):
            # Avoid being overloaded with crash reports from stable release builds
            return

        # Safely assemble commit information string
        commit_info = (
            self.constants.commit_info[0].split("/")[-1] + "_" + 
            self.constants.commit_info[1].split("T")[0] + "_" + 
            self.constants.commit_info[2].split("/")[-1]
        )

        try:
            # Fallback to errors="ignore" / utf-8 ensures parsing corrupted logs won't crash the handler
            crash_log_contents = log_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return

        crash_data = {
            "KEY":                  SITE_KEY,
            "APPLICATION_VERSION": self.version,
            "APPLICATION_COMMIT":  commit_info,
            "OS_VERSION":          self.os,
            "MODEL":               self.model,
            "TIMESTAMP":           self.date,
            "CRASH_LOG":           crash_log_contents
        }

        network_handler.NetworkUtilities().post(CRASH_URL, json=crash_data)


    def _get_country(self) -> str:
        # Get approximate country from .GlobalPreferences.plist safely
        path = Path("/Library/Preferences/.GlobalPreferences.plist")
        if not path.exists():
            return "US"

        try:
            # Fixed Resource Leak: Using context manager to safely open and close file handle
            with path.open("rb") as f:
                result = plistlib.load(f)
        except Exception: # Fixed Vulnerability: Removed bare except clause
            return "US"

        if not isinstance(result, dict) or "Country" not in result:
            return "US"

        return str(result["Country"])


    def _generate_base_data(self) -> None:
        self.gpus = [str(gpu.arch) for gpu in self.constants.computer.gpus]
        self.firmware = str(self.constants.computer.firmware_vendor)
        self.location = str(self._get_country())

        # Fixed Bug: Keep data structure as a dictionary. 
        # Passing a pre-stringified JSON object to `json=` parameters double-encodes it.
        self.data = {
            'KEY':                  SITE_KEY,
            'UNIQUE_IDENTITY':      self.unique_identity,
            'APPLICATION_NAME':     self.application,
            'APPLICATION_VERSION':  self.version,
            'OS_VERSION':           self.os,
            'MODEL':                self.model,
            'GPUS':                 self.gpus,
            'FIRMWARE':             self.firmware,
            'LOCATION':             self.location,
            'TIMESTAMP':            self.date,
        }


    def _post_analytics_data(self) -> None:
        # Post data to analytics server
        if not ANALYTICS_SERVER or not SITE_KEY:
            return
        
        # Dictionary structure is passed clean here; network helper manages serialization
        network_handler.NetworkUtilities().post(ANALYTICS_SERVER, json=self.data)
