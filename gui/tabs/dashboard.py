"""Dashboard tab — status cards with live auto-refresh."""
import threading
import customtkinter as ctk
import psutil

from gui.theme import C, FONT_FAMILY, heading, card_frame, stat_card


class DashboardTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C.BG)
        self._build()
        self._refresh()

    def _build(self):
        heading(self, "Dashboard").pack(padx=24, pady=(24, 4), anchor="w")
        ctk.CTkLabel(self, text="System optimization status at a glance",
                     font=(FONT_FAMILY, 13), text_color=C.MUTED,
                     anchor="w").pack(padx=24, pady=(0, 18), anchor="w")

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(padx=24, fill="x")
        grid.columnconfigure((0, 1, 2, 3), weight=1, uniform="col")

        # Card 1 — Admin status
        f1, self._admin_val = stat_card(grid, "Privilege", "—")
        f1.grid(row=0, column=0, padx=(0, 8), pady=4, sticky="nsew")

        # Card 2 — Timer resolution
        f2, self._timer_val = stat_card(grid, "Timer Resolution", "—", " ms")
        f2.grid(row=0, column=1, padx=4, pady=4, sticky="nsew")

        # Card 3 — CTF status
        f3, self._ctf_val = stat_card(grid, "CTF / TSF", "—")
        f3.grid(row=0, column=2, padx=4, pady=4, sticky="nsew")

        # Card 4 — Active mods
        f4, self._mods_val = stat_card(grid, "Active Modifications", "—")
        f4.grid(row=0, column=3, padx=(8, 0), pady=4, sticky="nsew")

        # ── System info section ──
        info_frame = card_frame(self)
        info_frame.pack(padx=24, pady=(20, 8), fill="x")
        ctk.CTkLabel(info_frame, text="SYSTEM INFO",
                     font=(FONT_FAMILY, 11, "bold"),
                     text_color=C.MUTED).pack(padx=16, pady=(14, 8), anchor="w")

        self._sys_labels = {}
        for key in ["CPU", "Cores", "RAM", "OS"]:
            row = ctk.CTkFrame(info_frame, fg_color="transparent")
            row.pack(padx=16, pady=2, fill="x")
            ctk.CTkLabel(row, text=f"{key}:", font=(FONT_FAMILY, 13),
                         text_color=C.MUTED, width=100,
                         anchor="w").pack(side="left")
            lbl = ctk.CTkLabel(row, text="—", font=(FONT_FAMILY, 13),
                               text_color=C.TEXT, anchor="w")
            lbl.pack(side="left")
            self._sys_labels[key] = lbl

        # Spacer
        ctk.CTkLabel(info_frame, text="").pack(pady=4)

        self._populate_sys_info()

    def _populate_sys_info(self):
        import platform
        try:
            self._sys_labels["CPU"].configure(text=platform.processor() or "Unknown")
            cores_l = psutil.cpu_count(logical=True)
            cores_p = psutil.cpu_count(logical=False)
            self._sys_labels["Cores"].configure(text=f"{cores_p}P / {cores_l}L")
            ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
            self._sys_labels["RAM"].configure(text=f"{ram_gb} GB")
            self._sys_labels["OS"].configure(
                text=f"{platform.system()} {platform.release()} (build {platform.version()})")
        except Exception:
            pass

    def _refresh(self):
        """Auto-refresh status cards every 3 seconds."""
        threading.Thread(target=self._fetch_status, daemon=True).start()
        self.after(3000, self._refresh)

    def _fetch_status(self):
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0

        timer_ms = "—"
        try:
            from bridge.windows_bridge import get_timer_resolution
            t = get_timer_resolution()
            timer_ms = str(t["current_ms"])
        except Exception:
            pass

        ctf_status = "Unknown"
        try:
            ctf_running = any(
                p.name().lower() == "ctfmon.exe"
                for p in psutil.process_iter(['name'])
            )
            ctf_status = "Active" if ctf_running else "Suppressed"
        except Exception:
            pass

        mod_count = 0
        try:
            from db import get_active_change_count
            mod_count = get_active_change_count()
        except Exception:
            pass

        # Schedule UI update on main thread
        self.after(0, lambda: self._update_ui(is_admin, timer_ms, ctf_status, mod_count))

    def _update_ui(self, is_admin, timer_ms, ctf_status, mod_count):
        try:
            self._admin_val.configure(
                text="Administrator" if is_admin else "Standard",
                text_color=C.SUCCESS if is_admin else C.DANGER)
            self._timer_val.configure(text=f"{timer_ms} ms")
            ctf_color = C.SUCCESS if ctf_status == "Suppressed" else C.WARNING
            self._ctf_val.configure(text=ctf_status, text_color=ctf_color)
            self._mods_val.configure(text=str(mod_count))
        except Exception:
            pass
