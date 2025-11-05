from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import tkinter as tk
from tkinter import ttk

THEME_FILE = Path(__file__).resolve().parents[2] / "assets" / "themes.json"


_FALLBACK_THEMES: Dict[str, Any] = {
    "functional": {
        "severity": {
            "crit": "#FF3B30",
            "warn": "#FF9500",
            "info": "#1F7AE0",
            "ok": "#16B365",
        },
        "modality": {
            "rf": "#007AFF",
            "thermal": "#FF3B30",
            "eo": "#34C759",
            "ir": "#FF9500",
            "acoustic": "#8E8E93",
        },
    },
    "skins": {
        "nostromo": {
            "bg": "#0F1115",
            "panel": "#141922",
            "text": "#E8EDF3",
            "subtext": "#8B94A7",
            "accent": "#5B2E90",
            "border": "#1E2530",
            "hover": "#18202B",
            "decor": {"grid": True, "scanlines": 0.03, "glow": 0},
        },
        "shinjuku": {
            "bg": "#0E0E12",
            "panel": "#13131A",
            "text": "#E5E7EB",
            "subtext": "#9AA2B1",
            "accent": "#00E6D1",
            "border": "#1A1A22",
            "hover": "#15151E",
            "decor": {"grid": False, "scanlines": 0, "glow": 0.08},
        },
        "section9": {
            "bg": "#0A0F14",
            "panel": "#0D1218",
            "text": "#DCE7F5",
            "subtext": "#9AB6D1",
            "accent": "#7FB7FF",
            "border": "#0F1620",
            "hover": "#0C141C",
            "decor": {"grid": True, "scanlines": 0, "glow": 0.04},
        },
    },
}


@lru_cache(maxsize=1)
def _load_theme_payload() -> Dict[str, Any]:
    try:
        raw = THEME_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict) or "skins" not in data:
            raise ValueError("invalid theme payload")
        return data
    except (OSError, ValueError, json.JSONDecodeError):
        return _FALLBACK_THEMES.copy()


def skin_names() -> list[str]:
    data = _load_theme_payload()
    return list(data["skins"].keys())


def _get_skin(name: str) -> Dict[str, Any]:
    data = _load_theme_payload()["skins"]
    if name not in data:
        return data.get("nostromo", next(iter(data.values())))
    return data[name]


def decor_defaults(name: str) -> Dict[str, Any]:
    skin = _get_skin(name)
    decor = skin.get("decor") or {}
    scanlines_val = decor.get("scanlines") if isinstance(decor.get("scanlines"), (int, float)) else (0.0 if not decor.get("scanlines") else 0.06)
    glow_val = decor.get("glow") if isinstance(decor.get("glow"), (int, float)) else (0.0 if not decor.get("glow") else 0.08)
    return {
        "grid": bool(decor.get("grid")),
        "scanlines": bool(scanlines_val),
        "glow": bool(glow_val),
        "scanlines_value": float(scanlines_val),
        "glow_value": float(glow_val),
        "grid_spacing": skin.get("grid_spacing", 120),
        "scan_step": skin.get("scan_step", 4),
    }


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip('#')
    if len(value) == 3:
        value = ''.join(ch * 2 for ch in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _lighten(color: str, factor: float) -> str:
    r, g, b = _hex_to_rgb(color)
    factor = _clamp(factor)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return _rgb_to_hex(r, g, b)


def _blend(color_a: str, color_b: str, ratio: float) -> str:
    ratio = _clamp(ratio)
    r1, g1, b1 = _hex_to_rgb(color_a)
    r2, g2, b2 = _hex_to_rgb(color_b)
    r = int(r1 * (1 - ratio) + r2 * ratio)
    g = int(g1 * (1 - ratio) + g2 * ratio)
    b = int(b1 * (1 - ratio) + b2 * ratio)
    return _rgb_to_hex(r, g, b)


def apply_skin(root: tk.Misc, style: ttk.Style, name: str, *, contrast: float = 0.0) -> Dict[str, Any]:
    skin = _get_skin(name)
    bg = skin["bg"]
    panel = skin["panel"]
    accent = skin["accent"]
    border = skin["border"]
    hover = skin["hover"]
    text = _lighten(skin["text"], _clamp(contrast))
    subtext = _lighten(skin["subtext"], _clamp(contrast + 0.08))
    muted = _lighten(skin["subtext"], _clamp(contrast + 0.16))
    surface = _blend(bg, panel, 0.4)

    try:
        root.tk_setPalette(background=bg, foreground=text, activeBackground=hover, activeForeground=text)
    except tk.TclError:
        pass

    style.configure("Root.TFrame", background=bg)
    style.configure("TFrame", background=bg)
    style.configure("Surface.TFrame", background=surface)
    style.configure("Card.TFrame", background=panel, bordercolor=border, relief="solid", borderwidth=1)

    style.configure("TLabel", background=bg, foreground=text)
    style.configure("CardTitle.TLabel", background=panel, foreground=text)
    style.configure("Muted.TLabel", background=bg, foreground=muted)
    style.configure("Value.TLabel", background=panel, foreground=text)

    style.configure("Treeview", background=panel, fieldbackground=panel, foreground=text, rowheight=26, bordercolor=border)
    style.configure("Treeview.Heading", background=panel, foreground=text)
    style.map("Treeview", background=[("selected", accent)], foreground=[("selected", bg)])

    style.configure("Notebook", background=bg)
    style.configure("Notebook.Tab", background=panel, foreground=muted, padding=(16, 8))
    style.map("Notebook.Tab", background=[("selected", panel), ("active", hover)], foreground=[("selected", text), ("!selected", muted)])

    style.configure("TButton", background=panel, foreground=text, bordercolor=border, padding=(10, 6))
    style.map("TButton", background=[("active", hover), ("pressed", hover)], foreground=[("disabled", muted)])

    style.configure("TCheckbutton", background=panel, foreground=text)
    style.map("TCheckbutton", background=[("active", hover)], foreground=[("disabled", muted)])

    style.configure("TCombobox", fieldbackground=panel, background=panel, foreground=text, bordercolor=border)

    root.configure(bg=bg)

    return {
        "bg": bg,
        "panel": panel,
        "text": text,
        "subtext": subtext,
        "accent": accent,
        "border": border,
        "hover": hover,
        "decor": skin.get("decor", {}),
    }
