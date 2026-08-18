# 2026-08-18 -- One Desk chip for API + Gateway

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops
- **Related:** `CHANGELOG.md` 2026-08-18 -- One Desk chip for API + Gateway

## Task

Merge the header API and Gateway pills. One control should open the same Trading prerequisites popup, and the operator should be able to X out of it.

## Goal

One honest Desk chip. Same checklist. Visible X (and Escape) to dismiss.

## Why it mattered

When both were green they looked redundant. They are still two systems (Nova :8000 vs IB Gateway), but the header does not need two pills to say "up."

## What we changed

- IBKR header: one Desk chip instead of API + Gateway
- Chip value: `up` / `delayed` / `offline` / `API down`
- Click opens the existing checklist; double-click still launches the current Gateway target
- Checklist close control is an X with aria-label; Escape also closes
- Legacy alpaca discovery still shows a standalone API chip + Feed chip

## How it works now

Desk is the connection entry. The popup still lists Nova API and IB Gateway as separate checklist rows so a red Desk chip is explained. Paper | Live stays its own capsule.

## Why this approach

Rejected hiding the difference entirely (one "Connected" with no failure text). Rejected keeping both chips and only sharing the popup -- that was the visual noise. Worst-of label keeps honesty when only one side is down.

## Verification

See CHANGELOG Verified by.

## Follow-ups

Do not put Paper | Live inside Desk. That capsule is the attach switch; Desk is health + checklist.

## Keywords

Desk chip, API up, Gateway up, Trading prerequisites, X close
