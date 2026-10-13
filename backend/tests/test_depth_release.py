"""Nova never cancels a Level 2 request IBKR has not answered (operator ask, 2026-10-13).

Tested on the live Gateway that evening (a read-only client of its own, depth only): AMD's request,
cancelled in the same instant, was granted 302 ms after the cancel and its line stayed held -- a second
cancel and a disconnect did not free it; only a Gateway restart did. Every line cancelled after its grant
was freed. These tests drive the pinned ib_async's own IB, registry and error path, with only the socket
stubbed, and hold ``ibkr/depth/release.py`` to that rule.
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import pathlib
import re

import pytest
from ib_async import IB

from constants_ibkr import (
    IBKR_DEPTH_SMART,
    IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_KEPT,
    IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_LOST,
    IBKR_ERROR_DEPTH_MAX_LINES,
    IBKR_NOTICE_DEPTH_EXCHANGES,
)
from ibkr.depth import release

GRANT_TEXT = "Exchanges - Depth: NASDAQ; IEX; Top: BYX; Need additional market data permission"
REFUSED_TEXT = "Max number (3) of market depth requests has been reached"
CON_IDS = {"AMD": 4391, "MSFT": 272093, "NVDA": 4815747, "TSLA": 76792991, "META": 107113386}


def _ib() -> tuple[IB, dict[str, list]]:
    """A real IB whose requests go nowhere; every request and cancel it sends is recorded."""
    ib = IB()
    sent: dict[str, list] = {"depth": [], "depth_cancel": []}
    seq = iter(range(100, 10_000))
    ib.client.getReqId = lambda: next(seq)
    ib.client.reqMktDepth = lambda reqId, *a: sent["depth"].append(reqId)
    ib.client.cancelMktDepth = lambda reqId, smart: sent["depth_cancel"].append((reqId, smart))
    return ib, sent


class _Desk:
    """The depth facade on a real IB, with IBKR's session switchable between READY and not."""

    def __init__(self, monkeypatch) -> None:
        import ibkr.client as client_mod
        import ibkr.depth as depth_mod
        from ibkr import loop_supervisor, session_errors

        importlib.reload(depth_mod)
        depth_mod.reset_all()
        self.depth = depth_mod
        self.new_connection()
        self.ready = True
        self.connectivity = IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_KEPT
        monkeypatch.setattr(client_mod, "is_connected", lambda: True)
        monkeypatch.setattr(client_mod, "is_ready", lambda: self.ready)
        monkeypatch.setattr(client_mod, "get_ib", lambda: self.ib if self.ready else None)
        monkeypatch.setattr(loop_supervisor, "publish_to_http", lambda cb, *a, **k: cb(*a, **k))
        monkeypatch.setattr(session_errors, "last_connectivity_code", lambda: self.connectivity)
        depth_mod._subscribe_lock = None

    def new_connection(self) -> None:
        """A new IB whose request ids start over, as ib_async's do on every connection."""
        self.ib, self.sent = _ib()

        async def qualify(contract):
            contract.conId = CON_IDS[contract.symbol]
            return [contract]

        self.ib.qualifyContractsAsync = qualify

    def subscribe(self, symbol: str) -> int:
        assert asyncio.run(self.depth.subscribe_async(symbol))["ok"] is True
        return self.sent["depth"][-1]

    def grant(self, req_id: int) -> None:
        self.ib.wrapper.error(req_id, IBKR_NOTICE_DEPTH_EXCHANGES, GRANT_TEXT, "")

    def refuse(self, req_id: int) -> None:
        self.ib.wrapper.error(req_id, IBKR_ERROR_DEPTH_MAX_LINES, REFUSED_TEXT, "")

    def rows(self, req_id: int) -> None:
        """One packet carrying a depth row on the request, through ib_async's wrapper (insert, bid)."""
        self.ib.wrapper.tcpDataArrived()
        self.ib.wrapper.updateMktDepthL2(req_id, 0, "NSDQ", 0, 1, 152.10, 300.0, True)
        self.ib.wrapper.tcpDataProcessed()


