/**
 * @vitest-environment jsdom
 *
 * V4: the sample desk has no bot. Its Bots page is a stated absence and asks
 * the backend for nothing -- no session, no kill switch, no practice history.
 */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SAMPLE_BOT_ABSENT } from '../sample_data/sampleCopy';
import { BotsPage } from './BotsPage';

vi.mock('../sample_data/useSampleRoute', () => ({ useSampleRoute: () => true }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('Bots page on the sample desk', () => {
  it('states the absence and polls nothing', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<BotsPage />);
    expect(screen.getByText(SAMPLE_BOT_ABSENT)).toBeTruthy();
    expect(screen.queryByTestId('bots-hero')).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
