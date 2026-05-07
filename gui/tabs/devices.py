"""Devices / MSI tab — PCI device list with MSI enable/disable toggles."""
import threading
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

from gui.theme import C, FONT_FAMILY, heading, card_frame, primary_button, \
    secondary_button, danger_button, muted_label


class DevicesTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C.BG)
        self._devices = []
        self._build()

    def _build(self):
        heading(self, "Devices / MSI Mode").pack(padx=24, pady=(24, 4), anchor="w")
        muted_label(self, "Enable Message Signaled Interrupts for PCI devices"
                    ).pack(padx=24, pady=(0, 14), anchor="w")

        # ── Controls ──
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(padx=24, fill="x")
        primary_button(ctrl, "🔄  Refresh Devices", self._refresh_devices, width=180
                       ).pack(side="left", padx=(0, 8))
        primary_button(ctrl, "⚡  Enable All MSI", self._enable_all, width=160
                       ).pack(side="left", padx=(0, 8))

        self._status_lbl = ctk.CTkLabel(ctrl, text="",
                                        font=(FONT_FAMILY, 13), text_color=C.MUTED)
        self._status_lbl.pack(side="left", padx=16)

        # ── Device table ──
        table_card = card_frame(self)
        table_card.pack(padx=24, pady=(16, 16), fill="both", expand=True)

        ctk.CTkLabel(table_card, text="PCI DEVICES",
                     font=(FONT_FAMILY, 11, "bold"),
                     text_color=C.MUTED).pack(padx=16, pady=(12, 4), anchor="w")

        style = ttk.Style()
        style.configure("DEV.Treeview",
                        background=C.SURFACE, foreground=C.TEXT,
                        fieldbackground=C.SURFACE, borderwidth=0,
                        font=(FONT_FAMILY, 12), rowheight=28)
        style.configure("DEV.Treeview.Heading",
                        background=C.SURFACE_HI, foreground=C.MUTED,
                        font=(FONT_FAMILY, 11, "bold"), borderwidth=0)
        style.map("DEV.Treeview", background=[("selected", C.PRIMARY)])

        cols = ("name", "driver", "device_id", "msi")
        tree_frame = ctk.CTkFrame(table_card, fg_color=C.SURFACE)
        tree_frame.pack(padx=12, pady=(4, 8), fill="both", expand=True)

        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                  style="DEV.Treeview", height=14)
        self._tree.heading("name", text="Device")
        self._tree.heading("driver", text="Driver")
        self._tree.heading("device_id", text="Instance ID")
        self._tree.heading("msi", text="MSI")
        self._tree.column("name", width=280, minwidth=150)
        self._tree.column("driver", width=100)
        self._tree.column("device_id", width=260, minwidth=100)
        self._tree.column("msi", width=80, anchor="center")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical",
                                  command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # ── Per-device actions ──
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(padx=24, fill="x", pady=(0, 16))
        primary_button(action_frame, "Enable MSI (selected)", self._enable_selected,
                       width=200).pack(side="left", padx=(0, 8))
        danger_button(action_frame, "Disable MSI (selected)", self._disable_selected,
                      width=200).pack(side="left")

    def _refresh_devices(self):
        self._status_lbl.configure(text="Scanning…", text_color=C.WARNING)
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            import winreg
            from bridge.windows_bridge import get_pci_devices, reg_read
            devices = get_pci_devices()
            for d in devices:
                reg_path = (
                    f"SYSTEM\\CurrentControlSet\\Enum\\{d['device_id']}\\"
                    f"Device Parameters\\Interrupt Management\\"
                    f"MessageSignaledInterruptProperties"
                )
                msi_val, _ = reg_read(winreg.HKEY_LOCAL_MACHINE, reg_path, "MSISupported")
                d["msi_enabled"] = msi_val == 1 if msi_val is not None else False
            self._devices = devices
            self.after(0, lambda: self._populate_tree(devices))
        except Exception as e:
            self.after(0, lambda: self._status_lbl.configure(
                text=f"Error: {e}", text_color=C.DANGER))

    def _populate_tree(self, devices):
        for item in self._tree.get_children():
            self._tree.delete(item)
        for d in devices:
            msi_text = "✓ ON" if d.get("msi_enabled") else "✗ OFF"
            self._tree.insert("", "end", values=(
                d["friendly_name"], d.get("driver_name", ""),
                d["device_id"], msi_text
            ))
        self._status_lbl.configure(
            text=f"{len(devices)} devices found", text_color=C.SUCCESS)

    def _get_selected_device(self):
        sel = self._tree.selection()
        if not sel:
            self._status_lbl.configure(text="Select a device first", text_color=C.WARNING)
            return None
        idx = self._tree.index(sel[0])
        if idx < len(self._devices):
            return self._devices[idx]
        return None

    def _enable_selected(self):
        dev = self._get_selected_device()
        if not dev:
            return
        self._status_lbl.configure(text="Enabling MSI…", text_color=C.WARNING)
        threading.Thread(target=self._enable_worker, args=(dev,), daemon=True).start()

    def _enable_worker(self, dev):
        try:
            from bridge.windows_bridge import create_restore_point, enable_msi
            from db import record_change, save_restore_point
            rp = create_restore_point(f"OP TOOL: MSI enable {dev['device_id'][:30]}")
            if not rp["success"]:
                self.after(0, lambda: self._status_lbl.configure(
                    text=f"Restore point failed: {rp.get('error', '')}", text_color=C.DANGER))
                return
            save_restore_point(rp["sequence_number"], f"MSI enable {dev['device_id'][:50]}")
            reg_path = (
                f"SYSTEM\\CurrentControlSet\\Enum\\{dev['device_id']}\\"
                f"Device Parameters\\Interrupt Management\\"
                f"MessageSignaledInterruptProperties"
            )
            record_change("msi", reg_path, "MSISupported", 0, 1, device_id=dev['device_id'])
            result = enable_msi(dev["device_id"])
            msg = "MSI enabled ✓" if result["success"] else f"Failed: {result.get('error','')}"
            color = C.SUCCESS if result["success"] else C.DANGER
            self.after(0, lambda: self._status_lbl.configure(text=msg, text_color=color))
            self.after(500, self._refresh_devices)
        except Exception as e:
            self.after(0, lambda: self._status_lbl.configure(
                text=str(e), text_color=C.DANGER))

    def _disable_selected(self):
        dev = self._get_selected_device()
        if not dev:
            return
        self._status_lbl.configure(text="Disabling MSI…", text_color=C.WARNING)
        threading.Thread(target=self._disable_worker, args=(dev,), daemon=True).start()

    def _disable_worker(self, dev):
        try:
            from bridge.windows_bridge import disable_msi
            from db import get_active_changes, mark_restored
            changes = get_active_changes()
            entry = next((c for c in changes if c.get('device_id') == dev['device_id']
                          and c['change_type'] == 'msi'), None)
            orig = int(entry['original_value']) if entry else 0
            result = disable_msi(dev["device_id"], orig)
            if result["success"] and entry:
                mark_restored(entry['id'])
            msg = "MSI disabled ✓" if result["success"] else "Failed"
            color = C.SUCCESS if result["success"] else C.DANGER
            self.after(0, lambda: self._status_lbl.configure(text=msg, text_color=color))
            self.after(500, self._refresh_devices)
        except Exception as e:
            self.after(0, lambda: self._status_lbl.configure(
                text=str(e), text_color=C.DANGER))

    def _enable_all(self):
        self._status_lbl.configure(text="Enabling MSI on all…", text_color=C.WARNING)
        threading.Thread(target=self._enable_all_worker, daemon=True).start()

    def _enable_all_worker(self):
        try:
            from bridge.windows_bridge import create_restore_point, enable_msi, get_pci_devices
            from db import record_change, save_restore_point
            rp = create_restore_point("OP TOOL: MSI enable all")
            if not rp["success"]:
                self.after(0, lambda: self._status_lbl.configure(
                    text="Restore point failed", text_color=C.DANGER))
                return
            save_restore_point(rp["sequence_number"], "MSI enable all")
            devices = get_pci_devices()
            count = 0
            for dev in devices:
                drv = (dev.get("driver_name") or "").upper()
                if any(k in drv for k in ["USB", "NET", "AUDIO", "HDA", "RTKV"]):
                    reg_path = (
                        f"SYSTEM\\CurrentControlSet\\Enum\\{dev['device_id']}\\"
                        f"Device Parameters\\Interrupt Management\\"
                        f"MessageSignaledInterruptProperties"
                    )
                    record_change("msi", reg_path, "MSISupported", 0, 1,
                                  device_id=dev["device_id"])
                    enable_msi(dev["device_id"])
                    count += 1
            self.after(0, lambda: self._status_lbl.configure(
                text=f"MSI enabled on {count} devices ✓", text_color=C.SUCCESS))
            self.after(500, self._refresh_devices)
        except Exception as e:
            self.after(0, lambda: self._status_lbl.configure(
                text=str(e), text_color=C.DANGER))
