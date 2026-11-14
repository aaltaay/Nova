/**
 * Settings > Strategies (ADR 072; approved mockup retire-bots v1): every strategy with a scanner, its side, the
 * template in play, what it watches (Level 1) and how many setups it has on today's board, with Edit opening the
 * parameters-and-templates editor the Bots page had. Every strategy only watches: none places an order, on any
 * venue. A strategy's count opens the Setups board (Scanner > Contenders > Setups) on that strategy's chip, where
 * its forming names are. Nothing here places an order.
 */
import { useState } from 'react';
import {
  STRATEGIES_SETTINGS_BLURB,
  STRATEGIES_SETTINGS_EDITOR_NOTE,
  STRATEGIES_SETTINGS_LOADING,
  STRATEGIES_SETTINGS_OPEN_BOARD,
  STRATEGIES_SETTINGS_TITLE,
  STRATEGIES_SETTINGS_WATCHING,
  STRATEGIES_SETTINGS_YOURS,
} from '../constantGroups/bots_page';
import { SETUP_SIDE_TAG, SETUP_SIDE_TAG_TIPS } from '../constantGroups/short_setups';
import { requestSetupsBoard, setupLabel, useSetupsBoard } from '../setups';
import { tipProps } from '../ux/hoverTip';
import { requestScannerTab } from '../workspace';
import { BotTemplateEditor } from './BotTemplateEditor';
import { useSetupTemplates } from './useSetupTemplates';
import './strategiesSettings.css';

export function StrategiesSettings({ onClose }: { onClose?: () => void }) {
  const tpl = useSetupTemplates();
  const board = useSetupsBoard()?.board ?? null;
  const [editing, setEditing] = useState<string | null>(null);
  const setups = (tpl.payload?.setups ?? []).filter(s => s.scanner);
  const today = (id: string): number | null =>
    board ? board.rows.filter(r => (r.setup_type ?? 'first_pullback') === id).length : null;

  const openBoard = (id: string) => {
    requestSetupsBoard(id);
    requestScannerTab('watchlist');
    onClose?.();
  };

  return (
    <section className="strategies-settings" data-testid="settings-strategies">
      <h4>{STRATEGIES_SETTINGS_TITLE}</h4>
      <p>{STRATEGIES_SETTINGS_BLURB}</p>
      {tpl.error ? <p className="strategies-settings__error" role="alert">{tpl.error}</p> : null}
      {tpl.payload == null && !tpl.error ? <p className="strategies-settings__muted" role="status">{STRATEGIES_SETTINGS_LOADING}</p> : null}
      {setups.length ? (
        <table className="strategies-settings__table">
          <thead>
            <tr>
              <th>Strategy</th><th>Side</th><th>Template in play</th><th>Watching</th>
              <th className="is-num">Setups today</th><th aria-label="Edit" />
            </tr>
          </thead>
          <tbody>
            {setups.map(s => {
              const inPlay = s.templates.find(t => t.id === s.in_play) ?? null;
              const n = today(s.id);
              const label = setupLabel(s.id);
              const side = s.side === 'short' ? 'short' : 'long';
              return (
                <tr key={s.id} data-testid={`settings-strategy-${s.id}`}>
                  <td>{label}</td>
                  <td>
                    <span className={`strategies-settings__side is-${side}`} {...tipProps(SETUP_SIDE_TAG_TIPS[side])}>
                      {SETUP_SIDE_TAG[side]}
                    </span>
                  </td>
                  <td>
                    {inPlay?.name ?? '—'}
                    {inPlay && !inPlay.builtin ? <i> · {STRATEGIES_SETTINGS_YOURS}</i> : null}
                  </td>
                  <td className="strategies-settings__watch">{STRATEGIES_SETTINGS_WATCHING}</td>
                  <td className="is-num">
                    {n == null ? '—' : (
                      <button type="button" className="strategies-settings__count" data-testid={`settings-strategy-count-${s.id}`}
                        {...tipProps(STRATEGIES_SETTINGS_OPEN_BOARD(label), label)} onClick={() => openBoard(s.id)}>
                        {n}
                      </button>
                    )}
                  </td>
                  <td className="is-num">
                    <button type="button" className="strategies-settings__edit" data-testid={`settings-strategy-edit-${s.id}`}
                      onClick={() => setEditing(s.id)}>Edit</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : null}
      <p className="strategies-settings__muted">{STRATEGIES_SETTINGS_EDITOR_NOTE}</p>
      <BotTemplateEditor open={editing != null} setup={editing ? tpl.setup(editing) : null}
        maxPerSetup={tpl.payload?.max_per_setup ?? 6} onClose={() => setEditing(null)} onApply={tpl.apply} />
    </section>
  );
}
