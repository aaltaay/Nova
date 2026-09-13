/**
 * Rewrite local IBC config.ini the same way backend/ibkr/launch_gateway.py
 * aligns TradingMode + IbLoginId. Never logs values.
 */

export type IbcDoor = 'paper' | 'live';

function readIniKey(text: string, key: string): string {
  const prefix = `${key}=`;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    if (line.startsWith(prefix)) return line.slice(prefix.length);
  }
  return '';
}

function rewriteIniKey(text: string, key: string, value: string): string {
  const pattern = new RegExp(`^${key}=.*$`, 'm');
  if (pattern.test(text)) {
    return text.replace(pattern, `${key}=${value}`);
  }
  const ending = text.endsWith('\n') ? '' : '\n';
  return `${text}${ending}${key}=${value}\n`;
}

export function ibcConfigHasCredentials(text: string): boolean {
  return Boolean(readIniKey(text, 'IbLoginId') && readIniKey(text, 'IbPassword'));
}

export function alignIbcConfigIni(text: string, mode: IbcDoor): string {
  const loginKey = mode === 'live' ? 'IbLoginIdLive' : 'IbLoginIdPaper';
  const login = readIniKey(text, loginKey) || readIniKey(text, 'IbLoginId');
  let out = rewriteIniKey(text, 'TradingMode', mode);
  out = rewriteIniKey(out, 'OverrideTwsApiPort', mode === 'live' ? '4001' : '4002');
  if (login) {
    out = rewriteIniKey(out, 'IbLoginId', login);
  }
  return out;
}
