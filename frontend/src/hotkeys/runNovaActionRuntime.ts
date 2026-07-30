/**
 * Runtime shape for Nova Action execution (shared across executor modules).
 */

import type { IbkrPosition } from '../ibkr/types';
import type { TopOfBook } from './TopOfBookContext';

export interface NovaActionRuntime {
  symbol: string | null;
  connected: boolean;
  spendStatus?: string;
  /** paper | live | disconnected — shown in confirm dialogs. */
  accountMode?: string;
  /** Set when useIbkrAccount last poll failed — block exit/flatten actions. */
  accountError?: string | null;
  position: IbkrPosition | null;
  topOfBook: TopOfBook | null;
  /** Called when place-confirm is required; return true to proceed. */
  requestConfirm?: (summary: string) => Promise<boolean>;
}
