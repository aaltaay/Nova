from ibkr.mode_identity import follow_paper_allowed, switch_plan


def test_switch_plan_noop_when_already_that_account():
    assert switch_plan(target="live", account_kind="live") == "noop"
    assert switch_plan(target="paper", account_kind="paper") == "noop"


def test_switch_plan_start_ibc_when_other_class_and_target_dark():
    assert switch_plan(target="live", account_kind="paper") == "start_ibc"
    assert switch_plan(target="paper", account_kind="live") == "start_ibc"
    assert switch_plan(target="live", account_kind="mixed") == "start_ibc"


def test_switch_plan_reconnect_when_target_port_already_up():
    assert (
        switch_plan(
            target="live",
            account_kind="paper",
            target_port_listening=True,
            connected_on_target_port=False,
        )
        == "reconnect"
    )
    assert (
        switch_plan(
            target="paper",
            account_kind="live",
            target_port_listening=True,
        )
        == "reconnect"
    )


def test_switch_plan_replace_when_wrong_class_on_target_port():
    assert (
        switch_plan(
            target="live",
            account_kind="paper",
            target_port_listening=True,
            connected_on_target_port=True,
        )
        == "replace_target"
    )


def test_switch_plan_reconnect_when_kind_unknown_and_port_up():
    assert (
        switch_plan(
            target="live",
            account_kind="unknown",
            target_port_listening=True,
        )
        == "reconnect"
    )


def test_switch_plan_start_ibc_when_kind_unknown_and_port_dark():
    assert switch_plan(target="live", account_kind="unknown") == "start_ibc"
    assert switch_plan(target="live", account_kind="") == "start_ibc"


def test_follow_paper_blocked_during_intentional_live():
    assert follow_paper_allowed(requested_mode="live", intentional="live") is False
    assert follow_paper_allowed(requested_mode="live", intentional=None) is True
    assert follow_paper_allowed(requested_mode="paper", intentional=None) is False
