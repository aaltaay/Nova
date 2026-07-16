/**
 * DAS .htk parse/export — short records and ~byteLength continuation chunks.
 * Splits only the first two `:` delimiters so nested RT:STOP / http:// survive.
 */

import {
  HOTKEY_HTK_CHUNK_BYTES,
  HOTKEY_HTK_NAME_MAX_CHARS,
  HOTKEY_HTK_SHORT_SCRIPT_MAX_BYTES,
} from '../constants';
import type { HotkeyKeyChord, HotkeyRecord, HtkParseIssue, HtkParseResult } from './types';

/** Re-export DAS .htk layout constants for tests / callers. */
export const HTK_SHORT_SCRIPT_MAX_BYTES = HOTKEY_HTK_SHORT_SCRIPT_MAX_BYTES;
export const HTK_CHUNK_BYTES = HOTKEY_HTK_CHUNK_BYTES;
export const HTK_NAME_MAX_CHARS = HOTKEY_HTK_NAME_MAX_CHARS;

let _idSeq = 0;

export function resetHtkIdSeqForTests(): void {
  _idSeq = 0;
}

function nextId(): string {
  _idSeq += 1;
  return `hk_${Date.now().toString(36)}_${_idSeq}`;
}

/** Split on the first two colons only. */
export function splitHtkFields(line: string): [string, string, string] | null {
  const first = line.indexOf(':');
  if (first < 0) return null;
  const second = line.indexOf(':', first + 1);
  if (second < 0) return null;
  return [
    line.slice(0, first),
    line.slice(first + 1, second),
    line.slice(second + 1),
  ];
}

export function parseKeyChord(label: string): HotkeyKeyChord {
  const trimmed = label.trim();
  if (!trimmed) {
    return { label: '', key: '' };
  }
  const parts = trimmed.split('+').map((p) => p.trim()).filter(Boolean);
  if (parts.length === 0) {
    return { label: trimmed, key: trimmed };
  }
  const chord: HotkeyKeyChord = { label: trimmed, key: '' };
  const keyPart = parts[parts.length - 1] ?? '';
  for (let i = 0; i < parts.length - 1; i++) {
    const mod = parts[i].toLowerCase();
    if (mod === 'ctrl' || mod === 'control') chord.ctrl = true;
    else if (mod === 'shift') chord.shift = true;
    else if (mod === 'alt') chord.alt = true;
    else if (mod === 'win' || mod === 'meta' || mod === 'cmd' || mod === 'command') {
      chord.meta = true;
    }
  }
  chord.key = keyPart;
  return chord;
}

export function formatKeyChord(chord: HotkeyKeyChord): string {
  if (chord.label) return chord.label;
  const parts: string[] = [];
  if (chord.ctrl) parts.push('Ctrl');
  if (chord.shift) parts.push('Shift');
  if (chord.alt) parts.push('Alt');
  if (chord.meta) parts.push('Win');
  parts.push(chord.key);
  return parts.join('+');
}

function utf8ByteLength(s: string): number {
  if (typeof TextEncoder !== 'undefined') {
    return new TextEncoder().encode(s).length;
  }
  // Fallback for environments without TextEncoder
  return unescape(encodeURIComponent(s)).length;
}

function utf8SliceByBytes(s: string, startByte: number, endByte: number): string {
  if (typeof TextEncoder === 'undefined' || typeof TextDecoder === 'undefined') {
    return s.slice(startByte, endByte);
  }
  const bytes = new TextEncoder().encode(s);
  return new TextDecoder().decode(bytes.slice(startByte, endByte));
}

/**
 * Parse a full .htk file body into records.
 * Long scripts: Key:Name:~ N:first51\nnext51\n...
 */
export function parseHtk(text: string): HtkParseResult {
  const lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  const records: HotkeyRecord[] = [];
  const issues: HtkParseIssue[] = [];
  let i = 0;

  while (i < lines.length) {
    const lineNum = i + 1;
    const line = lines[i];
    i += 1;

    if (!line.trim()) continue;

    const fields = splitHtkFields(line);
    if (!fields) {
      issues.push({
        line: lineNum,
        message: 'Expected Key:Name:Command (at least two colons)',
        raw: line,
      });
      continue;
    }

    const [keyRaw, nameRaw, rest] = fields;
    const key = parseKeyChord(keyRaw);
    const name = nameRaw.slice(0, HTK_NAME_MAX_CHARS);

    if (rest.startsWith('~')) {
      // ~ 57:ROUTE=... first chunk on same line
      const afterTilde = rest.slice(1).trimStart();
      const lengthMatch = /^(\d+)\s*:(.*)$/.exec(afterTilde);
      if (!lengthMatch) {
        issues.push({
          line: lineNum,
          message: 'Malformed long script header (expected ~ length:script)',
          raw: line,
        });
        continue;
      }
      const declaredLen = Number(lengthMatch[1]);
      let script = lengthMatch[2] ?? '';
      // Continuation lines: raw 51-byte chunks until we have enough bytes
      while (utf8ByteLength(script) < declaredLen && i < lines.length) {
        const cont = lines[i];
        // Stop if next line looks like a new hotkey record (has two colons and is not a chunk-only line)
        // Continuation chunks typically have no Key:Name: prefix — append raw.
        // Heuristic: if line matches Key:Name:Command and we already have some script, stop
        // only when declared length is satisfied OR next line is clearly a new record AND
        // we somehow overshot — prefer declared length.
        i += 1;
        script += cont;
      }
      if (utf8ByteLength(script) < declaredLen) {
        issues.push({
          line: lineNum,
          message: `Long script declared ${declaredLen} bytes but only ${utf8ByteLength(script)} found`,
        });
      }
      // Trim to declared length when overshot from an extra line
      if (utf8ByteLength(script) > declaredLen) {
        script = utf8SliceByBytes(script, 0, declaredLen);
      }
      records.push({
        id: nextId(),
        name: name || '(unnamed)',
        key,
        command: script,
      });
      continue;
    }

    records.push({
      id: nextId(),
      name: name || '(unnamed)',
      key,
      command: rest,
    });
  }

  return { records, issues };
}

/** Serialize records to DAS-compatible .htk text. */
export function serializeHtk(records: HotkeyRecord[]): string {
  const out: string[] = [];
  for (const rec of records) {
    const keyLabel = formatKeyChord(rec.key);
    const name = (rec.name || '').slice(0, HTK_NAME_MAX_CHARS);
    const cmd = rec.command ?? '';
    const bytes = utf8ByteLength(cmd);

    if (bytes <= HTK_SHORT_SCRIPT_MAX_BYTES) {
      out.push(`${keyLabel}:${name}:${cmd}`);
      continue;
    }

    // Long form: Key:Name:~ N:first51\nchunk\nchunk...
    const first = utf8SliceByBytes(cmd, 0, HTK_CHUNK_BYTES);
    out.push(`${keyLabel}:${name}:~ ${bytes}:${first}`);
    let offset = HTK_CHUNK_BYTES;
    while (offset < bytes) {
      out.push(utf8SliceByBytes(cmd, offset, offset + HTK_CHUNK_BYTES));
      offset += HTK_CHUNK_BYTES;
    }
  }
  return out.join('\n') + (out.length ? '\n' : '');
}

export function createEmptyRecord(partial?: Partial<HotkeyRecord>): HotkeyRecord {
  return {
    id: nextId(),
    name: partial?.name ?? 'New Hotkey',
    key: partial?.key ?? { label: '', key: '' },
    command: partial?.command ?? '',
    commandEdited: partial?.commandEdited,
  };
}
