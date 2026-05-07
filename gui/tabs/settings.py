"""Settings tab — user preferences and data management."""
import customtkinter as ctk

from gui.theme import C, FONT_FAMILY, section_header, card, primary_button, \
    danger_button, muted_label


class SettingsTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C.BG)
        self._build()

    def _build(self):
        section_header(self, "Settings").pack(padx=24, pady=(24, 4), anchor="w")
        muted_label(self, "Application preferences and data management"
                    ).pack(padx=24, pady=(0, 14), anchor="w")

        try:
            from db import load_settings
            s = load_settings()
        except Exception:
            s = {}

        # ── General Settings ──
        gen_card = card(self)
        gen_card.pack(padx=24, pady=(0, 12), fill="x")
        ctk.CTkLabel(gen_card, text="GENERAL", font=(FONT_FAMILY, 11, "bold"),
                     text_color=C.MUTED).pack(padx=16, pady=(12, 8), anchor="w")

        self._start_boot = ctk.IntVar(value=s.get("start_on_boot", 0))
        ctk.CTkSwitch(gen_card, text="Start on Windows Boot (via Task Scheduler)",
                      variable=self._start_boot, progress_color=C.PRIMARY
                      ).pack(padx=16, pady=(8, 8), anchor="w")

        self._min_tray = ctk.IntVar(value=s.get("show_tray", 0))
        ctk.CTkSwitch(gen_card, text="Minimize to System Tray",
                      variable=self._min_tray, progress_color=C.PRIMARY
                      ).pack(padx=16, pady=(0, 16), anchor="w")

        # ── DPC Settings ──
        dpc_card = card(self)
        dpc_card.pack(padx=24, pady=(0, 12), fill="x")
        ctk.CTkLabel(dpc_card, text="DPC MONITORING", font=(FONT_FAMILY, 11, "bold"),
                     text_color=C.MUTED).pack(padx=16, pady=(12, 8), anchor="w")

        row = ctk.CTkFrame(dpc_card, fg_color="transparent")
        row.pack(padx=16, pady=(0, 16), fill="x")
        ctk.CTkLabel(row, text="Alert Threshold (µs):", font=(FONT_FAMILY, 13),
                     text_color=C.TEXT).pack(side="left", padx=(0, 12))
        self._threshold = ctk.CTkEntry(row, width=80, fg_color=C.SURFACE_HI,
                                       border_color=C.BORDER, text_color=C.TEXT)
        self._threshold.insert(0, str(s.get("alert_threshold_us", 500)))
        self._threshold.pack(side="left")

        # ── Data Management ──
        data_card = card(self)
        data_card.pack(padx=24, pady=(0, 16), fill="x")
        ctk.CTkLabel(data_card, text="DATA MANAGEMENT", font=(FONT_FAMILY, 11, "bold"),
                     text_color=C.MUTED).pack(padx=16, pady=(12, 8), anchor="w")

        danger_button(data_card, "Clear DPC History", self._clear_dpc, width=160
                      ).pack(padx=16, pady=(0, 16), anchor="w")

        # ── Save ──
        bot_row = ctk.CTkFrame(self, fg_color="transparent")
        bot_row.pack(padx=24, fill="x")
        primary_button(bot_row, "Save Settings", self._save_settings, width=140
                       ).pack(side="left", padx=(0, 12))
        self._status_lbl = ctk.CTkLabel(bot_row, text="", font=(FONT_FAMILY, 13),
                                        text_color=C.MUTED)
        self._status_lbl.pack(side="left")

    def _save_settings(self):
        try:
            from db import save_settings
            thresh = int(self._threshold.get())
            save_settings({
                "start_on_boot": bool(self._start_boot.get()),
                "show_tray": bool(self._min_tray.get()),
                "alert_threshold_us": thresh
            })
            self._status_lbl.configure(text="Settings saved ✓", text_color=C.SUCCESS)
        except Exception as e:
            self._status_lbl.configure(text=f"Error: {e}", text_color=C.DANGER)

    def _clear_dpc(self):
        try:
            from db import clear_dpc_samples
            clear_dpc_samples()
            self._status_lbl.configure(text="DPC history cleared ✓", text_color=C.SUCCESS)
        except Exception as e:
            self._status_lbl.configure(text=f"Error: {e}", text_color=C.DANGER)
