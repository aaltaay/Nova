"""The day movers index (ADR 050): one row per stock per session that moved, from the Massive files.

Built offline by ``research/movers/build_movers.py`` through ``day_movers.store``; read by the agent
endpoints (``agent_desk``) to find stock-days to show in the Sim. Read-only to the backend.
"""