@pytest.fixture
def desk(monkeypatch):
    release.reset_for_tests()
    d = _Desk(monkeypatch)
    yield d
    d.depth.reset_all()
    release.reset_for_tests()


# ── the race, as tested at 17:57 ET ───────────────────────────────────────────


def test_a_line_let_go_before_ibkr_answers_is_cancelled_only_once_ibkr_grants_it(desk):
    """AMD 17:57:01: cancelled in the same instant as the request, granted 302 ms later -- held for good."""
    req_id = desk.subscribe("AMD")
    desk.depth.unsubscribe("AMD")
    assert desk.sent["depth_cancel"] == []  # IBKR has not answered: no cancel races its grant
    assert [h["symbol"] for h in release.view()["held"]] == ["AMD"]

    desk.grant(req_id)
    assert desk.sent["depth_cancel"] == [(req_id, IBKR_DEPTH_SMART)]  # after the grant: the order that frees
    assert release.view()["held"] == []
    assert release.view()["counts"]["cancelled_on_answer"] == 1


def test_a_line_ibkr_already_granted_is_cancelled_at_once(desk):
    """MSFT, NVDA, TSLA, GOOGL, NFLX 17:57-18:00: cancelled after the grant, every slot came back."""
    req_id = desk.subscribe("MSFT")
    desk.grant(req_id)
    desk.depth.unsubscribe("MSFT")
    assert desk.sent["depth_cancel"] == [(req_id, IBKR_DEPTH_SMART)]
    assert release.view()["held"] == []


def test_depth_rows_are_a_grant_even_without_its_notice(desk):
    req_id = desk.subscribe("NVDA")
    desk.rows(req_id)
    desk.depth.unsubscribe("NVDA")
    assert desk.sent["depth_cancel"] == [(req_id, IBKR_DEPTH_SMART)]


def test_rows_arriving_on_a_held_request_release_it(desk):
    req_id = desk.subscribe("TSLA")
    desk.depth.unsubscribe("TSLA")
    assert desk.sent["depth_cancel"] == []
    desk.rows(req_id)
    assert desk.sent["depth_cancel"] == [(req_id, IBKR_DEPTH_SMART)]
    assert release.view()["held"] == []


def test_a_held_request_ibkr_refuses_is_dropped_without_a_cancel_and_the_next_ask_is_real(desk):
    req_id = desk.subscribe("META")
    desk.depth.unsubscribe("META")
    desk.refuse(req_id)
    assert desk.sent["depth_cancel"] == []
    assert release.view()["held"] == []
    assert desk.subscribe("META") != req_id  # ib_async let the refused request go: a real new request


def test_asking_again_takes_the_held_request_back(desk):
    req_id = desk.subscribe("AMD")
    desk.depth.unsubscribe("AMD")       # a remount past the grace, before IBKR answered
    desk.subscribe("AMD")
    assert desk.sent["depth"] == [req_id]  # ib_async reused the request: nothing asked twice
    assert release.view()["held"] == []
    desk.grant(req_id)
    assert desk.sent["depth_cancel"] == []  # the grant is the line's, not a cue to cancel it
    assert desk.depth.is_subscribed("AMD") is True
    assert release.view()["counts"]["taken_back"] == 1


# ── IBKR's connection ─────────────────────────────────────────────────────────


def test_nothing_is_cancelled_while_ibkr_is_unreachable_and_ready_sends_it(desk):
    req_id = desk.subscribe("MSFT")
    desk.grant(req_id)
    desk.ready = False                   # 1100: IB Gateway lost IBKR
    desk.depth.unsubscribe("MSFT")
    assert desk.sent["depth_cancel"] == []
    assert release.view()["held"][0]["answered"] is True

    desk.ready = True                    # 1102: restored with the data kept
    release.on_session_ready(desk.ib)
    assert desk.sent["depth_cancel"] == [(req_id, IBKR_DEPTH_SMART)]


