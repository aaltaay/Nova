/**
 * A member's face (ADR 066): the official portrait the desk keeps, or their initials when none is kept -- said as
 * such on hover, never a stand-in picture. The party badge beside a name.
 */
import { useState } from 'react';
import { API_BASE_URL } from '../constants';
import { CONGRESS_PHOTO_PATH, PARTY_COLOR, PARTY_NAME } from './constants';
import { initials } from './format';
import type { Member } from './types';

interface FaceProps {
  member: Pick<Member, 'bioguide' | 'name' | 'party' | 'photo'> | null;
  name?: string | null;
  size?: number;
  ring?: string | null;
  testId?: string;
}

export function Face({ member, name, size = 34, ring = null, testId }: FaceProps) {
  const [broken, setBroken] = useState(false);
  const label = member?.name ?? name ?? '?';
  const style = { width: size, height: size, boxShadow: ring ? `0 0 0 2px ${ring}` : undefined };
  if (member?.photo && !broken) {
    return (
      <img
        className="cg-face"
        src={`${API_BASE_URL}${CONGRESS_PHOTO_PATH}/${encodeURIComponent(member.bioguide)}`}
        alt={label}
        title={label}
        style={style}
        onError={() => setBroken(true)}
        data-testid={testId}
      />
    );
  }
  return (
    <span
      className="cg-face cg-face--initials"
      style={{ ...style, fontSize: Math.round(size * 0.36) }}
      title={`${label} -- no official portrait kept`}
      data-testid={testId}
    >
      {initials(label)}
    </span>
  );
}

export function PartyBadge({ party, size = 17 }: { party: string | null; size?: number }) {
  if (!party) return null;
  return (
    <span
      className="cg-party"
      style={{ width: size, height: size, background: PARTY_COLOR[party] ?? '#636366' }}
      title={PARTY_NAME[party] ?? party}
    >
      {party}
    </span>
  );
}

/** Up to `n` faces overlapped, then "+k". */
export function FaceStack({ members, ring, n = 4, size = 26 }: {
  members: (Pick<Member, 'bioguide' | 'name' | 'party' | 'photo'> | null)[];
  ring: string;
  n?: number;
  size?: number;
}) {
  const shown = members.slice(0, n);
  return (
    <span className="cg-stack" style={{ ['--cg-ring' as string]: ring }}>
      {shown.map((m, i) => (
        <span className="cg-stack__one" key={m?.bioguide ?? i}>
          <Face member={m} size={size} />
        </span>
      ))}
      {members.length > n ? <span className="cg-stack__more">+{members.length - n}</span> : null}
    </span>
  );
}
