"""The agent endpoints (ADR 050): agents find stock-days and show them on the desk in the Sim.

Owns ``/api/agent`` -- the search over the day movers index, the commands the main desk window runs (show a
stock-day, move the playhead, open in Nova), the at-stake check before a confirmed show moves the venue, and
the operator's dictionary of commands. Nothing here places, stages or cancels an order, or arms the desk.
"""
