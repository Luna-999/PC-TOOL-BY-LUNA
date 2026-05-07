"""Dashboard tab — subscribes to system_snapshot from the app poll thread (OPT 3)."""
import customtkinter as ctk
import psutil

from gui.theme import C, FONT_FAMILY, heading, card_frame, stat_card


class DashboardTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C.BG)
        self._build()
        self._populate_sys_info()

        # OPT 3: Subscribe to the single poll thread's snapshot
        self.after(100, self._subscribe)

    def _subscribe(self):
        try:
            app = self.winfo_toplevel()
            app.subscribe("system_snapshot", self._on_snapshot)
        except Exception:
            pass

    def _build(self):
        heading(self, "Dashboard").pack(padx=24, pady=(24, 4), anchor="w")
        ctk.CTkLabel(self, text="System optimization status at a glance",
                     font=(FONT_FAMILY, 13), text_color=C.MUTED,
                     anchor="w").pack(padx=24, pady=(0, 18), anchor="w")

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(padx=24, fill="x")
        grid.columnconfigure((0, 1, 2, 3), weight=1, uniform="col")

        f1, self._admin_val = stat_card(grid, "Privilege", "—")
        f1.grid(row=0, column=0, padx=(0, 8), pady=4, sticky="nsew")

        f2, self._timer_val = stat_card(grid, "Timer Resolution", "—", " ms")
        f2.grid(row=0, column=1, padx=4, pady=4, sticky="nsew")

        f3, self._ctf_val = stat_card(grid, "CTF / TSF", "—")
        f3.grid(row=0, column=2, padx=4, pady=4, sticky="nsew")

        f4, self._mods_val = stat_card(grid, "Active Modifications", "—")
        f4.grid(row=0, column=3, padx=(8, 0), pady=4, sticky="nsew")

        # System info section
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

        ctk.CTkLabel(info_frame, text="").pack(pady=4)

        # Initial admin check
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        self._admin_val.configure(
            text="Administrator" if is_admin else "Standard",
            text_color=C.SUCCESS if is_admin else C.DANGER)

    def _populate_sys_info(self):
        import platform
        import winreg
        try:
            # Read the real CPU brand name from registry (not platform.processor() which is useless)
            try:
                cpu_key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
                )
                cpu_name, _ = winreg.QueryValueEx(cpu_key, "ProcessorNameString")
                winreg.CloseKey(cpu_key)
                cpu_name = cpu_name.strip()
            except Exception:
                cpu_name = platform.processor() or "Unknown"

            self._sys_labels["CPU"].configure(text=cpu_name)
            cores_l = psutil.cpu_count(logical=True)
            cores_p = psutil.cpu_count(logical=False)
            self._sys_labels["Cores"].configure(text=f"{cores_p}P / {cores_l}L")
            ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
            self._sys_labels["RAM"].configure(text=f"{ram_gb} GB")
            self._sys_labels["OS"].configure(
                text=f"{platform.system()} {platform.release()} (build {platform.version()})")
        except Exception:
            pass

    def _on_snapshot(self, snapshot):
        """OPT 3: Receive data from the single app-level poll thread."""
        try:
            self._timer_val.configure(text=f"{snapshot['timer_ms']} ms")
            self._mods_val.configure(text=str(snapshot['active_changes']))

            ctf_running = any(
                p.name().lower() == "ctfmon.exe"
                for p in psutil.process_iter(['name'])
            )
            if ctf_running:
                self._ctf_val.configure(text="Active", text_color=C.WARNING)
            else:
                self._ctf_val.configure(text="Suppressed", text_color=C.SUCCESS)
        except Exception:
            pass
