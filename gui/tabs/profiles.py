"""Profiles tab — OPT 2: step-by-step status feedback during profile application."""
import threading
import customtkinter as ctk

from gui.theme import C, FONT_FAMILY, section_header, card, primary_button, \
    danger_button, muted_label


class ProfilesTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C.BG)
        self._build()

    def _build(self):
        section_header(self, "Profiles").pack(padx=24, pady=(24, 4), anchor="w")
        muted_label(self, "Save and apply bulk optimization settings"
                    ).pack(padx=24, pady=(0, 14), anchor="w")

        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(padx=24, fill="x", pady=(0, 16))
        primary_button(ctrl, "➕  New Profile", self._show_create, width=160
                       ).pack(side="left", padx=(0, 8))
        self._status_lbl = ctk.CTkLabel(ctrl, text="",
                                        font=(FONT_FAMILY, 13), text_color=C.MUTED)
        self._status_lbl.pack(side="left", padx=16)

        self._scroll = ctk.CTkScrollableFrame(self, fg_color=C.BG,
                                              scrollbar_button_color=C.BORDER)
        self._scroll.pack(padx=24, pady=(0, 16), fill="both", expand=True)

        self._refresh()

    # ── List ──

    def _refresh(self):
        for w in self._scroll.winfo_children():
            w.destroy()
        try:
            from db import get_profiles
            profiles = get_profiles()
            if not profiles:
                ctk.CTkLabel(self._scroll, text="No profiles created yet.",
                             font=(FONT_FAMILY, 14), text_color=C.MUTED).pack(pady=40)
                return

            for p in profiles:
                self._render_profile_card(p)
        except Exception as e:
            self._status_lbl.configure(text=f"Error: {e}", text_color=C.DANGER)

    def _render_profile_card(self, p):
        card = card(self._scroll)
        card.pack(fill="x", pady=(0, 12))

        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(padx=16, pady=(12, 4), fill="x")
        ctk.CTkLabel(hdr, text=p["name"], font=(FONT_FAMILY, 16, "bold"),
                     text_color=C.TEXT).pack(side="left")

        if p.get("description"):
            ctk.CTkLabel(card, text=p["description"], font=(FONT_FAMILY, 12),
                         text_color=C.MUTED).pack(padx=16, pady=(0, 8), anchor="w")

        # Tags
        meta = ctk.CTkFrame(card, fg_color="transparent")
        meta.pack(padx=16, pady=(0, 12), fill="x")
        tags = []
        if p.get("timer_resolution_100ns") and p["timer_resolution_100ns"] < 156250:
            tags.append(f"Timer: {round(p['timer_resolution_100ns']*100/1000000, 2)}ms")
        if p.get("ctf_suppressed"):
            tags.append("CTF Suppressed")
        if p.get("msi_enabled"):
            tags.append("MSI All")
        for t in tags:
            badge = ctk.CTkFrame(meta, fg_color=C.SURFACE_HI, corner_radius=4)
            badge.pack(side="left", padx=(0, 6))
            ctk.CTkLabel(badge, text=t, font=(FONT_FAMILY, 11),
                         text_color=C.ACCENT).pack(padx=8, pady=2)

        # Actions
        act = ctk.CTkFrame(card, fg_color="transparent")
        act.pack(padx=16, pady=(0, 12), fill="x")
        primary_button(act, "Apply Profile", lambda pid=p["id"]: self._apply(pid),
                       width=120).pack(side="left", padx=(0, 8))
        danger_button(act, "Delete", lambda pid=p["id"]: self._delete(pid),
                      width=80).pack(side="left")

    # ── OPT 2: Step-by-step apply with live feedback ──

    def _apply(self, pid):
        self._status_lbl.configure(text="", text_color=C.MUTED)

        # Create a live steps panel at the top of the scroll area
        self._steps_card = card(self._scroll)
        # Insert at position 0 so it appears at the top
        self._steps_card.pack(fill="x", pady=(0, 12), before=self._scroll.winfo_children()[0]
                              if self._scroll.winfo_children() else None)

        ctk.CTkLabel(self._steps_card, text="APPLYING PROFILE…",
                     font=(FONT_FAMILY, 11, "bold"),
                     text_color=C.WARNING).pack(padx=16, pady=(12, 8), anchor="w")

        self._step_widgets = {}
        self._steps_frame = ctk.CTkFrame(self._steps_card, fg_color="transparent")
        self._steps_frame.pack(padx=16, pady=(0, 16), fill="x")

        threading.Thread(target=self._apply_worker, args=(pid,), daemon=True).start()

    def _add_step(self, name, status="running", message=""):
        """Add or update a step in the live panel. Thread-safe via after()."""
        def _do():
            if name in self._step_widgets:
                dot, lbl = self._step_widgets[name]
            else:
                row = ctk.CTkFrame(self._steps_frame, fg_color="transparent")
                row.pack(fill="x", pady=2)
                dot = ctk.CTkLabel(row, text="●", font=(FONT_FAMILY, 14), width=24)
                dot.pack(side="left")
                lbl = ctk.CTkLabel(row, text="", font=(FONT_FAMILY, 13),
                                   text_color=C.TEXT)
                lbl.pack(side="left", padx=4)
                self._step_widgets[name] = (dot, lbl)

            colors = {"running": C.WARNING, "ok": C.SUCCESS, "fail": C.DANGER}
            icons = {"running": "◌", "ok": "●", "fail": "✖"}
            dot.configure(text=icons.get(status, "●"),
                         text_color=colors.get(status, C.MUTED))
            text = name
            if message:
                text += f" — {message}"
            lbl.configure(text=text)

        self.after(0, _do)

    def _apply_worker(self, pid):
        from db import get_profile, new_session, save_restore_point
        from bridge import windows_bridge as wb
        from bridge.change_log import restore_session

        p = get_profile(pid)
        if not p:
            self._add_step("Load Profile", "fail", "Profile not found")
            return

        self._add_step("Load Profile", "ok", p["name"])

        session_id = new_session()

        # Step 1: Restore point (MANDATORY — no rollback needed if this fails)
        self._add_step("Restore Point", "running")
        rp = wb.create_restore_point(f"OP TOOL: {p['name']}")
        if not rp["success"]:
            self._add_step("Restore Point", "fail", rp.get("error", "Failed"))
            self._add_step("ABORTED", "fail", "Cannot continue without restore point")
            return
        save_restore_point(rp["sequence_number"], f"Apply {p['name']}")
        self._add_step("Restore Point", "ok", f"#{rp['sequence_number']}")

        # ── All steps after restore point are wrapped for automatic rollback ──
        try:
            devices = None  # cached across steps

            # Step 2: Timer
            if p.get("timer_resolution_100ns") and p["timer_resolution_100ns"] < 156250:
                self._add_step("Timer Resolution", "running")
                result = wb.set_timer_resolution(p["timer_resolution_100ns"])
                if not result["success"]:
                    raise RuntimeError(f"Timer failed: NTSTATUS {result.get('ntstatus')}")
                ms = result.get("actual_resolution_ms", "?")
                self._add_step("Timer Resolution", "ok", f"{ms}ms")

            # Step 3: CTF
            if p.get("ctf_suppressed"):
                self._add_step("CTF Suppression", "running")
                result = wb.suppress_ctf()
                if not result.get("verified"):
                    raise RuntimeError("CTF suppression failed — ctfmon.exe still running")
                self._add_step("CTF Suppression", "ok")

            # Step 4: MSI
            if p.get("msi_enabled"):
                self._add_step("MSI Mode", "running")
                devices = wb.get_pci_devices()
                msi_count = 0
                msi_fail = 0
                for dev in devices:
                    drv = (dev.get("driver_name") or "").upper()
                    if any(k in drv for k in ["USB", "NET", "AUDIO", "HDA"]):
                        r = wb.enable_msi(dev["device_id"])
                        if r["success"]:
                            msi_count += 1
                        else:
                            msi_fail += 1
                if msi_fail > 0 and msi_count == 0:
                    raise RuntimeError(f"MSI failed on all {msi_fail} devices")
                self._add_step("MSI Mode", "ok", f"{msi_count} devices")

            # Step 5: Affinity
            if p.get("affinity_usb_core"):
                self._add_step("USB Affinity", "running")
                if devices is None:
                    devices = wb.get_pci_devices()
                mask = 1 << int(p["affinity_usb_core"])
                for dev in devices:
                    if "USB" in (dev.get("driver_name") or "").upper():
                        r = wb.set_interrupt_affinity(dev["device_id"], mask)
                        if not r["success"]:
                            raise RuntimeError(f"USB affinity failed: {dev['device_id'][:30]}")
                self._add_step("USB Affinity", "ok", f"Core {p['affinity_usb_core']}")

            if p.get("affinity_nic_core"):
                self._add_step("NIC Affinity", "running")
                if devices is None:
                    devices = wb.get_pci_devices()
                mask = 1 << int(p["affinity_nic_core"])
                for dev in devices:
                    if "NET" in (dev.get("driver_name") or "").upper():
                        r = wb.set_interrupt_affinity(dev["device_id"], mask)
                        if not r["success"]:
                            raise RuntimeError(f"NIC affinity failed: {dev['device_id'][:30]}")
                self._add_step("NIC Affinity", "ok", f"Core {p['affinity_nic_core']}")

        except Exception as step_error:
            # ── AUTOMATIC ROLLBACK ──
            # Something failed after the restore point succeeded.
            # Revert every change logged under this session_id.
            self._add_step("ROLLING BACK", "running", str(step_error))
            try:
                rb = restore_session(session_id)
                rolled = rb.get("succeeded", 0)
                total = rb.get("total", 0)
                self._add_step("ROLLED BACK", "ok",
                               f"Reverted {rolled}/{total} changes")
            except Exception as rb_err:
                self._add_step("ROLLBACK FAILED", "fail", str(rb_err))

            self._add_step("ABORTED", "fail", str(step_error))
            self.after(0, lambda: self._status_lbl.configure(
                text=f"Failed & rolled back: {step_error}", text_color=C.DANGER))

            # Still publish so Restore tab refreshes
            try:
                app = self.winfo_toplevel()
                self.after(0, lambda: app.publish("profile_applied",
                                                  {"profile": p, "session": session_id,
                                                   "rolled_back": True}))
            except Exception:
                pass
            return

        # ── All steps succeeded ──
        self._add_step("Complete", "ok", f"Profile '{p['name']}' active")
        self.after(0, lambda: self._status_lbl.configure(
            text=f"✓ Applied '{p['name']}'", text_color=C.SUCCESS))

        try:
            app = self.winfo_toplevel()
            self.after(0, lambda: app.publish("profile_applied",
                                              {"profile": p, "session": session_id}))
        except Exception:
            pass

    # ── Delete ──

    def _delete(self, pid):
        try:
            from db import delete_profile
            delete_profile(pid)
            self._refresh()
        except Exception as e:
            self._status_lbl.configure(text=f"Error: {e}", text_color=C.DANGER)

    # ── Create dialog ──

    def _show_create(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("New Profile")
        dialog.geometry("400x480")
        dialog.configure(fg_color=C.BG)
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Profile Name:", font=(FONT_FAMILY, 12, "bold"),
                     text_color=C.TEXT).pack(padx=20, pady=(20, 4), anchor="w")
        name_entry = ctk.CTkEntry(dialog, fg_color=C.SURFACE, border_color=C.BORDER,
                                  text_color=C.TEXT)
        name_entry.pack(padx=20, fill="x")

        ctk.CTkLabel(dialog, text="Description:", font=(FONT_FAMILY, 12, "bold"),
                     text_color=C.TEXT).pack(padx=20, pady=(12, 4), anchor="w")
        desc_entry = ctk.CTkEntry(dialog, fg_color=C.SURFACE, border_color=C.BORDER,
                                  text_color=C.TEXT)
        desc_entry.pack(padx=20, fill="x")

        msi_var = ctk.IntVar(value=0)
        ctk.CTkSwitch(dialog, text="Enable all MSI", variable=msi_var,
                      progress_color=C.PRIMARY).pack(padx=20, pady=(20, 10), anchor="w")

        ctf_var = ctk.IntVar(value=0)
        ctk.CTkSwitch(dialog, text="Suppress CTF/TSF", variable=ctf_var,
                      progress_color=C.PRIMARY).pack(padx=20, pady=10, anchor="w")

        timer_var = ctk.IntVar(value=0)
        ctk.CTkSwitch(dialog, text="Force 0.5ms Timer", variable=timer_var,
                      progress_color=C.PRIMARY).pack(padx=20, pady=10, anchor="w")

        def _save():
            name = name_entry.get().strip()
            if not name:
                return
            try:
                from db import create_profile
                create_profile(
                    name=name,
                    description=desc_entry.get().strip(),
                    msi_enabled=msi_var.get(),
                    ctf_suppressed=ctf_var.get(),
                    timer_resolution_100ns=5000 if timer_var.get() else 156250
                )
                dialog.destroy()
                self._refresh()
            except Exception as e:
                print(f"Error saving: {e}")

        primary_button(dialog, "Save Profile", _save, width=120).pack(pady=30)
