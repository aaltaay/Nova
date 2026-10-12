/**
 * Which target would have paid (#845, operator ask 2026-10-12), under a setup's read-out on its card: every target
 * choice scored side by side on the same triggers since a date (`targetChoicesApi.ts`) -- the count, the win share,
 * mean and sum R, the same net of the stated cost, and how often a choice fell back to the fixed amount -- best
 * first, with the backend's note (no leader below its minimum count). Read-only: it asks only when opened, and a
 * lead changes no template. R is the risk a share, the unit the scores are measured in.
 */
import { useEffect, useState } from 'react';
import {
  BOTS_TARGET_CHOICES_FROM,
  BOTS_TARGET_CHOICES_LABEL,
  BOTS_TARGET_CHOICES_TIP,
} from '../constantGroups/bots_page';
import { tipProps } from '../ux/hoverTip';
import { fmtR } from './botsPageFormat';
import { choiceLabel, fetchTargetChoices, type TargetChoices } from './targetChoicesApi';
import './botTargetChoices.css';

const DATE = /^\d{4}-\d{2}-\d{2}$/;

interface Read {
  data: TargetChoices | null;
  error: string | null;
  loading: boolean;
}

function pct(v: number | null): string {
  return v == null ? '—' : `${v.toFixed(1)}%`;
}

function tone(v: number | null): string {
  return v == null ? '' : v > 0 ? 'is-up' : v < 0 ? 'is-down' : '';
}

function ChoicesTable({ data, short }: { data: TargetChoices; short: boolean }) {
  return (
    <table className="bots-tchoices__table" data-testid="bots-target-choices-table">
      <thead>
        <tr>
          <th>Target</th><th>n</th><th>Win %</th><th>Mean R</th><th>Sum R</th><th>Net mean</th><th>Net sum</th>
          <th {...tipProps('Triggers where the choice had no level and fell back to the fixed amount.')}>Fell back</th>
        </tr>
      </thead>
      <tbody>
        {data.choices.map(c => (
          <tr key={c.name} className={c.name === data.leader ? 'is-leader' : ''} data-testid={`bots-target-choice-${c.name}`}>
            <td>{choiceLabel(c.name, short)}{c.name === data.leader ? ' · leads' : ''}</td>
            <td>{c.n}{c.open ? <small> +{c.open} open</small> : null}</td>
            <td>{pct(c.win_pct)}</td>
            <td className={tone(c.mean_r)}>{fmtR(c.mean_r)}</td>
            <td className={tone(c.sum_r)}>{fmtR(c.sum_r)}</td>
            <td className={tone(c.mean_net_r)}>{fmtR(c.mean_net_r)}</td>
            <td className={tone(c.sum_net_r)}>{fmtR(c.sum_net_r)}</td>
            <td>{c.fell_back}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function BotTargetChoices({ setup, short = false }: { setup: string; short?: boolean }) {
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState(BOTS_TARGET_CHOICES_FROM);
  const [read, setRead] = useState<Read>({ data: null, error: null, loading: false });
  const valid = DATE.test(from);
  useEffect(() => {
    if (!open || !valid) return undefined;
    const ctl = new AbortController();
    setRead(r => ({ ...r, error: null, loading: true }));
    fetchTargetChoices(from, setup, ctl.signal)
      .then(data => setRead({ data, error: null, loading: false }))
      .catch((e: unknown) => {
        if (!ctl.signal.aborted) setRead({ data: null, error: e instanceof Error ? e.message : String(e), loading: false });
      });
    return () => ctl.abort();
  }, [open, valid, from, setup]);
  const data = read.data;
  return (
    <div className="bots-tchoices" data-testid={`bots-target-choices-${setup}`}>
      <button type="button" className="bots-linkbtn bots-tchoices__toggle" aria-expanded={open}
        onClick={() => setOpen(o => !o)} {...tipProps(BOTS_TARGET_CHOICES_TIP, BOTS_TARGET_CHOICES_LABEL)}
        data-testid={`bots-target-choices-toggle-${setup}`}>
        {open ? '▾' : '▸'} {BOTS_TARGET_CHOICES_LABEL}
      </button>
      {open ? (
        <div className="bots-tchoices__body">
          <label className="bots-tchoices__from">
            From
            <input type="date" value={from} onChange={e => setFrom(e.target.value)} onKeyDown={e => e.stopPropagation()}
              data-testid={`bots-target-choices-from-${setup}`} />
          </label>
          {!valid ? <p className="bots-tchoices__note">A start date like {BOTS_TARGET_CHOICES_FROM}.</p> : null}
          {read.loading ? <p className="bots-tchoices__note">Reading the scores…</p> : null}
          {read.error ? <p className="bots-tchoices__error" role="alert">{read.error}</p> : null}
          {data ? (
            <>
              <p className="bots-tchoices__note" data-testid={`bots-target-choices-cost-${setup}`}>
                {data.triggers} trigger{data.triggers === 1 ? '' : 's'} since {data.from}, {data.scored} scored · net of
                {' '}${data.cost.toFixed(2)} a share a fill · a leader needs {data.min_n} scored a choice
              </p>
              {data.choices.length ? <ChoicesTable data={data} short={short} /> : null}
              <p className="bots-tchoices__note" data-testid={`bots-target-choices-note-${setup}`}>{data.note}</p>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
