"""Dashboard tab — subscribes to system_snapshot from the app poll thread (OPT 3)."""
import customtkinter as ctk
import psutil

from gui.theme import C, FONT_FAMILY, section_header, card, stat_card

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

class MetricCard(ctk.CTkFrame):
    """A live-updating metric card for the dashboard."""

    def __init__(self, parent, title: str, unit: str = "",
                 good_threshold=None, warn_threshold=None, lower_is_better=True):
        super().__init__(parent, fg_color=C.SURFACE, corner_radius=8)
        self._unit = unit
        self._good_threshold = good_threshold
        self._warn_threshold = warn_threshold
        self._lower_is_better = lower_is_better

        ctk.CTkLabel(
            self, text=title.upper(),
            font=(FONT_FAMILY, 10), text_color=C.MUTED
        ).pack(anchor="w", padx=14, pady=(12, 0))

        self._value_label = ctk.CTkLabel(
            self, text="—",
            font=(FONT_FAMILY, 28, "bold"), text_color=C.TEXT
        )
        self._value_label.pack(anchor="w", padx=14, pady=(2, 0))

        self._sub_label = ctk.CTkLabel(
            self, text="waiting...",
            font=(FONT_FAMILY, 11), text_color=C.MUTED
        )
        self._sub_label.pack(anchor="w", padx=14, pady=(0, 4))

        self._bar = ctk.CTkProgressBar(self, height=3, corner_radius=0)
        self._bar.pack(fill="x", padx=0, pady=(0, 0), side="bottom")
        self._bar.set(0)

    def update(self, value, subtitle: str = "", bar_fill: float = 0.0):
        """Update card value, subtitle, and bar fill (0.0 to 1.0)."""
        color = self._get_color(value)
        self._value_label.configure(
            text=f"{value}{self._unit}" if value != "—" else "—",
            text_color=color
        )
        self._sub_label.configure(text=subtitle, text_color=C.MUTED)
        self._bar.configure(progress_color=color)
        self._bar.set(min(max(bar_fill, 0.0), 1.0))

    def _get_color(self, value):
        if value == "—" or self._good_threshold is None:
            return C.TEXT
        try:
            v = float(value)
        except (TypeError, ValueError):
            return C.TEXT

        if self._lower_is_better:
            if v <= self._good_threshold:
                return C.SUCCESS
            elif v <= self._warn_threshold:
                return C.WARNING
            else:
                return C.DANGER
        else:
            if v >= self._good_threshold:
                return C.SUCCESS
            elif v >= self._warn_threshold:
                return C.WARNING
            else:
                return C.DANGER

