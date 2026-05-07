"""CTF tab — suppress/restore CTF (Text Framework) service."""
import threading
import customtkinter as ctk
from gui.theme import C, FONT_FAMILY, section_header, card, primary_button, \
    danger_button, muted_label


class CtfTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C.BG)
        self._build()
        self._check_status()

    def _build(self):
        section_header(self, "CTF / TSF Suppression").pack(padx=24, pady=(24, 4), anchor="w")
        muted_label(self, "Disable the Collaborative Translation Framework to reduce input latency"
                    ).pack(padx=24, pady=(0, 14), anchor="w")

        status_card = card(self)
        status_card.pack(padx=24, pady=(0, 12), fill="x")
        ctk.CTkLabel(status_card, text="CTF STATUS", font=(FONT_FAMILY, 11, "bold"),
                     text_color=C.MUTED).pack(padx=16, pady=(12, 4), anchor="w")
        status_row = ctk.CTkFrame(status_card, fg_color="transparent")
        status_row.pack(padx=16, pady=(0, 16), fill="x")
        self._status_dot = ctk.CTkLabel(status_row, text="●", font=(FONT_FAMILY, 22),
                                        text_color=C.MUTED)
        self._status_dot.pack(side="left")
        self._status_text = ctk.CTkLabel(status_row, text="Checking…",
                                         font=(FONT_FAMILY, 18, "bold"), text_color=C.TEXT)
        self._status_text.pack(side="left", padx=8)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(padx=24, fill="x", pady=(0, 12))
        self._suppress_btn = primary_button(btn_row, "🛡  Suppress CTF", self._suppress, width=180)
        self._suppress_btn.pack(side="left", padx=(0, 8))
        self._restore_btn = danger_button(btn_row, "↺  Restore CTF", self._restore, width=160)
        self._restore_btn.pack(side="left")
        self._action_lbl = ctk.CTkLabel(btn_row, text="", font=(FONT_FAMILY, 13),
                                        text_color=C.MUTED)
        self._action_lbl.pack(side="left", padx=16)

        steps_card = card(self)
        steps_card.pack(padx=24, pady=(0, 12), fill="x")
        ctk.CTkLabel(steps_card, text="SUPPRESSION STEPS", font=(FONT_FAMILY, 11, "bold"),
                     text_color=C.MUTED).pack(padx=16, pady=(12, 8), anchor="w")
        sf = ctk.CTkFrame(steps_card, fg_color="transparent")
        sf.pack(padx=16, pady=(0, 16), fill="x")
        self._step_labels = {}
        steps = [
            ("reg_input_service", "Disable InputServiceEnabled registry key"),
            ("reg_input_cci", "Disable InputServiceEnabledForCCI registry key"),
            ("stop_service", "Stop TabletInputService"),
            ("disable_service", "Disable TabletInputService startup"),
            ("kill_ctfmon", "Kill ctfmon.exe process"),
            ("verified", "Verify ctfmon.exe is not running"),
        ]
        for key, desc in steps:
            row = ctk.CTkFrame(sf, fg_color="transparent")
            row.pack(fill="x", pady=2)
            dot = ctk.CTkLabel(row, text="○", font=(FONT_FAMILY, 14),
                               text_color=C.MUTED, width=24)
            dot.pack(side="left")
            ctk.CTkLabel(row, text=desc, font=(FONT_FAMILY, 13),
                         text_color=C.TEXT).pack(side="left", padx=4)
            self._step_labels[key] = dot

        info_card = card(self)
        info_card.pack(padx=24, pady=(0, 16), fill="x")
        ctk.CTkLabel(info_card, text="ℹ  CTF suppression disables Windows text services. "
                     "A system restore point is created before any changes.",
                     font=(FONT_FAMILY, 12), text_color=C.MUTED, wraplength=700,
                     anchor="w").pack(padx=16, pady=12, anchor="w")

    def _check_status(self):
        threading.Thread(target=self._status_worker, daemon=True).start()

    def _status_worker(self):
        try:
            import psutil
            running = any(p.name().lower() == "ctfmon.exe"
                          for p in psutil.process_iter(['name']))
            self.after(0, lambda: self._update_status(running))
        except Exception:
            pass

    def _update_status(self, running):
        if running:
            self._status_dot.configure(text_color=C.WARNING)
            self._status_text.configure(text="CTF Active", text_color=C.WARNING)
        else:
            self._status_dot.configure(text_color=C.SUCCESS)
            self._status_text.configure(text="CTF Suppressed", text_color=C.SUCCESS)

    def _suppress(self):
        self._action_lbl.configure(text="Suppressing…", text_color=C.WARNING)
        self._suppress_btn.configure(state="disabled")
        threading.Thread(target=self._suppress_worker, daemon=True).start()

    def _suppress_worker(self):
        try:
            from bridge.windows_bridge import create_restore_point, suppress_ctf
            from db import record_change, save_restore_point
            rp = create_restore_point("OP TOOL: CTF suppress")
            if not rp["success"]:
                self.after(0, lambda: self._action_lbl.configure(
                    text="Restore point failed", text_color=C.DANGER))
                self.after(0, lambda: self._suppress_btn.configure(state="normal"))
                return
            save_restore_point(rp["sequence_number"], "CTF suppress")
            record_change("ctf", "SOFTWARE\\Microsoft\\Input", "InputServiceEnabled", 1, 0)
            result = suppress_ctf()
            self.after(0, lambda: self._show_steps(result))
            self.after(0, lambda: self._action_lbl.configure(
                text="CTF suppressed ✓", text_color=C.SUCCESS))
            self.after(0, lambda: self._suppress_btn.configure(state="normal"))
            self.after(500, self._check_status)
        except Exception as e:
            self.after(0, lambda: self._action_lbl.configure(text=str(e), text_color=C.DANGER))
            self.after(0, lambda: self._suppress_btn.configure(state="normal"))

    def _restore(self):
        self._action_lbl.configure(text="Restoring…", text_color=C.WARNING)
        self._restore_btn.configure(state="disabled")
        threading.Thread(target=self._restore_worker, daemon=True).start()

    def _restore_worker(self):
        try:
            from bridge.windows_bridge import restore_ctf
            from db import get_active_changes, mark_restored
            restore_ctf()
            for e in [c for c in get_active_changes() if c['change_type'] == 'ctf']:
                mark_restored(e['id'])
            self.after(0, lambda: self._action_lbl.configure(
                text="CTF restored ✓", text_color=C.SUCCESS))
            self.after(0, lambda: self._restore_btn.configure(state="normal"))
            for dot in self._step_labels.values():
                self.after(0, lambda d=dot: d.configure(text="○", text_color=C.MUTED))
            self.after(500, self._check_status)
        except Exception as e:
            self.after(0, lambda: self._action_lbl.configure(text=str(e), text_color=C.DANGER))
            self.after(0, lambda: self._restore_btn.configure(state="normal"))

    def _show_steps(self, result):
        for key, dot in self._step_labels.items():
            val = result.get(key)
            if val is True or (isinstance(val, dict) and val.get("success")):
                dot.configure(text="●", text_color=C.SUCCESS)
            elif val is False:
                dot.configure(text="●", text_color=C.DANGER)
            else:
                dot.configure(text="●", text_color=C.WARNING)
