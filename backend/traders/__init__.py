"""The AI traders' On / Off switches, the positions they hand you and their limits (ADR 072, ``traders.md``).

Owns ``trader-switches.json`` (``switches``), ``trader-handed.json`` (``handed``), ``trader-limits.json``
(``limits``, read-only until batch 4), what turning a trader Off does (``off``), the door's refusal of a switched-off
trader's new order (``door``) and ``/api/traders`` (``view``, ``routes``). The books themselves are ``owners``'.
"""
