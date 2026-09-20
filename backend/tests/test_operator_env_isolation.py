"""A test run means the same thing on every machine (#293, #307).

Importing ``main`` runs ``configure_logging()`` and ``load_dotenv()`` as import
side effects. Left alone, that appends fake broker lines to the production
``backend/logs/blast.log`` and pulls the operator's real ``NOVA_API_KEY`` into
``os.environ``, which flips the "no key configured" route tests to 401 on a
developer machine while CI stays green.

``backend/tests/conftest.py`` pins ``NOVA_LOG_DIR`` / ``NOVA_ENV_PATH`` and
drops ``NOVA_API_KEY`` before those imports. These tests guard that pinning, so
a future edit that drops it fails here instead of silently polluting evidence.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path
from uuid import uuid4

import main  # noqa: F401  -- imported for its logging/dotenv side effects
import paths

_REPO_LOG_DIR = Path(paths.__file__).resolve().parent / "logs"
_REPO_ENV_FILE = Path(paths.__file__).resolve().parent.parent / ".env"
# A just-emitted record lands at the end; bound the read so a large
# production log never makes this guard expensive.
_BLAST_TAIL_BYTES = 1 << 20


def test_log_dir_is_not_the_operator_log_dir():
    assert paths.log_dir().resolve() != _REPO_LOG_DIR.resolve()


def test_no_log_handler_writes_into_backend_logs():
    """Every configured file handler must sit outside ``backend/logs/``."""
    targets: list[Path] = []
    for handler in logging.getLogger().handlers:
        listener = getattr(handler, "listener", None)
        candidates = list(getattr(listener, "handlers", ())) if listener else [handler]
        for candidate in candidates:
            filename = getattr(candidate, "baseFilename", None)
            if filename:
                targets.append(Path(filename).resolve())
    for target in targets:
        assert _REPO_LOG_DIR.resolve() not in target.parents, target


def test_blast_log_is_not_written_by_the_suite():
    """The suite's own log records must never land in the operator's blast.log.

    Asserting the file is *absent* only held on a machine where the desk had
    never run. On the operator's own trading PC ``backend/logs/blast.log`` is a
    real, actively-appended production log, so the absence check failed there
    for a machine difference rather than a pollution -- the exact asymmetry
    this module exists to rule out. A unique marker separates the two: it is
    present only if *this* process wrote it, whatever else owns the file.
    """
    marker = f"operator-isolation probe {uuid4()}"
    logging.getLogger(__name__).info(marker)
    for handler in logging.getLogger().handlers:
        handler.flush()
    blast = _REPO_LOG_DIR / "blast.log"
    if not blast.exists():
        return  # Clean machine or CI: the suite did not bring it into existence.
    with blast.open("rb") as stream:
        stream.seek(max(0, blast.stat().st_size - _BLAST_TAIL_BYTES))
        tail = stream.read().decode("utf-8", errors="replace")
    assert marker not in tail, "a suite log record reached the operator's blast.log"


def test_env_path_is_not_the_operator_env_file():
    assert paths.env_file_path().resolve() != _REPO_ENV_FILE.resolve()


def test_operator_api_key_is_not_visible_to_tests():
    """Route tests that assert the unauthenticated path must see no key.

    They are the ones that returned 401 instead of 400/404 whenever the
    operator had ``NOVA_API_KEY`` in their ``.env``.
    """
    assert not (os.environ.get("NOVA_API_KEY") or "").strip()
