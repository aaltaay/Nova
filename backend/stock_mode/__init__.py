"""Who trades each stock (ADR 037): the operator's per-stock Buy / Sell switch -- Signal only, Approve,
Auto-entry, Bot at Strategy -- and the runner that acts on it on Paper and on Sim at the live edge.

``store`` holds the switch, the approvals and Nova's trades in memory; ``model`` is the pure rules
(modes, locks, sizing); ``gates`` reads the desk's gates; ``orders`` is every send, through the
execution door (ADR 007); ``runner`` hears the setup scanner's triggers and manages what it sent;
``actions`` are the writes the routes call; ``view`` answers one stock; ``routes`` serves them.
Nothing here places on Live.
"""
