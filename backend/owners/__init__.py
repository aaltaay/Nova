"""Whose shares: your book and the bots' book inside one account (ADR 069).

Owns the whose-trade rule (ADR 063 decision 2, moved here so one module answers it): which book an order
belongs to (``whose``), which holder inside the bots' book, how one fill splits across the holders
(``split``), each holder's shares and cost (``holdings``), Paper's rules that keep the books apart
(``rules``), the bots' budget (``budget``) and the books on the wire (``books``, ``routes``). The practice
ledger, the Account history and the loss limit's count all read it here.
"""
