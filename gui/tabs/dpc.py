"""DPC Monitor tab — start/stop DPC collection, driver table, recommendations."""
import threading
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

from gui.theme import C, FONT_FAMILY, heading, card_frame, primary_button, \
    secondary_button, muted_label, severity_color


class DpcTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=C.BG)
        self._running = False
        self._build()

    def _build(self):
        heading(self, "DPC Monitor").pack(padx=24, pady=(24, 4), anchor="w")
        muted_label(self, "Measure Deferred Procedure Call latency per driver"
                    ).pack(padx=24, pady=(0, 14), anchor="w")

        # ── Controls ──
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(padx=24, fill="x")
        self._start_btn = primary_button(ctrl, "▶  Start Scan", self._on_start, width=160)
        self._start_btn.pack(side="left", padx=(0, 8))
        self._stop_btn = secondary_button(ctrl, "■  Stop", self._on_stop, width=100)
        self._stop_btn.pack(side="left", padx=(0, 8))
        self._stop_btn.configure(state="disabled")

        self._status_lbl = ctk.CTkLabel(ctrl, text="Idle",
                                        font=(FONT_FAMILY, 13), text_color=C.MUTED)
        self._status_lbl.pack(side="left", padx=16)

        # Duration control
        ctk.CTkLabel(ctrl, text="Duration (s):", font=(FONT_FAMILY, 12),
                     text_color=C.MUTED).pack(side="right", padx=(0, 4))
        self._dur_var = ctk.StringVar(value="10")
        dur_entry = ctk.CTkEntry(ctrl, textvariable=self._dur_var, width=60,
                                 fg_color=C.SURFACE, border_color=C.BORDER,
                                 text_color=C.TEXT, corner_radius=6)
        dur_entry.pack(side="right")

        # ── Results table (using ttk.Treeview for better table support) ──
        table_card = card_frame(self)
        table_card.pack(padx=24, pady=(16, 8), fill="both", expand=True)

        ctk.CTkLabel(table_card, text="DRIVER LATENCY",
                     font=(FONT_FAMILY, 11, "bold"),
                     text_color=C.MUTED).pack(padx=16, pady=(12, 4), anchor="w")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("DPC.Treeview",
                        background=C.SURFACE, foreground=C.TEXT,
                        fieldbackground=C.SURFACE, borderwidth=0,
                        font=(FONT_FAMILY, 12), rowheight=28)
        style.configure("DPC.Treeview.Heading",
                        background=C.SURFACE_HI, foreground=C.MUTED,
                        font=(FONT_FAMILY, 11, "bold"), borderwidth=0)
        style.map("DPC.Treeview", background=[("selected", C.PRIMARY)])

        cols = ("driver", "avg", "max", "std", "freq", "severity")
        tree_frame = ctk.CTkFrame(table_card, fg_color=C.SURFACE)
        tree_frame.pack(padx=12, pady=(4, 12), fill="both", expand=True)

        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                  style="DPC.Treeview", height=12)
        self._tree.heading("driver", text="Driver")
        self._tree.heading("avg", text="Avg (µs)")
        self._tree.heading("max", text="Max (µs)")
        self._tree.heading("std", text="Std Dev")
        self._tree.heading("freq", text="Count")
        self._tree.heading("severity", text="Status")

        self._tree.column("driver", width=220, minwidth=120)
        self._tree.column("avg", width=90, anchor="center")
        self._tree.column("max", width=90, anchor="center")
        self._tree.column("std", width=90, anchor="center")
        self._tree.column("freq", width=70, anchor="center")
        self._tree.column("severity", width=90, anchor="center")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical",
                                  command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # ── Recommendations ──
        rec_card = card_frame(self)
        rec_card.pack(padx=24, pady=(0, 16), fill="x")
        ctk.CTkLabel(rec_card, text="RECOMMENDATIONS",
                     font=(FONT_FAMILY, 11, "bold"),
                     text_color=C.MUTED).pack(padx=16, pady=(12, 4), anchor="w")
        self._rec_frame = ctk.CTkFrame(rec_card, fg_color="transparent")
        self._rec_frame.pack(padx=16, pady=(0, 12), fill="x")
        ctk.CTkLabel(self._rec_frame, text="Run a scan to see recommendations",
                     font=(FONT_FAMILY, 12), text_color=C.MUTED
                     ).pack(anchor="w")

    def _on_start(self):
        if self._running:
            return
        self._running = True
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._status_lbl.configure(text="Collecting…", text_color=C.WARNING)

        try:
            duration = int(self._dur_var.get())
        except ValueError:
            duration = 10

        threading.Thread(target=self._worker, args=(duration,), daemon=True).start()

    def _on_stop(self):
        self._running = False
        self._stop_btn.configure(state="disabled")
        self._status_lbl.configure(text="Stopping…", text_color=C.MUTED)

    def _worker(self, duration):
        try:
            from bridge.windows_bridge import collect_dpc_data
            results = collect_dpc_data(duration)
            if results:
                from db import save_dpc_samples
                save_dpc_samples(results)
            self.after(0, lambda: self._show_results(results))
        except Exception as e:
            self.after(0, lambda: self._status_lbl.configure(
                text=f"Error: {e}", text_color=C.DANGER))
        finally:
            self._running = False
            self.after(0, lambda: self._finish())

    def _finish(self):
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._status_lbl.configure(text="Complete", text_color=C.SUCCESS)

    def _show_results(self, results):
        for item in self._tree.get_children():
            self._tree.delete(item)

        for r in results:
            sev = r["severity"].upper()
            self._tree.insert("", "end", values=(
                r["driver_name"], r["avg_us"], r["max_us"],
                r["std_dev_us"], r["frequency"], sev
            ))

        # Update recommendations
        for w in self._rec_frame.winfo_children():
            w.destroy()

        recs = [r for r in results if r["severity"] in ("critical", "warning")]
        if not recs:
            ctk.CTkLabel(self._rec_frame, text="✓ All drivers within normal latency range",
                         font=(FONT_FAMILY, 13), text_color=C.SUCCESS).pack(anchor="w")
        else:
            for r in recs[:5]:
                color = severity_color(r["severity"])
                msg = (f"{'⚠' if r['severity']=='warning' else '✖'} "
                       f"{r['driver_name']} — max {r['max_us']}µs. "
                       f"Enable MSI mode and pin to dedicated core.")
                ctk.CTkLabel(self._rec_frame, text=msg,
                             font=(FONT_FAMILY, 12), text_color=color,
                             wraplength=700, anchor="w").pack(anchor="w", pady=2)
