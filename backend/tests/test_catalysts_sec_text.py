"""SEC filing text to a headline (ADR 024): the extractor shared by the live feed and the research backfill."""
from __future__ import annotations

from catalysts.sec_text import headline


def test_a_headline_cut_on_a_connecting_word_is_joined():
    lines = ["EX-99.1", "Beneficient Announces Strategy to Eliminate HCLP Debt and", "Heppner Equity Interests",
             "DALLAS, Sept. 23, 2026 -- Beneficient today announced a plan."]
    assert headline(lines)[0] == "Beneficient Announces Strategy to Eliminate HCLP Debt and Heppner Equity Interests"


def test_a_short_wrapped_headline_is_joined_and_a_finished_one_is_not():
    assert headline(["Acme Corp Announces", "Record Third Quarter Revenue"])[0] == (
        "Acme Corp Announces Record Third Quarter Revenue")
    finished = ["Acme Corp Announces Record Third Quarter Revenue of $12 Million",
                "Revenue grew 40% year over year on new customer wins"]
    assert headline(finished)[0] == finished[0]


def test_the_dateline_is_never_joined_to_the_headline():
    lines = ["Acme Signs Supply Agreement With the", "NEW YORK, Sept. 23, 2026 -- Acme today announced ..."]
    assert headline(lines)[0] == "Acme Signs Supply Agreement With the"
