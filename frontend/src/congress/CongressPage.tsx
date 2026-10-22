/**
 * The Congress page (ADR 066; PNG v1 approved 2026-10-14, build asked 2026-10-21): what members of Congress
 * reported trading, read from their own House and Senate reports. Trades (the overview: both chambers' seats with
 * the members' photos, the newest reports, the most traded stocks, the most active members, how late trades are
 * reported), Members and Following; a member's page and a stock's page. Read-only: nothing here places an order.
 * Nothing is read before the operator agrees, once, to the reports' use rule.
 */
import { useMemo, useState } from 'react';
import { useSampleRoute } from '../sample_data/useSampleRoute';
import { useCongressBoard } from './api';
import { ConsentCard } from './ConsentCard';
import { CONGRESS_OFF, CONGRESS_OLD_API, CONGRESS_SUBTITLE, CONGRESS_TITLE, FILTERS, SAMPLE_NOTE } from './constants';
import { etTime } from './format';
import { JustReported } from './JustReported';
import { LagCard } from './LagCard';
import { MembersView } from './MembersView';
import { MemberView } from './MemberView';
import { MostActive } from './MostActive';
import { MostTraded } from './MostTraded';
import { toggleFollow, useCongressPrefs } from './prefs';
import { SearchBox } from './SearchBox';
import { SeatsCard } from './SeatsCard';
import { TickerView } from './TickerView';
import type { Board, Filter, Member, View } from './types';
import './congress.css';

type Topic = Filter | 'following';

function statusLine(board: Board): { text: string; cls: string } {
  const filings = board.sources.filter((s) => s.id === 'house' || s.id === 'senate');
  const failing = board.sources.find((s) => s.state === 'failing');
  const left = filings.reduce((n, s) => n + (s.state === 'reading' ? s.todo : 0), 0);
  if (failing) return { text: `${failing.name}: ${failing.error ?? 'not answering'}`, cls: 'is-warn' };
  if (filings.some((s) => s.state === 'reading')) return { text: `Reading reports · ${left} left`, cls: 'is-busy' };
  if (filings.some((s) => s.state === 'waiting')) return { text: 'Starting to read the reports', cls: 'is-busy' };
  const at = Math.max(...filings.map((s) => s.read_at ?? 0));
  return { text: at ? `House + Senate filings read ${etTime(at)} ET` : 'Not read yet', cls: at ? 'is-open' : '' };
}

