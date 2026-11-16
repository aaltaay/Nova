"""The three lanes of Level 2 and Time & Sales lines: the operator's, Claude's seat's, the bots' (ADR 071).

Owns which stock each lane is on, and every live Level 2 and AllLast line: a lane is one of each on the same stock,
IBKR gives three of each, and each lane has one owner. No owner takes, borrows or is lent another's lane, and only a
lane opens a live line (``lanes.refusal`` is the gate ``ibkr.depth`` and ``ibkr.tape_stream`` ask).

table.py (pure: who is on which stock, and the lines a change ends and opens), lanes.py (the lanes at run time, and
the lines), yours.py / claude.py / bots.py (what moves each lane), bots_pick.py (the setups a bot may buy -- none
since the bots retired, ADR 072), recording.py (Nova records what a lane watches), sockets.py (what a socket tells your lane), focus.py (which
stocks a desk window shows in front), view.py and routes.py (``GET /api/ibkr/lanes``), runner.py (the tick).
"""
