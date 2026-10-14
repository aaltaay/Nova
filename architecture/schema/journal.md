# Data schema: trade journal statistics

Owner: `backend/journal/metrics.py`, exposed by `backend/routes/journal.py`.

`GET /api/journal/metrics?include_mock=false` returns:

```text
{includes_mock_data: boolean, total_closed_trades: integer,
 win_rate_pct: number | null, avg_win_dollars: number | null,
 avg_loss_dollars: number | null, profit_loss_ratio: number | null,
 total_pnl_dollars: number | null, adherence_pct: number | null}
```

Only closed trades count. Mock rows are excluded by default, and included only when requested and labeled.
Missing rates remain null, never invented. The counts, P/L ratio and adherence percentage are measurements
for the operator to interpret. They never decide trading eligibility.

Operator decision 2026-10-13 (#791): remove `go_no_go` and its sample/adherence/profitability thresholds and
remove the Journal's Live-money GO/NO-GO bar. No readiness verdict, Paper sample or review/drill checklist
may grant or refuse permission. Explicit operator Live opt-ins/PIN and broker/account/order safety remain.
This read-only route never places an order. Existing journal rows require no migration.
