"""Profiles tab — create, apply, and delete optimization profiles."""
import threading
import customtkinter as ctk

from gui.theme import C, FONT_FAMILY, heading, card_frame, primary_button, \
    danger_button, secondary_button, muted_label


class ProfilesTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C.BG)
        self._build()

    def _build(self):
        heading(self, "Profiles").pack(padx=24, pady=(24, 4), anchor="w")
        muted_label(self, "Save and apply bulk optimization settings"
                    ).pack(padx=24, pady=(0, 14), anchor="w")

        # ── Controls ──
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(padx=24, fill="x", pady=(0, 16))
        primary_button(ctrl, "➕  New Profile", self._show_create, width=160
                       ).pack(side="left", padx=(0, 8))
        self._status_lbl = ctk.CTkLabel(ctrl, text="",
                                        font=(FONT_FAMILY, 13), text_color=C.MUTED)
        self._status_lbl.pack(side="left", padx=16)

        # ── Scrollable list ──
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=C.BG,
                                              scrollbar_button_color=C.BORDER)
        self._scroll.pack(padx=24, pady=(0, 16), fill="both", expand=True)

        self._refresh()

    def _refresh(self):
        for w in self._scroll.winfo_children():
            w.destroy()

        try:
            from db import get_profiles
            profiles = get_profiles()
            if not profiles:
                ctk.CTkLabel(self._scroll, text="No profiles created yet.",
                             font=(FONT_FAMILY, 14), text_color=C.MUTED
                             ).pack(pady=40)
                return

            for p in profiles:
                card = card_frame(self._scroll)
                card.pack(fill="x", pady=(0, 12))

                hdr = ctk.CTkFrame(card, fg_color="transparent")
                hdr.pack(padx=16, pady=(12, 4), fill="x")
                ctk.CTkLabel(hdr, text=p["name"], font=(FONT_FAMILY, 16, "bold"),
                             text_color=C.TEXT).pack(side="left")

                if p.get("description"):
                    ctk.CTkLabel(card, text=p["description"], font=(FONT_FAMILY, 12),
                                 text_color=C.MUTED).pack(padx=16, pady=(0, 8), anchor="w")

                # Meta tags
                meta = ctk.CTkFrame(card, fg_color="transparent")
                meta.pack(padx=16, pady=(0, 12), fill="x")

                tags = []
                if p.get("timer_resolution_100ns"):
                    tags.append(f"Timer: {round(p['timer_resolution_100ns']*100/1000000, 2)}ms")
                if p.get("ctf_suppressed"):
                    tags.append("CTF Suppressed")
                if p.get("msi_enabled"):
                    tags.append("MSI All")
                if p.get("affinity_usb_core") or p.get("affinity_nic_core") or p.get("affinity_gpu_core"):
                    tags.append("Affinity Set")

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

        except Exception as e:
            self._status_lbl.configure(text=f"Error: {e}", text_color=C.DANGER)

    def _apply(self, pid):
        self._status_lbl.configure(text="Applying profile…", text_color=C.WARNING)
        threading.Thread(target=self._apply_worker, args=(pid,), daemon=True).start()

    def _apply_worker(self, pid):
        try:
            from db import get_profile, record_change, new_session, save_restore_point
            from bridge import windows_bridge as wb

            p = get_profile(pid)
            if not p:
                raise ValueError("Profile not found")

            session_id = new_session()
            rp = wb.create_restore_point(f"OP TOOL: Apply {p['name']}")
            if not rp["success"]:
                raise RuntimeError(f"Restore point failed: {rp['error']}")
            save_restore_point(rp["sequence_number"], f"Apply {p['name']}")

            # Timer
            if p.get("timer_resolution_100ns"):
                current = wb.get_timer_resolution()["current_100ns"]
                record_change("timer", "SYSTEM\\TIMER", "Resolution", current,
                              p["timer_resolution_100ns"], profile_name=p["name"])
                wb.set_timer_resolution(p["timer_resolution_100ns"])

            # CTF
            if p.get("ctf_suppressed"):
                record_change("ctf", "SOFTWARE\\Microsoft\\Input", "InputServiceEnabled",
                              1, 0, profile_name=p["name"])
                wb.suppress_ctf()

            # MSI
            devices = None
            if p.get("msi_enabled"):
                devices = wb.get_pci_devices()
                for dev in devices:
                    drv = (dev.get("driver_name") or "").upper()
                    if any(k in drv for k in ["USB", "NET", "AUDIO", "HDA", "RTKV"]):
                        reg_path = (f"SYSTEM\\CurrentControlSet\\Enum\\{dev['device_id']}\\"
                                    f"Device Parameters\\Interrupt Management\\MessageSignaledInterruptProperties")
                        record_change("msi", reg_path, "MSISupported", 0, 1,
                                      device_id=dev["device_id"], profile_name=p["name"])
                        wb.enable_msi(dev["device_id"])

            # Affinity
            if p.get("affinity_usb_core"):
                if not devices:
                    devices = wb.get_pci_devices()
                mask = 1 << int(p["affinity_usb_core"])
                for dev in devices:
                    drv = (dev.get("driver_name") or "").upper()
                    if "USB" in drv:
                        reg_path = (f"SYSTEM\\CurrentControlSet\\Enum\\{dev['device_id']}\\"
                                    f"Device Parameters\\Interrupt Management\\Affinity Policy")
                        record_change("affinity", reg_path, "DevicePolicy", 0, 4,
                                      device_id=dev["device_id"], profile_name=p["name"])
                        wb.set_interrupt_affinity(dev["device_id"], mask)

            self.after(0, lambda: self._status_lbl.configure(
                text=f"Profile '{p['name']}' applied ✓", text_color=C.SUCCESS))
        except Exception as e:
            self.after(0, lambda: self._status_lbl.configure(text=str(e), text_color=C.DANGER))

    def _delete(self, pid):
        try:
            from db import delete_profile
            delete_profile(pid)
            self._refresh()
        except Exception as e:
            self._status_lbl.configure(text=f"Error: {e}", text_color=C.DANGER)

    def _show_create(self):
        # Quick modal using CTkInputDialog or custom TopLevel
        dialog = ctk.CTkToplevel(self)
        dialog.title("New Profile")
        dialog.geometry("400x500")
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

        # Toggles
        msi_var = ctk.IntVar(value=0)
        ctk.CTkSwitch(dialog, text="Enable all MSI", variable=msi_var,
                      progress_color=C.PRIMARY).pack(padx=20, pady=(20, 10), anchor="w")

        ctf_var = ctk.IntVar(value=0)
        ctk.CTkSwitch(dialog, text="Suppress CTF/TSF", variable=ctf_var,
                      progress_color=C.PRIMARY).pack(padx=20, pady=10, anchor="w")

        timer_var = ctk.IntVar(value=0)
        ctk.CTkSwitch(dialog, text="Force 0.5ms Timer Resolution", variable=timer_var,
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
