import { describe, expect, it } from 'vitest';
import {
  EXECUTION_TRANSPORT_TIMEOUT_MESSAGE,
  EXECUTION_TRANSPORT_UNREACHABLE_MESSAGE,
} from '../constantGroups/features';
import { executionTransportError } from './executionTransportError';

describe('executionTransportError', () => {
  it('does not call a dropped request a network outage', () => {
    expect(executionTransportError(new TypeError('Failed to fetch'))).toBe(
      EXECUTION_TRANSPORT_UNREACHABLE_MESSAGE,
    );
    const abort = new Error('The operation was aborted');
    abort.name = 'AbortError';
    expect(executionTransportError(abort)).toBe(EXECUTION_TRANSPORT_TIMEOUT_MESSAGE);
  });
});
