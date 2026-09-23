"""Unit tests for the Nova OS stable vocabulary + loss policy -- pure, no DB."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constants import (
    NOVA_OS_MODE_AUTO_PAPER,
    NOVA_OS_MODE_CONFIRM,
    NOVA_OS_MODE_SIGNAL,
)
from nova_os import codes


class TestVocabulary:
    def test_known_codes_validate(self):
        assert codes.is_valid_decision("BUY")
        assert codes.is_valid_mode("auto_paper")
        assert codes.is_valid_action("executed_paper")
        assert codes.is_valid_reason("PILLARS_PASS")

    def test_unknown_codes_rejected(self):
        assert not codes.is_valid_decision("SELL")
        assert not codes.is_valid_mode("yolo")
        assert not codes.is_valid_action("nuke")
        assert not codes.is_valid_reason("VIBES_BAD")

    def test_validate_reason_codes_returns_only_invalid(self):
        bad = codes.validate_reason_codes(["PILLARS_PASS", "MADE_UP", "TICKET_OK"])
        assert bad == ["MADE_UP"]
        assert codes.validate_reason_codes(["PILLARS_PASS", "TICKET_OK"]) == []

    def test_policy_version_is_nonempty_string(self):
        assert isinstance(codes.policy_version(), str)
        assert codes.policy_version()
