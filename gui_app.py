"""OP TOOL — Native CustomTkinter GUI Entry Shell."""
import sys
import ctypes
import customtkinter as ctk

from db import init_db
from gui.theme import C, FONT_FAMILY
from gui.tabs.dashboard import DashboardTab
from gui.tabs.dpc import DpcTab
from gui.tabs.devices import DevicesTab
from gui.tabs.affinity import AffinityTab
from gui.tabs.controllers import ControllersTab
from gui.tabs.timer import TimerTab
from gui.tabs.ctf import CtfTab
from gui.tabs.profiles import ProfilesTab
from gui.tabs.restore import RestoreTab
from gui.tabs.settings import SettingsTab


ctk.set_appearance_mode("dark")


class OpToolApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("OP TOOL v2.0")
        self.geometry("1000x700")
        self.configure(fg_color=C.BG)
        self.minsize(900, 600)

        # ── Sidebar ──
        self.sidebar = ctk.CTkFrame(self, width=220, fg_color=C.SURFACE,
                                    corner_radius=0, border_width=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Logo
        ctk.CTkLabel(self.sidebar, text="OP TOOL",
                     font=(FONT_FAMILY, 24, "bold"), text_color=C.PRIMARY
                     ).pack(pady=(30, 40))

        # ── Main Content Area ──
        self.main_content = ctk.CTkFrame(self, fg_color=C.BG, corner_radius=0)
        self.main_content.pack(side="right", fill="both", expand=True)

        # ── Tabs Configuration ──
        self.tabs = {
            "Dashboard": DashboardTab,
            "DPC Monitor": DpcTab,
            "Devices / MSI": DevicesTab,
            "Affinity": AffinityTab,
            "Controllers": ControllersTab,
            "Timer": TimerTab,
            "CTF / TSF": CtfTab,
            "Profiles": ProfilesTab,
            "Restore": RestoreTab,
            "Settings": SettingsTab
        }

        self.nav_buttons = {}
        self.active_frame = None

        for name in self.tabs:
            btn = ctk.CTkButton(self.sidebar, text=name, anchor="w",
                                fg_color="transparent", text_color=C.MUTED,
                                hover_color=C.SURFACE_HI, corner_radius=6,
                                font=(FONT_FAMILY, 14, "bold"), height=40,
                                command=lambda n=name: self.select_tab(n))
            btn.pack(padx=16, pady=4, fill="x")
            self.nav_buttons[name] = btn

        # Default tab
        self.select_tab("Dashboard")

    def select_tab(self, name):
        # Update button styling
        for btn_name, btn in self.nav_buttons.items():
            if btn_name == name:
                btn.configure(fg_color=C.SURFACE_HI, text_color=C.TEXT)
            else:
                btn.configure(fg_color="transparent", text_color=C.MUTED)

        # Swap frame
        if self.active_frame:
            self.active_frame.pack_forget()
            self.active_frame.destroy()

        tab_class = self.tabs[name]
        self.active_frame = tab_class(self.main_content)
        self.active_frame.pack(fill="both", expand=True)


def launch():
    # Ensure Admin elevation
    if not ctypes.windll.shell32.IsUserAnAdmin():
        ctypes.windll.user32.MessageBoxW(0, "OP TOOL requires Administrator privileges to modify system settings.", "Elevation Required", 0x10)
        sys.exit(1)

    # Initialize standalone SQLite Database
    init_db()

    app = OpToolApp()
    app.mainloop()


if __name__ == "__main__":
    launch()
