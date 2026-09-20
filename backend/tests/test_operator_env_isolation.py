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

import main  # noqa: F401  -- imported for its logging/dotenv side effects
import paths

_REPO_LOG_DIR = Path(paths.__file__).resolve().parent / "logs"
_REPO_ENV_FILE = Path(paths.__file__).resolve().parent.parent / ".env"


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


def test_blast_log_is_not_created_by_the_suite():
    logging.getLogger(__name__).info("operator-isolation probe")
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert not (_REPO_LOG_DIR / "blast.log").exists()


def test_env_path_is_not_the_operator_env_file():
    assert paths.env_file_path().resolve() != _REPO_ENV_FILE.resolve()


def test_operator_api_key_is_not_visible_to_tests():
    """Route tests that assert the unauthenticated path must see no key.

    They are the ones that returned 401 instead of 400/404 whenever the
    operator had ``NOVA_API_KEY`` in their ``.env``.
    """
    assert not (os.environ.get("NOVA_API_KEY") or "").strip()
