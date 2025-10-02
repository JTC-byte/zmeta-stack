from __future__ import annotations

"""Simple desktop GUI for interacting with the ZMeta backend."""

import asyncio
import contextlib
import json
import queue
import threading
from datetime import datetime
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
        super().__init__(master, padding=10)
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
        self.ws_status_var = tk.StringVar(value="disconnected")
        self.health_status_var = tk.StringVar(value="never")
        self.last_health_var = tk.StringVar(value="")

        self.tracks: dict[str, dict[str, Any]] = {}
        self.track_history: dict[str, list[tuple[float, float]]] = {}
        self.map_markers: dict[str, Any] = {}
        self.map_paths: dict[str, Any] = {}
        self.alert_markers: list[Any] = []
        self.max_trail_points = 60

        self._build_ui()
        self.after(150, self._poll_queue)

    # ------------------------------------------------------------------
    # UI construction helpers
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.grid(row=0, column=0, sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=0)
        self.rowconfigure(2, weight=5)
        self.rowconfigure(3, weight=2)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew")
        for c in range(7):
            top.columnconfigure(c, weight=1 if c == 1 else 0)

        ttk.Label(top, text="Base URL:").grid(row=0, column=0, padx=(0, 6))
        entry = ttk.Entry(top, textvariable=self.base_url_var)
        entry.grid(row=0, column=1, sticky="ew")
        entry.focus_set()

        ttk.Button(top, text="Refresh Health", command=lambda: self.fetch_health()).grid(row=0, column=2, padx=6)
        ttk.Button(top, text="Connect WS", command=lambda: self.connect_ws()).grid(row=0, column=3)
        ttk.Button(top, text="Disconnect", command=lambda: self.disconnect_ws()).grid(row=0, column=4, padx=(6, 0))
        ttk.Label(top, text="WS:").grid(row=0, column=5, padx=(12, 4))
        ttk.Label(top, textvariable=self.ws_status_var).grid(row=0, column=6, sticky="w")

        health_frame = ttk.LabelFrame(self, text="Health")
        health_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        health_frame.columnconfigure(0, weight=1)
        health_frame.rowconfigure(1, weight=1)

        status_row = ttk.Frame(health_frame)
        status_row.grid(row=0, column=0, sticky="ew")
        status_row.columnconfigure(2, weight=1)
        ttk.Label(status_row, text="Status:").grid(row=0, column=0, padx=(0, 6))
        ttk.Label(status_row, textvariable=self.health_status_var).grid(row=0, column=1, sticky="w")
        ttk.Label(status_row, textvariable=self.last_health_var, foreground="#555").grid(row=0, column=2, sticky="e")

        self.health_text = ScrolledText(health_frame, height=6, wrap="word")
        self.health_text.grid(row=1, column=0, sticky="nsew")
        self.health_text.configure(state="disabled")

        live_frame = ttk.LabelFrame(self, text="Live Map & Streams")
        live_frame.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        live_frame.columnconfigure(0, weight=1)
        live_frame.rowconfigure(0, weight=4)
        live_frame.rowconfigure(1, weight=3)

        map_container = ttk.Frame(live_frame)
        map_container.grid(row=0, column=0, sticky="nsew")
        map_container.columnconfigure(0, weight=1)
        map_container.rowconfigure(0, weight=1)

        self.map_widget = TkinterMapView(map_container, corner_radius=0)
        self.map_widget.grid(row=0, column=0, sticky="nsew")
        self.map_widget.set_tile_server("https://tile.openstreetmap.org/{z}/{x}/{y}.png", max_zoom=19)
        self.map_widget.set_position(35.271, -78.637)
        self.map_widget.set_zoom(7)

        bottom = ttk.Frame(live_frame)
        bottom.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        bottom.columnconfigure(0, weight=3)
        bottom.columnconfigure(1, weight=1)
        bottom.rowconfigure(0, weight=1)

        cols = ("modality", "lat", "lon", "timestamp")
        self.track_tree = ttk.Treeview(bottom, columns=cols, show="headings", height=6)
        headings = {
            "modality": "Modality",
            "lat": "Lat",
            "lon": "Lon",
            "timestamp": "Timestamp",
        }
        for col in cols:
            self.track_tree.heading(col, text=headings[col])
            width = 160 if col == "timestamp" else 110
            self.track_tree.column(col, width=width, anchor="center")
        self.track_tree.grid(row=0, column=0, sticky="nsew")
        self.track_tree.bind("<<TreeviewSelect>>", self._on_track_select)

        alerts_panel = ttk.Frame(bottom)
        alerts_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        alerts_panel.rowconfigure(1, weight=1)
        alerts_panel.columnconfigure(0, weight=1)

        ttk.Label(alerts_panel, text="Alerts").grid(row=0, column=0, sticky="w")
        self.alerts_list = tk.Listbox(alerts_panel, height=8)
        self.alerts_list.grid(row=1, column=0, sticky="nsew")

        log_frame = ttk.LabelFrame(self, text="WebSocket Log")
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = ScrolledText(log_frame, height=12, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Event handlers and helpers
    # ------------------------------------------------------------------
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
            text = f"error: {detail}"
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
                summary = self._format_alert(data)
                self.alerts_list.insert(0, summary)
                if self.alerts_list.size() > 200:
                    self.alerts_list.delete(200, tk.END)
                self._spawn_alert_marker(data)
            elif data.get("location"):
                self._upsert_track(data)
            else:
                self._append_log(f"[WS] Ignored payload without location: {data}")
        except Exception as exc:
            self._append_log(f"[WS MESSAGE ERROR] {exc}")

    def _handle_health(self, payload: dict[str, Any]) -> None:
        pretty = json.dumps(payload, indent=2)
        self.health_status_var.set(payload.get("status", "unknown"))
        self.last_health_var.set(datetime.now().strftime("updated %H:%M:%S"))
        self.health_text.configure(state="normal")
        self.health_text.delete("1.0", tk.END)
        self.health_text.insert(tk.END, pretty + "\n")
        self.health_text.configure(state="disabled")

    def _handle_health_error(self, error: str) -> None:
        self.health_status_var.set("error")
        self.last_health_var.set("")
        self.health_text.configure(state="normal")
        self.health_text.delete("1.0", tk.END)
        self.health_text.insert(tk.END, f"Health check failed: {error}\n")
        self.health_text.configure(state="disabled")
        messagebox.showwarning("Health check failed", error)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        line_index = self.log_text.index("end-1c").split(".")[0]
        if line_index.isdigit() and int(line_index) > 500:
            self.log_text.delete("1.0", "2.0")
        self.log_text.configure(state="disabled")

    def _upsert_track(self, data: dict[str, Any]) -> None:
        loc = data.get("location") or {}
        lat = loc.get("lat")
        lon = loc.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return
        track_id = self._track_id(data)
        modality = data.get("modality", "?")
        timestamp = data.get("timestamp") or ""
        values = (
            modality,
            f"{lat:.5f}",
            f"{lon:.5f}",
            timestamp,
        )
        if self.track_tree.exists(track_id):
            self.track_tree.item(track_id, values=values)
        else:
            self.track_tree.insert("", tk.END, iid=track_id, values=values)
        self.tracks[track_id] = data
        self._update_map_track(track_id, float(lat), float(lon), str(modality), timestamp)

    def _update_map_track(self, track_id: str, lat: float, lon: float, modality: str, timestamp: str) -> None:
        color = self._modality_color(modality)
        history = self.track_history.setdefault(track_id, [])
        history.append((lat, lon))
        if len(history) > self.max_trail_points:
            history.pop(0)
        if len(history) == 1:
            self.map_widget.set_position(lat, lon)
            if self.map_widget.get_zoom() < 11:
                self.map_widget.set_zoom(11)

        text_lines = [track_id, modality]
        if timestamp:
            text_lines.append(timestamp)
        marker_text = "\n".join(text_lines)

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

        if len(history) >= 2:
            path = self.map_paths.get(track_id)
            if path is not None:
                path.set_position_list(history)
            else:
                self.map_paths[track_id] = self.map_widget.set_path(
                    history,
                    color=color,
                    width=3,
                )

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
    def _format_alert(alert: dict[str, Any]) -> str:
        rule = alert.get("rule", "alert")
        severity = alert.get("severity", "?")
        loc = alert.get("loc") or {}
        lat = loc.get("lat")
        lon = loc.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            coords = f"({lat:.4f}, {lon:.4f})"
        else:
            coords = "(n/a)"
        return f"{severity.upper()} - {rule} {coords}"

    def _modality_color(self, modality: str) -> str:
        return MODALITY_COLORS.get(modality.lower(), MODALITY_COLORS["default"])

    def _severity_color(self, severity: str) -> str:
        return SEVERITY_COLORS.get(severity.lower(), SEVERITY_COLORS["default"])

    def _on_track_select(self, event: tk.Event) -> None:
        selection = self.track_tree.selection()
        if not selection:
            return
        track_id = selection[0]
        history = self.track_history.get(track_id)
        if not history:
            return
        lat, lon = history[-1]
        self.map_widget.set_position(lat, lon)
        current_zoom = self.map_widget.get_zoom()
        if current_zoom < 9:
            self.map_widget.set_zoom(9)

    # ------------------------------------------------------------------
    # Command callbacks
    # ------------------------------------------------------------------
    def fetch_health(self) -> None:
        url = self._base_url() + "/healthz"
        self.health_status_var.set("loading")
        self.last_health_var.set("")
        self.loop_thread.create_task(self._fetch_health_async(url))

    async def _fetch_health_async(self, url: str) -> None:
        try:
            data = await asyncio.to_thread(self._get_json, url)
            self.queue.put(("health", data))
        except Exception as exc:  # pragma: no cover - surface to UI
            self.queue.put(("health_error", str(exc)))

    @staticmethod
    def _get_json(url: str) -> dict[str, Any]:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json()

    def connect_ws(self) -> None:
        self.ws_status_var.set("starting...")
        self.ws_client.start()

    def disconnect_ws(self) -> None:
        self.ws_client.stop()

    def on_close(self) -> None:
        self.disconnect_ws()
        self.after(50, self._shutdown)

    def _shutdown(self) -> None:
        self.loop_thread.stop()
        self.master.destroy()

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------
    def _base_url(self) -> str:
        return self.base_url_var.get().rstrip("/")

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
        return f"{scheme}{host}/ws"


def main() -> None:
    root = tk.Tk()
    ZMetaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()



