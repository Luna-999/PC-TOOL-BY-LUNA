"""Timer Resolution tab — set/restore system timer resolution."""
import threading
import customtkinter as ctk

from gui.theme import C, FONT_FAMILY, heading, card_frame, primary_button, \
    danger_button, muted_label


# Preset values: (label, 100ns value)
PRESETS = [
    ("0.5 ms (max)", 5000),
    ("1.0 ms", 10000),
    ("5.0 ms", 50000),
    ("10.0 ms", 100000),
    ("15.625 ms (default)", 156250),
]


class TimerTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C.BG)
        self._build()
        self._refresh_current()

    def _build(self):
        heading(self, "Timer Resolution").pack(padx=24, pady=(24, 4), anchor="w")
        muted_label(self, "Set the Windows system timer resolution via NtSetTimerResolution"
                    ).pack(padx=24, pady=(0, 14), anchor="w")

        # ── Current resolution display ──
        cur_card = card_frame(self)
        cur_card.pack(padx=24, pady=(0, 12), fill="x")
        ctk.CTkLabel(cur_card, text="CURRENT RESOLUTION",
                     font=(FONT_FAMILY, 11, "bold"),
                     text_color=C.MUTED).pack(padx=16, pady=(12, 4), anchor="w")

        res_row = ctk.CTkFrame(cur_card, fg_color="transparent")
        res_row.pack(padx=16, pady=(0, 16), fill="x")
        self._cur_val = ctk.CTkLabel(res_row, text="— ms",
                                     font=(FONT_FAMILY, 32, "bold"),
                                     text_color=C.TEXT)
        self._cur_val.pack(side="left")
        self._cur_detail = ctk.CTkLabel(res_row, text="",
                                        font=(FONT_FAMILY, 12),
                                        text_color=C.MUTED)
        self._cur_detail.pack(side="left", padx=20)

        # ── Slider control ──
        ctrl_card = card_frame(self)
        ctrl_card.pack(padx=24, pady=(0, 12), fill="x")
        ctk.CTkLabel(ctrl_card, text="SET RESOLUTION",
                     font=(FONT_FAMILY, 11, "bold"),
                     text_color=C.MUTED).pack(padx=16, pady=(12, 8), anchor="w")

        slider_frame = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        slider_frame.pack(padx=16, fill="x")

        self._slider_val = ctk.CTkLabel(slider_frame, text="0.5 ms",
                                        font=(FONT_FAMILY, 16, "bold"),
                                        text_color=C.ACCENT, width=100)
        self._slider_val.pack(side="left")

        self._slider = ctk.CTkSlider(slider_frame, from_=5000, to=156250,
                                     number_of_steps=50,
                                     command=self._on_slider,
                                     fg_color=C.BORDER,
                                     progress_color=C.PRIMARY,
                                     button_color=C.ACCENT,
                                     button_hover_color=C.PRIMARY_HVR,
                                     width=400)
        self._slider.set(5000)
        self._slider.pack(side="left", padx=12, fill="x", expand=True)

        # Presets
        preset_frame = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        preset_frame.pack(padx=16, pady=(8, 4), fill="x")
        ctk.CTkLabel(preset_frame, text="Presets:", font=(FONT_FAMILY, 12),
                     text_color=C.MUTED).pack(side="left", padx=(0, 8))
        for label, val in PRESETS:
            btn = ctk.CTkButton(preset_frame, text=label, width=120, height=28,
                                fg_color=C.SURFACE_HI, hover_color=C.PRIMARY,
                                text_color=C.TEXT, corner_radius=4,
                                font=(FONT_FAMILY, 11),
                                command=lambda v=val: self._set_preset(v))
            btn.pack(side="left", padx=2)

        # Buttons
        btn_row = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        btn_row.pack(padx=16, pady=(12, 16), fill="x")
        primary_button(btn_row, "⚡  Apply", self._apply, width=140
                       ).pack(side="left", padx=(0, 8))
        danger_button(btn_row, "↺  Restore Default", self._restore, width=180
                      ).pack(side="left")
        self._status_lbl = ctk.CTkLabel(btn_row, text="",
                                        font=(FONT_FAMILY, 13), text_color=C.MUTED)
        self._status_lbl.pack(side="left", padx=16)

        # ── Info ──
        info_card = card_frame(self)
        info_card.pack(padx=24, pady=(0, 16), fill="x")
        ctk.CTkLabel(info_card, text="ℹ  Lower values reduce input latency but increase CPU usage. "
                     "The setting persists only while OP TOOL is running.",
                     font=(FONT_FAMILY, 12), text_color=C.MUTED,
                     wraplength=700, anchor="w").pack(padx=16, pady=12, anchor="w")

    def _on_slider(self, value):
        ms = round(value * 100 / 1_000_000, 2)
        self._slider_val.configure(text=f"{ms} ms")

    def _set_preset(self, val):
        self._slider.set(val)
        self._on_slider(val)

    def _refresh_current(self):
        threading.Thread(target=self._fetch_current, daemon=True).start()

    def _fetch_current(self):
        try:
            from bridge.windows_bridge import get_timer_resolution
            t = get_timer_resolution()
            self.after(0, lambda: self._update_display(t))
        except Exception:
            pass

    def _update_display(self, t):
        self._cur_val.configure(text=f"{t['current_ms']} ms")
        self._cur_detail.configure(
            text=f"({t['current_100ns']} × 100ns)  |  "
                 f"Min: {t['minimum_100ns']}  Max: {t['maximum_100ns']}")

    def _apply(self):
        val = int(self._slider.get())
        self._status_lbl.configure(text="Setting…", text_color=C.WARNING)
        threading.Thread(target=self._apply_worker, args=(val,), daemon=True).start()

    def _apply_worker(self, val):
        try:
            from bridge.windows_bridge import set_timer_resolution, get_timer_resolution
            from db import record_change
            current = get_timer_resolution()
            record_change("timer", "SYSTEM\\TIMER", "Resolution",
                          current["current_100ns"], val)
            result = set_timer_resolution(val)
            if result["success"]:
                self.after(0, lambda: self._status_lbl.configure(
                    text=f"Set to {result['actual_resolution_ms']} ms ✓",
                    text_color=C.SUCCESS))
            else:
                self.after(0, lambda: self._status_lbl.configure(
                    text=f"Failed (NTSTATUS {result['ntstatus']})",
                    text_color=C.DANGER))
            self.after(200, self._refresh_current)
        except Exception as e:
            self.after(0, lambda: self._status_lbl.configure(
                text=str(e), text_color=C.DANGER))

    def _restore(self):
        self._status_lbl.configure(text="Restoring…", text_color=C.WARNING)
        threading.Thread(target=self._restore_worker, daemon=True).start()

    def _restore_worker(self):
        try:
            from bridge.windows_bridge import restore_timer_resolution
            from db import get_active_changes, mark_restored
            result = restore_timer_resolution()
            entries = [c for c in get_active_changes() if c['change_type'] == 'timer']
            for e in entries:
                mark_restored(e['id'])
            msg = "Restored to default ✓" if result["success"] else "Failed"
            color = C.SUCCESS if result["success"] else C.DANGER
            self.after(0, lambda: self._status_lbl.configure(text=msg, text_color=color))
            self.after(200, self._refresh_current)
        except Exception as e:
            self.after(0, lambda: self._status_lbl.configure(
                text=str(e), text_color=C.DANGER))
