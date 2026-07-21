/** Side-by-side Alpaca vs IBKR listing flags — never merged into one Yes/No. */
import {
  QUOTE_ASSET_LABELS,
  QUOTE_BROKER_SECTION_TITLE,
  QUOTE_LISTING_ALPACA_TITLE,
  QUOTE_LISTING_COMPARE_HINT,
  QUOTE_LISTING_IBKR_TITLE,
} from '../constants';
import type { AssetInfo, IbkrListingFlags, ListingCompare } from '../types/ticker';
import {
  fmtMaintMarginPct,
  fmtMarginReqString,
  fmtYesNo,
  formatAssetAttributeList,
} from '../utils/quoteFormat';

interface Props {
  asset: AssetInfo | null | undefined;
  listing?: ListingCompare | null;
}

function fmtShortType(value: string | null | undefined): string {
  if (!value) return '—';
  return value.replace(/_/g, ' ');
}

function fmtShares(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function alpacaFromAsset(asset: AssetInfo | null | undefined): ListingCompare['alpaca'] {
  const shortable = asset?.shortable;
  const etb = asset?.easy_to_borrow;
  let short_type: string | null = null;
  if (shortable === true && etb === true) short_type = 'easy_to_borrow';
  else if (shortable === true && etb === false) short_type = 'hard_to_borrow';
  else if (shortable === false) short_type = 'not_shortable';
  return {
    source: 'alpaca_assets',
    status: asset?.status ?? null,
    tradable: asset?.tradable ?? null,
    shortable: shortable ?? null,
    easy_to_borrow: etb ?? null,
    short_type,
    short_type_detail: null,
    marginable: asset?.marginable ?? null,
    fractionable: asset?.fractionable ?? null,
    maintenance_margin_requirement: asset?.maintenance_margin_requirement ?? null,
    margin_requirement_long: asset?.margin_requirement_long ?? null,
    margin_requirement_short: asset?.margin_requirement_short ?? null,
    asset_class: asset?.asset_class ?? null,
    exchange: asset?.exchange ?? null,
    attributes: asset?.attributes ?? [],
    error: asset ? null : 'Alpaca asset metadata empty',
  };
}

function ibkrCell(ibkr: IbkrListingFlags | null | undefined, field: string): string {
  if (!ibkr) return '—';
  if (ibkr.error && !ibkr.qualified && field !== 'error') {
    if (field === 'status') return ibkr.connected === false ? 'offline' : '—';
  }
  switch (field) {
    case 'status':
      if (!ibkr.connected) return 'offline';
      if (ibkr.qualified) return 'qualified';
      return ibkr.error ? 'error' : '—';
    case 'tradable':
      return ibkr.tradable_hint || (ibkr.qualified ? 'qualified' : '—');
    case 'shortable':
      return fmtShares(ibkr.shortable_shares);
    case 'short_type':
      return fmtShortType(ibkr.short_type);
    case 'marginable':
      return '—';
    case 'stock_type':
      return ibkr.stock_type || '—';
    case 'exchange':
      return ibkr.exchange || '—';
    case 'detail':
      return ibkr.short_type_detail || ibkr.error || '—';
    default:
      return '—';
  }
}

export function TickerBrokerGrid({ asset, listing }: Props) {
  const alpaca = listing?.alpaca ?? alpacaFromAsset(asset);
  const ibkr = listing?.ibkr ?? null;

  const rows: { label: string; alpaca: string; ibkr: string; alpacaTitle?: string; ibkrTitle?: string }[] = [
    {
      label: QUOTE_ASSET_LABELS.status,
      alpaca: alpaca.status ? String(alpaca.status) : '—',
      ibkr: ibkrCell(ibkr, 'status'),
      ibkrTitle: ibkr?.error || undefined,
    },
    {
      label: QUOTE_ASSET_LABELS.tradable,
      alpaca: fmtYesNo(alpaca.tradable ?? undefined),
      ibkr: ibkrCell(ibkr, 'tradable'),
    },
    {
      label: QUOTE_ASSET_LABELS.shortable,
      alpaca: fmtYesNo(alpaca.shortable ?? undefined),
      ibkr: ibkrCell(ibkr, 'shortable'),
      alpacaTitle: 'Alpaca shortable flag (platform inventory)',
      ibkrTitle: 'IBKR shortableShares (tick 236) — not Alpaca ETB',
    },
    {
      label: QUOTE_ASSET_LABELS.shortType,
      alpaca: fmtShortType(alpaca.short_type),
      ibkr: ibkrCell(ibkr, 'short_type'),
      alpacaTitle: alpaca.short_type_detail || undefined,
      ibkrTitle: ibkr?.short_type_detail || undefined,
    },
    {
      label: QUOTE_ASSET_LABELS.easyToBorrow,
      alpaca: fmtYesNo(alpaca.easy_to_borrow ?? undefined),
      ibkr: 'n/a',
      alpacaTitle: 'Alpaca easy_to_borrow only',
      ibkrTitle: 'IBKR has no ETB boolean — use shortable shares / locate',
    },
    {
      label: QUOTE_ASSET_LABELS.marginable,
      alpaca: fmtYesNo(alpaca.marginable ?? undefined),
      ibkr: ibkrCell(ibkr, 'marginable'),
      ibkrTitle: 'IBKR margin requirements not exposed on this snapshot',
    },
    {
      label: QUOTE_ASSET_LABELS.fractionable,
      alpaca: fmtYesNo(alpaca.fractionable ?? undefined),
      ibkr: '—',
    },
    {
      label: QUOTE_ASSET_LABELS.maintMargin,
      alpaca: fmtMaintMarginPct(alpaca.maintenance_margin_requirement ?? null),
      ibkr: '—',
    },
    {
      label: QUOTE_ASSET_LABELS.marginLong,
      alpaca: fmtMarginReqString(alpaca.margin_requirement_long ?? null),
      ibkr: '—',
    },
    {
      label: QUOTE_ASSET_LABELS.marginShort,
      alpaca: fmtMarginReqString(alpaca.margin_requirement_short ?? null),
      ibkr: '—',
    },
    {
      label: QUOTE_ASSET_LABELS.assetClass,
      alpaca: alpaca.asset_class ? String(alpaca.asset_class) : '—',
      ibkr: ibkrCell(ibkr, 'stock_type'),
    },
    {
      label: QUOTE_ASSET_LABELS.attributes,
      alpaca: formatAssetAttributeList(alpaca.attributes),
      ibkr: ibkr?.long_name || '—',
      ibkrTitle: ibkr?.long_name ? 'IBKR long name' : undefined,
    },
  ];

  return (
    <>
      <div className="cq-section-title">{QUOTE_BROKER_SECTION_TITLE}</div>
      <p className="cq-listing-compare-hint">{QUOTE_LISTING_COMPARE_HINT}</p>
      <div className="cq-listing-compare" data-testid="listing-compare">
        <table>
          <thead>
            <tr>
              <th scope="col">Field</th>
              <th scope="col">{QUOTE_LISTING_ALPACA_TITLE}</th>
              <th scope="col">{QUOTE_LISTING_IBKR_TITLE}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <th scope="row">{row.label}</th>
                <td
                  className={alpaca.tradable === false && row.label === QUOTE_ASSET_LABELS.tradable ? 'negative' : undefined}
                  title={row.alpacaTitle}
                >
                  {row.alpaca}
                </td>
                <td title={row.ibkrTitle}>{row.ibkr}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
