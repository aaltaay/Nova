# Candidate Strategies for Nova

Curated shortlist for **automation on Nova** (scanner + optional IBKR).  
Update this note as Pinecone recall surfaces better evidence.

## Evaluation criteria (automation-friendly)

- Clear **numeric** entry / exit / invalidation rules
- Fits Nova’s strengths: **gappers, relative volume, HOD momentum, news catalysts**
- Can paper-trade via IBKR without discretionary “feel”
- Risk can be coded (max loss %, share size, time stop)

## Candidates (fill after first Pinecone queries)

| Strategy | Course source | Automatable? | Fits Nova scanner? | Priority | Notes |
|---|---|---|---|---|---|
| HOD breakout | Basics / SS / HOD Momo | TBD | High | TBD | Overlaps existing HOD Momo module |
| News catalyst spike | Basics + news module | TBD | High | TBD | Nova already has news catalyst panel |
| Algo scalping (AS101) | Algo Scalping | TBD | Low–Med | TBD | May need faster data than IEX |

## Working recommendation (update after study)

**Status:** Not decided yet — run:

```text
py recall.py "Which day trading strategies have clear mechanical entry and exit rules suitable for automation?"
py recall.py "Gap and Go setup rules risk management"
py recall.py "HOD breakout criteria relative volume"
```

Then rank the table above and copy the winner into `03-Nova-Decisions/Active-Strategy.md`.
