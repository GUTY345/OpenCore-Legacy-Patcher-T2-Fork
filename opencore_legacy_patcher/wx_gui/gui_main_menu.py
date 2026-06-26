"""
gui_main_menu.py: Generate GUI for main menu
"""

import wx
import wx.html2

import sys
import logging
import subprocess
import requests
import markdown2
import threading
import webbrowser
from pathlib import Path
from packaging import version

from .. import constants

from ..support import (
    global_settings,
    updates
)
from ..datasets import (
    os_data,
    css_data
)
from ..wx_gui import (
    gui_build,
    gui_macos_installer_download,
    gui_support,
    gui_help,
    gui_settings,
    gui_sys_patch_display,
    gui_update,
)


class MainFrame(wx.Frame):
    def __init__(self, parent: wx.Frame, title: str, global_constants: constants.Constants, screen_location: tuple = None):
        logging.info("Initializing Main Menu Frame")
        super(MainFrame, self).__init__(parent, title=title, size=(700, 800), style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX))
        gui_support.GenerateMenubar(self, global_constants).generate()

        self.constants: constants.Constants = global_constants
        self.title: str = title

        self.model_label: wx.StaticText = None
        self.build_button: wx.Button = None

        self.constants.update_stage = gui_support.AutoUpdateStages.INACTIVE

        self._generate_elements()

        self.Centre()
        self.Show()


        self._preflight_checks()


    def _generate_elements(self) -> None:
        """
        Generate UI elements for the main menu
        """

        # Logo
        logo = wx.StaticBitmap(self, bitmap=wx.Bitmap(str(self.constants.icns_resource_path / "OC-Patcher.icns"), wx.BITMAP_TYPE_ICON), pos=(-1, 0), size=(128, 128))
        logo.Centre(wx.HORIZONTAL)

        # Title label
        title_label = wx.StaticText(self, label=self.constants.patcher_name, pos=(-1, 128))
        title_label.SetFont(gui_support.font_factory(25, wx.FONTWEIGHT_BOLD))
        title_label.Centre(wx.HORIZONTAL)

        version_label = wx.StaticText(self, label=f"Version {self.constants.patcher_version_label}", pos=(-1, title_label.GetPosition()[1] + 32))
        version_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        version_label.Centre(wx.HORIZONTAL)
        version_label.SetForegroundColour(wx.Colour(128, 128, 128))

        # Model label
        model_label = wx.StaticText(self, label=f"Model: {self.constants.custom_model or self.constants.computer.real_model}", pos=(-1, version_label.GetPosition()[1] + 30))
        model_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        model_label.Centre(wx.HORIZONTAL)
        self.model_label = model_label

        # Main 4 Feature Buttons
        menu_buttons = {
            "Build and Install OpenCore": {
                "function": self.on_build_and_install,
                "description": ["Prepares provided drive to be able", "to boot unsupported OSes.", "Use on installers or internal drives."],
                "icon": str(self.constants.icns_resource_path / "OC-Build.icns"),
            },
            "Create macOS Installer": {
                "function": self.on_create_macos_installer,
                "description": ["Download and flash a macOS", "Installer for your system."],
                "icon": str(self.constants.icns_resource_path / "OC-Installer.icns"),
            },
            "Install drivers and patches": {
                "function": self.on_post_install_root_patch,
                "description": ["Installs hardware drivers and", "patches for your system after", "installing a new version of macOS."],
                "icon": str(self.constants.icns_resource_path / "OC-Patch.icns"),
            },
            "Support": {
                "function": self.on_help,
                "description": ["Resources for OpenCore Legacy", "Patcher."],
                "icon": str(self.constants.icns_resource_path / "OC-Support.icns"),
            },
        }

        if self._host_is_macbookpro151():
            menu_buttons["Patch Tahoe Stage-2"] = {
                "function": self.on_patch_tahoe_stage2,
                "description": ["Repairs staged Tahoe installer", "metadata after first restart.", "MacBookPro15,1 only."],
                "icon": str(self.constants.icns_resource_path / "OC-Installer.icns"),
            }

        button_x = 30
        button_y = model_label.GetPosition()[1] + 30
        rollover = 2
        index = 0
        max_height = 0

        for button_name, button_function in menu_buttons.items():
            if "icon" in button_function:
                icon = wx.StaticBitmap(self, bitmap=wx.Bitmap(button_function["icon"], wx.BITMAP_TYPE_ICON), pos=(button_x - 10, button_y), size=(64, 64))
                if button_name == "Build and Install OpenCore":
                    icon.SetSize((70, 70))
            
            button = wx.Button(self, label=button_name, pos=(button_x + 70, button_y), size=(180, 30))
            button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
            button.Bind(wx.EVT_BUTTON, lambda event, f=button_function["function"]: f(event))
            
            description_label = wx.StaticText(self, label='\n'.join(button_function["description"]), pos=(button_x + 75, button.GetPosition()[1] + 33))
            description_label.SetFont(gui_support.font_factory(10, wx.FONTWEIGHT_NORMAL))

            # Maintain spacing
            row_height = 85
            button_y += row_height
            
            if button_y > max_height:
                max_height = button_y

            index += 1
            if index == rollover:
                button_x = 320
                button_y = model_label.GetPosition()[1] + 30

        # --- FOOTER BUTTONS (Settings & Gemini) ---
        total_footer_width = 120 + 10 + 150 # Buttons + gap
        start_x = (self.GetSize().width - total_footer_width) // 2
        footer_y = max_height + 10

        settings_btn = wx.Button(self, label="⚙️ Settings", pos=(start_x, footer_y), size=(120, 30))
        settings_btn.Bind(wx.EVT_BUTTON, self.on_settings)

        gemini_btn = wx.Button(self, label="✨ Ask Gemini", pos=(start_x + 130, footer_y), size=(150, 30))
        gemini_btn.Bind(wx.EVT_BUTTON, self.on_gemini_help)

        gemini_desc = wx.StaticText(self, label="AI Troubleshooting and\nInstallation help.", pos=(start_x + 135, footer_y + 35))
        gemini_desc.SetFont(gui_support.font_factory(10, wx.FONTWEIGHT_NORMAL))

        # --- COPYRIGHT ---
        copy_label = wx.StaticText(self, label=self.constants.copyright_date, pos=(-1, gemini_desc.GetPosition()[1] + 45))
        copy_label.SetFont(gui_support.font_factory(10, wx.FONTWEIGHT_NORMAL))
        copy_label.Centre(wx.HORIZONTAL)

        # Final Window Size adjustment
        self.SetSize((-1, copy_label.GetPosition()[1] + 60))

    def _preflight_checks(self):
        try:
            # 1. HEAL THE CONFIG: If no build model is set, set it to the current Mac
            if self.constants.computer.build_model is None:
                logging.info("No build model detected. Defaulting to current host hardware.")
                self.constants.computer.build_model = self.constants.computer.real_model
            # Clean strings and diagnostic print
            real_model = str(self.constants.computer.real_model).strip()
            build_model = str(self.constants.computer.build_model).strip() if self.constants.computer.build_model else None
            
            print(f"DEBUG: Real: '{real_model}' | Build: '{build_model}'")

            if (
                build_model is not None and
                build_model != real_model and
                self.constants.computer.build_model != self.constants.computer.real_model and
                self.constants.host_is_hackintosh is False
            ):
                # This block is skipped for native Macs
                pop_up = wx.MessageDialog(
                    self,
                    f"We found you are currently booting OpenCore built for a different unit: {build_model}\n\nPlease Build and Install a new OpenCore config.",
                    "Unsupported Configuration Detected!",
                    style=wx.OK | wx.ICON_EXCLAMATION
                )
                pop_up.ShowModal()
                self.on_build_and_install()
                return

        except Exception as e:
            print(f"DEBUG: Preflight error: {e}")

        # The update check remains outside the if-statement
        threading.Thread(target=self._check_for_updates).start()

        if "--update_installed" in sys.argv and self.constants.has_checked_updates is False and gui_support.CheckProperties(self.constants).host_can_build():
            # Notify user that the update has been installed
            self.constants.has_checked_updates = True
            pop_up = wx.MessageDialog(
                self,
                f"{self.constants.patcher_name} has been updated to the latest version: {self.constants.patcher_version_label}\n\nWould you like to update OpenCore and your root volume patches?",
                "Update successful!",
                style=wx.YES_NO | wx.YES_DEFAULT | wx.ICON_INFORMATION
            )
            pop_up.ShowModal()

            if pop_up.GetReturnCode() != wx.ID_YES:
                logging.info("Skipping OpenCore and root volume patch update...")
                return


            logging.info("Updating OpenCore and root volume patches...")
            self.constants.update_stage = gui_support.AutoUpdateStages.CHECKING
            self.Hide()
            pos = self.GetPosition()
            gui_build.BuildFrame(
                parent=None,
                title=self.title,
                global_constants=self.constants,
                screen_location=pos
            )
            self.Close()

        threading.Thread(target=self._check_for_updates).start()

    def _host_is_macbookpro151(self) -> bool:
        return (self.constants.custom_model or self.constants.computer.real_model) == "MacBookPro15,1"

    def _tahoe_stage2_script_path(self) -> Path:
        return Path(__file__).resolve().parents[2] / "docs" / "scripts" / "tahoe_stage2_asset_patch.py"

    def on_patch_tahoe_stage2(self, event: wx.Event = None):
        if not self._host_is_macbookpro151():
            wx.MessageBox(
                "Tahoe Stage-2 patching is currently limited to MacBookPro15,1.",
                "Unsupported Model",
                wx.OK | wx.ICON_WARNING
            )
            return

        script_path = self._tahoe_stage2_script_path()
        if not script_path.exists():
            wx.MessageBox(
                f"Could not find Tahoe Stage-2 patch script:\n\n{script_path}",
                "Patch Script Missing",
                wx.OK | wx.ICON_ERROR
            )
            return

        warning = wx.MessageDialog(
            self,
            "This will scan /Volumes for staged macOS Tahoe Install Data and apply the MacBookPro15,1 Tahoe Stage-2 metadata repair.\n\n"
            "Use this after the installer has copied files and restarted once, before booting the macOS Installer stage again.",
            "Patch Tahoe Stage-2?",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING
        )
        warning.ShowModal()
        if warning.GetReturnCode() != wx.ID_YES:
            logging.info("User cancelled Tahoe Stage-2 patch.")
            return

        logging.info("- Running Tahoe Stage-2 GUI patch")
        threading.Thread(target=self._run_tahoe_stage2_patch, args=(script_path,), daemon=True).start()

    def _run_tahoe_stage2_patch(self, script_path: Path):
        command = [
            sys.executable,
            str(script_path),
            "--diagnose-logs",
            "--materialize-additional-manifests",
            "--materialize-bootcache-system-volume",
            "--patch-msu-manifest",
            "--apply",
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        output = result.stdout.strip() or "(no output)"
        logging.info("Tahoe Stage-2 patch exited with code %s", result.returncode)
        logging.info(output)
        wx.CallAfter(self._show_tahoe_stage2_result, result.returncode, output)

    def _show_tahoe_stage2_result(self, returncode: int, output: str):
        if returncode == 0:
            wx.MessageBox(
                f"Tahoe Stage-2 patch completed.\n\n{output}",
                "Tahoe Stage-2 Patch Complete",
                wx.OK | wx.ICON_INFORMATION
            )
            return

        wx.MessageBox(
            f"Tahoe Stage-2 patch failed.\n\n{output}",
            "Tahoe Stage-2 Patch Failed",
            wx.OK | wx.ICON_ERROR
        )


    def _check_for_updates(self):
        if self.constants.has_checked_updates is True:
            return
    
        ignore_updates = global_settings.GlobalEnviromentSettings().read_property("IgnoreAppUpdates")
        if ignore_updates is True:
            self.constants.ignore_updates = True
            return
    
        self.constants.ignore_updates = False
        self.constants.has_checked_updates = True
        
        # 1. Fetch update info
        update_dict = updates.CheckBinaryUpdates(self.constants).check_binary_updates()
        if not update_dict:
            return
    
        remote_version_str = update_dict["Version"]
        local_version_str = self.constants.patcher_version
    
        try:
            # 2. Robust Comparison
            remote_v = version.parse(str(remote_version_str))
            local_v = version.parse(local_version_str)
    
            # Only trigger if remote is NEWER. 
            # If remote <= local, we are already up to date or ahead.
            if remote_v <= local_v:
                logging.info(f"{self.constants.patcher_name} is up to date. (Local: {local_v} >= Remote: {remote_v})")
                return
    
        except version.InvalidVersion:
            # Fallback for non-standard strings: only prompt if they are not identical
            if remote_version_str == local_version_str:
                return
    
        # 3. Trigger update
        logging.info(f"Newer version detected: {remote_version_str}")
        wx.CallAfter(self.on_update, update_dict["Link"], remote_version_str, update_dict["Github Link"])
        
    def on_build_and_install(self, event: wx.Event = None):
        self.Hide()
        gui_build.BuildFrame(
            parent=None,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetPosition()
        )
        self.Destroy()


    def on_post_install_root_patch(self, event: wx.Event = None):
        gui_sys_patch_display.SysPatchDisplayFrame(
            parent=self,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetPosition()
        )


    def on_create_macos_installer(self, event: wx.Event = None):
        gui_macos_installer_download.macOSInstallerDownloadFrame(
            parent=self,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetPosition()
        )


    def on_settings(self, event: wx.Event = None):
        gui_settings.SettingsFrame(
            parent=self,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetPosition()
        )

    def on_help(self, event: wx.Event = None):
        gui_help.HelpFrame(
            parent=self,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetPosition()
        )

    def on_update(self, oclp_url: str, oclp_version: str, oclp_github_url: str):

        ID_GITHUB = wx.NewId()
        ID_UPDATE = wx.NewId()

        url = "https://api.github.com/repos/albert-mueller/OpenCore-Legacy-Patcher-T2/releases/latest"
        response = requests.get(url).json()
        try:
            changelog = response["body"].split("## Asset Information")[0]
        except: #if user constantly checks for updates, github will rate limit them
            changelog = """## Unable to fetch changelog

Please check the Github page for more information about this release."""

        html_markdown = markdown2.markdown(changelog, extras=["tables"])
        html_css = css_data.updater_css
        frame = wx.Dialog(None, -1, title="", size=(650, 500))
        frame.SetMinSize((650, 500))
        frame.SetWindowStyle(wx.STAY_ON_TOP)
        panel = wx.Panel(frame)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(10)
        self.title_text = wx.StaticText(panel, label=f"A new version of {self.constants.patcher_name} is available!")
        self.description = wx.StaticText(panel, label=f"{self.constants.patcher_name} {oclp_version} is now available - You have {self.constants.patcher_version_label}. Would you like to update?")
        self.title_text.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        self.description.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        self.web_view = wx.html2.WebView.New(panel, style=wx.BORDER_SUNKEN)
        html_code = f'''
<html>
    <head>
        <style>
            {html_css}
        </style>
    </head>
    <body class="markdown-body">
        {html_markdown.replace("<a href=", "<a target='_blank' href=")}
    </body>
</html>
'''
        self.web_view.SetPage(html_code, "")
        self.web_view.Bind(wx.html2.EVT_WEBVIEW_NEWWINDOW, self._onWebviewNav)
        self.web_view.EnableContextMenu(False)
        self.close_button = wx.Button(panel, label="Dismiss")
        self.close_button.Bind(wx.EVT_BUTTON, lambda event: frame.EndModal(wx.ID_CANCEL))
        self.view_button = wx.Button(panel, ID_GITHUB, label="View on GitHub")
        self.view_button.Bind(wx.EVT_BUTTON, lambda event: frame.EndModal(ID_GITHUB))
        self.install_button = wx.Button(panel, label="Download and Install")
        self.install_button.Bind(wx.EVT_BUTTON, lambda event: frame.EndModal(ID_UPDATE))
        self.install_button.SetDefault()

        buttonsizer = wx.BoxSizer(wx.HORIZONTAL)
        buttonsizer.Add(self.close_button, 0, wx.ALIGN_CENTRE | wx.RIGHT, 5)
        buttonsizer.Add(self.view_button, 0, wx.ALIGN_CENTRE | wx.LEFT|wx.RIGHT, 5)
        buttonsizer.Add(self.install_button, 0, wx.ALIGN_CENTRE | wx.LEFT, 5)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.title_text, 0, wx.ALIGN_CENTRE | wx.TOP, 20)
        sizer.Add(self.description, 0, wx.ALIGN_CENTRE | wx.BOTTOM, 20)
        sizer.Add(self.web_view, 1, wx.EXPAND | wx.LEFT|wx.RIGHT, 10)
        sizer.Add(buttonsizer, 0, wx.ALIGN_RIGHT | wx.ALL, 20)
        panel.SetSizer(sizer)
        frame.Centre()

        result = frame.ShowModal()


        if result == ID_GITHUB:
            webbrowser.open(oclp_github_url)
        elif result == ID_UPDATE:
            gui_update.UpdateFrame(
            parent=self,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetPosition(),
            url=oclp_url,
            version_label=oclp_version
        )

        frame.Destroy()

    def _onWebviewNav(self, event):
        url = event.GetURL()
        webbrowser.open(url)
    
    def on_gemini_help(self, event: wx.Event):
        import webview # Import here to avoid slowing down OCLP startup
        
        logging.info("- Launching Gemini AI Assistant (pywebview)")
        
        # Create a sleek, floating window
        window = webview.create_window(
            title='Gemini AI Assistant',
            url='https://gemini.google.com',
            width=500,
            height=850,
            confirm_close=False,
            background_color='#ffffff'
        )
        
        # start() is blocking by default, but in a wxPython app, 
        # it usually needs to run in its own flow.
        webview.start()
