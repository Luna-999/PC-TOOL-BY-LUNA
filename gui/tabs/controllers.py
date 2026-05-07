"""Controllers tab — scan and display HID game controllers."""
import threading
import customtkinter as ctk

from gui.theme import C, FONT_FAMILY, section_header, card, primary_button, muted_label


class ControllersTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C.BG)
        self._build()

    def _build(self):
        section_header(self, "Controllers").pack(padx=24, pady=(24, 4), anchor="w")
        muted_label(self, "Detect and analyze HID game controllers"
                    ).pack(padx=24, pady=(0, 14), anchor="w")

        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(padx=24, fill="x")
        primary_button(ctrl, "🎮  Scan Controllers", self._scan, width=190
                       ).pack(side="left", padx=(0, 8))
        self._status_lbl = ctk.CTkLabel(ctrl, text="",
                                        font=(FONT_FAMILY, 13), text_color=C.MUTED)
        self._status_lbl.pack(side="left", padx=16)

        # Scrollable container for controller cards
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=C.BG,
                                              scrollbar_button_color=C.BORDER)
        self._scroll.pack(padx=24, pady=(16, 16), fill="both", expand=True)

        # Load cached
        self._load_cached()

    def _load_cached(self):
        try:
            from db import get_controllers
            ctrls = get_controllers()
            if ctrls:
                self._display(ctrls)
        except Exception:
            pass

    def _scan(self):
        self._status_lbl.configure(text="Scanning…", text_color=C.WARNING)
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            from bridge.windows_bridge import get_hid_controllers
            from db import save_controllers
            controllers = get_hid_controllers()
            save_controllers(controllers)
            self.after(0, lambda: self._display(controllers))
            self.after(0, lambda: self._status_lbl.configure(
                text=f"{len(controllers)} controller(s) found", text_color=C.SUCCESS))
        except Exception as e:
            self.after(0, lambda: self._status_lbl.configure(
                text=str(e), text_color=C.DANGER))

    def _display(self, controllers):
        for w in self._scroll.winfo_children():
            w.destroy()

        if not controllers:
            ctk.CTkLabel(self._scroll, text="No controllers detected. Click Scan.",
                         font=(FONT_FAMILY, 14), text_color=C.MUTED
                         ).pack(pady=40)
            return

        for c in controllers:
            card = card(self._scroll)
            card.pack(fill="x", pady=(0, 8))

            # Name
            ctk.CTkLabel(card, text=c.get("friendly_name", "Unknown Controller"),
                         font=(FONT_FAMILY, 15, "bold"),
                         text_color=C.TEXT).pack(padx=16, pady=(14, 6), anchor="w")

            # Meta grid
            meta = ctk.CTkFrame(card, fg_color="transparent")
            meta.pack(padx=16, pady=(0, 4), fill="x")

            items = [
                ("VID", c.get("vid", "—")),
                ("PID", c.get("pid", "—")),
                ("Connection", (c.get("connection_type") or "—").replace("_", " ")),
                ("Polling", f"{c.get('polling_rate_hz') or '—'} Hz"),
                ("API", c.get("recommended_api", "—")),
            ]
            for i, (k, v) in enumerate(items):
                col_frame = ctk.CTkFrame(meta, fg_color="transparent")
                col_frame.pack(side="left", padx=(0, 24))
                ctk.CTkLabel(col_frame, text=k, font=(FONT_FAMILY, 11),
                             text_color=C.MUTED).pack(anchor="w")
                ctk.CTkLabel(col_frame, text=v, font=(FONT_FAMILY, 13),
                             text_color=C.TEXT).pack(anchor="w")

            # XInput warning
            if c.get("xinput_capped"):
                ctk.CTkLabel(card,
                             text="⚠ XInput controller — polling capped at 250Hz by default",
                             font=(FONT_FAMILY, 12), text_color=C.WARNING
                             ).pack(padx=16, pady=(4, 12), anchor="w")
            else:
                ctk.CTkLabel(card, text="").pack(pady=4)
