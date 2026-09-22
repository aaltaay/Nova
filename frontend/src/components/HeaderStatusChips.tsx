/**
 * The status cluster's freshness chips: third-party integrations, the Roster
 * honesty chip (feed_error / subscriptionError / unavailable / last-good) and
 * the Prices age chip. Presentational; HeaderConnectionStatus decides what to
 * show and passes the words.
 */
import { Activity, ListOrdered } from 'lucide-react';
import {
  HEADER_INTEGRATION_CHIP_LABELS,
  HEADER_INTEGRATION_CHIP_ORDER,
} from '../constants';
import { SCANNER_HONESTY_CHIP_ROLE } from '../scanner/scannerHonesty';
import type { HealthStatus, IntegrationChipStatus } from '../types/health';
import { integrationTone, toneDot, type HeaderChipTone } from './headerConnectionStatusModel';

export function HeaderIntegrationChips({ health }: { health: HealthStatus }) {
  return (
    <>
      {HEADER_INTEGRATION_CHIP_ORDER.map((key) => {
        const chip: IntegrationChipStatus | undefined = health.integrations?.[key];
        if (!chip) return null;
        const tone = integrationTone(chip.status);
        const role = HEADER_INTEGRATION_CHIP_LABELS[key] || key;
        return (
          <span
            key={key}
            className={`status-chip status-chip--${tone}`}
            title={chip.detail || `${role} integration status`}
            data-testid={`status-chip-integration-${key}`}
          >
            <span className={`dot ${toneDot(tone)}`} />
            <span className="status-chip__role">{role}</span>
            <span className="status-chip__value">{chip.status}</span>
          </span>
        );
      })}
    </>
  );
}

export function HeaderHonestyChip({ text, compactClass }: { text: string; compactClass: string }) {
  return (
    <span
      className={`status-chip${compactClass} status-chip--warn`}
      title={`${SCANNER_HONESTY_CHIP_ROLE}: ${text}`}
      aria-label={`${SCANNER_HONESTY_CHIP_ROLE}: ${text}`}
      data-testid="status-chip-honesty"
    >
      <span className="dot loading" />
      <ListOrdered className="status-chip__icon" aria-hidden="true" />
      <span className="status-chip__role">{SCANNER_HONESTY_CHIP_ROLE}</span>
      <span className="status-chip__value">{text}</span>
    </span>
  );
}

interface PricesProps {
  text: string;
  tone: HeaderChipTone;
  lastPriceTs?: number | null;
  pricesStale: boolean;
  compactClass: string;
}

export function HeaderPricesChip({ text, tone, lastPriceTs, pricesStale, compactClass }: PricesProps) {
  const title = lastPriceTs === 0
    ? 'No IBKR L1 price_patch has arrived for the active scanner tab.'
    : pricesStale
      ? 'Last successful table price tick is late or skipped -- prices are not live right now.'
      : 'Age of the last successful table price tick for the active scanner tab.';
  return (
    <span
      className={`status-chip${compactClass} status-chip--${tone}`}
      aria-label={`Prices: ${text}`}
      title={`Prices: ${text}\n\n${title}`}
      data-testid="status-chip-prices"
    >
      <span className={`dot ${lastPriceTs === 0 || pricesStale ? 'loading' : 'connected'}`} />
      <Activity className="status-chip__icon" aria-hidden="true" />
      <span className="status-chip__role">Prices</span>
      <span className="status-chip__value">{text}</span>
    </span>
  );
}
