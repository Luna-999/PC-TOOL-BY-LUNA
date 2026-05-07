"""OP TOOL — Native CustomTkinter GUI Entry Shell.

BUG 5:  Tabs use pack_forget (hide) instead of destroy — background threads survive navigation.
BUG 8:  launch() auto-elevates via ShellExecuteW instead of showing a MessageBox and dying.
OPT 1:  Event bus (publish/subscribe) for cross-tab communication.
OPT 3:  Single background poll thread owned by the app, all tabs subscribe to 'system_snapshot'.
"""
import sys
import ctypes
import time
import threading
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

        # ── OPT 1: Event Bus ──
        self._subscribers = {}

        # ── Sidebar ──
        self.sidebar = ctk.CTkFrame(self, width=220, fg_color=C.SURFACE,
                                    corner_radius=0, border_width=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        ctk.CTkLabel(self.sidebar, text="OP TOOL",
                     font=(FONT_FAMILY, 24, "bold"), text_color=C.PRIMARY
                     ).pack(pady=(30, 40))

        # ── Main Content Area ──
        self.main_content = ctk.CTkFrame(self, fg_color=C.BG, corner_radius=0)
        self.main_content.pack(side="right", fill="both", expand=True)

        # ── Tab definitions ──
        self.tab_classes = {
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

        for name in self.tab_classes:
            if name == "Restore":
                restore_container = ctk.CTkFrame(self.sidebar, fg_color="transparent")
                restore_container.pack(fill="x", padx=8, pady=2)
                btn = ctk.CTkButton(restore_container, text=name, anchor="w",
                                    fg_color="transparent", text_color=C.MUTED,
                                    hover_color=C.SURFACE_HI, corner_radius=6,
                                    font=(FONT_FAMILY, 14, "bold"), height=40,
                                    command=lambda n=name: self.select_tab(n))
                btn.pack(side="left", fill="x", expand=True)

                self._restore_badge = ctk.CTkLabel(
                    restore_container,
                    text="0",
                    font=(FONT_FAMILY, 10, "bold"),
                    fg_color=C.DANGER,
                    text_color="white",
                    corner_radius=10,
                    width=20, height=20
                )
            else:
                btn = ctk.CTkButton(self.sidebar, text=name, anchor="w",
                                    fg_color="transparent", text_color=C.MUTED,
                                    hover_color=C.SURFACE_HI, corner_radius=6,
                                    font=(FONT_FAMILY, 14, "bold"), height=40,
                                    command=lambda n=name: self.select_tab(n))
                btn.pack(padx=16, pady=4, fill="x")

            self.nav_buttons[name] = btn

        # ── BUG 5: Pre-instantiate all tabs (hide/show, never destroy) ──
        self._tab_instances = {}
        for name, tab_class in self.tab_classes.items():
            frame = tab_class(self.main_content)
            self._tab_instances[name] = frame
            # All start hidden

        self._current_tab = None
        self.select_tab("Dashboard")

        # ── OPT 3: Single background poll thread ──
        self._polling = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

        # ── Clean shutdown ──
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _update_restore_badge(self, count: int):
        """Show/hide and update the restore badge count."""
        if count > 0:
            self._restore_badge.configure(text=str(count))
            self._restore_badge.pack(side="right", padx=4)
        else:
            self._restore_badge.pack_forget()

    # ── OPT 1: Event Bus ──────────────────────────────

    def publish(self, event_name, data=None):
        """Fire an event to all subscribers (thread-safe via after())."""
        for cb in self._subscribers.get(event_name, []):
            try:
                self.after(0, lambda c=cb, d=data: c(d))
            except Exception:
                pass

    def subscribe(self, event_name, callback):
        """Register a callback for an event."""
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        self._subscribers[event_name].append(callback)

    # ── BUG 5: Tab switching via hide/show ────────────

    def select_tab(self, name):
        for btn_name, btn in self.nav_buttons.items():
            if btn_name == name:
                btn.configure(fg_color=C.SURFACE_HI, text_color=C.TEXT)
            else:
                btn.configure(fg_color="transparent", text_color=C.MUTED)

        # Hide all, show selected
        for tab_name, frame in self._tab_instances.items():
            if tab_name == name:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()

        self._current_tab = name

    # ── OPT 3: Single background poll thread ─────────

    def _poll_loop(self):
        while self._polling:
            try:
                from bridge.windows_bridge import get_timer_resolution
                import db

                timer = get_timer_resolution()
                changes = db.get_active_change_count()

                snapshot = {
                    "timer_ms": timer["current_ms"],
                    "timer_100ns": timer["current_100ns"],
                    "active_changes": changes,
                    "timestamp": time.time()
                }

                self.after(0, lambda s=snapshot: self.publish("system_snapshot", s))
                self.after(0, lambda c=changes: self._update_restore_badge(c))
            except Exception:
                pass
            time.sleep(2)
    # ── Clean shutdown ────────────────────────────────

    def _on_close(self):
        self._polling = False
        self.destroy()


def launch():
    """
    BUG 8: Auto-elevate via ShellExecuteW instead of showing a
    MessageBox and dying.  run.py already handles this, but if
    someone calls launch() directly we still do the right thing.
    """
    if not ctypes.windll.shell32.IsUserAnAdmin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit(0)

    init_db()
    app = OpToolApp()
    app.mainloop()


if __name__ == "__main__":
    launch()
