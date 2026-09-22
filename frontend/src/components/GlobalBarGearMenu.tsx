/**
 * The gear at the end of the global bar and its popover -- the homes for what
 * left the row in the redesign: Reload backend · Theme · Gateway & feed status
 * (the checklist, plus the full status cluster as details) · sample data door
 * · Settings…. Nothing is lost; it is one click deeper.
 */
import { Settings } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import {
  GLOBAL_BAR_GEAR_ARIA,
  GLOBAL_BAR_GEAR_TITLE,
  GLOBAL_BAR_MENU_GATEWAY_LABEL,
  GLOBAL_BAR_MENU_GATEWAY_TITLE,
  GLOBAL_BAR_MENU_SAMPLE_EXIT_LABEL,
  GLOBAL_BAR_MENU_SAMPLE_OPEN_LABEL,
  GLOBAL_BAR_MENU_SAMPLE_TITLE,
  GLOBAL_BAR_MENU_SETTINGS_LABEL,
  GLOBAL_BAR_MENU_THEME_LABEL,
  GLOBAL_BAR_SETTINGS_TITLE,
} from '../constants';
import { openTradingPrerequisites } from '../ibkr/tradingPrereqUi';
import { useSettingsOptional } from '../settings/SettingsContext';
import { canReloadLocalBackend } from '../utils/startLocalApi';
import { BackendReloadButton } from './BackendReloadButton';
import type { GlobalAppBarScanner } from './globalAppBarScanner';
import { HeaderConnectionStatus } from './HeaderConnectionStatus';
import { apiProcessOk } from './headerConnectionStatusModel';
import { ThemeToggle } from './ThemeToggle';

interface Props {
  scanner: GlobalAppBarScanner | null;
  ibkrAccountKind: string | null;
  ibkrIntentionalMode: 'paper' | 'live' | null;
  onOpenSymbol: (symbol: string) => void;
}

export function GlobalBarGearMenu({ scanner, ibkrAccountKind, ibkrIntentionalMode, onOpenSymbol }: Props) {
  const settingsApi = useSettingsOptional();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const settingsOpen = settingsApi?.settings.showSettings ?? false;
  const apiOk = scanner ? apiProcessOk(scanner.health) : true;
  const canReload = apiOk && !scanner?.sampleDataActive && canReloadLocalBackend();
  const sampleToggle = scanner?.onSampleDataToggle;

  return (
    <div className="global-app-bar__gear" ref={wrapRef}>
      <button
        type="button"
        className={`global-app-bar__icon-btn global-app-bar__gear-btn${open || settingsOpen ? ' is-active' : ''}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={GLOBAL_BAR_GEAR_ARIA}
        title={GLOBAL_BAR_GEAR_TITLE}
        data-testid="global-bar-gear"
        onClick={() => setOpen((v) => !v)}
      >
        <Settings className="global-app-bar__icon" aria-hidden="true" />
      </button>
      {open && (
        <div
          id={menuId}
          className="global-app-bar__card global-app-bar__gear-menu"
          role="menu"
          aria-label={GLOBAL_BAR_GEAR_ARIA}
          data-testid="global-bar-gear-menu"
        >
          {canReload && (
            <div className="global-app-bar__gear-row" role="none">
              <BackendReloadButton onReloaded={scanner?.onBackendStarted} />
            </div>
          )}
          <div className="global-app-bar__gear-row" role="none" data-testid="global-bar-theme-row">
            <span className="global-app-bar__gear-label">{GLOBAL_BAR_MENU_THEME_LABEL}</span>
            <ThemeToggle />
          </div>
          <button
            type="button"
            role="menuitem"
            className="global-app-bar__menu-action"
            title={GLOBAL_BAR_MENU_GATEWAY_TITLE}
            data-testid="global-bar-gateway-status"
            onClick={() => {
              openTradingPrerequisites();
              setOpen(false);
            }}
          >
            {GLOBAL_BAR_MENU_GATEWAY_LABEL}
          </button>
          {scanner && (
            <div className="global-app-bar__gear-status" role="none" data-testid="global-bar-gear-status">
              <HeaderConnectionStatus
                embedded
                health={scanner.health}
                discoveryProvider={scanner.discoveryProvider}
                ibkrConnected={scanner.ibkrConnected}
                ibkrMode={scanner.ibkrMode}
                ibkrGatewayMode={scanner.ibkrGatewayMode}
                ibkrAccountKind={ibkrAccountKind}
                ibkrIntentionalMode={ibkrIntentionalMode}
                activeFeed={scanner.activeFeed}
                feedFellBack={scanner.feedFellBack}
                secondsAgo={scanner.secondsAgo}
                lastPriceTs={scanner.lastPriceTs}
                pricesStale={scanner.pricesStale}
                honestyText={scanner.honestyText}
                historyDate={scanner.historyDate}
                showScannerSource={scanner.showScannerSource ?? true}
                onBackendStarted={scanner.onBackendStarted}
                onOpenSymbol={onOpenSymbol}
              />
            </div>
          )}
          {sampleToggle && (
            <button
              type="button"
              role="menuitem"
              className="global-app-bar__menu-action"
              title={GLOBAL_BAR_MENU_SAMPLE_TITLE}
              data-testid="global-bar-sample-data"
              onClick={() => {
                sampleToggle(!scanner?.sampleDataActive);
                setOpen(false);
              }}
            >
              {scanner?.sampleDataActive ? GLOBAL_BAR_MENU_SAMPLE_EXIT_LABEL : GLOBAL_BAR_MENU_SAMPLE_OPEN_LABEL}
            </button>
          )}
          {settingsApi && (
            <>
              <div className="global-app-bar__menu-divider" role="none" />
              <button
                type="button"
                role="menuitem"
                className="global-app-bar__menu-action"
                title={GLOBAL_BAR_SETTINGS_TITLE}
                aria-pressed={settingsOpen}
                data-testid="global-bar-settings"
                onClick={() => {
                  settingsApi.toggleSettings();
                  setOpen(false);
                }}
              >
                {GLOBAL_BAR_MENU_SETTINGS_LABEL}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
