"""Setup template routes (ADR 029). Nothing here places, stages or cancels an order.

  GET    /api/setups/templates                          every setup: its catalogue, templates, the one in play
  POST   /api/setups/templates/{setup}                  {name, from?, values?, note?} -> a new template
  PATCH  /api/setups/templates/{setup}/{template_id}    {name?, values?, note?} -> rename or change its rules
  DELETE /api/setups/templates/{setup}/{template_id}
  POST   /api/setups/templates/{setup}/{template_id}/play   put it in play

A refusal is ``{"detail": {"reason": CODE, "error": "...", "field": KEY | null}}``
(the bot routes' shape). Writes need the desk's API key even on loopback
(``auth.py``): a template sets what the bot may enter at Strategy.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from constants_setups import SETUP_TEMPLATES_MAX_PER_SETUP, SETUP_TEMPLATES_SCHEMA_VERSION
from setup_templates import catalogue
from setup_templates.catalogue import TemplateError
from setup_templates.store import Template, get_store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["setups"])

_STATUS = {"SETUP_UNKNOWN": 404, "TEMPLATE_UNKNOWN": 404, "TEMPLATE_BUILTIN": 409, "TEMPLATE_LIMIT": 409,
           "TEMPLATE_NAME_TAKEN": 409, "TEMPLATES_UNREADABLE": 409, "TEMPLATE_NO_PARAMS": 409}


def _refuse(exc: TemplateError) -> HTTPException:
    return HTTPException(status_code=_STATUS.get(exc.code, 400),
                         detail={"reason": exc.code, "error": str(exc), "field": exc.field})


def _readout(t: Template) -> dict[str, Any] | None:
    """The template's own read-out, briefly (first pullback only: the only scanner)."""
    try:
        from setup_scanner.readout import current

        out = current(template=t)
    except Exception as exc:
        logger.warning("setup templates: read-out failed for %s", t.id, exc_info=True)
        return {"state": "unavailable", "passed": False, "reason": f"read-out failed: {exc}", "go_triggered": None,
                "min_go": None, "go_avg_net_r": None}
    return {"state": out.get("state"), "passed": bool(out.get("passed")), "reason": out.get("reason"),
            "go_triggered": (out.get("go") or {}).get("triggered"),
            "min_go": (out.get("rules") or {}).get("min_go"),
            "go_avg_net_r": (out.get("go") or {}).get("avg_net_r")}


def _setup_view(setup_id: str) -> dict[str, Any]:
    store = get_store()
    playing = store.in_play(setup_id).id
    templates = []
    for t in store.templates(setup_id):
        row = t.wire(in_play=t.id == playing)
        if catalogue.has_scanner(setup_id):
            row["readout"] = _readout(t)
        templates.append(row)
    return {"id": setup_id, "scanner": catalogue.has_scanner(setup_id), "catalogue": catalogue.wire(setup_id),
            "in_play": playing, "templates": templates}


@router.get("/api/setups/templates")
def list_templates() -> dict[str, Any]:
    store = get_store()
    return {"schema_version": SETUP_TEMPLATES_SCHEMA_VERSION, "error": store.error(),
            "max_per_setup": SETUP_TEMPLATES_MAX_PER_SETUP,
            "setups": [_setup_view(sid) for sid in catalogue.setup_ids()]}


def _values(payload: dict[str, Any]) -> dict[str, Any] | None:
    values = payload.get("values")
    if values is not None and not isinstance(values, dict):
        raise TemplateError("values is an object of parameter: value", "values")
    return values


@router.post("/api/setups/templates/{setup_id}", status_code=201)
def create_template(setup_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        t = get_store().create(setup_id, name=payload.get("name"), from_id=payload.get("from") or None,
                               values=_values(payload), note=payload.get("note"))
    except TemplateError as exc:
        raise _refuse(exc) from exc
    return {"template": t.wire(in_play=False), "setup": _setup_view(setup_id)}


@router.patch("/api/setups/templates/{setup_id}/{template_id}")
def update_template(setup_id: str, template_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    try:
        t, rules_changed = get_store().update(setup_id, template_id, name=payload.get("name"),
                                              values=_values(payload), note=payload.get("note"))
    except TemplateError as exc:
        raise _refuse(exc) from exc
    view = _setup_view(setup_id)
    return {"template": next(x for x in view["templates"] if x["id"] == t.id), "rules_changed": rules_changed,
            "setup": view}


@router.delete("/api/setups/templates/{setup_id}/{template_id}")
def delete_template(setup_id: str, template_id: str) -> dict[str, Any]:
    try:
        get_store().delete(setup_id, template_id)
    except TemplateError as exc:
        raise _refuse(exc) from exc
    return {"ok": True, "setup": _setup_view(setup_id)}


@router.post("/api/setups/templates/{setup_id}/{template_id}/play")
def play_template(setup_id: str, template_id: str) -> dict[str, Any]:
    try:
        get_store().play(setup_id, template_id)
    except TemplateError as exc:
        raise _refuse(exc) from exc
    return {"ok": True, "setup": _setup_view(setup_id)}
