"""Next-move picks on screen: clickable cards for the Claude desktop app, a text menu elsewhere.

The desktop app draws an HTML card in the chat (its `show_widget` tool) whose
buttons send a message as if the operator typed it, so a pick is one click
(operator ask 2026-10-13). Cursor, Codex and the CLI get the same picks as a
numbered markdown menu the operator answers with a digit. Both come from
`next_move_picks.rank`, so the two never disagree.
"""

from __future__ import annotations

from html import escape
from typing import Any

from tools.next_move_picks import TOUCHES_ORDERS

MENU_HEADING = "**Next move**"
STAR = "★"

TONES = {
    "danger": "background:var(--bg-danger);color:var(--text-danger)",
    "warning": "background:var(--bg-warning);color:var(--text-warning)",
    "accent": "background:var(--bg-accent);color:var(--text-accent)",
    "neutral": "background:var(--surface-1);color:var(--text-secondary)",
}
ICONS = {
    "thread": "ti-arrow-right", "pr": "ti-git-pull-request", "fix": "ti-bug",
    "batch": "ti-package", "triage": "ti-inbox", "decide": "ti-user-question",
    "operator": "ti-user",
}
BUTTONS = {
    "thread": "Continue", "pr": "Fix it", "fix": "Fix it", "batch": "Start it",
    "triage": "Triage it", "decide": "Ask me", "operator": "Walk me through",
}
CARD_STYLE = (
    "<style>.nm{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));"
    "gap:12px;padding:.5rem 0}.nm>div{background:var(--surface-2);border:.5px solid "
    "var(--border);border-radius:12px;padding:1rem 1.25rem;display:flex;flex-direction:column;"
    "gap:10px}.nm>div.top{border:2px solid var(--border-accent)}.nm .b{display:flex;gap:6px;"
    "flex-wrap:wrap}.nm .b span{font-size:12px;padding:4px 12px;border-radius:var(--radius)}"
    ".nm .h{display:flex;gap:10px;align-items:center;font-size:15px;font-weight:500}"
    ".nm .h i{font-size:20px}.nm p{font-size:13px;color:var(--text-secondary);margin:0;"
    "line-height:1.5}.nm button{margin-top:auto}</style>"
)


def _icon(p: dict[str, Any]) -> str:
    if p["kind"] == "fix" and TOUCHES_ORDERS in p["badge"]:
        return "ti-shield-x"
    return ICONS.get(p["kind"], "ti-arrow-right")


def render_card(picks: list[dict[str, Any]]) -> str:
    """HTML for the desktop app's `show_widget` tool; the first pick is the recommendation."""
    if not picks:
        return ""
    cards = []
    for i, p in enumerate(picks):
        badges = [f'<span style="{TONES["accent"]}">Recommended</span>'] if i == 0 else []
        badges.append(f'<span style="{TONES.get(p["tone"], TONES["neutral"])}">{escape(p["badge"])}</span>')
        top = ' class="top"' if i == 0 else ""
        cards.append(
            f"<div{top}>"
            f'<div class="b">{"".join(badges)}</div>'
            f'<div class="h"><i class="ti {_icon(p)}" aria-hidden="true"></i>{escape(p["title"])}</div>'
            f'<p>{escape(p["reason"])}</p>'
            f'<button type="button" data-prompt="{escape(p["prompt"], quote=True)}" '
            f'onclick="sendPrompt(this.dataset.prompt)">{BUTTONS.get(p["kind"], "Do it")} ↗</button>'
            "</div>"
        )
    summary = (f'<h2 class="sr-only">Next move: {len(picks)} ranked picks, each with a reason '
               "and a button that sends it.</h2>")
    return CARD_STYLE + summary + '<div class="nm">' + "".join(cards) + "</div>"


def render_menu(picks: list[dict[str, Any]]) -> str:
    """The text menu for clients without cards; empty when nothing is worth offering."""
    if not picks:
        return ""
    lines = [f"{MENU_HEADING} (reply with a number; `0` = other):"]
    for i, p in enumerate(picks, 1):
        star = f"{STAR} " if i == 1 else ""
        lines.append(f"{i}. {star}**{p['title']}** -- {p['reason']} *({p['badge']})*")
    return "\n".join(lines)


def render_seed(picks: list[dict[str, Any]], *, as_of: str, source: str) -> list[str]:
    """What the session brief and `seed` print: the ranked picks with their scores and prompts."""
    head = (f"Next-move picks (as of {as_of}, source={source}; ranked best first -- reword "
            "each in plain English with `--say id='Headline|Why'`, then end the reply with "
            "`py -3 tools/next_moves.py card` in the desktop app, `menu` elsewhere):")
    if not picks:
        return [head, "- nothing worth offering: skip the menu"]
    return [head] + [
        f"{i}. [{p['score']}] {p['id']}: {p['title']} -- {p['reason']} ({p['badge']})"
        for i, p in enumerate(picks, 1)
    ]