def test_a_grant_while_ibkr_is_unreachable_waits_for_ready(desk):
    req_id = desk.subscribe("NVDA")
    desk.depth.unsubscribe("NVDA")
    desk.ready = False
    desk.grant(req_id)
    assert desk.sent["depth_cancel"] == []
    desk.ready = True
    release.on_session_ready(desk.ib)
    assert desk.sent["depth_cancel"] == [(req_id, IBKR_DEPTH_SMART)]


def test_an_unanswered_request_ibkr_lost_with_its_data_is_dropped_without_a_cancel(desk):
    desk.subscribe("TSLA")
    desk.depth.unsubscribe("TSLA")
    desk.connectivity = IBKR_ERROR_CONNECTIVITY_RESTORED_DATA_LOST  # 1101: IBKR forgot every line
    release.on_session_ready(desk.ib)
    assert desk.sent["depth_cancel"] == []
    assert release.view()["held"] == []


def test_a_held_request_whose_socket_dropped_is_forgotten(desk):
    desk.subscribe("META")
    desk.depth.unsubscribe("META")
    fresh, fresh_sent = _ib()            # a new session: IB Gateway ended the old client's requests
    release.on_session_ready(fresh)
    assert release.view()["held"] == []
    assert desk.sent["depth_cancel"] == [] and fresh_sent["depth_cancel"] == []


def test_an_unanswered_request_still_held_at_ready_waits_on(desk):
    desk.subscribe("AMD")
    desk.depth.unsubscribe("AMD")
    release.on_session_ready(desk.ib)    # 1102: IBKR kept the request; its answer may still come
    assert [h["symbol"] for h in release.view()["held"]] == ["AMD"]
    assert desk.sent["depth_cancel"] == []


def test_an_answer_from_an_earlier_connection_never_releases_a_new_request_with_the_same_id(desk):
    """Ids restart per connection (291481 at 17:33, 291175 after the 17:49 Gateway restart)."""
    old_id = desk.subscribe("AMD")
    desk.grant(old_id)                   # remembered for the old connection's request
    desk.new_connection()                # ids start over
    desk.depth.reset_all()
    new_id = desk.subscribe("MSFT")
    assert new_id == old_id
    desk.depth.unsubscribe("MSFT")
    assert desk.sent["depth_cancel"] == []  # the old answer is not this request's
    assert [h["symbol"] for h in release.view()["held"]] == ["MSFT"]
    desk.grant(new_id)
    assert desk.sent["depth_cancel"] == [(new_id, IBKR_DEPTH_SMART)]


# ── review of PR #924 ─────────────────────────────────────────────────────────


def test_a_cancel_that_cannot_be_sent_stays_held_and_ready_sends_it(desk):
    """ib_async drops a request even when its cancel send raises: Nova sends first and drops only after."""
    req_id = desk.subscribe("MSFT")
    desk.grant(req_id)
    recorded = desk.ib.client.cancelMktDepth

    def broken(reqId, smart):
        raise ConnectionError("Not connected")

    desk.ib.client.cancelMktDepth = broken
    desk.depth.unsubscribe("MSFT")
    held = release.view()["held"]
    assert [h["symbol"] for h in held] == ["MSFT"] and held[0]["answered"] is True
    assert desk.ib.wrapper.subscriptions.get_sub(req_id) is not None  # still ib_async's, so it can be sent again
    desk.ib.client.cancelMktDepth = recorded
    release.on_session_ready(desk.ib)
    assert desk.sent["depth_cancel"] == [(req_id, IBKR_DEPTH_SMART)]
    assert desk.ib.wrapper.subscriptions.get_sub(req_id) is None
    assert release.view()["late_grants"]["count"] == 0


