from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

@dataclass
class Condition:
    field: str
    eq: Optional[Any] = None
    in_: Optional[List[Any]] = None
    between: Optional[List[float]] = None  # [min, max] inclusive
    gte: Optional[float] = None
    lte: Optional[float] = None

@dataclass
class Rule:
    name: str
    enabled: bool
    severity: str  # "info" | "warn" | "crit"
    message: str
    conditions: List[Condition]
    any_match: bool = False  # if True: OR; else AND

def _get_field(obj: Dict[str, Any], path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur

def _cond_ok(cond: Condition, value: Any) -> bool:
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
    # empty condition matches nothing
    return False

class RuleSet:
    def __init__(self, rules: List[Rule]):
        self.rules = rules

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
                conds.append(
                    Condition(
                        field=c.get("field", ""),
                        eq=c.get("eq"),
                        in_=c.get("in"),
                        between=c.get("between"),
                        gte=c.get("gte"),
                        lte=c.get("lte"),
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
                )
            )
        return cls(rules)

    def eval(self, z: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return list of alert dicts for matching rules."""
        alerts: List[Dict[str, Any]] = []
        for r in self.rules:
            results = []
            for c in r.conditions:
                v = _get_field(z, c.field)
                results.append(_cond_ok(c, v))
            ok = any(results) if r.any_match else all(results)
            if ok:
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
        return alerts

# Singleton-ish holder
class Rules:
    def __init__(self, path: str | Path = "config/rules.yaml"):
        self.path = Path(path)
        self.set = RuleSet([])
    def load(self):
        if self.path.exists():
            self.set = RuleSet.from_yaml(self.path)
        else:
            self.set = RuleSet([])
    def apply(self, z: Dict[str, Any]) -> List[Dict[str, Any]]:
        return self.set.eval(z)

rules = Rules()
