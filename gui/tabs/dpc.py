"""DPC Monitor tab — driver latency analysis."""
import threading
import customtkinter as ctk

from gui.theme import C, FONT_FAMILY, heading, card_frame, primary_button, \
    muted_label, label, severity_color


class DpcTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C.BG)
        self._scanning = False
        self._build()

    def _build(self):
        heading(self, "DPC Latency Monitor").pack(padx=24, pady=(24, 4), anchor="w")
        muted_label(self, "Identify drivers causing system stutter and input lag"
                    ).pack(padx=24, pady=(0, 18), anchor="w")

        # ── Controls ──
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(padx=24, fill="x", pady=(0, 16))

        label(ctrl, "Duration:").pack(side="left", padx=(0, 8))
        self._duration = ctk.CTkComboBox(ctrl, values=["5", "10", "20", "30"],
                                         width=80, fg_color=C.SURFACE_HI,
                                         border_color=C.BORDER, button_color=C.PRIMARY,
                                         button_hover_color=C.PRIMARY_HVR)
        self._duration.set("10")
        self._duration.pack(side="left", padx=(0, 16))

        self._btn = primary_button(ctrl, "▶  Start Live Scan", self._toggle_scan, width=160)
        self._btn.pack(side="left")

        self._status_lbl = ctk.CTkLabel(ctrl, text="",
                                        font=(FONT_FAMILY, 13), text_color=C.MUTED)
        self._status_lbl.pack(side="left", padx=16)

        # ── Results Table ──
        table_hdr = ctk.CTkFrame(self, fg_color=C.SURFACE_HI, height=35)
        table_hdr.pack(padx=24, fill="x")
        table_hdr.pack_propagate(False)

        label(table_hdr, "DRIVER / COMPONENT", 11, bold=True).place(relx=0.02, rely=0.5, anchor="w")
        label(table_hdr, "AVG (µs)", 11, bold=True).place(relx=0.50, rely=0.5, anchor="w")
        label(table_hdr, "MAX (µs)", 11, bold=True).place(relx=0.65, rely=0.5, anchor="w")
        label(table_hdr, "FREQ", 11, bold=True).place(relx=0.80, rely=0.5, anchor="w")
        label(table_hdr, "STATUS", 11, bold=True).place(relx=0.92, rely=0.5, anchor="w")

        self._scroll = ctk.CTkScrollableFrame(self, fg_color=C.BG,
                                              scrollbar_button_color=C.BORDER)
        self._scroll.pack(padx=24, pady=(0, 24), fill="both", expand=True)

        self._refresh_list([])

    def _toggle_scan(self):
        if self._scanning:
            return

        self._scanning = True
        self._btn.configure(state="disabled", text="⌛ Scanning...")
        self._status_lbl.configure(text="Collecting trace data via WPR...", text_color=C.WARNING)

        dur = int(self._duration.get())
        threading.Thread(target=self._scan_worker, args=(dur,), daemon=True).start()

    def _scan_worker(self, duration):
        try:
            from bridge.windows_bridge import collect_dpc_data
            from db import save_dpc_samples, load_settings
            
            # (OPT 6) Read thresholds from settings
            s = load_settings()
            crit = s.get("alert_threshold_us", 500)
            
            # (BUG 5) This survives navigation because self is persistent
            results = collect_dpc_data(
                duration_seconds=duration,
                critical_threshold_us=crit,
                warning_threshold_us=crit // 4
            )
            
            if results:
                save_dpc_samples(results)
                # (OPT 1) Notify other components
                self.after(0, lambda: self.winfo_toplevel().publish("dpc_data_updated", results))

            self.after(0, lambda: self._on_scan_complete(results))
        except Exception as e:
            self.after(0, lambda: self._on_scan_complete([], str(e)))

    def _on_scan_complete(self, results, error=None):
        self._scanning = False
        self._btn.configure(state="normal", text="▶  Start Live Scan")
        if error:
            self._status_lbl.configure(text=f"Error: {error}", text_color=C.DANGER)
        else:
            self._status_lbl.configure(text=f"Scan complete ✓ ({len(results)} drivers)",
                                        text_color=C.SUCCESS)
            self._refresh_list(results)

    def _refresh_list(self, results):
        for w in self._scroll.winfo_children():
            w.destroy()

        if not results:
            ctk.CTkLabel(self._scroll, text="No scan data available.",
                         font=(FONT_FAMILY, 14), text_color=C.MUTED
                         ).pack(pady=40)
            return

        for r in results:
            row = ctk.CTkFrame(self._scroll, fg_color="transparent")
            row.pack(fill="x", pady=1)

            ctk.CTkLabel(row, text=r['driver_name'], font=(FONT_FAMILY, 13),
                         text_color=C.TEXT, anchor="w").place(relx=0.02, rely=0.5, anchor="w")
            ctk.CTkLabel(row, text=str(r['avg_us']), font=(FONT_FAMILY, 13),
                         text_color=C.TEXT).place(relx=0.50, rely=0.5, anchor="w")
            ctk.CTkLabel(row, text=str(r['max_us']), font=(FONT_FAMILY, 13, "bold"),
                         text_color=C.TEXT).place(relx=0.65, rely=0.5, anchor="w")
            ctk.CTkLabel(row, text=str(r['frequency']), font=(FONT_FAMILY, 13),
                         text_color=C.MUTED).place(relx=0.80, rely=0.5, anchor="w")
            
            # Status tag
            tag_color = severity_color(r['severity'])
            tag = ctk.CTkFrame(row, fg_color=tag_color, width=60, height=20, corner_radius=4)
            tag.place(relx=0.92, rely=0.5, anchor="w")
            tag.pack_propagate(False)
            ctk.CTkLabel(tag, text=r['severity'].upper(), font=(FONT_FAMILY, 9, "bold"),
                         text_color=C.BG).pack(expand=True)
            
            # Separator
            ctk.CTkFrame(self._scroll, fg_color=C.BORDER, height=1).pack(fill="x", padx=4)