def test_a_viewer_asking_again_while_a_held_request_is_cancelled_gets_a_new_request(desk):
    """The answer's cancel and a reconnecting viewer cannot interleave: the viewer never reuses a cancelled request."""
    import threading

    from ib_async import Stock

    req_id = desk.subscribe("AMD")
    desk.depth.unsubscribe("AMD")
    contract = Stock("AMD", "SMART", "USD")
    contract.conId = CON_IDS["AMD"]
    recorded = desk.ib.client.cancelMktDepth
    seen: dict = {}

    def slow_send(reqId, smart):
        viewer = threading.Thread(target=lambda: seen.update(took=release.take_back(desk.ib, contract)))
        viewer.start()
        viewer.join(0.2)
        seen["waited"] = viewer.is_alive()  # the viewer is held off while the cancel goes out
        seen["thread"] = viewer
        recorded(reqId, smart)

    desk.ib.client.cancelMktDepth = slow_send
    desk.grant(req_id)                   # IB loop: the held request is answered and cancelled
    seen["thread"].join(2)
    assert seen["waited"] is True
    assert seen["took"] is False         # by then it was gone from ib_async: nothing to take back
    desk.ib.client.cancelMktDepth = recorded
    assert desk.subscribe("AMD") != req_id  # a real new request, never the cancelled one


# ── what the operator sees ────────────────────────────────────────────────────


def test_the_309_message_counts_held_requests_as_novas(desk):
    desk.subscribe("MSFT")
    desk.subscribe("NVDA")
    desk.subscribe("AMD")
    desk.depth.unsubscribe("AMD")        # let go before IBKR answered: held, still a slot of Nova's
    from ibkr.depth.subscribe import refusal_message

    message = refusal_message("TSLA")
    assert "MSFT, NVDA and AMD" in message
    assert "cancels the moment IBKR answers" in message
    assert "IB Gateway" not in message


def test_a_309_with_fewer_lines_than_the_cap_is_an_error_with_the_evidence(desk, caplog):
    desk.subscribe("MSFT")
    from ibkr.depth.subscribe import refusal_message

    with caplog.at_level(logging.ERROR):
        message = refusal_message("TSLA")
    assert "Nova holds only 1 (MSFT)" in message and "restarting IB Gateway frees them" in message
    assert "2 line(s) are held outside Nova" in caplog.text


def test_a_grant_after_novas_cancel_is_reported_as_the_rule_failing(desk, caplog):
    req_id = desk.subscribe("MSFT")
    desk.grant(req_id)
    desk.depth.unsubscribe("MSFT")       # cancelled after the grant: the safe order
    with caplog.at_level(logging.ERROR):
        desk.grant(req_id)               # IBKR answering again after the cancel would be a held line
        desk.grant(req_id)               # reported once per request
    assert desk.sent["depth_cancel"] == [(req_id, IBKR_DEPTH_SMART)]  # no second cancel: it frees nothing
    late = release.view()["late_grants"]
    assert late["count"] == 1 and late["last"]["symbol"] == "MSFT" and late["last"]["req_id"] == req_id
    assert caplog.text.count("held inside IB Gateway until it restarts") == 1


def test_the_grant_that_releases_a_held_request_is_no_late_grant(desk, caplog):
    req_id = desk.subscribe("AMD")
    desk.depth.unsubscribe("AMD")
    with caplog.at_level(logging.ERROR):
        desk.grant(req_id)               # the answer the hold waited for: the cancel follows it
    assert desk.sent["depth_cancel"] == [(req_id, IBKR_DEPTH_SMART)]
    assert release.view()["late_grants"]["count"] == 0
    assert "held inside IB Gateway" not in caplog.text


# ── one door ──────────────────────────────────────────────────────────────────


def test_only_the_release_module_sends_a_level_2_cancel():
    """A ``cancelMktDepth`` anywhere else could beat IBKR's grant and hold a line until the Gateway restarts."""
    backend = pathlib.Path(__file__).resolve().parents[1]
    allowed = {backend / "ibkr" / "depth" / "release.py"}
    call = re.compile(r"\.cancelMktDepth\(")
    offenders = [
        f"{path.relative_to(backend)}:{n}"
        for path in backend.rglob("*.py")
        if "tests" not in path.relative_to(backend).parts and path not in allowed
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if call.search(line) and not line.lstrip().startswith("#")
    ]
    assert offenders == []
