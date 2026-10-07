"""The Live short proof (ADR 048 step 6): what Nova saw on Paper before a short may go to Live.

Three Paper days with shorts, each reviewed by the operator, and four drills with a Paper short open --
Freeze all orders, Flatten, the 15:55 cover and a Gateway drop. ``observe`` records them as they happen
into ``short-proof.json`` (``store``), so a reset of the Paper ledger never loses them; ``view`` is the
Bot card's checklist of the operator's steps; ``status`` is the door's reading (``short_sale.check``'s
``live_proof`` rule, ``SHORT_PROOF_INCOMPLETE``). How a day is reviewed waits on the operator (#778,
question 3): until then no day is marked and the proof stays incomplete.
"""
from __future__ import annotations

from short_proof.view import status

__all__ = ["status"]
