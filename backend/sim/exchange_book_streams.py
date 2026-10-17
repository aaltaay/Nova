"""An exchange book file's bytes, inflated whatever compressed them -- plain, gzip or zstd (ADR 057).

``open_inflated`` answers the inflated stream and the exceptions a damaged stream of that kind raises while it is
read, so ``sim.exchange_book_files`` refuses a damaged file with the reason instead of a traceback (PR #1036
review). A zstd file is read frame by frame and refused when it ends inside one: zstandard's own stream reader
stops there without a word, which would import a cut-short file as a shorter book. Python's gzip raises
``EOFError`` itself.

``zstandard`` is imported only for a zstd file.
"""
from __future__ import annotations

import csv
import gzip
import io
import zlib

_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
_GZIP_MAGIC = b"\x1f\x8b"
READ_BYTES = 1 << 20
#: What a damaged or unreadable stream raises while it is read (a zstd file adds zstandard's own error).
READ_ERRORS: tuple[type[BaseException], ...] = (EOFError, OSError, zlib.error, UnicodeDecodeError, csv.Error)


class ExchangeBookError(ValueError):
    """A file the importer refuses, with the reason in the operator's words."""


def unreadable(exc: BaseException, where: str) -> ExchangeBookError:
    return ExchangeBookError(f"The file cannot be read {where} ({type(exc).__name__}: {exc}) -- it is cut short "
                             "or damaged")


class Prefixed(io.RawIOBase):
    """A stream that serves bytes already read before the rest of ``inner``."""

    def __init__(self, head: bytes, inner):
        self._head, self._inner = memoryview(head), inner

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        if len(self._head):
            n = min(len(buffer), len(self._head))
            buffer[:n] = self._head[:n]
            self._head = self._head[n:]
            return n
        data = self._inner.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)


class _ZstdFrames(io.RawIOBase):
    """A zstd file's frames one after another, inflated; ending inside a frame is refused."""

    def __init__(self, raw, zstandard):
        self._raw, self._zstd = raw, zstandard
        self._frame = zstandard.ZstdDecompressor().decompressobj()
        self._started = False           # the frame being read has taken bytes
        self._out, self._at = b"", 0    # inflated, and how much of it was read
        self._done = False

    def readable(self) -> bool:
        return True

    def _feed(self, chunk: bytes) -> bytes:
        parts = []
        while chunk:
            self._started = True
            parts.append(self._frame.decompress(chunk))
            if not self._frame.eof:
                break
            chunk = self._frame.unused_data
            self._frame, self._started = self._zstd.ZstdDecompressor().decompressobj(), False
        return b"".join(parts)

    def readinto(self, buffer) -> int:
        while self._at >= len(self._out) and not self._done:
            chunk = self._raw.read(READ_BYTES)
            if not chunk:
                if self._started:
                    raise ExchangeBookError("The zstd file ends inside a frame -- it is cut short")
                self._done = True
                break
            self._out, self._at = self._feed(chunk), 0
        n = min(len(buffer), len(self._out) - self._at)
        buffer[:n] = self._out[self._at:self._at + n]
        self._at += n
        return n


def open_inflated(raw) -> tuple[object, str | None, tuple[type[BaseException], ...]]:
    """``(stream, compression, read errors)`` for the open binary file ``raw``."""
    head = raw.read(4)
    raw.seek(0)
    if head == _ZSTD_MAGIC:
        try:
            import zstandard
        except ImportError:
            raise ExchangeBookError("This file is zstd-compressed: install the zstandard package "
                                    "(py -3 -m pip install zstandard) or decompress it first") from None
        return _ZstdFrames(raw, zstandard), "zstd", (*READ_ERRORS, zstandard.ZstdError)
    if head[:2] == _GZIP_MAGIC:
        return gzip.GzipFile(fileobj=raw), "gzip", READ_ERRORS
    return raw, None, READ_ERRORS


def read_exact(stream, n: int) -> bytes:
    """Up to ``n`` bytes: fewer only at the end of the stream (a decompressor may answer in pieces)."""
    parts, have = [], 0
    while have < n:
        part = stream.read(n - have)
        if not part:
            break
        parts.append(part)
        have += len(part)
    return b"".join(parts)
