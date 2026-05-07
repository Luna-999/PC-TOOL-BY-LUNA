"""Affinity tab — CPU core map with USB/NIC/GPU interrupt pinning."""
import threading
import customtkinter as ctk
import psutil

from gui.theme import C, FONT_FAMILY, heading, card_frame, primary_button, \
    danger_button, muted_label


class AffinityTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C.BG)
        self._core_count = psutil.cpu_count(logical=True) or 8
        self._build()

    def _build(self):
        heading(self, "Interrupt Affinity").pack(padx=24, pady=(24, 4), anchor="w")
        muted_label(self, "Pin device interrupts to specific CPU cores"
                    ).pack(padx=24, pady=(0, 14), anchor="w")

        # ── Core map display ──
        core_card = card_frame(self)
        core_card.pack(padx=24, pady=(0, 12), fill="x")
        ctk.CTkLabel(core_card, text="CPU CORE MAP",
                     font=(FONT_FAMILY, 11, "bold"),
                     text_color=C.MUTED).pack(padx=16, pady=(12, 8), anchor="w")

        core_grid = ctk.CTkFrame(core_card, fg_color="transparent")
        core_grid.pack(padx=16, pady=(0, 16), fill="x")

        cols = min(self._core_count, 8)
        for i in range(cols):
            core_grid.columnconfigure(i, weight=1, uniform="core")

        self._core_labels = []
        for i in range(self._core_count):
            col = i % cols
            row = i // cols
            cell = ctk.CTkFrame(core_grid, fg_color=C.SURFACE_HI,
                                corner_radius=6, border_width=1,
                                border_color=C.BORDER, height=60)
            cell.grid(row=row, column=col, padx=3, pady=3, sticky="nsew")
            cell.grid_propagate(False)
            num = ctk.CTkLabel(cell, text=str(i), font=(FONT_FAMILY, 16, "bold"),
                               text_color=C.TEXT)
            num.pack(pady=(8, 0))
            role = ctk.CTkLabel(cell, text="—", font=(FONT_FAMILY, 9),
                                text_color=C.MUTED)
            role.pack()
            self._core_labels.append((cell, num, role))

        # ── Assignment controls ──
        assign_card = card_frame(self)
        assign_card.pack(padx=24, pady=(0, 12), fill="x")
        ctk.CTkLabel(assign_card, text="PIN DEVICES TO CORES",
                     font=(FONT_FAMILY, 11, "bold"),
                     text_color=C.MUTED).pack(padx=16, pady=(12, 8), anchor="w")

        form = ctk.CTkFrame(assign_card, fg_color="transparent")
        form.pack(padx=16, pady=(0, 16), fill="x")

        core_values = [str(i) for i in range(self._core_count)]

        # USB core
        row1 = ctk.CTkFrame(form, fg_color="transparent")
        row1.pack(fill="x", pady=4)
        ctk.CTkLabel(row1, text="USB Controller Core:", width=180,
                     font=(FONT_FAMILY, 13), text_color=C.TEXT,
                     anchor="w").pack(side="left")
        self._usb_var = ctk.StringVar(value="")
        ctk.CTkComboBox(row1, values=[""] + core_values, variable=self._usb_var,
                        width=100, fg_color=C.SURFACE, border_color=C.BORDER,
                        button_color=C.PRIMARY, dropdown_fg_color=C.SURFACE_HI,
                        text_color=C.TEXT).pack(side="left")

        # NIC core
        row2 = ctk.CTkFrame(form, fg_color="transparent")
        row2.pack(fill="x", pady=4)
        ctk.CTkLabel(row2, text="Network Adapter Core:", width=180,
                     font=(FONT_FAMILY, 13), text_color=C.TEXT,
                     anchor="w").pack(side="left")
        self._nic_var = ctk.StringVar(value="")
        ctk.CTkComboBox(row2, values=[""] + core_values, variable=self._nic_var,
                        width=100, fg_color=C.SURFACE, border_color=C.BORDER,
                        button_color=C.PRIMARY, dropdown_fg_color=C.SURFACE_HI,
                        text_color=C.TEXT).pack(side="left")

        # GPU core
        row3 = ctk.CTkFrame(form, fg_color="transparent")
        row3.pack(fill="x", pady=4)
        ctk.CTkLabel(row3, text="GPU Core:", width=180,
                     font=(FONT_FAMILY, 13), text_color=C.TEXT,
                     anchor="w").pack(side="left")
        self._gpu_var = ctk.StringVar(value="")
        ctk.CTkComboBox(row3, values=[""] + core_values, variable=self._gpu_var,
                        width=100, fg_color=C.SURFACE, border_color=C.BORDER,
                        button_color=C.PRIMARY, dropdown_fg_color=C.SURFACE_HI,
                        text_color=C.TEXT).pack(side="left")

        # Buttons
        btn_row = ctk.CTkFrame(assign_card, fg_color="transparent")
        btn_row.pack(padx=16, pady=(0, 16), fill="x")
        primary_button(btn_row, "Apply Affinity", self._apply, width=160
                       ).pack(side="left", padx=(0, 8))
        danger_button(btn_row, "Restore Default", self._restore, width=160
                      ).pack(side="left")
        self._status_lbl = ctk.CTkLabel(btn_row, text="",
                                        font=(FONT_FAMILY, 13), text_color=C.MUTED)
        self._status_lbl.pack(side="left", padx=16)

    def _apply(self):
        usb = self._usb_var.get().strip()
        nic = self._nic_var.get().strip()
        gpu = self._gpu_var.get().strip()
        if not usb and not nic and not gpu:
            self._status_lbl.configure(text="Select at least one core", text_color=C.WARNING)
            return
        self._status_lbl.configure(text="Applying…", text_color=C.WARNING)
        threading.Thread(target=self._apply_worker,
                         args=(usb or None, nic or None, gpu or None),
                         daemon=True).start()

    def _apply_worker(self, usb_core, nic_core, gpu_core):
        try:
            from bridge.windows_bridge import (create_restore_point,
                                               set_interrupt_affinity, get_pci_devices)
            from db import record_change, save_restore_point
            rp = create_restore_point("OP TOOL: Affinity apply")
            if not rp["success"]:
                self.after(0, lambda: self._status_lbl.configure(
                    text="Restore point failed", text_color=C.DANGER))
                return
            save_restore_point(rp["sequence_number"], "Affinity apply")
            devices = get_pci_devices()
            count = 0

            def apply_to(keyword, core_str):
                nonlocal count
                if core_str is None:
                    return
                mask = 1 << int(core_str)
                for dev in devices:
                    drv = (dev.get("driver_name") or "").upper()
                    if keyword in drv:
                        reg_path = (
                            f"SYSTEM\\CurrentControlSet\\Enum\\{dev['device_id']}\\"
                            f"Device Parameters\\Interrupt Management\\Affinity Policy"
                        )
                        record_change("affinity", reg_path, "DevicePolicy", 0, 4,
                                      device_id=dev["device_id"])
                        set_interrupt_affinity(dev["device_id"], mask)
                        count += 1

            apply_to("USB", usb_core)
            apply_to("NET", nic_core)
            apply_to("VIDEO", gpu_core)

            self.after(0, lambda: self._status_lbl.configure(
                text=f"Applied to {count} devices ✓", text_color=C.SUCCESS))
            self.after(0, self._update_core_map)
        except Exception as e:
            self.after(0, lambda: self._status_lbl.configure(
                text=str(e), text_color=C.DANGER))

    def _restore(self):
        self._status_lbl.configure(text="Restoring…", text_color=C.WARNING)
        threading.Thread(target=self._restore_worker, daemon=True).start()

    def _restore_worker(self):
        try:
            from bridge.windows_bridge import remove_interrupt_affinity
            from db import get_active_changes, mark_restored
            entries = [c for c in get_active_changes() if c['change_type'] == 'affinity']
            for e in entries:
                if e.get('device_id'):
                    r = remove_interrupt_affinity(e['device_id'])
                    if r["success"]:
                        mark_restored(e['id'])
            self.after(0, lambda: self._status_lbl.configure(
                text="Affinity restored ✓", text_color=C.SUCCESS))
            self.after(0, self._update_core_map)
        except Exception as e:
            self.after(0, lambda: self._status_lbl.configure(
                text=str(e), text_color=C.DANGER))

    def _update_core_map(self):
        # Reset all
        for cell, num, role in self._core_labels:
            cell.configure(border_color=C.BORDER, fg_color=C.SURFACE_HI)
            role.configure(text="—")

        usb = self._usb_var.get().strip()
        nic = self._nic_var.get().strip()
        gpu = self._gpu_var.get().strip()

        assignments = {}
        if usb:
            assignments[int(usb)] = "USB"
        if nic:
            assignments[int(nic)] = assignments.get(int(nic), "") + " NIC"
        if gpu:
            assignments[int(gpu)] = assignments.get(int(gpu), "") + " GPU"

        for core_idx, role_text in assignments.items():
            if core_idx < len(self._core_labels):
                cell, num, role = self._core_labels[core_idx]
                cell.configure(border_color=C.PRIMARY, fg_color=C.SURFACE)
                role.configure(text=role_text.strip(), text_color=C.ACCENT)
