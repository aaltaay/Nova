/**
 * "Just reported" (ADR 066, PNG v1): the newest reports, each with its member's face, its largest trade and how long
 * after the trade it was reported; a scanned or paper report says so and links to the filing. Click a row for the
 * member; every report opens on its own site.
 */
import { PAPER_WORDS } from './constants';
import { Face, PartyBadge } from './Face';
import { chamberWord, day, lagClass, rangeText, seat, sideClass, sideWord } from './format';
import type { ReportRow } from './types';

function ScanIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round" aria-hidden>
      <path d="M15 12h-5M15 8h-5M19 17V5a2 2 0 0 0-2-2H4" />
      <path d="M8 21h12a2 2 0 0 0 2-2v-1a1 1 0 0 0-1-1H11a1 1 0 0 0-1 1v1a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v2a1 1 0 0 0 1 1h3" />
    </svg>
  );
}

export function JustReported({ rows, year, onOpen }: { rows: ReportRow[]; year: number; onOpen: (bioguide: string) => void }) {
  return (
    <section className="cg-card cg-list" data-testid="congress-just-reported">
      <div className="cg-card__head">
        <h3 className="cg-card__title">Just reported</h3>
        <span className="cg-card__source">newest first · every row opens its filing</span>
      </div>
      {rows.length === 0 ? <p className="cg-muted cg-empty">No reports yet for this view.</p> : null}
      {rows.map((r) => {
        const m = r.member;
        const name = m?.name ?? r.filer ?? 'Unknown filer';
        const open = () => m && onOpen(m.bioguide);
        return (
          <div key={r.id} className={`cg-jr${m ? ' is-clickable' : ''}`} onClick={open} data-testid={`congress-report-${r.id}`}
            role={m ? 'button' : undefined} tabIndex={m ? 0 : undefined}
            onKeyDown={(e) => { if (e.key === 'Enter') open(); }}>
            {r.read ? <Face member={m} name={name} size={36} /> : <span className="cg-scan"><ScanIcon /></span>}
            <div className="cg-jr__main">
              <div className="cg-jr__name">
                {name}
                <PartyBadge party={m?.party ?? null} />
                <span className="cg-jr__seat">{m ? `${seat(m)} · ${chamberWord(m.chamber)}` : chamberWord(r.chamber)}</span>
              </div>
              <div className="cg-jr__what">
                {r.top ? (
                  <>
                    <b className={sideClass(r.top)}>{sideWord(r.top)}</b>{' '}
                    {r.top.ticker ?? r.top.asset}{r.top.kind === 'option' ? ' options' : ''} · {rangeText(r.top.amount)}
                    {r.trades > 1 ? <span className="cg-muted"> · +{r.trades - 1} more</span> : null}
                  </>
                ) : r.read ? <span className="cg-muted">No transactions listed</span> : <span className="cg-muted">{PAPER_WORDS}</span>}
                {r.amends ? <span className="cg-muted"> · corrects the {day(r.amends, year)} report</span> : null}
              </div>
            </div>
            <div className="cg-jr__when">
              {day(r.filed, year)}
              {r.top?.lag_days != null ? (
                <span className={`cg-lag ${lagClass(r.top.lag_days)}`}>traded {r.top.lag_days} days before</span>
              ) : (
                <a className="cg-link" href={r.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                  Open filing ↗
                </a>
              )}
            </div>
          </div>
        );
      })}
    </section>
  );
}