class DpcGraph(ctk.CTkFrame):
    """Live DPC latency graph embedded in the dashboard."""

    MAX_POINTS = 60  # 60 data points = 2 minutes at 2s poll rate

    def __init__(self, parent):
        super().__init__(parent, fg_color=C.SURFACE, corner_radius=8)
        self._data = {}  # driver_name -> list of (timestamp, avg_us) tuples

        ctk.CTkLabel(
            self,
            text="LIVE DPC LATENCY",
            font=(FONT_FAMILY, 10),
            text_color=C.MUTED
        ).pack(anchor="w", padx=14, pady=(12, 0))

        # Create matplotlib figure with dark theme
        self._fig = Figure(figsize=(8, 2.5), dpi=96, facecolor="#12101a")
        self._ax = self._fig.add_subplot(111)
        self._style_axes()

        self._canvas = FigureCanvasTkAgg(self._fig, master=self)
        self._canvas.get_tk_widget().pack(fill="both", expand=True, padx=2, pady=(4, 12))

        # Color cycle for drivers
        self._colors = [
            "#a855f7", "#22c55e", "#f59e0b", "#ef4444",
            "#60a5fa", "#f472b6", "#34d399", "#fb923c"
        ]
        self._driver_colors = {}
        self._color_index = 0

    def _style_axes(self):
        """Apply dark theme to matplotlib axes."""
        ax = self._ax
        ax.set_facecolor("#12101a")
        ax.tick_params(colors="#7c748a", labelsize=8)
        ax.spines['bottom'].set_color("#2a2535")
        ax.spines['left'].set_color("#2a2535")
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.set_ylabel("µs", color="#7c748a", fontsize=8)
        ax.yaxis.set_label_position('right')
        ax.yaxis.tick_right()
        ax.grid(True, color="#2a2535", linewidth=0.5, alpha=0.5)

    def update_data(self, dpc_samples: list):
        """
        Update graph with new DPC data.
        dpc_samples: list of {driver_name, avg_us, severity} dicts
        """
        import time
        now = time.time()

        # Update data store
        for sample in dpc_samples:
            name = sample.get("driver_name", "unknown")
            avg = sample.get("avg_us", 0)
            if name not in self._data:
                self._data[name] = []
            self._data[name].append((now, avg))
            # Keep only last MAX_POINTS
            self._data[name] = self._data[name][-self.MAX_POINTS:]

        # Assign colors to new drivers
        for name in self._data:
            if name not in self._driver_colors:
                self._driver_colors[name] = self._colors[
                    self._color_index % len(self._colors)
                ]
                self._color_index += 1

        # Redraw
        self._ax.clear()
        self._style_axes()

        # Only show top 5 drivers by max value to avoid clutter
        top_drivers = sorted(
            self._data.keys(),
            key=lambda d: max((v for _, v in self._data[d]), default=0),
            reverse=True
        )[:5]

        for name in top_drivers:
            points = self._data[name]
            if len(points) < 2:
                continue
            times = [p[0] - now for p in points]  # seconds ago
            values = [p[1] for p in points]
            color = self._driver_colors.get(name, "#a855f7")
            short_name = name.replace(".sys", "").replace(".SYS", "")[-16:]
            self._ax.plot(times, values, color=color, linewidth=1.2,
                         label=short_name, alpha=0.9)

        if top_drivers:
            legend = self._ax.legend(
                loc="upper left",
                fontsize=7,
                facecolor="#1a1724",
                edgecolor="#2a2535",
                labelcolor="#f0eeff"
            )

        self._canvas.draw_idle()  # non-blocking redraw


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
            app.subscribe("dpc_data_updated", self._on_dpc)
            app.subscribe("timer_measured", self._on_timer_measured)
        except Exception:
            pass

    def _on_dpc(self, data):
        if hasattr(self, '_dpc_graph'):
            self._dpc_graph.update_data(data)

    def _on_timer_measured(self, result):
        grade = result.get('grade', 'UNKNOWN')
        effective = result.get('effective_resolution_ms', 0.0)
        self._timer_card.update(effective, f"Timer Resolution — {grade}", 1.0)

    def _build(self):
        section_header(self, "Dashboard").pack(padx=24, pady=(24, 4), anchor="w")
        ctk.CTkLabel(self, text="System optimization status at a glance",
                     font=(FONT_FAMILY, 13), text_color=C.MUTED,
                     anchor="w").pack(padx=24, pady=(0, 18), anchor="w")

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(padx=24, fill="x")
        grid.columnconfigure((0, 1, 2, 3), weight=1, uniform="col")

        self._admin_card = MetricCard(grid, "Privilege")
        self._admin_card.grid(row=0, column=0, padx=(0, 8), pady=4, sticky="nsew")

        self._timer_card = MetricCard(grid, "Timer Resolution", " ms", good_threshold=0.5, warn_threshold=1.0)
        self._timer_card.grid(row=0, column=1, padx=4, pady=4, sticky="nsew")

        self._ctf_card = MetricCard(grid, "CTF / TSF")
        self._ctf_card.grid(row=0, column=2, padx=4, pady=4, sticky="nsew")

        self._mods_card = MetricCard(grid, "Active Modifications")
        self._mods_card.grid(row=0, column=3, padx=(8, 0), pady=4, sticky="nsew")

        self._dpc_graph = DpcGraph(self)
        self._dpc_graph.pack(padx=24, pady=(16, 8), fill="x")

        # System info section
        info_frame = card(self)
        info_frame.pack(padx=24, pady=(12, 8), fill="x")
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
        if is_admin:
            self._admin_card.update("Administrator", "Elevated", 1.0)
            self._admin_card._bar.configure(progress_color=C.SUCCESS)
            self._admin_card._value_label.configure(text_color=C.SUCCESS)
        else:
            self._admin_card.update("Standard", "Needs Elevation", 1.0)
            self._admin_card._bar.configure(progress_color=C.DANGER)
            self._admin_card._value_label.configure(text_color=C.DANGER)

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
            # Update timer from poll if not yet measured actually
            if self._timer_card._value_label.cget("text") == "—" or "Reported" in self._timer_card._sub_label.cget("text"):
                val = snapshot.get('timer_ms', 0)
                self._timer_card.update(val, "Reported Resolution", min(1.0, 0.5/val if val else 0))

            mods = snapshot.get('active_changes', 0)
            self._mods_card.update(str(mods), f"{mods} active profile tweaks", 1.0 if mods > 0 else 0)
            self._mods_card._value_label.configure(text_color=C.ACCENT if mods > 0 else C.TEXT)
            self._mods_card._bar.configure(progress_color=C.ACCENT if mods > 0 else C.BG)

            ctf_running = any(
                p.name().lower() == "ctfmon.exe"
                for p in psutil.process_iter(['name'])
            )
            if ctf_running:
                self._ctf_card.update("Active", "Default latency", 1.0)
                self._ctf_card._value_label.configure(text_color=C.WARNING)
                self._ctf_card._bar.configure(progress_color=C.WARNING)
            else:
                self._ctf_card.update("Suppressed", "Low latency", 1.0)
                self._ctf_card._value_label.configure(text_color=C.SUCCESS)
                self._ctf_card._bar.configure(progress_color=C.SUCCESS)
        except Exception:
            pass
