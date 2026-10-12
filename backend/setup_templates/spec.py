"""What one template parameter is (ADR 029): its kind, unit, bounds, default and words. Pure data.

Moved out of ``params.py`` (2026-10-12, #845) so the parameter tables -- every setup's (``params.py``,
``params_short.py``) and the target menu every setup shares (``params_targets.py``) -- build on one type
without importing each other.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

NUMBER, INT, BOOL, TIME, CHOICE = "number", "int", "bool", "time", "choice"
DECIMALS = 6                      # a value's places, as the operator types it


class TemplateError(ValueError):
    """A value the catalogue refuses; ``field`` names the parameter (or None).

    ``message`` is written for the operator (it is what the API answers);
    nothing else about the error ever leaves the backend."""

    def __init__(self, message: str, field: str | None = None, code: str = "TEMPLATE_INVALID"):
        super().__init__(message)
        self.message = message
        self.field = field
        self.code = code


@dataclass(frozen=True)
class ParamSpec:
    key: str
    group: str
    label: str
    kind: str
    default: Any
    unit: str = ""
    min: float | str | None = None
    max: float | str | None = None
    step: float | None = None
    choices: tuple[tuple[str, str], ...] = ()
    nullable: bool = False
    help: str = ""
    live: bool = True

    def wire(self, *, affects_readout: bool = True) -> dict[str, Any]:
        return {
            "key": self.key, "group": self.group, "label": self.label, "kind": self.kind,
            "default": self.default, "unit": self.unit, "min": self.min, "max": self.max,
            "step": self.step, "choices": [{"value": v, "label": lbl} for v, lbl in self.choices],
            "nullable": self.nullable, "help": self.help, "live": self.live, "affects_readout": affects_readout,
        }


def minutes(text: str) -> int:
    hour, minute = text.split(":")
    return int(hour) * 60 + int(minute)


def _pct(fraction: float | None) -> float | None:
    return None if fraction is None else round(fraction * 100, DECIMALS)


def _p(key: str, group: str, label: str, kind: str, default: Any, **kw: Any) -> ParamSpec:
    return ParamSpec(key=key, group=group, label=label, kind=kind, default=default, **kw)
