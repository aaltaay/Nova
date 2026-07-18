"""Phase 3: domain constant modules remain import-compatible."""

from __future__ import annotations


def test_barrel_exports_domain_values():
    import constants as c

    assert c.GAPPER_MIN_GAP_PCT == 10.0
    # Mute (per-strategy cooldown) is intentionally off — burst consolidation
    # (HOD_MOMO_CONSOLIDATION_SEC) is the only anti-spam window. See
    # PROBLEM_LOG "HOD Momo mute/burst cleanup".
    assert c.HOD_MOMO_COOLDOWN_SEC == 0.0
    assert c.HOD_MOMO_CONSOLIDATION_SEC > 0
    assert c.IBKR_HOST
    assert c.ARCHIVE_SCHEMA_VERSION
    assert c.NOVA_OS_MODE_AUTO_LIVE == "auto_live"
    assert "staged" in c.ALERTS_NOVA_OS_NOTIFY_ACTIONS or c.NOVA_OS_ACTION_STAGED in c.ALERTS_NOVA_OS_NOTIFY_ACTIONS


def test_domain_modules_importable():
    import constants_archive_news
    import constants_hod_momo
    import constants_ibkr
    import constants_nova_os
    import constants_scanner

    assert constants_scanner.SCANNER_MIN_PRICE == constants_ibkr.IBKR_SCAN_ABOVE_PRICE
    assert constants_hod_momo.HOD_MOMO_CONFIG_FILE.endswith("hod-momo-config.json")
    assert constants_nova_os.NOVA_OS_DEFAULT_MODE == "signal"
    assert constants_archive_news.ARCHIVE_HOT_RETENTION_DAYS > 0


def test_mirror_gap_floor_matches_frontend_source():
    """GAPPER_MIN_GAP_PCT must stay mirrored in frontend constantGroups."""
    from pathlib import Path

    import constants as c

    fe = Path(__file__).resolve().parents[2] / "frontend" / "src" / "constantGroups"
    text = "\n".join(p.read_text(encoding="utf-8") for p in fe.glob("*.ts"))
    assert "GAPPER_MIN_GAP_PCT =" in text
    assert str(int(c.GAPPER_MIN_GAP_PCT)) in text
