"""Evaluate YAML-defined rules with cooldowns and polygon AOIs."""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog
import yaml

log = structlog.get_logger("zmeta.rules")


@dataclass
class Condition:
    field: str
    eq: Optional[Any] = None
    in_: Optional[List[Any]] = None
    between: Optional[List[float]] = None  # [min, max] inclusive
    gte: Optional[float] = None
    lte: Optional[float] = None
    polygon: Optional[List[Tuple[float, float]]] = None  # [(lat, lon), ...]


@dataclass
class Rule:
    name: str
    enabled: bool
    severity: str  # "info" | "warn" | "crit"
    message: str
    conditions: List[Condition]
    any_match: bool = False  # if True: OR; else AND
    cooldown_seconds: Optional[float] = None


def _get_field(obj: Dict[str, Any], path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _point_from_value(value: Any, root: Dict[str, Any], field_path: str) -> Optional[Tuple[float, float]]:
    if isinstance(value, dict):
        lat = value.get("lat")
        lon = value.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return float(lat), float(lon)
    lat = _get_field(root, f"{field_path}.lat")
    lon = _get_field(root, f"{field_path}.lon")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return float(lat), float(lon)
    return None


def _point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
    if len(polygon) < 3:
        return False
    lat, lon = point
    inside = False
    for i in range(len(polygon)):
        lat1, lon1 = polygon[i]
        lat2, lon2 = polygon[(i + 1) % len(polygon)]
        intersects = ((lon1 > lon) != (lon2 > lon)) and (
            lat < (lat2 - lat1) * (lon - lon1) / (lon2 - lon1 + 1e-12) + lat1
        )
        if intersects:
            inside = not inside
    return inside


def _cond_ok(cond: Condition, value: Any, root: Dict[str, Any]) -> bool:
    if cond.eq is not None:
        return value == cond.eq
    if cond.in_ is not None:
        return value in cond.in_
    if cond.between is not None and value is not None:
        try:
            lo, hi = cond.between
            v = float(value)
            return (v >= float(lo)) and (v <= float(hi))
        except Exception:
            return False
    if cond.gte is not None and value is not None:
        try:
            return float(value) >= float(cond.gte)
        except Exception:
            return False
    if cond.lte is not None and value is not None:
        try:
            return float(value) <= float(cond.lte)
        except Exception:
            return False
    if cond.polygon:
        point = _point_from_value(value, root, cond.field)
        if point is None:
            return False
        return _point_in_polygon(point, [(float(lat), float(lon)) for lat, lon in cond.polygon])
    return False


class RuleSet:
    def __init__(self, rules: List[Rule]):
        self.rules = rules
        self._last_fired: Dict[str, float] = {}
        self.fire_counts: Counter[str] = Counter()

    @classmethod
    def from_yaml(cls, path: Path) -> "RuleSet":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        items = data.get("rules", [])
        rules: List[Rule] = []
        for it in items:
            if not it or not it.get("enabled", True):
                continue
            conds: List[Condition] = []
            for c in it.get("conditions", []):
                polygon = c.get("polygon")
                if polygon:
                    polygon = [(float(lat), float(lon)) for lat, lon in polygon]
                conds.append(
                    Condition(
                        field=c.get("field", ""),
                        eq=c.get("eq"),
                        in_=c.get("in"),
                        between=c.get("between"),
                        gte=c.get("gte"),
                        lte=c.get("lte"),
                        polygon=polygon,
                    )
                )
            rules.append(
                Rule(
                    name=it.get("name", "unnamed"),
                    enabled=True,
                    severity=str(it.get("severity", "info")),
                    message=str(it.get("message", "")),
                    conditions=conds,
                    any_match=bool(it.get("any", False)),
                    cooldown_seconds=it.get("cooldown_seconds"),
                )
            )
        return cls(rules)

    def eval(self, z: Dict[str, Any]) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        now = time.time()
        for r in self.rules:
            results = []
            for c in r.conditions:
                v = _get_field(z, c.field)
                results.append(_cond_ok(c, v, z))
            ok = any(results) if r.any_match else all(results)
            if not ok:
                continue
            if r.cooldown_seconds:
                last = self._last_fired.get(r.name)
                if last is not None and (now - last) < float(r.cooldown_seconds):
                    continue
                self._last_fired[r.name] = now
            loc = z.get("location") or {}
            alerts.append(
                {
                    "type": "alert",
                    "rule": r.name,
                    "severity": r.severity,
                    "message": r.message,
                    "timestamp": z.get("timestamp"),
                    "loc": {"lat": loc.get("lat"), "lon": loc.get("lon")},
                    "sensor_id": z.get("sensor_id"),
                    "modality": z.get("modality"),
                }
            )
            self.fire_counts[r.name] += 1
            log.info(
                "rule fired",
                rule=r.name,
                severity=r.severity,
                sensor_id=z.get("sensor_id"),
                modality=z.get("modality"),
            )
        return alerts


class Rules:
    def __init__(self, path: str | Path = "config/rules.yaml"):
        self.path = Path(path)
        self.set = RuleSet([])

    def load(self):
        if self.path.exists():
            self.set = RuleSet.from_yaml(self.path)
        else:
            self.set = RuleSet([])
        log.info("rules loaded", rules=len(self.set.rules), path=str(self.path))

    def apply(self, z: Dict[str, Any]) -> List[Dict[str, Any]]:
        return self.set.eval(z)

    def fire_counts(self) -> Dict[str, int]:
        return dict(self.set.fire_counts)


rules = Rules()
