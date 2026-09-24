"""The operator's setup templates on disk (ADR 029).

Owner: this module -- the only reader and writer of ``setup-templates.json``.
File: ``paths.cache_dir() / SETUP_TEMPLATES_FILENAME`` -- the operator cache,
never git: the operator's variations are their edge.
Schema: ``{schema_version: 1, setups: {SETUP: {in_play: ID | null, templates:
[{id, name, note, rev, values, created_at, updated_at}]}}}``. The built-in
``default`` is not stored: it is the catalogue's defaults at
``SETUP_TEMPLATE_DEFAULT_REV``. An unknown schema version or an unreadable file
is refused loudly: the file is left as it is, every setup reads its default
only, ``error()`` says why, and writes are refused until the operator moves the
file aside.
Invalidation: none -- the operator edits through the API; ``version()`` bumps
on every change so the scanner rebuilds its lanes.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from constants_setups import (
    SETUP_TEMPLATE_DEFAULT_ID,
    SETUP_TEMPLATE_DEFAULT_NAME,
    SETUP_TEMPLATE_DEFAULT_REV,
    SETUP_TEMPLATE_NAME_MAX,
    SETUP_TEMPLATE_NOTE_MAX,
    SETUP_TEMPLATES_FILENAME,
    SETUP_TEMPLATES_MAX_PER_SETUP,
    SETUP_TEMPLATES_SCHEMA_VERSION,
)
from setup_templates import catalogue
from setup_templates.catalogue import TemplateError

logger = logging.getLogger(__name__)


@dataclass
class Template:
    setup: str
    id: str
    name: str
    rev: int
    values: dict[str, Any]
    builtin: bool = False
    note: str = ""
    created_at: float | None = None
    updated_at: float | None = None
    error: str | None = None
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        self.fingerprint = catalogue.fingerprint(self.values)

    def stored(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "note": self.note, "rev": self.rev, "values": self.values,
                "created_at": self.created_at, "updated_at": self.updated_at}

    def wire(self, *, in_play: bool) -> dict[str, Any]:
        return {**self.stored(), "setup": self.setup, "builtin": self.builtin, "in_play": in_play,
                "fingerprint": self.fingerprint, "error": self.error}


def default_template(setup_id: str) -> Template:
    return Template(setup=setup_id, id=SETUP_TEMPLATE_DEFAULT_ID, name=SETUP_TEMPLATE_DEFAULT_NAME,
                    rev=SETUP_TEMPLATE_DEFAULT_REV, values=catalogue.defaults(setup_id), builtin=True)


class TemplateStore:
    def __init__(self, path: Path | None = None):
        self._path = path
        self._lock = threading.RLock()
        self._loaded = False
        self._error: str | None = None
        self._version = 0
        self._setups: dict[str, dict[str, Any]] = {}

    # -- file ----------------------------------------------------------------
    def path(self) -> Path:
        if self._path is None:
            from paths import cache_dir

            self._path = cache_dir() / SETUP_TEMPLATES_FILENAME
        return self._path

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        path = self.path()
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self._error = f"{path.name} could not be read ({exc}); every setup runs its default until it is moved aside"
            logger.exception("setup templates: %s", self._error)
            return
        version = raw.get("schema_version") if isinstance(raw, dict) else None
        if version != SETUP_TEMPLATES_SCHEMA_VERSION:
            self._error = (f"{path.name} has schema version {version!r}; this build reads "
                           f"{SETUP_TEMPLATES_SCHEMA_VERSION}. Every setup runs its default until it is moved aside")
            logger.error("setup templates: %s", self._error)
            return
        for setup_id, entry in (raw.get("setups") or {}).items():
            if setup_id not in catalogue.CATALOGUE or not isinstance(entry, dict):
                logger.warning("setup templates: ignoring unknown setup %r in %s", setup_id, path.name)
                continue
            templates = [self._from_stored(setup_id, t) for t in entry.get("templates") or [] if isinstance(t, dict)]
            self._setups[setup_id] = {"in_play": entry.get("in_play"), "templates": [t for t in templates if t]}

    @staticmethod
    def _from_stored(setup_id: str, row: dict[str, Any]) -> Template | None:
        tid = str(row.get("id") or "")
        if not tid or tid == SETUP_TEMPLATE_DEFAULT_ID:
            return None
        error = None
        try:
            values = catalogue.validate(setup_id, None, base=row.get("values") or {})
        except TemplateError as exc:
            # Keep it visible and editable, but never run it: its rules no longer validate.
            values, error = {**catalogue.defaults(setup_id), **(row.get("values") or {})}, str(exc)
        return Template(setup=setup_id, id=tid, name=str(row.get("name") or tid), rev=int(row.get("rev") or 1),
                        values=values, note=str(row.get("note") or ""), created_at=row.get("created_at"),
                        updated_at=row.get("updated_at"), error=error)

    def _save(self) -> None:
        payload = {"schema_version": SETUP_TEMPLATES_SCHEMA_VERSION,
                   "setups": {sid: {"in_play": e.get("in_play"), "templates": [t.stored() for t in e["templates"]]}
                              for sid, e in self._setups.items()}}
        path = self.path()
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
        os.replace(tmp, path)
        self._version += 1

    def _writable(self) -> None:
        if self._error:
            raise TemplateError(self._error, code="TEMPLATES_UNREADABLE")

    # -- reads -----------------------------------------------------------------
    def error(self) -> str | None:
        with self._lock:
            self._load()
            return self._error

    def version(self) -> int:
        with self._lock:
            self._load()
            return self._version

    def templates(self, setup_id: str) -> list[Template]:
        """The default first, then the operator's in the order they were made."""
        catalogue.specs(setup_id)
        with self._lock:
            self._load()
            return [default_template(setup_id)] + list(self._setups.get(setup_id, {}).get("templates", []))

    def get(self, setup_id: str, template_id: str) -> Template:
        for t in self.templates(setup_id):
            if t.id == template_id:
                return t
        raise TemplateError(f"no template {template_id!r} for {setup_id.replace('_', ' ')}", template_id,
                            code="TEMPLATE_UNKNOWN")

    def in_play(self, setup_id: str) -> Template:
        with self._lock:
            self._load()
            wanted = self._setups.get(setup_id, {}).get("in_play")
            for t in self.templates(setup_id):
                if t.id == wanted and not t.error:
                    return t
            return default_template(setup_id)

    # -- writes ----------------------------------------------------------------
    def _entry(self, setup_id: str) -> dict[str, Any]:
        return self._setups.setdefault(setup_id, {"in_play": None, "templates": []})

    def _check_name(self, setup_id: str, name: Any, *, skip: str | None = None) -> str:
        text = " ".join(str(name or "").split())
        if not text:
            raise TemplateError("a template needs a name", "name")
        if len(text) > SETUP_TEMPLATE_NAME_MAX:
            raise TemplateError(f"a name is at most {SETUP_TEMPLATE_NAME_MAX} characters", "name")
        for t in self.templates(setup_id):
            if t.id != skip and t.name.casefold() == text.casefold():
                raise TemplateError(f"{setup_id.replace('_', ' ')} already has a template called {t.name!r}", "name",
                                    code="TEMPLATE_NAME_TAKEN")
        return text

    @staticmethod
    def _check_note(note: Any) -> str:
        text = str(note or "").strip()
        if len(text) > SETUP_TEMPLATE_NOTE_MAX:
            raise TemplateError(f"a note is at most {SETUP_TEMPLATE_NOTE_MAX} characters", "note")
        return text

    def create(self, setup_id: str, *, name: Any, from_id: str | None = None,
               values: dict[str, Any] | None = None, note: Any = None, now: float | None = None) -> Template:
        """A new template: ``from_id``'s values (else the one in play) with ``values`` over them."""
        with self._lock:
            self._load()
            self._writable()
            if not catalogue.specs(setup_id):
                raise TemplateError(f"{setup_id.replace('_', ' ')} has no parameters yet -- nothing to vary",
                                    code="TEMPLATE_NO_PARAMS")
            if len(self.templates(setup_id)) >= SETUP_TEMPLATES_MAX_PER_SETUP:
                raise TemplateError(f"a setup keeps at most {SETUP_TEMPLATES_MAX_PER_SETUP} templates, the default "
                                    "included -- delete one first", code="TEMPLATE_LIMIT")
            base = self.get(setup_id, from_id) if from_id else self.in_play(setup_id)
            checked = catalogue.validate(setup_id, values, base=base.values)
            stamp = time.time() if now is None else now
            t = Template(setup=setup_id, id=f"t-{uuid.uuid4().hex[:8]}", name=self._check_name(setup_id, name),
                         rev=1, values=checked, note=self._check_note(note), created_at=stamp, updated_at=stamp)
            self._entry(setup_id)["templates"].append(t)
            self._save()
            return t

    def update(self, setup_id: str, template_id: str, *, name: Any = None, values: dict[str, Any] | None = None,
               note: Any = None, now: float | None = None) -> tuple[Template, bool]:
        """Rename, re-note or change a template's rules. Returns (template, rules_changed)."""
        with self._lock:
            self._load()
            self._writable()
            current = self.get(setup_id, template_id)
            if current.builtin:
                raise TemplateError("the default is the pre-registered rules and stays as it is -- duplicate it "
                                    "to make a variation", template_id, code="TEMPLATE_BUILTIN")
            changed = False
            new_values = current.values
            if values is not None:
                new_values = catalogue.validate(setup_id, values, base=current.values)
                changed = new_values != current.values or current.error is not None
            new_name = current.name if name is None else self._check_name(setup_id, name, skip=template_id)
            new_note = current.note if note is None else self._check_note(note)
            if not changed and new_name == current.name and new_note == current.note:
                return current, False
            t = Template(setup=setup_id, id=current.id, name=new_name, rev=current.rev + (1 if changed else 0),
                         values=new_values, note=new_note, created_at=current.created_at,
                         updated_at=time.time() if now is None else now)
            items = self._entry(setup_id)["templates"]
            items[[x.id for x in items].index(template_id)] = t
            self._save()
            return t, changed

    def delete(self, setup_id: str, template_id: str) -> None:
        with self._lock:
            self._load()
            self._writable()
            if self.get(setup_id, template_id).builtin:
                raise TemplateError("the default cannot be deleted", template_id, code="TEMPLATE_BUILTIN")
            entry = self._entry(setup_id)
            entry["templates"] = [t for t in entry["templates"] if t.id != template_id]
            if entry.get("in_play") == template_id:
                entry["in_play"] = None
            self._save()

    def play(self, setup_id: str, template_id: str) -> Template:
        """Put ``template_id`` in play for its setup (the one that proposes)."""
        with self._lock:
            self._load()
            self._writable()
            t = self.get(setup_id, template_id)
            if t.error:
                raise TemplateError(f"{t.name} no longer validates ({t.error}) -- fix it first", template_id)
            self._entry(setup_id)["in_play"] = None if t.builtin else t.id
            self._save()
            return t

    def wire(self, setup_id: str) -> dict[str, Any]:
        playing = self.in_play(setup_id).id
        return {"in_play": playing, "templates": [t.wire(in_play=t.id == playing) for t in self.templates(setup_id)]}


_store: TemplateStore | None = None
_store_lock = threading.Lock()


def get_store() -> TemplateStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = TemplateStore()
        return _store


def set_store_for_tests(store: TemplateStore | None) -> None:
    global _store
    with _store_lock:
        _store = store
