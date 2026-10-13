"""Whether IBKR's chart history is answering: the tape silence's second witness (#722).

2026-10-13: a 5-minute history request answered at 07:59:22.468 ET, and every request sent after it
timed out until 08:03, the same seconds every live tape line stopped printing.
"""
from __future__ import annotations

import pytest

from ibkr import history_answers

T = 1_791_892_762.4


@pytest.fixture(autouse=True)
def _fresh():
    history_answers.reset_for_tests()
    yield
    history_answers.reset_for_tests()


def test_a_timeout_after_the_last_answer_says_history_stopped_when_that_request_went_out():
    history_answers.note_answered(T + 0.068)
    history_answers.note_timed_out(T + 0.1)
    history_answers.note_timed_out(T + 60)
    assert history_answers.unanswered_since() == T + 0.1


def test_an_answer_ends_it():
    history_answers.note_timed_out(T)
    history_answers.note_answered(T + 240)
    assert history_answers.unanswered_since() is None


def test_a_request_slow_alone_is_not_history_stopping():
    history_answers.note_answered(T + 5)          # another request answered after this one went out
    history_answers.note_timed_out(T)
    assert history_answers.unanswered_since() is None


def test_only_a_stop_near_the_silence_counts():
    history_answers.note_timed_out(T)
    assert history_answers.unanswered_near(T + 0.4, window=120) == T
    assert history_answers.unanswered_near(T + 121, window=120) is None
    history_answers.reset_for_tests()
    assert history_answers.unanswered_near(T, window=120) is None
