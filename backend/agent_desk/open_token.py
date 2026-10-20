"""Install token for Open in Nova.

Owner: this module reads and writes ``open-in-nova-token.json`` under the cache dir.
Invalidation: an unknown ``schema_version`` refuses loud. Process start does not rotate the token.
schema_version: 1.

The file is private to the current user. POSIX uses mode ``0o600``. Windows ignores
that mode, so the DACL is replaced with one allow ACE for the current user.
"""
from __future__ import annotations

import ctypes
import hmac
import json
import logging
import os
import secrets
from ctypes import wintypes
from pathlib import Path

from paths import cache_dir

logger = logging.getLogger(__name__)

TOKEN_SCHEMA = 1
TOKEN_FILENAME = "open-in-nova-token.json"
OPEN_TOKEN_UNAVAILABLE = "OPEN_TOKEN_UNAVAILABLE"
OPEN_TOKEN_UNAVAILABLE_TEXT = (
    "Open in Nova could not lock its token file, so the token was not kept."
)

# Shapes for the Windows DACL. They live at module level: a class body that
# assigns a name to itself cannot see the enclosing function's locals and
# raises NameError on Windows. ctypes itself is cross-platform; kernel32 is
# loaded only on Windows.


class TokenError(RuntimeError):
    """The token file is there and this process will not guess past it."""


def token_path() -> Path:
    return cache_dir() / TOKEN_FILENAME


def load_or_create() -> dict:
    """The install token. Created once, private to this user, never rotated on startup.

    Any failure deletes the file when it is not private to this user, then raises
    ``TokenError``. A private file with a bad schema is kept and still refused.
    """
    path = token_path()
    try:
        return _load_or_create(path)
    except TokenError:
        _discard_if_unprotected(path)
        raise
    except Exception as exc:
        _discard_if_unprotected(path)
        logger.exception("open in nova: token file refused")
        raise TokenError(OPEN_TOKEN_UNAVAILABLE_TEXT) from exc


def _load_or_create(path: Path) -> dict:
    if path.is_file():
        _restrict_private(path)
        return _read(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"schema_version": TOKEN_SCHEMA, "token": secrets.token_hex(32)}
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        _restrict_private(path)
        return _read(path)
    try:
        os.write(fd, json.dumps(body).encode("utf-8"))
    finally:
        os.close(fd)
    _restrict_private(path)
    return body


def _discard_if_unprotected(path: Path) -> None:
    """Delete a token file this user does not exclusively own. A privacy check that throws counts as not private."""
    if not path.is_file():
        return
    try:
        private = token_file_private(path)
    except Exception:
        logger.exception("open in nova: could not read the token file's permissions")
        private = False
    if private:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.exception("open in nova: could not delete an unprotected token file")


def acl_is_current_user_only(user_sid: str, aces: list[tuple[str, str]]) -> bool:
    """True when every ACE is an allow for ``user_sid`` and there is at least one."""
    if not user_sid or not aces:
        return False
    return all(kind == "allow" and sid == user_sid for kind, sid in aces)


def token_file_private(path: Path) -> bool:
    """POSIX mode ``0o600``, or a protected Windows DACL with one allow ACE for this user."""
    if os.name != "nt":
        return (path.stat().st_mode & 0o777) == 0o600
    try:
        user_sid, aces, protected = _windows_acl(path)
    except (OSError, TokenError):
        return False
    return protected and len(aces) == 1 and acl_is_current_user_only(user_sid, aces)


def _restrict_private(path: Path) -> None:
    if os.name != "nt":
        os.chmod(path, 0o600)
        return
    _windows_lock_to_current_user(path)


def token_matches(provided: str | None) -> bool:
    """True when ``provided`` is the install token. ``TokenError`` propagates (the route answers 503)."""
    expected = str(load_or_create().get("token") or "")
    got = (provided or "").strip()
    if not expected or not got:
        return False
    return hmac.compare_digest(got, expected)


def _read(path: Path) -> dict:
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TokenError(f"open-in-nova token file cannot be read: {exc}") from exc
    if not isinstance(body, dict) or body.get("schema_version") != TOKEN_SCHEMA:
        version = body.get("schema_version") if isinstance(body, dict) else None
        raise TokenError(f"open-in-nova token schema {version!r} is not {TOKEN_SCHEMA}")
    token = body.get("token")
    if not isinstance(token, str) or not token:
        raise TokenError("open-in-nova token file has no token")
    return body


def _windows_lock_to_current_user(path: Path) -> None:
    """Replace the DACL with one allow ACE for the current user. chmod is a no-op here."""
    import ctypes
    from ctypes import wintypes

    kernel32, advapi32, types = _win_api()
    token = wintypes.HANDLE()
    if not kernel32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        _win_fail("OpenProcessToken")
    try:
        sid = _token_user_sid(advapi32, types, token)
        sid_len = advapi32.GetLengthSid(sid)
        acl_size = ctypes.sizeof(types.Acl) + ctypes.sizeof(types.AllowedAce) + sid_len - ctypes.sizeof(wintypes.DWORD)
        acl_buf = ctypes.create_string_buffer(acl_size)
        if not advapi32.InitializeAcl(acl_buf, acl_size, 2):
            _win_fail("InitializeAcl")
        mask = 0x120089 | 0x120116 | 0x00010000  # FILE_GENERIC_READ | FILE_GENERIC_WRITE | DELETE
        if not advapi32.AddAccessAllowedAce(acl_buf, 2, mask, sid):
            _win_fail("AddAccessAllowedAce")
        # SE_FILE_OBJECT = 1. DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION.
        status = advapi32.SetNamedSecurityInfoW(str(path), 1, 0x4 | 0x80000000, None, None, acl_buf, None)
        if status != 0:
            raise TokenError(
                f"open-in-nova token file cannot be locked to this user (SetNamedSecurityInfo {status})"
            )
    finally:
        kernel32.CloseHandle(token)


