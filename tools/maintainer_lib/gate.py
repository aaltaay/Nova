"""The finding kinds CI fails on (``maintainer_checks.py --gate``).

One list, read by CI and by an agent checking its own change::

    py -3 tools/maintainer_checks.py --gate --base origin/master

Every other kind is reported, not blocking: an oversize file without a reason
(``file_size``), a silent ``except`` off the money path, the CSS contract, a ruff
other than the pinned version (``ruff_version``). A
frozen legacy finding (``baseline: true``) never fails the gate; one past its
frozen count does. Merging stays advisory (AGENTS.md §5) -- a red gate is
visible, not a hold.
"""
from __future__ import annotations

GATE_KINDS = (
    # AGENTS.md §2.3 -- size
    "file_size_hard",          # an entry point past its logical-line limit
    "file_size_ceiling",       # any code file past 800 lines, reason or not
    "file_size_growth",        # past 400 and grew in this change, no reason stated
    "one_concern_no_reason",   # a one-concern marker with no reason
    # AGENTS.md §2.1 / §2.2 -- ownership and feature imports
    "package_owner_missing",
    "folder_owner_missing",
    "folder_owner_stale",
    "cross_feature_import",    # past its frozen count
    "import_main",             # past its frozen count
    # AGENTS.md §6.3 -- silent failures on the money path
    "swallowed_exception_money",
    "except_return_empty_money",
    "bare_except_money",
    "empty_catch_money",
    "empty_promise_catch_money",
    "allow_swallow_no_reason",
    # ADR 010 -- the IB loop never does blocking I/O
    "ib_loop_sync_io",
    # AGENTS.md §6.7 -- the backend lint CI's Backend tests runs (maintainer_lib/lint.py)
    "ruff",                    # a ruff finding in backend/
    "ruff_unavailable",        # ruff not installed here, so the lint did not run
    "ruff_error",              # ruff ran but gave no readable answer
)
