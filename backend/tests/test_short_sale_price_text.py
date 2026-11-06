"""A short's words quote a stock under $1 to its four digits, never the cent it rounds to."""
from short_sale.check import _px
from short_sale.ssr import _money


def test_a_price_under_a_dollar_keeps_four_digits():
    assert _px(0.3188) == "0.3188"
    assert _money(0.3188) == "0.3188"


def test_a_price_from_a_dollar_up_stays_on_the_cent():
    assert _px(5.77) == "5.77"
    assert _px(1.0) == "1.00"
    assert _money(1234.5) == "1,234.50"
    assert _money(None) == "?"


def test_the_risk_on_a_dollar_stock_reads_in_cents():
    assert _px(0.12, 5.77) == "0.12"
    assert _px(0.0211, 0.3188) == "0.0211"
