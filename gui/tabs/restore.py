"""Restore tab — OPT 5: auto-refreshes via event bus when changes are made."""
import threading
import subprocess
import customtkinter as ctk

from gui.theme import C, FONT_FAMILY, section_header, card, primary_button, \
    danger_button, secondary_button, muted_label


class RestoreTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C.BG)
        self._build()

        # OPT 5: Subscribe to events for auto-refresh
        self.after(100, self._subscribe)

    def _subscribe(self):
        try:
            app = self.winfo_toplevel()
            app.subscribe("profile_applied", lambda _: self._refresh())
            app.subscribe("system_snapshot", self._on_snapshot)
        except Exception:
            pass

    def _build(self):
        section_header(self, "Restore").pack(padx=24, pady=(24, 4), anchor="w")

        desc_row = ctk.CTkFrame(self, fg_color="transparent")
        desc_row.pack(padx=24, fill="x", pady=(0, 14))
        muted_label(desc_row, "Review modifications and rollback system changes"
                    ).pack(side="left")
        self._count_badge = ctk.CTkLabel(
            desc_row, text="", font=(FONT_FAMILY, 12, "bold"), text_color=C.ACCENT)
        self._count_badge.pack(side="right")

        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(padx=24, fill="x", pady=(0, 16))
        primary_button(ctrl, "🔄  Refresh", self._refresh, width=120
                       ).pack(side="left", padx=(0, 8))
        secondary_button(ctrl, "🛡  Open System Restore", self._open_rstrui, width=180
                         ).pack(side="left", padx=(0, 8))
        secondary_button(ctrl, "➕  Manual Restore Point", self._manual_rp, width=180
                         ).pack(side="left")

        self._status_lbl = ctk.CTkLabel(ctrl, text="",
                                        font=(FONT_FAMILY, 13), text_color=C.MUTED)
        self._status_lbl.pack(side="left", padx=16)

        self._scroll = ctk.CTkScrollableFrame(self, fg_color=C.BG,
                                              scrollbar_button_color=C.BORDER)
        self._scroll.pack(padx=24, pady=(0, 16), fill="both", expand=True)

        self._refresh()

    def _on_snapshot(self, snapshot):
        """OPT 5: Update badge count from the poll thread."""
        try:
            count = snapshot.get("active_changes", 0)
            self._count_badge.configure(
                text=f"{count} active modification{'s' if count != 1 else ''}")
        except Exception:
            pass

    def _open_rstrui(self):
        try:
            subprocess.Popen(['rstrui.exe'])
        except Exception as e:
            self._status_lbl.configure(text=f"Error: {e}", text_color=C.DANGER)

    def _manual_rp(self):
        self._status_lbl.configure(text="Creating…", text_color=C.WARNING)
        threading.Thread(target=self._rp_worker, daemon=True).start()

    def _rp_worker(self):
        try:
            from bridge.windows_bridge import create_restore_point
            from db import save_restore_point
            rp = create_restore_point("OP TOOL: Manual GUI restore point")
            if rp["success"]:
                save_restore_point(rp["sequence_number"], "Manual GUI restore point")
                self.after(0, lambda: self._status_lbl.configure(
                    text="Restore point created ✓", text_color=C.SUCCESS))
            else:
                self.after(0, lambda: self._status_lbl.configure(
                    text=f"Failed: {rp.get('error', '')}", text_color=C.DANGER))
        except Exception as e:
            self.after(0, lambda: self._status_lbl.configure(
                text=str(e), text_color=C.DANGER))

    def _refresh(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        try:
            from db import get_active_sessions
            sessions = get_active_sessions()
            if not sessions:
                ctk.CTkLabel(self._scroll, text="No active system modifications.",
                             font=(FONT_FAMILY, 14), text_color=C.SUCCESS
                             ).pack(pady=40)
                return

            for s in sessions:
                card = card(self._scroll)
                card.pack(fill="x", pady=(0, 12))

                hdr = ctk.CTkFrame(card, fg_color="transparent")
                hdr.pack(padx=16, pady=(12, 8), fill="x")
                title = f"Session: {s['session_id']}"
                if s.get("profile_name"):
                    title += f" (Profile: {s['profile_name']})"
                ctk.CTkLabel(hdr, text=title, font=(FONT_FAMILY, 15, "bold"),
                             text_color=C.TEXT).pack(side="left")
                ctk.CTkLabel(hdr, text=s["applied_at"], font=(FONT_FAMILY, 12),
                             text_color=C.MUTED).pack(side="right")

                changes_frame = ctk.CTkFrame(card, fg_color="transparent")
                changes_frame.pack(padx=16, pady=(0, 12), fill="x")
                for c in s["changes"][:5]:
                    row = ctk.CTkFrame(changes_frame, fg_color="transparent")
                    row.pack(fill="x", pady=2)
                    lbl = f"• [{c['change_type'].upper()}] "
                    if c.get("device_id"):
                        lbl += f"{c['device_id'][:30]}… "
                    lbl += f"→ {c['reg_value_name']}"
                    ctk.CTkLabel(row, text=lbl, font=(FONT_FAMILY, 12),
                                 text_color=C.TEXT).pack(side="left")

                if len(s["changes"]) > 5:
                    ctk.CTkLabel(changes_frame,
                                 text=f"… and {len(s['changes'])-5} more",
                                 font=(FONT_FAMILY, 12), text_color=C.MUTED
                                 ).pack(anchor="w", pady=2)

                danger_button(card, "Revert Session",
                              lambda sid=s["session_id"]: self._revert(sid),
                              width=140).pack(padx=16, pady=(0, 16), anchor="w")

        except Exception as e:
            self._status_lbl.configure(text=f"Error: {e}", text_color=C.DANGER)

    def _revert(self, session_id):
        self._status_lbl.configure(text="Reverting…", text_color=C.WARNING)
        threading.Thread(target=self._revert_worker, args=(session_id,),
                         daemon=True).start()

    def _revert_worker(self, session_id):
        try:
            import winreg
            from db import get_session_changes, mark_restored
            from bridge.windows_bridge import reg_write, restore_ctf, restore_timer_resolution

            changes = get_session_changes(session_id)
            ok = 0
            for c in changes:
                if c["change_type"] == "timer":
                    if restore_timer_resolution()["success"]:
                        mark_restored(c["id"]); ok += 1
                elif c["change_type"] == "ctf":
                    restore_ctf(); mark_restored(c["id"]); ok += 1
                else:
                    try:
                        orig = eval(c["original_value"])
                    except Exception:
                        orig = c["original_value"]
                    reg_type = winreg.REG_DWORD
                    if c["change_type"] == "affinity_binary":
                        reg_type = winreg.REG_BINARY
                        try:
                            orig = bytes.fromhex(c["original_value"])
                        except Exception:
                            pass
                    if reg_write(winreg.HKEY_LOCAL_MACHINE, c["reg_path"],
                                 c["reg_value_name"], orig, reg_type):
                        mark_restored(c["id"]); ok += 1

            self.after(0, lambda: self._status_lbl.configure(
                text=f"Reverted {ok}/{len(changes)} ✓", text_color=C.SUCCESS))
            self.after(500, self._refresh)
        except Exception as e:
            self.after(0, lambda: self._status_lbl.configure(
                text=str(e), text_color=C.DANGER))