export function CongressPage({ onOpenTrader }: { onOpenTrader: (symbol: string) => void }) {
  const sample = useSampleRoute();
  const [prefs, setPrefs] = useCongressPrefs(!sample);
  const [view, setView] = useState<View>({ kind: 'trades' });
  const [topic, setTopic] = useState<Topic>('all');
  const [query, setQuery] = useState('');
  const filter: Filter = topic === 'following' ? 'all' : topic;
  const members = topic === 'following' ? prefs.following : null;
  const { data: board, error, missing, reload } = useCongressBoard(filter, members);
  const byBio = useMemo(() => {
    const map = new Map<string, Member>();
    if (board) {
      [...board.seats.senate, ...board.seats.house, ...board.seats.delegates, ...board.seats.former].forEach((m) => map.set(m.bioguide, m));
      board.just_reported.forEach((r) => r.member && map.set(r.member.bioguide, r.member));
    }
    return map;
  }, [board]);

  const openMember = (bioguide: string) => setView({ kind: 'member', bioguide });
  const openTicker = (ticker: string) => setView({ kind: 'ticker', ticker });
  const back = () => setView({ kind: 'trades' });
  const year = board?.year ?? new Date().getFullYear();
  const totalMembers = board ? board.seats.senate.length + board.seats.house.length + board.seats.delegates.length : 0;

  const head = (
    <div className="cg-head cg-head">
      <h2 className="cg-head__title">{CONGRESS_TITLE}</h2>
      <div className="cg-ptabs" role="tablist">
        {([['trades', 'Trades', null], ['members', 'Members', totalMembers || null], ['following', 'Following', prefs.following.length || null]] as const)
          .map(([id, label, n]) => (
            <button key={id} type="button" role="tab" aria-selected={view.kind === id} className={view.kind === id ? 'is-on' : ''}
              onClick={() => setView({ kind: id } as View)} data-testid={`congress-tab-${id}`}>
              {label}{n ? <b>{n}</b> : null}
            </button>
          ))}
      </div>
      <p className="cg-head__sub">{sample ? SAMPLE_NOTE : CONGRESS_SUBTITLE}</p>
      {board ? <span className={`cg-status cg-status ${statusLine(board).cls}`} data-testid="congress-status">{statusLine(board).text}</span> : null}
    </div>
  );

  if (missing || (board && !board.enabled) || !board) {
    return (
      <div className="cg-page cg-page" data-testid="congress-page">
        {head}
        <p className="cg-muted" role="status">{missing ? CONGRESS_OLD_API : board && !board.enabled ? CONGRESS_OFF : error ?? 'Reading the reports …'}</p>
      </div>
    );
  }
  if (board.consent.state !== 'given') {
    return <div className="cg-page cg-page" data-testid="congress-page">{head}<ConsentCard consent={board.consent} onGiven={reload} /></div>;
  }

  const topics = (
    <div className="cg-topics">
      {FILTERS.map(({ id, label }) => {
        const n = id === 'following' ? prefs.following.length : board.counts[id as Filter];
        return (
          <button key={id} type="button" className={`cg-topic${topic === id ? ' is-on' : ''}`} onClick={() => setTopic(id)}
            data-testid={`congress-topic-${id}`}>
            {id === 'following' ? '★ ' : ''}{label}<span>{n?.toLocaleString() ?? ''}</span>
          </button>
        );
      })}
      <SearchBox query={query} onQuery={setQuery} members={byBio} onMember={openMember} onTicker={openTicker} />
    </div>
  );
  const follow = (b: string) => setPrefs(toggleFollow(prefs, b));
  let body;
  if (view.kind === 'member') {
    body = <MemberView bioguide={view.bioguide} year={year} following={prefs.following.includes(view.bioguide)}
      onToggleFollow={() => follow(view.bioguide)} onBack={back} onTicker={openTicker} />;
  } else if (view.kind === 'ticker') {
    body = <TickerView ticker={view.ticker} year={year} onBack={back} onOpenMember={openMember} onOpenTrader={onOpenTrader} />;
  } else if (view.kind === 'members' || view.kind === 'following') {
    body = <MembersView year={year} chamber={topic === 'house' || topic === 'senate' ? topic : null} query={query}
      only={view.kind === 'following' ? prefs.following : null} following={prefs.following} onToggleFollow={follow} onOpen={openMember} />;
  } else {
    body = (
      <>
        <div className="cg-row-a">
          <SeatsCard seats={board.seats} reported={board.reported} period={prefs.seatsPeriod} year={year}
            onPeriod={(p) => setPrefs({ ...prefs, seatsPeriod: p })} onOpen={openMember} />
          <JustReported rows={board.just_reported} year={year} onOpen={openMember} />
        </div>
        <div className="cg-row-b">
          <MostTraded rows={board.most_traded[prefs.tradedPeriod] ?? []} period={prefs.tradedPeriod} year={year}
            from={board.periods[prefs.tradedPeriod].from} byBio={byBio}
            onPeriod={(p) => setPrefs({ ...prefs, tradedPeriod: p })} onTicker={openTicker} />
          <div className="cg-col">
            <MostActive rows={board.most_active} total={totalMembers} onOpen={openMember} onAll={() => setView({ kind: 'members' })} />
            <LagCard lag={board.lag} />
          </div>
        </div>
      </>
    );
  }
  return (
    <div className="cg-page cg-page" data-testid="congress-page">
      {head}
      {topics}
      {error ? <p className="is-warn cg-small" role="alert">{error}</p> : null}
      {body}
    </div>
  );
}
