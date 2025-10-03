from __future__ import annotations

"""Simple desktop GUI for interacting with the ZMeta backend."""

import asyncio
import contextlib
import json
import queue
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

import requests
from websockets.client import connect as ws_connect
from websockets.exceptions import WebSocketException

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

from tkintermapview import TkinterMapView


MODALITY_COLORS: dict[str, str] = {
    "rf": "#007aff",
    "thermal": "#ff3b30",
    "eo": "#34c759",
    "ir": "#ff9500",
    "acoustic": "#8e8e93",
    "default": "#5856d6",
}

SEVERITY_COLORS: dict[str, str] = {
    "crit": "#ff3b30",
    "warn": "#ff9500",
    "info": "#007aff",
    "default": "#007aff",
}


class AsyncLoopThread:
    """Run a dedicated asyncio loop in a background thread."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def create_task(self, coro: Coroutine[Any, Any, Any]) -> None:
        def _schedule() -> None:
            self.loop.create_task(coro)

        self.loop.call_soon_threadsafe(_schedule)

    def stop(self) -> None:
        async def _shutdown() -> None:
            tasks = [t for t in asyncio.all_tasks(self.loop) if not t.done()]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        fut = asyncio.run_coroutine_threadsafe(_shutdown(), self.loop)
        with contextlib.suppress(Exception):
            fut.result(timeout=1.0)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=1.0)
        self.loop.close()


class WebSocketClient:
    """Minimal WebSocket consumer with auto-reconnect capability."""

    def __init__(
        self,
        loop_thread: AsyncLoopThread,
        url_factory: Callable[[], str],
        emitter: Callable[[str, Any], None],
    ) -> None:
        self.loop_thread = loop_thread
        self.loop = loop_thread.loop
        self.url_factory = url_factory
        self._emit = emitter
        self._task: asyncio.Task | None = None
        self._ws = None
        self._active = False
        self._keepalive_task: asyncio.Task | None = None
        self.reconnect_delay = 3.0
        self.keepalive_interval = 15.0

    def start(self) -> None:
        def _schedule() -> None:
            if self._task and not self._task.done():
                return
            self._active = True
            self._task = self.loop.create_task(self._runner())

        self.loop.call_soon_threadsafe(_schedule)

    def stop(self) -> None:
        def _cancel() -> None:
            self._active = False
            if self._task and not self._task.done():
                self._task.cancel()

        self.loop.call_soon_threadsafe(_cancel)

    async def _runner(self) -> None:
        uri = self.url_factory()
        while self._active:
            self._emit("status", {"state": "connecting", "detail": uri})
            final_state = {"state": "closed", "detail": None}
            try:
                async with ws_connect(uri, ping_interval=20, ping_timeout=20) as ws:
                    self._ws = ws
                    await ws.send('__listener__')
                    self._emit("status", {"state": "connected", "detail": uri})
                    self._keepalive_task = asyncio.create_task(self._keepalive(ws))
                    async for message in ws:
                        self._emit("message", message)
                final_state = {"state": "closed", "detail": "server closed"}
            except asyncio.CancelledError:
                final_state = {"state": "closed", "detail": "cancelled"}
                if self._ws is not None:
                    with contextlib.suppress(Exception):
                        await self._ws.close()
                self._active = False
            except WebSocketException as exc:
                final_state = {"state": "error", "detail": str(exc)}
            except Exception as exc:  # pragma: no cover - defensive catch
                final_state = {"state": "error", "detail": str(exc)}
            finally:
                if self._keepalive_task is not None:
                    self._keepalive_task.cancel()
                    with contextlib.suppress(Exception):
                        await self._keepalive_task
                    self._keepalive_task = None
                self._ws = None
                self._emit("status", final_state)

            if not self._active or final_state.get("detail") == "cancelled":
                break

            await asyncio.sleep(self.reconnect_delay)

        self._task = None

    async def _keepalive(self, ws) -> None:
        try:
            while self._active:
                await asyncio.sleep(self.keepalive_interval)
                if not self._active:
                    break
                try:
                    pong = ws.ping()
                    await asyncio.wait_for(pong, timeout=10)
                except Exception:
                    try:
                        await ws.send('__ping__')
                    except Exception:  # pragma: no cover - keep loop defensive
                        break
        except asyncio.CancelledError:
            pass



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

        self.alerts: deque[dict[str, Any]] = deque(maxlen=200)
        self.alert_total_count = 0
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

        self.tracks: dict[str, dict[str, Any]] = {}
        self.track_history: dict[str, list[tuple[float, float]]] = {}
        self.map_markers: dict[str, Any] = {}
        self.map_paths: dict[str, Any] = {}
        self.show_trails_var = tk.BooleanVar(value=True)
        self.max_trail_points = 60
        self._track_refresh_job: int | None = None

        self.alert_tree: ttk.Treeview | None = None
        self.track_tree: ttk.Treeview | None = None

        self.alert_markers: list[Any] = []

        self.log_history = deque(maxlen=500)
        self.log_text: ScrolledText | None = None
        self.notebook: ttk.Notebook | None = None

        self._init_styles()
        self._build_ui()
        self.after(150, self._poll_queue)
        self.fetch_health()
        self._schedule_health_poll()

    def _init_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        base_font = ("Segoe UI", 14)
        small_font = ("Segoe UI", 12)
        title_font = ("Segoe UI", 16, "bold")

        style.configure("TLabel", font=base_font, foreground="#0f1419")
        style.configure("Card.TFrame", background="#ffffff", borderwidth=1, relief="solid")
        style.configure("CardTitle.TLabel", font=title_font, foreground="#0f1419")
        style.configure("Muted.TLabel", foreground="#637081", font=small_font)
        style.configure("Value.TLabel", font=("Segoe UI", 18, "bold"))

        style.configure("Treeview", rowheight=26, font=small_font, background="#ffffff", fieldbackground="#ffffff", bordercolor="#e6e9ef")
        style.configure("Treeview.Heading", font=("Segoe UI", 12, "bold"), foreground="#0f1419")
        style.map("Treeview", background=[('selected', '#d6e4ff')])

        style.configure('Notebook.Tab', padding=(16, 8), font=small_font)
        style.map('Notebook.Tab', foreground=[('active', '#0f1419'), ('selected', '#0f1419')])

        style.configure('TButton', padding=(10, 6), font=small_font)

    def _build_ui(self) -> None:
        self.grid(row=0, column=0, sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=(0, 0, 0, 10))
        top.grid(row=0, column=0, sticky="ew")
        for col in range(8):
            top.columnconfigure(col, weight=1 if col in (1, 3) else 0)

        ttk.Label(top, text="Base URL:").grid(row=0, column=0, padx=(0, 6))
        entry = ttk.Entry(top, textvariable=self.base_url_var)
        entry.grid(row=0, column=1, sticky="ew")
        entry.focus_set()

        ttk.Label(top, text="Secret:").grid(row=0, column=2, padx=(12, 6))
        secret_entry = ttk.Entry(top, textvariable=self.secret_var, show="*")
        secret_entry.grid(row=0, column=3, sticky="ew")

        ttk.Button(top, text="Refresh Health", command=self.fetch_health).grid(row=0, column=4, padx=6)
        ttk.Button(top, text="Connect WS", command=self.connect_ws).grid(row=0, column=5, padx=(6, 0))
        ttk.Button(top, text="Disconnect", command=self.disconnect_ws).grid(row=0, column=6, padx=(6, 0))
        ttk.Label(top, text="WS:").grid(row=0, column=7, padx=(12, 4))
        ttk.Label(top, textvariable=self.ws_status_var).grid(row=0, column=8, sticky="w")

        notebook = ttk.Notebook(self)
        notebook.grid(row=1, column=0, sticky="nsew")
        self.notebook = notebook

        live_tab = ttk.Frame(notebook)
        live_tab.columnconfigure(0, weight=1)
        live_tab.rowconfigure(0, weight=1)
        notebook.add(live_tab, text="Live")

        debug_tab = ttk.Frame(notebook, padding=12)
        debug_tab.columnconfigure(0, weight=1)
        debug_tab.rowconfigure(1, weight=1)
        notebook.add(debug_tab, text="Debug")

        self._build_live_tab(live_tab)
        self._build_debug_tab(debug_tab)


    def _build_live_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        content = ttk.Frame(parent)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)
        content.rowconfigure(0, weight=1)

        map_frame = ttk.Frame(content, borderwidth=1, relief="solid")
        map_frame.grid(row=0, column=0, sticky="nsew")
        map_frame.columnconfigure(0, weight=1)
        map_frame.rowconfigure(0, weight=1)

        self.map_widget = TkinterMapView(map_frame, corner_radius=0)
        self.map_widget.grid(row=0, column=0, sticky="nsew")
        self.map_widget.set_tile_server("https://tile.openstreetmap.org/{z}/{x}/{y}.png", max_zoom=19)
        self.map_widget.set_position(35.271, -78.637)
        self.map_widget.set_zoom(7)

        sidebar = ttk.Frame(content, padding=(12, 0))
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

        header = ttk.Frame(parent)
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

        filters = ttk.Frame(card)
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
        try:
            if data.get("type") == "alert":
                self._record_alert(data)
                self._spawn_alert_marker(data)
            elif data.get("location"):
                self._upsert_track(data)
            else:
                self._append_log(f"[WS] Ignored payload without location: {data}")
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
        self.alerts.appendleft(entry)
        self.alert_total_count += 1
        self.alert_total_var.set(f"Alerts: {self.alert_total_count}")
        self.health_alerts_var.set(str(self.alert_total_count))
        self._refresh_alert_view()

    def _refresh_alert_view(self) -> None:

        if not self.alert_tree:

            return

        tree = self.alert_tree

        tree.delete(*tree.get_children())

        for idx, entry in enumerate(self._filtered_alerts()):

            time_display = self._format_time_local(entry.get("timestamp") or entry["received_at"])

            location_display = self._format_coords(entry.get("lat"), entry.get("lon"))

            severity_display = f"{self._severity_dot(entry['severity'])} {entry['severity'].upper()}"

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
        for entry in self.alerts:
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
            self.health_alerts_var.set(str(self.alert_total_count))
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
        self.log_history.append(text)
        print(text)
        self._refresh_log_widget()


    def _refresh_log_widget(self) -> None:
        if not self.log_text:
            return
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        if self.log_history:
            self.log_text.insert(tk.END, "\n".join(self.log_history) + "\n")
        self.log_text.configure(state="disabled")
        self.log_text.see(tk.END)

    def _copy_log(self) -> None:
        text = "\n".join(self.log_history)
        self.clipboard_clear()
        if text:
            self.clipboard_append(text)

    def _clear_log(self) -> None:
        self.log_history.clear()
        self._refresh_log_widget()

    def _upsert_track(self, data: dict[str, Any]) -> None:
        loc = data.get("location") or {}
        lat = loc.get("lat")
        lon = loc.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return
        track_id = self._track_id(data)
        modality = data.get("modality", "?")
        timestamp = data.get("timestamp") or ""
        self.tracks[track_id] = data

        history = self.track_history.setdefault(track_id, [])
        history.append((float(lat), float(lon)))
        if len(history) > self.max_trail_points:
            history.pop(0)

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

        for track_id, payload in sorted(self.tracks.items(), key=sort_key, reverse=True)[:400]:
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
        color = self._modality_color(modality)
        history = self.track_history.setdefault(track_id, [])
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
        for track_id, history in self.track_history.items():
            if len(history) < 2:
                continue
            payload = self.tracks.get(track_id) or {}
            modality = str(payload.get("modality", "default"))
            color = self._modality_color(modality)
            self.map_paths[track_id] = self.map_widget.set_path(history, color=color, width=3)

    def _spawn_alert_marker(self, alert: dict[str, Any]) -> None:
        loc = alert.get("loc") or {}
        lat = loc.get("lat")
        lon = loc.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return
        severity = str(alert.get("severity") or "info").lower()
        rule = alert.get("rule", "alert")
        color = self._severity_color(severity)
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

    @staticmethod
    def _track_id(data: dict[str, Any]) -> str:
        for key in ("tracking_id", "pid", "sensor_id"):
            value = data.get(key)
            if value:
                return str(value)
        data_type = data.get("data", {}).get("type", "unknown")
        sensor = data.get("sensor_id", "sensor")
        return f"{sensor}:{data_type}"

    @staticmethod
    def _modality_color(modality: str) -> str:
        return MODALITY_COLORS.get(modality.lower(), MODALITY_COLORS["default"])

    @staticmethod
    def _severity_color(severity: str) -> str:
        return SEVERITY_COLORS.get(severity.lower(), SEVERITY_COLORS["default"])

    @staticmethod
    def _severity_dot(severity: str) -> str:
        return '?'

    def _on_track_select(self, event: tk.Event) -> None:
        if not self.track_tree:
            return
        selection = self.track_tree.selection()
        if not selection:
            return
        track_id = selection[0]
        history = self.track_history.get(track_id)
        if not history:
            return
        lat, lon = history[-1]
        self.map_widget.set_position(lat, lon)
        if self.map_widget.get_zoom() < 12:
            self.map_widget.set_zoom(12)

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











