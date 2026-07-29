# 2026-07-28 -- Follow-up ask coaching footer (constitution §5)

- **Status:** completed
- **Agents:** parent (in-session, zero-hop)
- **Domain:** docs / governance
- **Related:** `CHANGELOG.md` 2026-07-28 "Follow-up ask footer added to coaching rule" · extends 2026-07-28 Better ask footer entry

## Task

User asked that every substantive assistant reply gain a second coaching paragraph, same format as **Better ask:**, that teaches them how to ask a follow-up question about the current problem or answer. Explicitly a constitution edit.

## Goal

`AGENTS.md` §5 requires two ordered end-of-reply paragraphs (**Better ask:** then **Follow-up ask:**), maintenance log records the change, CHANGELOG + task log ship in the same commit, and the committing reply demonstrates the new format.

## Why it mattered

The Better ask footer improves the question already asked; the user also wants coaching on the *next* question. Both rules only work if they live in the constitution -- session-level instructions evaporate between chats.

## What we changed

- `AGENTS.md` §5: Co-Pilot Coaching Footer bullet rewritten from one paragraph to a two-paragraph ordered requirement (Better ask + Follow-up ask), skip rules unchanged.
- `AGENTS.md` §11: maintenance log row prepended.
- `CHANGELOG.md`: entry prepended.
- This task-log entry + `INDEX.md` row.

## How it works now

Substantive replies end with two short paragraphs: **Better ask:** (how the request could have been sharper + one thing worth knowing), then **Follow-up ask:** (one concrete next question about this problem/answer + why it is the highest-value follow-up). Trivial exchanges may skip both. `gemini.md` needs no edit -- it `@`-imports AGENTS.md.

## Why this approach

- **Constitution edit, not a chat instruction:** user said "it is going to be a constitution edit"; §5 is where the Better ask rule lives, so the sibling rule belongs in the same bullet to keep one enforceable contract instead of two scattered ones.
- **New label, not a merged paragraph:** a separate **Follow-up ask:** label keeps the two coaching jobs visually scannable and lets future sessions verify compliance mechanically (search for two labels).
- **Same skip rule for both:** extending the existing "trivial exchanges" carve-out avoids a second judgement path that agents would resolve inconsistently.
- Rejected: putting the rule in `.cursor/rules/*.mdc` -- the footer is a core behavioral rule, and the constitution already owns it; duplicating across two governance layers invites the drift the 2026-07-28 single-sourcing entry just removed.

## Verification

Rules-only change; no code to run. Verified by re-reading the edited §5/§11 text, the CHANGELOG entry, and by demonstrating the two-paragraph format in the shipping reply.

## Follow-ups

None. Do not reopen unless the user wants the label renamed or the skip policy changed.

## Keywords

coaching footer, Better ask, Follow-up ask, AGENTS.md §5, constitution, user directive
