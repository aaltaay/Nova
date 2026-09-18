import { describe, expect, it } from 'vitest';
import {
  formatReleaseTag,
  loadNovaReleaseTag,
  releaseTagFromText,
} from '../../electron/releaseTag.mjs';

describe('releaseTagFromText', () => {
  it('keeps the VERSION vNNN tag', () => {
    expect(releaseTagFromText('v477\n')).toBe('v477');
    expect(releaseTagFromText('v042')).toBe('v042');
    expect(releaseTagFromText('v1000')).toBe('v1000');
  });

  it('maps electron-builder semver 0.1.N to the same public tag', () => {
    expect(releaseTagFromText('0.1.477')).toBe('v477');
    expect(releaseTagFromText('0.1.42')).toBe('v042');
    expect(releaseTagFromText('0.1.1')).toBe('v001');
  });

  it('refuses unknown shapes', () => {
    expect(releaseTagFromText('')).toBe('');
    expect(releaseTagFromText('not-a-version')).toBe('');
    expect(releaseTagFromText('1.2')).toBe('');
  });
});

describe('formatReleaseTag', () => {
  it('pads to at least three digits like tools/bump_version.py', () => {
    expect(formatReleaseTag(1)).toBe('v001');
    expect(formatReleaseTag(42)).toBe('v042');
    expect(formatReleaseTag(477)).toBe('v477');
    expect(formatReleaseTag(1000)).toBe('v1000');
  });
});

describe('loadNovaReleaseTag', () => {
  it('prefers the VERSION file when unpackaged', () => {
    expect(
      loadNovaReleaseTag({
        appVersion: '0.1.1',
        isPackaged: false,
        versionFileText: 'v477\n',
      }),
    ).toBe('v477');
  });

  it('uses app.getVersion() mapping when packaged', () => {
    expect(
      loadNovaReleaseTag({
        appVersion: '0.1.477',
        isPackaged: true,
        versionFileText: 'v001',
      }),
    ).toBe('v477');
  });

  it('falls back to mapped package version when VERSION is missing in dev', () => {
    expect(
      loadNovaReleaseTag({
        appVersion: '0.1.42',
        isPackaged: false,
        versionFileText: '',
      }),
    ).toBe('v042');
  });
});
