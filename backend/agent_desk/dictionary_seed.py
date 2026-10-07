"""The dictionary's first entries (ADR 050): commands every agent understands before the operator adds any.

None of them defines a shape word. "Ascending", "fader" and the like are the operator's to define: an agent
proposes numbers, the operator tunes them, and the confirmed phrasing is saved as an operator entry.
"""
from __future__ import annotations

SEED_ENTRIES: tuple[dict, ...] = (
    {
        "id": "find-big-high",
        "phrases": ["find a small cap that ran 300%", "small caps whose high of day was up 300%",
                    "stocks that ran N% at the high"],
        "means": "Stock-days whose high (04:00-20:00 ET) was at least N% over the prior official close. "
                 "'Small cap' is a prior close of $20 or less until the operator says otherwise.",
        "call": {"method": "GET", "path": "/api/agent/movers",
                 "params": {"high_min": "N", "price_max": 20, "sort": "newest"}},
        "then": "List the matches with their date, high %, close % and when the high printed; offer to show one.",
    },
    {
        "id": "float-under",
        "phrases": ["with a float under 10M", "low float"],
        "means": "Add float_max (shares). A stock passes on the float Nova recorded that day or on SEC shares "
                 "outstanding under the limit; otherwise it is 'float unknown' and listed apart when asked. "
                 "'Low float' has no agreed number yet: ask.",
        "call": {"method": "GET", "path": "/api/agent/movers", "params": {"float_max": "SHARES"}},
    },
    {
        "id": "show-in-sim",
        "phrases": ["show me", "let me see it", "open the second one", "pull it up in the sim"],
        "means": "Put the desk on that stock and day in the Sim, loaded from the files, paused a few minutes before "
                 "the run began (at=run), unless the operator names another moment.",
        "call": {"method": "POST", "path": "/api/agent/show", "body": {"symbol": "SYM", "date": "YYYY-MM-DD", "at": "run"}},
        "then": "Follow the command (GET /api/agent/commands/{id}?wait=20) and say when it is on screen. If the desk "
                "is not on the Sim and something is at stake, list it and ask before confirm_switch.",
    },
    {
        "id": "jump-to-high",
        "phrases": ["jump to the high", "show me the top"],
        "means": "Move the playhead to the first minute of the day's high.",
        "call": {"method": "POST", "path": "/api/agent/move", "body": {"to": "high"}},
    },
    {
        "id": "move-minutes",
        "phrases": ["back 5 minutes", "forward 10 minutes"],
        "means": "Move the playhead by that many minutes (negative is back).",
        "call": {"method": "POST", "path": "/api/agent/move", "body": {"by_min": -5}},
    },
    {
        "id": "play-pause",
        "phrases": ["play", "pause", "stop it there"],
        "means": "Play or pause the Sim playback (one speed).",
        "call": {"method": "POST", "path": "/api/agent/move", "body": {"paused": False}},
    },
    {
        "id": "what-is-on-screen",
        "phrases": ["what am I looking at", "where is the sim"],
        "means": "The desk's venue, the Sim's day, playhead and loaded window, and the page and symbol in front.",
        "call": {"method": "GET", "path": "/api/agent/desk"},
    },
)
