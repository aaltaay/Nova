"""Who trades each stock (ADR 037, ADR 042 F): the operator's per-stock Buy / Sell switch -- Signal only,
Approve, Auto-entry, Bot -- and the runner that acts on it on Paper and on Sim at the live edge.

Stock mode is the bot list's one owner: every write to the bot's stocks goes through ``actions``.
``store`` holds the switch and the approvals in memory and Nova's trades on disk; ``model`` is the
pure rules (modes, locks, NOT A TRADE on a lane); ``gates`` reads the desk's gates; ``orders`` is every
send, through the execution door (ADR 007); ``runner`` hears the setup scanner's triggers and manages
what it sent (Auto-entry by the bot's rules, ``bot.first_pullback.admit``); ``leave`` cancels Nova's
working entries before the desk leaves a venue; ``view`` answers one stock; ``routes`` serves them.
Nothing here places on Live.
"""