def _windows_acl(path: Path) -> tuple[str, list[tuple[str, str]], bool]:
    """``(current user SID, [(allow|deny|other, sid), ...], dacl_protected)``. A null DACL is not private."""
    import ctypes
    from ctypes import wintypes

    kernel32, advapi32, types = _win_api()
    token = wintypes.HANDLE()
    if not kernel32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        raise OSError("OpenProcessToken failed")
    try:
        user_sid = _sid_string(advapi32, kernel32, _token_user_sid(advapi32, types, token))
    finally:
        kernel32.CloseHandle(token)
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    status = advapi32.GetNamedSecurityInfoW(
        str(path), 1, 0x4, None, None, ctypes.byref(dacl), None, ctypes.byref(descriptor),
    )
    if status != 0:
        raise OSError(f"GetNamedSecurityInfo {status}")
    try:
        protected = _dacl_protected(advapi32, descriptor)
        if not dacl.value:
            return user_sid, [], protected
        info = types.AclSize()
        if not advapi32.GetAclInformation(dacl, ctypes.byref(info), ctypes.sizeof(info), 2):
            raise OSError("GetAclInformation failed")
        aces: list[tuple[str, str]] = []
        for index in range(info.AceCount):
            ace = ctypes.c_void_p()
            if not advapi32.GetAce(dacl, index, ctypes.byref(ace)):
                raise OSError("GetAce failed")
            kind = {0: "allow", 1: "deny"}.get(ctypes.cast(ace, ctypes.POINTER(ctypes.c_byte)).contents.value, "other")
            sid_addr = ace.value + types.AllowedAce.SidStart.offset
            aces.append((kind, _sid_string(advapi32, kernel32, sid_addr)))
        return user_sid, aces, protected
    finally:
        if descriptor.value:
            kernel32.LocalFree(descriptor)


class _TokenUser(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class _Acl(ctypes.Structure):
    _fields_ = [
        ("AclRevision", ctypes.c_byte), ("Sbz1", ctypes.c_byte), ("AclSize", wintypes.WORD),
        ("AceCount", wintypes.WORD), ("Sbz2", wintypes.WORD),
    ]


class _AllowedAce(ctypes.Structure):
    _fields_ = [
        ("AceType", ctypes.c_byte), ("AceFlags", ctypes.c_byte), ("AceSize", wintypes.WORD),
        ("Mask", wintypes.DWORD), ("SidStart", wintypes.DWORD),
    ]


class _AclSize(ctypes.Structure):
    _fields_ = [("AceCount", wintypes.DWORD), ("AclBytesInUse", wintypes.DWORD), ("AclBytesFree", wintypes.DWORD)]


class WinTypes:
    """Names the structures after they exist, so the class body does not assign a name to itself."""

    TokenUser = _TokenUser
    Acl = _Acl
    AllowedAce = _AllowedAce
    AclSize = _AclSize


def structure_types() -> type[WinTypes]:
    """The DACL shapes. Safe to call on Linux: this does not load kernel32."""
    return WinTypes


def _win_api():
    types = structure_types()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    kernel32.OpenProcessToken.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.GetLengthSid.argtypes = [ctypes.c_void_p]
    advapi32.GetLengthSid.restype = wintypes.DWORD
    advapi32.CopySid.argtypes = [wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    advapi32.CopySid.restype = wintypes.BOOL
    advapi32.InitializeAcl.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
    advapi32.InitializeAcl.restype = wintypes.BOOL
    advapi32.AddAccessAllowedAce.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    advapi32.AddAccessAllowedAce.restype = wintypes.BOOL
    advapi32.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p,
    ]
    advapi32.SetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi32.GetAclInformation.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_int]
    advapi32.GetAclInformation.restype = wintypes.BOOL
    advapi32.GetAce.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    advapi32.GetAce.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi32.GetSecurityDescriptorControl.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetSecurityDescriptorControl.restype = wintypes.BOOL
    return kernel32, advapi32, types


def _dacl_protected(advapi32, descriptor) -> bool:
    """True when the DACL is present and protected (no inherited ACEs)."""
    control = wintypes.WORD()
    revision = wintypes.DWORD()
    if not descriptor.value:
        return False
    if not advapi32.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)):
        return False
    present = 0x0004
    protected = 0x1000
    return bool(control.value & present) and bool(control.value & protected)


def _token_user_sid(advapi32, types, token):
    """A buffer that owns a copy of the current user's SID."""
    import ctypes
    from ctypes import wintypes

    class TokenUser(ctypes.Structure):
        _fields_ = [("User", types.TokenUser)]

    needed = wintypes.DWORD()
    advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))
    buf = ctypes.create_string_buffer(needed.value)
    if not advapi32.GetTokenInformation(token, 1, buf, needed, ctypes.byref(needed)):
        _win_fail("GetTokenInformation")
    user = ctypes.cast(buf, ctypes.POINTER(TokenUser)).contents
    size = advapi32.GetLengthSid(user.User.Sid)
    copy = ctypes.create_string_buffer(size)
    if not advapi32.CopySid(size, copy, user.User.Sid):
        _win_fail("CopySid")
    return copy


def _sid_string(advapi32, kernel32, sid) -> str:
    import ctypes

    raw = ctypes.c_void_p()
    if not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(raw)):
        raise OSError("ConvertSidToStringSid failed")
    try:
        return ctypes.wstring_at(raw) or ""
    finally:
        kernel32.LocalFree(raw)


def _win_fail(action: str) -> None:
    import ctypes

    raise TokenError(
        f"open-in-nova token file cannot be locked to this user ({action}, winerror {ctypes.get_last_error()})"
    )
