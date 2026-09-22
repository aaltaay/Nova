"""constants_practice pins the surveyed practice-account parameters (ADR 020).

Sources are named in architecture/practice-account.md; this test keeps the
module honest against that page and against constants_sim.
"""

from __future__ import annotations

from pathlib import Path

import constants_practice as cp
import constants_sim


def test_starting_cash_is_the_sim_ledger_seed():
    assert cp.PRACTICE_STARTING_CASH == constants_sim.SIM_STARTING_CASH == 100_000.0


def test_ibkr_fixed_commission_schedule():
    assert cp.PRACTICE_COMMISSION_PER_SHARE == 0.005
    assert cp.PRACTICE_COMMISSION_MIN == 1.00
    assert cp.PRACTICE_COMMISSION_MAX_PCT == 0.01


def test_regulatory_fees_2026():
    assert abs(cp.PRACTICE_SEC_FEE_RATE - 0.0000206) < 1e-12
    assert cp.PRACTICE_FINRA_TAF_PER_SHARE == 0.000195
    assert cp.PRACTICE_FINRA_TAF_MAX == 9.79


def test_reg_t_margin_tiers():
    assert cp.PRACTICE_MARGIN_OVERNIGHT_MULT == 2.0
    assert cp.PRACTICE_MARGIN_INTRADAY_MULT == 4.0
    assert cp.PRACTICE_PDT_MIN_EQUITY == 25_000.0
    assert cp.PRACTICE_MARGIN_INTRADAY_MULT > cp.PRACTICE_MARGIN_OVERNIGHT_MULT


def test_identity_freshness_and_rollover():
    assert cp.PRACTICE_ACCOUNT_ID_PAPER == "NOVA-PAPER"
    assert cp.PRACTICE_ACCOUNT_ID_SIM == "NOVA-SIM"
    assert cp.PRACTICE_LIVE_FRESH_SEC == 15.0
    assert cp.PRACTICE_DAY_ROLLOVER_HOUR_ET == constants_sim.SIM_SESSION_OPEN_HOUR == 4


def test_refusal_codes_match_adr_020_contract():
    assert cp.PRACTICE_NO_LIVE_PRINT_CODE == "PRACTICE_NO_LIVE_PRINT"
    assert cp.PRACTICE_BUYING_POWER_CODE == "PRACTICE_BUYING_POWER"
    assert cp.PRACTICE_NO_LIVE_PRINT_REASON
    assert cp.PRACTICE_BUYING_POWER_REASON
    assert cp.PRACTICE_NO_LIVE_PRINT_CODE not in cp.PRACTICE_NO_LIVE_PRINT_REASON


def test_every_constant_is_documented_in_the_survey():
    doc = Path(__file__).resolve().parents[2] / "architecture" / "practice-account.md"
    text = doc.read_text(encoding="utf-8")
    assert text.count("\n") < 200
    for name in (
        "PRACTICE_STARTING_CASH",
        "PRACTICE_COMMISSION_PER_SHARE",
        "PRACTICE_SEC_FEE_RATE",
        "PRACTICE_FINRA_TAF_PER_SHARE",
        "PRACTICE_MARGIN_OVERNIGHT_MULT",
        "PRACTICE_MARGIN_INTRADAY_MULT",
        "PRACTICE_PDT_MIN_EQUITY",
        "PRACTICE_LIVE_FRESH_SEC",
        "PRACTICE_DAY_ROLLOVER_HOUR_ET",
        "PRACTICE_BUYING_POWER",
    ):
        assert name in text, name
