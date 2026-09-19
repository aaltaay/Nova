"""Compatibility barrel for Nova constants (Phase 3).

Authoritative values live in domain modules:
  constants_scanner, constants_hod_momo, constants_ibkr,
  constants_archive_news, constants_nova_os, constants_metrics,
  constants_advise, constants_bot.

Existing `from constants import X` keeps working via re-exports.

Facade owner: Pattern-Driven Architecture Phase 3.
Removal criterion: barrel stays under 400 lines and no new definitions are added
here; OR all production callers import domain modules directly.
"""

from constants_advise import *  # noqa: F403
from constants_archive_news import *  # noqa: F403
from constants_bot import *  # noqa: F403
from constants_hod_momo import *  # noqa: F403
from constants_ibkr import *  # noqa: F403
from constants_metrics import *  # noqa: F403
from constants_nova_os import *  # noqa: F403
from constants_scanner import *  # noqa: F403
from constants_sim import *  # noqa: F403
from constants_sensors import *  # noqa: F403
