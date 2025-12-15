from __future__ import annotations

"""Simple desktop GUI for interacting with the ZMeta backend."""

import asyncio
import contextlib
import json
import webbrowser
import queue
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests
from PIL import Image, ImageDraw, ImageTk

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

from tkintermapview import TkinterMapView

from .network import AsyncLoopThread, WebSocketClient
from .state import (
    AlertStore,
    LogBuffer,
    TrackStore,
    SEVERITY_COLORS,
    modality_color,
    resolve_track_id,
    severity_color,
    severity_dot,
)

USE_CLASSIC_MARKERS = True  # Set to False to try experimental dot/ring markers


class ZMetaApp(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master)
        self.master = master
        self.master.title("ZMeta Control Panel")
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)

        self.queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.loop_thread = AsyncLoopThread()
        self.ws_client = WebSocketClient(
            self.loop_thread,
            self._ws_url,
            lambda kind, payload: self.queue.put((f"ws_{kind}", payload)),
        )

        self.base_url_var = tk.StringVar(value="http://127.0.0.1:8000")
        self.secret_var = tk.StringVar(value="")
        self.ws_status_var = tk.StringVar(value="disconnected")

        self.live_updates_var = tk.BooleanVar(value=True)
        self.live_toggle_btn: ttk.Button | None = None
        self.max_paused_messages = 2000
        self._paused_messages: deque[dict[str, Any]] = deque(maxlen=self.max_paused_messages)

        self.alert_store = AlertStore()
        self.alert_total_var = tk.StringVar(value="Alerts: 0")
        self.alert_severity_filters: dict[str, tk.BooleanVar] = {
            level: tk.BooleanVar(value=True) for level in ("crit", "warn", "info")
        }
        self.alert_age_var = tk.StringVar(value="10m")

        self.health_status_var = tk.StringVar(value="unknown")
        self.health_clients_var = tk.StringVar(value="--")
        self.health_eps_var = tk.StringVar(value="--")
        self.health_last_packet_var = tk.StringVar(value="--")
        self.health_alerts_var = tk.StringVar(value="0")
        self.health_updated_var = tk.StringVar(value="never")
        self.health_payload: dict[str, Any] | None = None
        self.health_poll_ms = 15000
        self._health_poll_job: int | None = None
        self.health_details_visible = tk.BooleanVar(value=False)
        self.health_details_frame: ttk.Frame | None = None
        self.health_details_text: ScrolledText | None = None
        self.health_toggle_btn: ttk.Button | None = None

        self.track_store = TrackStore(max_trail_points=60)
        self.map_markers: dict[str, Any] = {}
        self.map_paths: dict[str, Any] = {}
        self.show_trails_var = tk.BooleanVar(value=True)
        self._track_refresh_job: int | None = None

        self.alert_tree: ttk.Treeview | None = None
        self.track_tree: ttk.Treeview | None = None

        self.alert_markers: list[Any] = []
        self.use_classic_markers = USE_CLASSIC_MARKERS
        self._icon_cache: dict[str, ImageTk.PhotoImage] = {}

        self.log_buffer = LogBuffer()
        self.log_text: ScrolledText | None = None
        self.notebook: ttk.Notebook | None = None

        self.preferences_path = Path.home() / ".inceptio_prefs.json"
        prefs = self._load_preferences()
        self._preferences = prefs
        if isinstance(prefs.get("base_url"), str):
            self.base_url_var.set(prefs["base_url"])
        if isinstance(prefs.get("secret"), str):
            self.secret_var.set(prefs["secret"])
        self._alert_buckets = {"warn": 0, "crit": 0}
        self._alert_decay_handles: list[int] = []
        self._safety_level = "none"

        self._init_styles()
        self._build_ui()
        self.after(150, self._poll_queue)
        self.fetch_health()
        self._schedule_health_poll()

    def _init_styles(self) -> None:
        style = ttk.Style()
        self.style = style
        try:
            style.theme_use("clam")
        except Exception:
            pass

        base_font = ("Segoe UI", 14)
        small_font = ("Segoe UI", 12)
        title_font = ("Segoe UI", 16, "bold")

        default_bg = style.lookup("TFrame", "background") or self.master.cget("bg")

        style.configure("Root.TFrame", background=default_bg)
        style.configure("Surface.TFrame", background=default_bg)
        style.configure("Card.TFrame", background=default_bg, borderwidth=1, relief="solid")

        style.configure("TLabel", background=default_bg, font=base_font)
        style.configure("CardTitle.TLabel", background=default_bg, font=title_font)
        style.configure("Muted.TLabel", background=default_bg, font=small_font)
        style.configure("Value.TLabel", background=default_bg, font=("Segoe UI", 18, "bold"))

        style.configure("Treeview", rowheight=26, font=small_font)
        style.configure("Treeview.Heading", font=("Segoe UI", 12, "bold"))

        style.configure('Notebook.Tab', padding=(16, 8), font=small_font)
        style.configure('TButton', padding=(10, 6), font=small_font)

    def _load_preferences(self) -> dict[str, Any]:
        try:
            raw = self.preferences_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _save_preferences(self) -> None:
        data = {
            "base_url": self.base_url_var.get(),
            "secret": self.secret_var.get(),
        }
        try:
            self.preferences_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as exc:
            self._append_log(f"[prefs] failed to save preferences: {exc}")

    def _note_alert_severity(self, severity: str) -> None:
        level = severity.lower()
        if level not in ("warn", "crit"):
            return
        self._alert_buckets[level] += 1
        handle = self.after(20000, lambda lvl=level: self._decay_alert_bucket(lvl))
        self._alert_decay_handles.append(handle)
        self._evaluate_safety()

    def _decay_alert_bucket(self, level: str) -> None:
        self._alert_buckets[level] = max(0, self._alert_buckets[level] - 1)
        self._evaluate_safety()

    def _evaluate_safety(self) -> None:
        highest = "crit" if self._alert_buckets["crit"] > 0 else ("warn" if self._alert_buckets["warn"] > 0 else "none")
        self._safety_level = highest

    def _sync_safety_from_metrics(self, severity: str) -> None:
        level = severity.lower()
        if level not in ("warn", "crit"):
            self._safety_level = "none"
            return
        self._safety_level = level
    def _build_ui(self) -> None:
        self.configure(style="Root.TFrame")
        self.grid(row=0, column=0, sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=(0, 0, 0, 10), style="Surface.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        for col in range(12):
            top.columnconfigure(col, weight=1 if col in (1, 3) else 0)

        ttk.Label(top, text="Base URL:").grid(row=0, column=0, padx=(0, 6))
        entry = ttk.Entry(top, textvariable=self.base_url_var)
        entry.grid(row=0, column=1, sticky="ew")
        entry.focus_set()

        ttk.Label(top, text="Secret:").grid(row=0, column=2, padx=(12, 6))
        secret_entry = ttk.Entry(top, textvariable=self.secret_var, show="*")
        secret_entry.grid(row=0, column=3, sticky="ew")

        ttk.Button(top, text="Docs", command=self._open_docs).grid(row=0, column=4, padx=(6, 0))
        ttk.Button(top, text="Refresh Health", command=self.fetch_health).grid(row=0, column=5, padx=6)
        ttk.Button(top, text="Connect WS", command=self.connect_ws).grid(row=0, column=6, padx=(6, 0))
        ttk.Button(top, text="Disconnect", command=self.disconnect_ws).grid(row=0, column=7, padx=(6, 0))
        self.live_toggle_btn = ttk.Button(top, text="Pause Live", command=self._toggle_live_updates)
        self.live_toggle_btn.grid(row=0, column=8, padx=(12, 0))
        ttk.Label(top, text="WS:").grid(row=0, column=9, padx=(12, 4))
        ttk.Label(top, textvariable=self.ws_status_var).grid(row=0, column=10, sticky="w")

        notebook = ttk.Notebook(self)
        notebook.grid(row=1, column=0, sticky="nsew")
        self.notebook = notebook

        live_tab = ttk.Frame(notebook, style="Surface.TFrame")
        live_tab.columnconfigure(0, weight=1)
        live_tab.rowconfigure(0, weight=1)
        notebook.add(live_tab, text="Live")

        debug_tab = ttk.Frame(notebook, padding=12, style="Surface.TFrame")
        debug_tab.columnconfigure(0, weight=1)
        debug_tab.rowconfigure(1, weight=1)
        notebook.add(debug_tab, text="Debug")

        self._build_live_tab(live_tab)
        self._build_debug_tab(debug_tab)

    def _build_live_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        content = ttk.Frame(parent, style="Surface.TFrame")
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)
        content.rowconfigure(0, weight=1)

        map_frame = ttk.Frame(content, borderwidth=1, relief="solid", style="Card.TFrame")
        map_frame.grid(row=0, column=0, sticky="nsew")
        map_frame.columnconfigure(0, weight=1)
        map_frame.rowconfigure(0, weight=1)

        self.map_widget = TkinterMapView(map_frame, corner_radius=0)
        self.map_widget.grid(row=0, column=0, sticky="nsew")
        self.map_widget.set_tile_server("https://tile.openstreetmap.org/{z}/{x}/{y}.png", max_zoom=19)
        self.map_widget.set_position(35.271, -78.637)
        self.map_widget.set_zoom(7)

        sidebar = ttk.Frame(content, padding=(12, 0), style="Surface.TFrame")
        sidebar.grid(row=0, column=1, sticky="nsew")
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(0, weight=3)
        sidebar.rowconfigure(1, weight=3)
        sidebar.rowconfigure(2, weight=2)

        self._build_alerts_card(sidebar, row=0)
        self._build_tracks_card(sidebar, row=1)
        self._build_health_card(sidebar, row=2)

    def _build_debug_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        header = ttk.Frame(parent, style="Surface.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Debug Log", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        buttons = ttk.Frame(header)
        buttons.grid(row=0, column=1, sticky="e")
        ttk.Button(buttons, text="Copy All", command=self._copy_log).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(buttons, text="Clear", command=self._clear_log).grid(row=0, column=1)

        text_widget = ScrolledText(parent, wrap="word")
        text_widget.grid(row=1, column=0, sticky="nsew")
        text_widget.configure(state="disabled")
        self.log_text = text_widget
        self._refresh_log_widget()

    def _create_card(self, parent: ttk.Frame, title: str, row: int) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame", padding=12)
        card.grid(row=row, column=0, sticky="nsew", pady=(0, 12))
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text=title, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        return card

    def _build_alerts_card(self, parent: ttk.Frame, row: int) -> None:
        card = self._create_card(parent, "Alerts", row)
        card.rowconfigure(2, weight=1)

        filters = ttk.Frame(card, style="Surface.TFrame")
        filters.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        for idx, level in enumerate(("crit", "warn", "info")):
            ttk.Checkbutton(
                filters,
                text=level.title(),
                variable=self.alert_severity_filters[level],
                command=self._refresh_alert_view,
            ).grid(row=0, column=idx, padx=(0 if idx == 0 else 6, 0))
        ttk.Label(filters, text="Age:").grid(row=0, column=3, padx=(12, 4))
        age_combo = ttk.Combobox(filters, values=["5m", "10m", "1h"], textvariable=self.alert_age_var, state="readonly", width=6)
        age_combo.grid(row=0, column=4)
        self.alert_age_var.trace_add("write", lambda *_: self._refresh_alert_view())

        columns = ("rule", "severity", "time", "location")
        tree = ttk.Treeview(card, columns=columns, show="headings", height=12)
        tree.grid(row=2, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(card, orient="vertical", command=tree.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)

        headings = {
            "rule": "Rule",
            "severity": "Severity",
            "time": "Time",
            "location": "Location",
        }
        widths = {
            "rule": 160,
            "severity": 90,
            "time": 110,
            "location": 130,
        }
        for column in columns:
            tree.heading(column, text=headings[column])
            align = "w" if column in ("rule", "location") else "center"
            tree.column(column, width=widths[column], anchor=align)
        tree.tag_configure("crit", foreground=SEVERITY_COLORS["crit"])
        tree.tag_configure("warn", foreground=SEVERITY_COLORS["warn"])
        tree.tag_configure("info", foreground=SEVERITY_COLORS["info"])
        self.alert_tree = tree

        ttk.Label(card, textvariable=self.alert_total_var, style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=(6, 0))

    def _build_tracks_card(self, parent: ttk.Frame, row: int) -> None:
        card = self._create_card(parent, "Tracks", row)
        card.rowconfigure(2, weight=1)

        controls = ttk.Frame(card)
        controls.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        ttk.Checkbutton(
            controls,
            text="Show trails",
            variable=self.show_trails_var,
            command=self._on_trails_toggle,
        ).grid(row=0, column=0, sticky="w")

        columns = ("modality", "lat", "lon", "time")
        tree = ttk.Treeview(card, columns=columns, show="headings", height=12)
        tree.grid(row=2, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(card, orient="vertical", command=tree.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)

        headings = {
            "modality": "Mod",
            "lat": "Lat",
            "lon": "Lon",
            "time": "Time",
        }
        widths = {
            "modality": 80,
            "lat": 120,
            "lon": 120,
            "time": 110,
        }
        for column in columns:
            tree.heading(column, text=headings[column])
            anchor = "center" if column == "modality" else "e"
            tree.column(column, width=widths[column], anchor=anchor)
        tree.bind("<<TreeviewSelect>>", self._on_track_select)
        self.track_tree = tree

    def _build_health_card(self, parent: ttk.Frame, row: int) -> None:
        card = self._create_card(parent, "Health", row)
        card.columnconfigure(0, weight=1)

        ttk.Label(card, textvariable=self.health_status_var, style="Value.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 8))

        grid = ttk.Frame(card)
        grid.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        for col in range(2):
            grid.columnconfigure(col, weight=1)

        metrics = [
            ("Clients", self.health_clients_var),
            ("EPS (10s)", self.health_eps_var),
            ("Last packet age", self.health_last_packet_var),
            ("Alerts total", self.health_alerts_var),
        ]
        for idx, (label, var) in enumerate(metrics):
            frame = ttk.Frame(grid)
            frame.grid(row=idx // 2, column=idx % 2, sticky="ew", padx=(0, 8), pady=(0, 4))
            ttk.Label(frame, text=f"{label}:", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
            ttk.Label(frame, textvariable=var).grid(row=0, column=1, sticky="w", padx=(4, 0))

        footer = ttk.Frame(card)
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.health_updated_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        toggle = ttk.Button(footer, text="Details (show)", command=self._toggle_health_details)
        toggle.grid(row=0, column=1, sticky="e")
        self.health_toggle_btn = toggle

        details = ttk.Frame(card)
        details.grid(row=4, column=0, sticky="nsew")
        details.columnconfigure(0, weight=1)
        text_widget = ScrolledText(details, height=8, wrap="word")
        text_widget.grid(row=0, column=0, sticky="nsew")
        text_widget.configure(state="disabled")
        self.health_details_frame = details
        self.health_details_text = text_widget
        details.grid_remove()

    def _schedule_health_poll(self) -> None:
        if self._health_poll_job is not None:
            self.after_cancel(self._health_poll_job)
        self._health_poll_job = self.after(self.health_poll_ms, self._health_poll_tick)

    def _health_poll_tick(self) -> None:
        self.fetch_health()
        self._schedule_health_poll()

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "ws_status":
                    self._handle_ws_status(payload)
                elif kind == "ws_message":
                    self._handle_ws_message(payload)
                elif kind == "health":
                    self._handle_health(payload)
                elif kind == "health_error":
                    self._handle_health_error(payload)
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _handle_ws_status(self, payload: dict[str, Any]) -> None:
        state = payload.get("state", "unknown")
        detail = payload.get("detail")
        if state == "connected":
            text = "connected"
        elif state == "connecting":
            text = f"connecting to {detail}" if detail else "connecting"
        elif state == "error":
            text = f"error: {detail}" if detail else "error"
        elif detail:
            text = f"{state} ({detail})"
        else:
            text = state
        self.ws_status_var.set(text)
        if state == "error" and detail:
            self._append_log(f"[WS ERROR] {detail}")

    def _handle_ws_message(self, message: str) -> None:
        if message.startswith("Echo: __"):
            return
        self._append_log(message)
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return

        if not self.live_updates_var.get():
            self._paused_messages.append(data)
            return

        try:
            self._dispatch_payload(data)
        except Exception as exc:
            self._append_log(f"[WS MESSAGE ERROR] {exc}")

    def _record_alert(self, data: dict[str, Any]) -> None:
        severity = str(data.get("severity", "info")).lower()
        rule = data.get("rule", "alert")
        loc = data.get("loc") or {}
        lat = loc.get("lat") if isinstance(loc, dict) else None
        lon = loc.get("lon") if isinstance(loc, dict) else None
        ts = self._parse_timestamp(data.get("timestamp"))
        entry = {
            "rule": rule,
            "severity": severity if severity in SEVERITY_COLORS else "info",
            "timestamp": ts,
            "lat": lat if isinstance(lat, (int, float)) else None,
            "lon": lon if isinstance(lon, (int, float)) else None,
            "raw": data,
            "received_at": datetime.now(timezone.utc),
        }
        self.alert_store.push(entry)
        self._note_alert_severity(entry["severity"])
        total = self.alert_store.total_received
        self.alert_total_var.set(f"Alerts: {total}")
        self.health_alerts_var.set(str(total))
        self._refresh_alert_view()

    def _refresh_alert_view(self) -> None:

        if not self.alert_tree:

            return

        tree = self.alert_tree

        tree.delete(*tree.get_children())

        for idx, entry in enumerate(self._filtered_alerts()):

            time_display = self._format_time_local(entry.get("timestamp") or entry["received_at"])

            location_display = self._format_coords(entry.get("lat"), entry.get("lon"))

            severity_display = f"{severity_dot(entry['severity'])} {entry['severity'].upper()}"

            tree.insert(

                "",

                idx,

                iid=f"alert-{idx}",

                values=(

                    entry["rule"],

                    severity_display,

                    time_display,

                    location_display,

                ),

                tags=(entry["severity"],),

            )


    def _filtered_alerts(self) -> list[dict[str, Any]]:
        active = {level for level, var in self.alert_severity_filters.items() if var.get()}
        window_minutes = self._age_window_minutes()
        now = datetime.now(timezone.utc)
        results: list[dict[str, Any]] = []
        for entry in self.alert_store:
            if entry["severity"] not in active:
                continue
            ts = entry.get("timestamp") or entry["received_at"]
            if window_minutes is not None and ts is not None:
                if (now - ts).total_seconds() > window_minutes * 60:
                    continue
            results.append(entry)
        return results

    def _age_window_minutes(self) -> int | None:
        mapping = {"5m": 5, "10m": 10, "1h": 60}
        return mapping.get(self.alert_age_var.get())

    def _parse_timestamp(self, value: Any) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        try:
            cleaned = value.replace("Z", "+00:00") if value.endswith("Z") else value
            dt = datetime.fromisoformat(cleaned)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _format_time_local(self, ts: datetime | None) -> str:
        if ts is None:
            return "--"
        try:
            local = ts.astimezone()
        except Exception:
            local = ts
        return local.strftime("%H:%M:%S")

    def _format_coords(self, lat: float | None, lon: float | None) -> str:
        if lat is None or lon is None:
            return "--"
        return f"{lat:.4f}, {lon:.4f}"

    def _get_track_icon(self, color: str) -> ImageTk.PhotoImage:
        return self._get_cached_icon(f"track:{color}", lambda: self._build_dot_icon(color, size=12, border="#ffffff", border_thickness=2))

    def _get_alert_icon(self, color: str) -> ImageTk.PhotoImage:
        return self._get_cached_icon(f"alert:{color}", lambda: self._build_alert_icon(color))

    def _get_cached_icon(self, key: str, builder: Callable[[], ImageTk.PhotoImage]) -> ImageTk.PhotoImage:
        icon = self._icon_cache.get(key)
        if icon is None:
            icon = builder()
            self._icon_cache[key] = icon
        return icon

    @staticmethod
    def _hex_to_rgba(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
        value = color.lstrip('#')
        if len(value) == 3:
            value = ''.join(ch * 2 for ch in value)
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
        return (r, g, b, alpha)

    def _build_dot_icon(self, color: str, *, size: int, border: str | None = None, border_thickness: int = 0) -> ImageTk.PhotoImage:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        if border and border_thickness > 0:
            draw.ellipse((0, 0, size - 1, size - 1), fill=self._hex_to_rgba(border))
            inset = border_thickness
            draw.ellipse((inset, inset, size - 1 - inset, size - 1 - inset), fill=self._hex_to_rgba(color))
        else:
            draw.ellipse((0, 0, size - 1, size - 1), fill=self._hex_to_rgba(color))
        return ImageTk.PhotoImage(img)

    def _build_alert_icon(self, color: str, *, size: int = 20, ring_thickness: int = 4, center_color: str = "#202020", center_radius: int = 4) -> ImageTk.PhotoImage:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((0, 0, size - 1, size - 1), fill=self._hex_to_rgba(color, 200))
        inset = ring_thickness
        draw.ellipse((inset, inset, size - 1 - inset, size - 1 - inset), fill=(0, 0, 0, 0))
        if center_radius > 0:
            cx = size / 2
            bounds = (cx - center_radius, cx - center_radius, cx + center_radius, cx + center_radius)
            draw.ellipse(bounds, fill=self._hex_to_rgba(center_color))
        return ImageTk.PhotoImage(img)

    def _handle_health(self, payload: dict[str, Any]) -> None:
        self.health_payload = payload
        self._update_health_summary(payload)
        if self.health_details_visible.get():
            self._update_health_details(payload)

    def _update_health_summary(self, payload: dict[str, Any]) -> None:
        status = str(payload.get("status", "unknown"))
        self.health_status_var.set(status.upper())
        clients = payload.get("clients")
        self.health_clients_var.set(str(clients) if clients is not None else "--")
        eps = payload.get("eps_10s")
        if eps is None:
            eps = payload.get("eps_1s")
        self.health_eps_var.set(f"{eps:.2f}" if isinstance(eps, (int, float)) else "--")
        age = payload.get("last_packet_age_s")
        self.health_last_packet_var.set(f"{age:.2f}s" if isinstance(age, (int, float)) else "--")
        alerts_total = payload.get("alerts_total")
        if isinstance(alerts_total, (int, float)):
            self.health_alerts_var.set(str(int(alerts_total)))
        else:
            self.health_alerts_var.set(str(self.alert_store.total_received))
        highest = payload.get("alerts_highest_severity")
        if isinstance(highest, str):
            self._sync_safety_from_metrics(highest)
        self.health_updated_var.set(datetime.now().strftime("updated %H:%M:%S"))

    def _handle_health_error(self, error: str) -> None:
        self.health_status_var.set("ERROR")
        self.health_clients_var.set("--")
        self.health_eps_var.set("--")
        self.health_last_packet_var.set("--")
        self.health_updated_var.set(datetime.now().strftime("error %H:%M:%S"))
        self._append_log(f"[HEALTH ERROR] {error}")
        if self.health_details_visible.get() and self.health_details_text:
            self.health_details_text.configure(state="normal")
            self.health_details_text.delete("1.0", tk.END)
            self.health_details_text.insert(tk.END, f"Health check failed: {error}\n")
            self.health_details_text.configure(state="disabled")

    def _toggle_health_details(self) -> None:
        if not self.health_details_frame or not self.health_details_text or not self.health_toggle_btn:
            return
        visible = not self.health_details_visible.get()
        self.health_details_visible.set(visible)
        if visible:
            self.health_details_frame.grid()
            self.health_toggle_btn.configure(text="Details (hide)")
            if self.health_payload:
                self._update_health_details(self.health_payload)
        else:
            self.health_details_frame.grid_remove()
            self.health_toggle_btn.configure(text="Details (show)")

    def _update_health_details(self, payload: dict[str, Any]) -> None:
        if not self.health_details_text:
            return
        data = json.dumps(payload, indent=2)
        self.health_details_text.configure(state="normal")
        self.health_details_text.delete("1.0", tk.END)
        self.health_details_text.insert(tk.END, data + "\n")
        self.health_details_text.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        self.log_buffer.append(text)
        print(text)
        self._refresh_log_widget()

    def _dispatch_payload(self, data: dict[str, Any]) -> None:
        if data.get("type") == "alert":
            self._record_alert(data)
            self._spawn_alert_marker(data)
        elif data.get("location"):
            self._upsert_track(data)
        else:
            self._append_log(f"[WS] Ignored payload without location: {data}")

    def _flush_paused_messages(self) -> None:
        if not self._paused_messages:
            return
        pending = list(self._paused_messages)
        self._paused_messages.clear()
        for payload in pending:
            try:
                self._dispatch_payload(payload)
            except Exception as exc:
                self._append_log(f"[WS MESSAGE ERROR] {exc}")

    def _toggle_live_updates(self) -> None:
        enabled = not self.live_updates_var.get()
        self.live_updates_var.set(enabled)
        if self.live_toggle_btn is not None:
            self.live_toggle_btn.configure(text="Pause Live" if enabled else "Resume Live")
        state = "resumed" if enabled else "paused"
        self._append_log(f"[UI] Live updates {state}")
        if enabled:
            self._flush_paused_messages()

    def _refresh_log_widget(self) -> None:
        if not self.log_text:
            return
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        entries = self.log_buffer.snapshot()
        if entries:
            self.log_text.insert(tk.END, "\n".join(entries) + "\n")
        self.log_text.configure(state="disabled")
        self.log_text.see(tk.END)

    def _copy_log(self) -> None:
        entries = self.log_buffer.snapshot()
        text = "\n".join(entries)
        self.clipboard_clear()
        if text:
            self.clipboard_append(text)

    def _clear_log(self) -> None:
        self.log_buffer.clear()
        self._refresh_log_widget()

    def _upsert_track(self, data: dict[str, Any]) -> None:
        loc = data.get("location") or {}
        lat = loc.get("lat")
        lon = loc.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return
        track_id = resolve_track_id(data)
        modality = data.get("modality", "?")
        timestamp = data.get("timestamp") or ""
        self.track_store.upsert(track_id, float(lat), float(lon), data)
        self._update_map_track(track_id, float(lat), float(lon), str(modality), timestamp)
        self._schedule_track_refresh()

    def _schedule_track_refresh(self) -> None:
        if self._track_refresh_job is not None:
            self.after_cancel(self._track_refresh_job)
        self._track_refresh_job = self.after(250, self._refresh_tracks_table)

    def _refresh_tracks_table(self) -> None:
        self._track_refresh_job = None
        if not self.track_tree:
            return
        tree = self.track_tree
        selection = set(tree.selection())
        tree.delete(*tree.get_children())

        def sort_key(item: tuple[str, dict[str, Any]]) -> float:
            _, payload = item
            ts = self._parse_timestamp(payload.get("timestamp"))
            if ts is None:
                return float("-inf")
            return ts.timestamp()

        for track_id, payload in sorted(self.track_store.items.items(), key=sort_key, reverse=True)[:400]:
            loc = payload.get("location") or {}
            lat = loc.get("lat")
            lon = loc.get("lon")
            ts = self._parse_timestamp(payload.get("timestamp"))
            values = (
                payload.get("modality", "?"),
                f"{lat:.5f}" if isinstance(lat, (int, float)) else "--",
                f"{lon:.5f}" if isinstance(lon, (int, float)) else "--",
                self._format_time_local(ts),
            )
            tree.insert("", "end", iid=track_id, values=values)
        for track_id in selection:
            if tree.exists(track_id):
                tree.selection_add(track_id)

    def _update_map_track(self, track_id: str, lat: float, lon: float, modality: str, timestamp: str) -> None:
        color = modality_color(modality)
        history = self.track_store.history.get(track_id, [])
        if len(history) == 1:
            self.map_widget.set_position(lat, lon)
            if self.map_widget.get_zoom() < 11:
                self.map_widget.set_zoom(11)

        lines = [track_id, modality]
        if timestamp:
            lines.append(timestamp)
        marker_text = "\n".join(lines)


        marker = self.map_markers.get(track_id)
        if marker is not None:
            marker.set_position(lat, lon)
            marker.set_text(marker_text)
        else:
            marker = self.map_widget.set_marker(
                lat,
                lon,
                text=marker_text,
                marker_color_circle=color,
                marker_color_outside="#202020",
            )
            self.map_markers[track_id] = marker

        if self.show_trails_var.get() and len(history) >= 2:
            path = self.map_paths.get(track_id)
            if path is not None:
                path.set_position_list(history)
            else:
                self.map_paths[track_id] = self.map_widget.set_path(history, color=color, width=3)
        else:
            path = self.map_paths.pop(track_id, None)
            if path is not None:
                with contextlib.suppress(Exception):
                    path.delete()

    def _on_trails_toggle(self) -> None:
        if self.show_trails_var.get():
            self._redraw_all_trails()
        else:
            self._clear_trails()

    def _clear_trails(self) -> None:
        for path in list(self.map_paths.values()):
            with contextlib.suppress(Exception):
                path.delete()
        self.map_paths.clear()

    def _redraw_all_trails(self) -> None:
        self._clear_trails()
        for track_id, history in self.track_store.history.items():
            if len(history) < 2:
                continue
            payload = self.track_store.items.get(track_id) or {}
            modality = str(payload.get("modality", "default"))
            color = modality_color(modality)
            self.map_paths[track_id] = self.map_widget.set_path(history, color=color, width=3)

    def _spawn_alert_marker(self, alert: dict[str, Any]) -> None:
        loc = alert.get("loc") or {}
        lat = loc.get("lat")
        lon = loc.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return
        severity = str(alert.get("severity") or "info").lower()
        rule = alert.get("rule", "alert")
        color = severity_color(severity)
        marker = self.map_widget.set_marker(
            lat,
            lon,
            text=f"{severity.upper()} {rule}",
            marker_color_circle=color,
            marker_color_outside="#202020",
        )
        self.alert_markers.append(marker)
        self.after(5000, lambda m=marker: self._remove_alert_marker(m))

    def _remove_alert_marker(self, marker: Any) -> None:
        if marker in self.alert_markers:
            self.alert_markers.remove(marker)
        with contextlib.suppress(Exception):
            marker.delete()

    def _on_track_select(self, event: tk.Event) -> None:
        if not self.track_tree:
            return
        selection = self.track_tree.selection()
        if not selection:
            return
        track_id = selection[0]
        history = self.track_store.history.get(track_id)
        if not history:
            return
        lat, lon = history[-1]
        self.map_widget.set_position(lat, lon)
        if self.map_widget.get_zoom() < 12:
            self.map_widget.set_zoom(12)

    def _open_docs(self) -> None:
        base = self._base_url()
        urls = [f"{base}/docs/local", f"{base}/docs/pipeline"]
        try:
            for url in urls:
                webbrowser.open(url, new=2)
        except Exception as exc:
            messagebox.showerror("Docs", f"Failed to open docs: {exc}")

    def fetch_health(self) -> None:
        url = self._base_url() + "/healthz"
        self.health_status_var.set("LOADING")
        headers = self._auth_headers()
        self.loop_thread.create_task(self._fetch_health_async(url, headers))

    async def _fetch_health_async(self, url: str, headers: dict[str, str]) -> None:
        try:
            data = await asyncio.to_thread(self._get_json, url, headers)
            self.queue.put(("health", data))
        except Exception as exc:
            self.queue.put(("health_error", str(exc)))

    @staticmethod
    def _get_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
        resp = requests.get(url, headers=headers or None, timeout=5)
        resp.raise_for_status()
        return resp.json()

    def connect_ws(self) -> None:
        self.ws_status_var.set("starting...")
        self.ws_client.start()

    def disconnect_ws(self) -> None:
        self.ws_client.stop()

    def on_close(self) -> None:
        self.disconnect_ws()
        self._save_preferences()
        for handle in list(self._alert_decay_handles):
            with contextlib.suppress(Exception):
                self.after_cancel(handle)
        self._alert_decay_handles.clear()
        if self._health_poll_job is not None:
            self.after_cancel(self._health_poll_job)
            self._health_poll_job = None
        if self._track_refresh_job is not None:
            self.after_cancel(self._track_refresh_job)
            self._track_refresh_job = None
        self.after(50, self._shutdown)

    def _shutdown(self) -> None:
        self.loop_thread.stop()
        self.master.destroy()

    def _base_url(self) -> str:
        return self.base_url_var.get().rstrip("/")

    def _auth_headers(self) -> dict[str, str]:
        secret = self.secret_var.get().strip()
        if not secret:
            return {}
        return {"X-ZMeta-Secret": secret}

    def _ws_url(self) -> str:
        base = self._base_url()
        if base.startswith("https://"):
            host = base[len("https://"):]
            scheme = "wss://"
        elif base.startswith("http://"):
            host = base[len("http://"):]
            scheme = "ws://"
        else:
            host = base
            scheme = "ws://"
        url = f"{scheme}{host}/ws"
        secret = self.secret_var.get().strip()
        if secret:
            connector = '&' if '?' in url else '?'
            url = f"{url}{connector}secret={secret}"
        return url

def main() -> None:
    root = tk.Tk()
    ZMetaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()






















