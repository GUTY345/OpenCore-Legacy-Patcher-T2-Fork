"""
gui_build.py: Generate UI for Building OpenCore
"""

import wx
import logging
import threading
import traceback
import time
import webbrowser
import wx.html2
import urllib.parse

from .. import constants

from ..efi_builder import build

from ..wx_gui import (
    gui_main_menu,
    gui_install_oc,
    gui_support
)

class BuildFrame(wx.Frame):
    """
    Create a frame for building OpenCore
    Uses a Modal Dialog for smoother transition from other frames
    """
    def __init__(self, parent: wx.Frame, title: str, global_constants: constants.Constants, screen_location: tuple = None) -> None:
        logging.info("Initializing Build Frame")
        super(BuildFrame, self).__init__(parent, title=title, size=(350, 200), style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX))
        gui_support.GenerateMenubar(self, global_constants).generate()

        self.build_successful: bool = False

        self.install_button: wx.Button = None
        self.text_box:     wx.TextCtrl = None
        self.frame_modal:    wx.Dialog = None

        self.constants: constants.Constants = global_constants
        self.title: str = title
        self.stock_output = logging.getLogger().handlers[0].stream

        self.frame_modal = wx.Dialog(self, title=title, size=(400, 200))

        self._generate_elements(self.frame_modal)

        if self.constants.update_stage != gui_support.AutoUpdateStages.INACTIVE:
            self.constants.update_stage = gui_support.AutoUpdateStages.BUILDING

        self.Centre()
        self.frame_modal.ShowWindowModal()

        self._invoke_build()


    def on_build_failure(self) -> None:
        """
        Custom error dialog that provides a direct 'Ask Gemini' bridge 
        for debugging complex build errors.
        """
        dlg = wx.Dialog(self, title="Build Error", size=(450, 250))
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Build error explanation
        msg = wx.StaticText(dlg, label="An error occurred while building OpenCore.\n\n"
                                       "If you are unsure how to fix this, you can ask \n"
                                       "Gemini for a technical analysis of your build log.")
        sizer.Add(msg, 0, wx.ALL | wx.CENTER, 20)

        # Button Row: Ask Gemini | View Log | Close
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        gemini_btn = wx.Button(dlg, label="Ask Gemini")
        gemini_btn.Bind(wx.EVT_BUTTON, lambda e: self.on_ask_gemini())
        
        close_btn = wx.Button(dlg, label="Close", style=wx.ID_CANCEL)
        
        btn_sizer.Add(gemini_btn, 0, wx.ALL, 5)
        btn_sizer.Add(close_btn, 0, wx.ALL, 5)
        
        sizer.Add(btn_sizer, 0, wx.CENTER)
        dlg.SetSizer(sizer)
        dlg.ShowModal()
        dlg.Destroy()

    def copy_to_clipboard(self):
        # 1. Get the error log
        log_content = self.text_box.GetValue().splitlines()[-15:]
        error_text = "Analyze this OpenCore build error: " + " ".join(log_content)
        """Copies the error to the clipboard and opens Gemini for the user."""
        # 1. Capture the log
        log_content = self.text_box.GetValue().splitlines()[-15:]
        error_text = "\n".join(log_content)
        
        # 2. Copy to system clipboard
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(error_text))
            wx.TheClipboard.Close()
            
        # 3. Inform the user what just happened
        wx.MessageBox(
            "The error log has been copied to your clipboard.\n\n"
            "1. Gemini will now open in a new window.\n"
            "2. Simply paste (Cmd+V) your error log into the chat box.",
            "Ask Gemini", 
            wx.OK | wx.ICON_INFORMATION
        )
        
    def on_ask_gemini(self) -> None:
        self.copy_to_clipboard()
        dlg = wx.Dialog(self, title="Ask Gemini Analysis", size=(800, 600))
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        webview = wx.html2.WebView.New(dlg)
        
        # REMOVE OR COMMENT OUT THIS LINE:
        # webview.Bind(wx.html2.EVT_WEBVIEW_LOADED, on_load)
        
        webview.LoadURL("https://gemini.google.com/")
        
        sizer.Add(webview, 1, wx.EXPAND)
        dlg.SetSizer(sizer)
        dlg.ShowModal()
        dlg.Destroy()
    
    def _generate_elements(self, frame: wx.Frame = None) -> None:
        """
        Generate UI elements for build frame

        Format:
            - Title label:        Build and Install OpenCore
            - Text:               Model: {Build or Host Model}
            - Button:             Install OpenCore
            - Read-only text box: {empty}
            - Button:             Return to Main Menu
        """
        frame = self if not frame else frame

        title_label = wx.StaticText(frame, label="Build and Install OpenCore", pos=(-1,5))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        title_label.Centre(wx.HORIZONTAL)

        model_label = wx.StaticText(frame, label=f"Model: {self.constants.custom_model or self.constants.computer.real_model}", pos=(-1,30))
        model_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        model_label.Centre(wx.HORIZONTAL)

        # Button: Install OpenCore
        install_button = wx.Button(frame, label="🔩 Install OpenCore", pos=(-1, model_label.GetPosition()[1] + model_label.GetSize()[1]), size=(150, 30))
        install_button.Bind(wx.EVT_BUTTON, self.on_install)
        install_button.Centre(wx.HORIZONTAL)
        install_button.Disable()
        self.install_button = install_button

        # Read-only text box: {empty}
        text_box = wx.TextCtrl(frame, value="", pos=(-1, install_button.GetPosition()[1] + install_button.GetSize()[1] + 10), size=(380, 350), style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_RICH2)
        text_box.Centre(wx.HORIZONTAL)
        self.text_box = text_box

        # Button: Return to Main Menu
        return_button = wx.Button(frame, label="Return to Main Menu", pos=(-1, text_box.GetPosition()[1] + text_box.GetSize()[1] + 5), size=(150, 30))
        return_button.Bind(wx.EVT_BUTTON, self.on_return_to_main_menu)
        return_button.Centre(wx.HORIZONTAL)
        return_button.Disable()
        self.return_button = return_button

        # Adjust window size to fit all elements
        frame.SetSize((-1, return_button.GetPosition()[1] + return_button.GetSize()[1] + 40))


    def _invoke_build(self) -> None:
        """
        Invokes build function and waits for it to finish
        """
        while gui_support.PayloadMount(self.constants, self).is_unpack_finished() is False:
            wx.Yield()
            time.sleep(self.constants.thread_sleep_interval)

        thread = threading.Thread(target=self._build)
        thread.start()

        gui_support.wait_for_thread(thread)

        self.return_button.Enable()

        # Check if config.plist was built
        if self.build_successful is False:
            self.on_build_failure()
            return
        else:
            dialog = wx.MessageDialog(
                parent=self,
                message=f"Would you like to install OpenCore now?",
                caption="Finished building your OpenCore configuration!",
                style=wx.YES_NO | wx.ICON_QUESTION
            )
            dialog.SetYesNoLabels("Install to disk", "View build log")
    
        self.on_install() if dialog.ShowModal() == wx.ID_YES else self.install_button.Enable()


    def _build(self) -> None:
        """
        Calls build function and redirects stdout to the text box
        """
        logger = logging.getLogger()
        handler = gui_support.ThreadHandler(self.text_box) # Keep a reference
        logger.addHandler(handler)
        try:
            build.BuildOpenCore(self.constants.custom_model or self.constants.computer.real_model, self.constants)
            self.build_successful = True
        except Exception as e:
            logging.error("An internal error occurred while building:\n")
            logging.error(traceback.format_exc())
        finally:
            # Ensure we ALWAYS remove the handler before the thread exits
            logger.removeHandler(handler)

            # Handle bug from 2.1.0 where None type was stored in config.plist from global settings
            if "TypeError: unsupported type: <class 'NoneType'>" in traceback.format_exc():
                logging.error("If you continue to see this error, delete the following file and restart the application:")
                logging.error("Path: /Users/Shared/.com.dortania.opencore-legacy-patcher.plist")

        if len(logger.handlers) > 2:
            logger.removeHandler(logger.handlers[2])


    def on_return_to_main_menu(self, event: wx.Event = None) -> None:
        """
        Return to main menu
        """
        self.frame_modal.Hide()
        main_menu_frame = gui_main_menu.MainFrame(
            None,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetScreenPosition()
        )
        main_menu_frame.Show()
        self.frame_modal.Destroy()
        self.Destroy()


    def on_install(self, event: wx.Event = None) -> None:
        """
        Launch install frame
        """
        # Stop any pending UI updates
        logger = logging.getLogger()
        for handler in logger.handlers[:]:
            if isinstance(handler, gui_support.ThreadHandler):
                logger.removeHandler(handler)
        
        self.frame_modal.Hide() # Hide first to feel responsive
        self.frame_modal.Destroy()
        self.Destroy()
        install_oc_frame = gui_install_oc.InstallOCFrame(
            None,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetScreenPosition()
        )
        install_oc_frame.Show()


