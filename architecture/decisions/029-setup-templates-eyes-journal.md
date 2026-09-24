# ADR 029 -- Setup templates, the eyes' journal, and eyes that watch a replay

**Status:** Accepted · **Date:** 2026-09-23
**Builds on:** [[022-setup-scanner-tape-gate]] · [[027-bot-playbook-readout-gate]] · [[019-practice-fills-on-replayed-sessions]] · [[020-three-venues-one-feed]]
**Decided by:** the operator, 2026-09-23 -- "I also need to see all their
parameters and be able to change them myself"; "each strategy will have
templates, because I'm sure we're going to want to keep a few variations of
each one"; "when we activate the eyes I also want it to be recording what it
sees ... keep it in the backend, no need for frontend, so when I ask for your
analysis you know how to pick them up, and when we are in the Sim I want to be
able to use these eyes so we can backtest them." The design below is the
agent's, under the operator's standing grant for routine calls; each item has
the operator's veto.

## Context

- The Bots page printed the first pullback's rules as prose, and the prose was
  not what the scanner ran: "07:00-10:00" where the scanner arms 07:00-11:30,
  "$3-10 · float < 10M" where it filters nothing and grades on $2-20 / 20M,
  "20c target" where target 1 is max(leg high, entry + 2R). The numbers lived
  in `constants_setups.py`; the operator could neither see nor change them.
- One rule set per setup. A variation could only be tried by editing code, and
  its evidence would have mixed with the pre-registered rules' in `setups.db`
  and in the read-out that gates Strategy.
- The scanner saw far more than the scoreboard keeps -- legs, pullbacks that
  broke a rule, every tape read, the names it followed -- and none of it was
  kept for later analysis.
- A Session Record carries the recorded Level 2 and tape: the only data that
  can test the tape gate. The scanner watched only the live market, so a
  recorded open could not be replayed through it.

## Decision

1. **A parameter catalogue per setup** (`backend/setup_templates/catalogue.py`,
   pure): every number a setup runs on, with its group, label, unit, bounds,
   default and whether a live scanner reads it. The Bots page renders the
   catalogue and a template's values -- never prose. First pullback: the
   stock filter, the pattern, entry, risk and target, the tape gate, the Five
   Pillars grade, and the bot's entry window and daily cap at Strategy.
   Flat-top breakout, red to green and Gap and Go: the research harness's
   pre-registered parameters, kept but not watched (no scanner). Micro
   pullback: none until it has a test -- the card says so.

2. **Templates.** Each setup has a built-in `default` -- its pre-registered
   rules, locked (duplicate it to vary) -- and the operator's named templates,
   stored off the repo in the operator cache (`setup-templates.json`, schema 1,
   owner `setup_templates/store.py`; the operator's variations are their edge
   and never enter git). One template per setup is **in play**. A template
   carries `rev`, bumped on every change to its parameters (a rename is not a
   change of rules).

3. **Every first-pullback template is watched at once.** The scanner runs one
   *lane* per template (a setup holds at most `SETUP_TEMPLATES_MAX_PER_SETUP`,
   the default included, and all of them are watched): its own detectors,
   tape reads and scoreboard rows, on the same bars and tape. Variations
   collect evidence on the same days, so they can be compared. Only the
   template in play raises proposals and draws the Setups board. `setups.db`
   (schema 2) rows carry `template_id`, `template_rev` and `params_hash`; every
   row from before templates is the default's.

4. **The read-out is per template and revision.** Strategy waits on the
   template in play's own read-out (ADR 027's rules unchanged); editing a
   template's parameters starts its evidence over, and the Bots page says so
   before it saves. The bot's entry window and daily cap at Strategy come from
   the template in play. The default, stock filters off, runs exactly the
   rules the scanner ran, plus the "at most two a symbol a day" ADR 022 stated
   and the code never enforced (it touches only second pullbacks, which the
   read-out excludes).

5. **The eyes' journal** (`backend/eyes/journal.py`): every observation of
   every lane -- the names followed, legs, arms and re-arms (levels, grade,
   pillars, catalyst), near, each change of the tape verdict while a setup is
   watched (verdict, reasons, metrics), triggers, fails, disarms, filtered
   setups, proposals raised and closed, scores -- one JSON line each in
   `<eyes dir>/journal/YYYY-MM-DD.jsonl` (Eastern date), stamped with the
   template and revision, the bot's level and Activate flag, and the venue.
   Always on while the backend runs: a morning the operator forgot to activate
   is still on record, and the stamp says whether the eyes were active. One
   writer thread; nothing is written on a loop (ADR 010). The desk never reads
   it; `tools/eyes_journal.py` does, and so does an agent asked for analysis.

6. **Eyes on a replay** (`backend/eyes/replay.py`): the same lanes over a
   Session Record -- prices and the tape gate from the recording's prints and
   Level 2, minute bars from the bar archive (the bars the live eyes saw,
   without IBKR's zero-volume bars for minutes with no trade, as the live seed
   reads them -- ADR 022), else the recording's own. On the Sim desk off the live edge with a Session Record
   loaded, the Setups board follows the playhead (`source: "sim"`, the recorded
   symbol) and its proposals are practice proposals on that desk -- journalled,
   never on the bot's audit stream. A historical download has no Level 2; the
   board says so instead of guessing. `POST /api/eyes/backtests` and
   `tools/eyes_backtest.py` run templates over every usable Session Record and
   keep each run under `<eyes dir>/backtests/<run_id>/`. A replayed setup never
   enters `setups.db` or the read-out: Strategy is earned on live evidence only.

## Consequences

- The Bots page shows the true numbers. Where the old prose promised a rule
  the scanner never ran (a $3-10 price band, a 20c target), the operator can
  now make it real in a template -- and that template starts its own read-out.
- More lanes cost more work on the scanner's loop per bar; the cap bounds it,
  and the indicators are extended per bar instead of recomputed.
- The journal grows a few MB a trading day; nothing prunes it yet (a retention
  policy is the operator's call, like the leaderboard's, #485).
- A backtest on Session Records is only as broad as the recordings: auto-record
  keeps the morning's leaders 07:00-10:00 (ADR 023), so that is what the eyes
  can be tested on. The results say how many sessions they covered.
- Nothing here places, stages or cancels an order. `auto_live` remains NO-GO.
