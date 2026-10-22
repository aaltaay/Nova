/**
 * "Who in Congress trades" (ADR 066, PNG v1): both chambers' seat maps. Every seat, seated by party; a senator who
 * reported trades in the period shows their photo, a representative a lit seat; a scanned-paper-only report a dashed
 * seat. Hover a seat for the member, click it for their page. Not the floor chart: the House has no assigned seats.
 */
import { useMemo, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { CONGRESS_PHOTO_PATH, PARTY_COLOR, periodLabel, PERIODS, SEATS_HELP } from './constants';
import { Face } from './Face';
import { seat } from './format';
import { hemicycle, seatOrder, tally } from './hemicycle';
import { Seg } from './Seg';
import type { Member, Period, Seats } from './types';

const W = 496;
const H = 252;
const R0 = 120;
const R1 = 234;

interface Hover {
  member: Member;
  x: number;
  y: number;
}

function Chamber({ id, members, reported, photos, onOpen, onHover }: {
  id: 'senate' | 'house';
  members: Member[];
  reported: Record<string, 'trades' | 'paper'>;
  photos: boolean;
  onOpen: (bioguide: string) => void;
  onHover: (h: Hover | null) => void;
}) {
  const dot = photos ? 10.6 : 4.7;
  const seated = useMemo(() => seatOrder(members), [members]);
  const spots = useMemo(() => hemicycle(seated.length, photos ? 5 : 11, R0, R1, W / 2, H - dot - 3), [seated.length, photos, dot]);
  return (
    <svg className="cg-hemi__svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${id} seats`} data-testid={`congress-seats-${id}`}>
      <defs>
        <clipPath id={`cg-clip-${id}`} clipPathUnits="objectBoundingBox">
          <circle cx=".5" cy=".5" r=".5" />
        </clipPath>
      </defs>
      {seated.map((m, i) => {
        const s = spots[i];
        if (!s) return null;
        const how = reported[m.bioguide];
        const color = PARTY_COLOR[m.party ?? ''] ?? '#8e8e93';
        const events = {
          onMouseEnter: () => onHover({ member: m, x: s.x, y: s.y }),
          onMouseLeave: () => onHover(null),
          onClick: () => onOpen(m.bioguide),
        };
        const common = { className: `cg-seat cg-seat--${how ?? 'none'}`, 'data-bioguide': m.bioguide, ...events };
        if (how === 'trades' && photos) {
          return (
            <g key={m.bioguide} {...common}>
              <circle cx={s.x} cy={s.y} r={dot + 1.8} fill={color} />
              {m.photo ? (
                <image href={`${API_BASE_URL}${CONGRESS_PHOTO_PATH}/${m.bioguide}`} x={s.x - dot} y={s.y - dot}
                  width={dot * 2} height={dot * 2} preserveAspectRatio="xMidYMin slice" clipPath={`url(#cg-clip-${id})`} />
              ) : (
                <>
                  <circle cx={s.x} cy={s.y} r={dot} fill="#3a3a3c" />
                  <text x={s.x} y={s.y + 3.5} className="cg-seat__ini">{m.name.split(' ').map((w) => w[0]).join('').slice(0, 2)}</text>
                </>
              )}
            </g>
          );
        }
        if (how === 'trades') return <circle key={m.bioguide} {...common} cx={s.x} cy={s.y} r={dot} fill={color} stroke="#f5f5f7" strokeWidth={1} />;
        if (how === 'paper') {
          return <circle key={m.bioguide} {...common} cx={s.x} cy={s.y} r={dot - 0.4} fill={color} fillOpacity={0.35} stroke={color} strokeWidth={1.3} strokeDasharray="1.6 1.4" />;
        }
        return <circle key={m.bioguide} {...common} cx={s.x} cy={s.y} r={dot * (photos ? 0.62 : 0.78)} fill={color} fillOpacity={0.26} />;
      })}
    </svg>
  );
}

export function SeatsCard({ seats, reported, period, year, onPeriod, onOpen }: {
  seats: Seats;
  reported: Record<Period, Record<string, 'trades' | 'paper'>>;
  period: Period;
  year: number;
  onPeriod: (p: Period) => void;
  onOpen: (bioguide: string) => void;
}) {
  const [hover, setHover] = useState<{ chamber: 'senate' | 'house'; h: Hover } | null>(null);
  const shown = reported[period] ?? {};
  const count = (ms: Member[]) => ms.filter((m) => shown[m.bioguide]).length;
  const paperOnly = seats.house.filter((m) => shown[m.bioguide] === 'paper').length;
  const caption = (name: string, ms: Member[], who: string) => (
    <div className="cg-hemi__cap">
      <b>{name}</b>
      <span className="cg-hemi__big"><b>{count(ms)}</b>of {ms.length}</span>
      <span>{who} reported trades</span>
      <span className="cg-hemi__tally">
        {tally(ms).map((t, i) => (
          <span key={t.party} style={{ color: PARTY_COLOR[t.party] }}>{i ? ' · ' : ''}{t.party} {t.count}</span>
        ))}
      </span>
    </div>
  );
  const side = (id: 'senate' | 'house', ms: Member[], photos: boolean, under: string) => (
    <div className="cg-hemi" onMouseLeave={() => setHover(null)}>
      <Chamber id={id} members={ms} reported={shown} photos={photos} onOpen={onOpen}
        onHover={(h) => setHover(h ? { chamber: id, h } : null)} />
      {caption(id === 'senate' ? 'Senate' : 'House', ms, id === 'senate' ? 'senators' : 'members')}
      <div className="cg-hemi__under">{under}</div>
      {hover?.chamber === id ? (
        <div className="cg-callout" style={{ left: `${(100 * hover.h.x) / W}%`, top: `${(100 * hover.h.y) / H}%` }}
          data-testid="congress-seat-callout">
          <Face member={hover.h.member} size={30} ring={PARTY_COLOR[hover.h.member.party ?? '']} />
          <div>
            <b>{hover.h.member.name}</b>
            <span>{seat(hover.h.member)} · {shown[hover.h.member.bioguide] === 'trades' ? 'reported trades' : shown[hover.h.member.bioguide] === 'paper' ? 'paper report only' : 'no trade reports'}</span>
          </div>
        </div>
      ) : null}
    </div>
  );
  const former = seats.former.map((m) => `${m.name} (left ${m.left ?? '?'})`).join(', ');
  return (
    <section className="cg-card cg-seats" data-testid="congress-seats">
      <div className="cg-card__head">
        <h3 className="cg-card__title">Who in Congress trades</h3>
        <span className="cg-muted cg-small" title={SEATS_HELP}>every seat · seated by party, not the floor chart</span>
        <Seg value={period} options={PERIODS} label={(p) => periodLabel(p, year)} onPick={onPeriod} testId="congress-seats-period" />
      </div>
      <div className="cg-hemis">
        {side('senate', seats.senate, true, former ? `+ reported, no longer seated: ${former}` : seats.empty.senate ? `${seats.empty.senate} empty seats` : '')}
        {side('house', seats.house, false, [seats.empty.house ? `${seats.empty.house} empty seats` : '', paperOnly ? `${paperOnly} filed only scanned paper` : ''].filter(Boolean).join(' · '))}
      </div>
      <div className="cg-legend">
        <span><i className="cg-key cg-key--on" />Photo or bright seat: reported trades</span>
        <span><i className="cg-key cg-key--paper" />Scanned paper only</span>
        <span><i className="cg-key cg-key--off" />No trade reports</span>
        <span className="cg-muted cg-push">Click a seat to open that member</span>
      </div>
    </section>
  );
}
