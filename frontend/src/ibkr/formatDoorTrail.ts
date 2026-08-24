/** Format Paper/Live door-trail rows for the operator UI. No account ids. */

export type DoorTrailEvent = {
  schema_version?: number;
  ts?: number;
  actor?: string;
  event?: string;
  requested?: string;
  kind_before?: string;
  kind_after?: string;
  plan?: string;
  launch_action?: string;
  switched?: boolean;
  note?: string;
};

const EVENT_LABEL: Record<string, string> = {
  click: 'Click',
  attached: 'Attached',
  refused: 'Refused',
  ibc_trading_mode: 'IBC trading mode',
  ibc_clicked_login: 'IBC clicked Log In',
  ibc_authenticating: 'Authenticating',
  ibc_login_completed: 'IBC login completed',
  ibc_simulated_trading: 'Simulated Trading (paper)',
  ibc_second_factor: 'Second Factor / IBKR Mobile',
};

export function doorTrailEventLabel(event: string | undefined): string {
  const key = String(event || '').trim();
  if (!key) return 'Unknown';
  return EVENT_LABEL[key] ?? key.replace(/_/g, ' ');
}

export function formatDoorTrailTime(ts: number | undefined): string {
  const n = Number(ts);
  if (!Number.isFinite(n) || n <= 0) return '--';
  const d = new Date(n * 1000);
  if (Number.isNaN(d.getTime())) return '--';
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function formatDoorTrailLine(row: DoorTrailEvent): string {
  const parts = [doorTrailEventLabel(row.event)];
  if (row.requested) parts.push(String(row.requested));
  if (row.plan) parts.push(`plan ${row.plan}`);
  if (row.launch_action) parts.push(row.launch_action);
  if (row.kind_before && row.kind_after) {
    parts.push(`${row.kind_before} -> ${row.kind_after}`);
  } else if (row.kind_after) {
    parts.push(`kind ${row.kind_after}`);
  }
  if (row.switched === true) parts.push('switched');
  if (row.switched === false) parts.push('no switch');
  if (row.note) parts.push(row.note);
  return parts.join(' -- ');
}

export function newestFirst(rows: DoorTrailEvent[]): DoorTrailEvent[] {
  return [...rows].reverse();
}
