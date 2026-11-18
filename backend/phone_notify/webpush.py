"""Web Push's message format: RFC 8291 (the scrambling) and RFC 8292 (who is sending). Pure.

A phone's subscription is an address at its browser maker's push service and two keys: its public key
(``p256dh``, a P-256 point) and a 16-byte secret (``auth``). ``encrypt`` scrambles a message so only that
phone can read it: the push service carries it and cannot. ``vapid_authorization`` proves to the push
service that the sender is the one the phone subscribed to, with a short-lived token signed by the PC's key.

No I/O and no clock of its own: the salt, the one-time sender key and the time are passed in by the caller
(``sender``), and a test passes the standard's own example values.
"""
from __future__ import annotations

import base64
import json
import os
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_INFO = b"WebPush: info\x00"
_CEK_INFO = b"Content-Encoding: aes128gcm\x00"
_NONCE_INFO = b"Content-Encoding: nonce\x00"
# One record holds the whole message: its text, a one-byte end mark, and AES-GCM's 16-byte tag.
_OVERHEAD = 17


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _hmac(key: bytes, data: bytes) -> bytes:
    h = hmac.HMAC(key, hashes.SHA256())
    h.update(data)
    return h.finalize()


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    """HKDF-SHA256 for one block (every output here is 32 bytes or fewer)."""
    return _hmac(_hmac(salt, ikm), info + b"\x01")[:length]


def public_bytes(key: ec.EllipticCurvePublicKey) -> bytes:
    """A P-256 public key as the 65 bytes the standards carry (uncompressed point)."""
    return key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def private_key_from_b64(text: str) -> ec.EllipticCurvePrivateKey:
    """The PC's sending key from its ``.env`` form: the 32-byte private number, base64url."""
    raw = b64url_decode(text.strip())
    if len(raw) != 32:
        raise ValueError("the sending key is not a 32-byte P-256 private number")
    return ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())


def private_key_to_b64(key: ec.EllipticCurvePrivateKey) -> str:
    return b64url_encode(key.private_numbers().private_value.to_bytes(32, "big"))


def new_private_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def encrypt(
    plaintext: bytes,
    p256dh: bytes,
    auth: bytes,
    *,
    salt: bytes | None = None,
    sender_key: ec.EllipticCurvePrivateKey | None = None,
    record_size: int = 4096,
) -> bytes:
    """The request body for one push: the ``aes128gcm`` header and one encrypted record (RFC 8291 section 4).

    ``salt`` and ``sender_key`` are fresh for every message; they are parameters only so a test can pass the
    standard's example. A message too long for one record is refused, never cut."""
    if len(auth) != 16:
        raise ValueError("a subscription's auth secret is 16 bytes")
    if len(plaintext) + _OVERHEAD > record_size:
        raise ValueError(f"the message is {len(plaintext)} bytes; one push holds {record_size - _OVERHEAD}")
    salt = os.urandom(16) if salt is None else salt
    if len(salt) != 16:
        raise ValueError("the salt is 16 bytes")
    sender_key = new_private_key() if sender_key is None else sender_key
    phone_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), p256dh)
    sender_public = public_bytes(sender_key.public_key())

    shared = sender_key.exchange(ec.ECDH(), phone_key)
    ikm = _hkdf(auth, shared, _KEY_INFO + p256dh + sender_public, 32)
    cek = _hkdf(salt, ikm, _CEK_INFO, 16)
    nonce = _hkdf(salt, ikm, _NONCE_INFO, 12)
    # 0x02 marks the last (here the only) record.
    record = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    header = salt + record_size.to_bytes(4, "big") + bytes([len(sender_public)]) + sender_public
    return header + record


def audience(endpoint: str) -> str:
    """The push service an address belongs to, as a token names it: scheme and host, no path."""
    parts = urlsplit(endpoint)
    return f"{parts.scheme}://{parts.netloc}"


def vapid_authorization(endpoint: str, key: ec.EllipticCurvePrivateKey, *, subject: str, expires_at: int) -> str:
    """The ``Authorization`` header of one push (RFC 8292): a token for this push service, signed by the PC's key."""
    def part(obj: dict) -> str:
        return b64url_encode(json.dumps(obj, separators=(",", ":")).encode("utf-8"))

    signing_input = f"{part({'typ': 'JWT', 'alg': 'ES256'})}.{part({'aud': audience(endpoint), 'exp': int(expires_at), 'sub': subject})}"
    der = key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    signature = b64url_encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={signing_input}.{signature}, k={b64url_encode(public_bytes(key.public_key()))}"
