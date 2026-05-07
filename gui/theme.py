"""OP TOOL — Theme constants and widget factories for CustomTkinter."""
import customtkinter as ctk


# ─── Color Palette (matches existing web UI) ────────
class C:
    BG          = "#0d0a12"
    SURFACE     = "#12101a"
    SURFACE_HI  = "#1a1724"
    PRIMARY     = "#7c3aed"
    PRIMARY_HVR = "#6d28d9"
    ACCENT      = "#a855f7"
    TEXT        = "#f0eeff"
    MUTED       = "#7c748a"
    SUCCESS     = "#22c55e"
    WARNING     = "#f59e0b"
    DANGER      = "#ef4444"
    BORDER      = "#2a2535"


FONT_FAMILY = "Segoe UI"

# ─── Reusable widget builders ───────────────────────

def heading(parent, text, size=18):
    return ctk.CTkLabel(parent, text=text, font=(FONT_FAMILY, size, "bold"),
                        text_color=C.TEXT, anchor="w")


def label(parent, text, size=13, color=None, bold=False):
    weight = "bold" if bold else "normal"
    return ctk.CTkLabel(parent, text=text,
                        font=(FONT_FAMILY, size, weight),
                        text_color=color or C.TEXT, anchor="w")


def muted_label(parent, text, size=12):
    return label(parent, text, size=size, color=C.MUTED)


def card_frame(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=C.SURFACE, corner_radius=8,
                        border_width=1, border_color=C.BORDER, **kw)


def primary_button(parent, text, command=None, width=140):
    return ctk.CTkButton(parent, text=text, command=command, width=width,
                         fg_color=C.PRIMARY, hover_color=C.PRIMARY_HVR,
                         text_color=C.TEXT, corner_radius=6,
                         font=(FONT_FAMILY, 13, "bold"))


def danger_button(parent, text, command=None, width=140):
    return ctk.CTkButton(parent, text=text, command=command, width=width,
                         fg_color="transparent", hover_color=C.DANGER,
                         text_color=C.DANGER, border_width=1,
                         border_color=C.DANGER, corner_radius=6,
                         font=(FONT_FAMILY, 13, "bold"))


def secondary_button(parent, text, command=None, width=140):
    return ctk.CTkButton(parent, text=text, command=command, width=width,
                         fg_color=C.SURFACE, hover_color=C.SURFACE_HI,
                         text_color=C.TEXT, border_width=1,
                         border_color=C.BORDER, corner_radius=6,
                         font=(FONT_FAMILY, 13))


def entry_field(parent, placeholder="", width=250):
    return ctk.CTkEntry(parent, placeholder_text=placeholder, width=width,
                        fg_color=C.SURFACE, border_color=C.BORDER,
                        text_color=C.TEXT, corner_radius=6,
                        font=(FONT_FAMILY, 13))


def severity_color(severity):
    return {
        'critical': C.DANGER,
        'warning': C.WARNING,
        'ok': C.SUCCESS,
    }.get(severity, C.MUTED)


def stat_card(parent, label_text, value_text, unit=""):
    """Create a stat card widget; returns (frame, value_label) for live updates."""
    frame = card_frame(parent)
    lbl = ctk.CTkLabel(frame, text=label_text.upper(),
                       font=(FONT_FAMILY, 11, "bold"),
                       text_color=C.MUTED, anchor="w")
    lbl.pack(padx=16, pady=(14, 2), anchor="w")
    val = ctk.CTkLabel(frame, text=f"{value_text}{unit}",
                       font=(FONT_FAMILY, 26, "bold"),
                       text_color=C.TEXT, anchor="w")
    val.pack(padx=16, pady=(0, 14), anchor="w")
    return frame, val
